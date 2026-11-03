from __future__ import annotations
import http.client, json, tempfile, threading, unittest
from unittest.mock import patch
from unexpected_runtime.providers import AIStudioGatewayProvider, OpenAICompatibleProvider, ProviderError, provider_from_env, _NoRedirect
from unexpected_runtime.http_api import create_server
from unexpected_runtime.coordinator import Coordinator

class Response:
    def __init__(self,obj): self.data=json.dumps(obj).encode()
    def read(self,n=-1): return self.data if n<0 else self.data[:n]
    def __enter__(self): return self
    def __exit__(self,*a): return False
class Opener:
    def __init__(self,obj): self.response=Response(obj); self.request=None
    def open(self,req,timeout): self.request=req; return self.response

class ProviderTests(unittest.TestCase):
    def test_live_gateway_response_and_bearer_auth(self):
        opener=Opener({"ok":True,"results":{"openai":{"status":"LIVE · verified response","text":"real answer","model":"gpt-4.1"}}})
        p=AIStudioGatewayProvider("https://unexpected-ai-studio.onrender.com/orchestrate","g"*48,mode="openai")
        with patch("unexpected_runtime.providers.urllib.request.build_opener",return_value=opener):
            out=p.generate(system_prompt="S",user_prompt="U",agent_id="orchestrator",task_id="t",timeout=12)
        self.assertIn("real answer",out); self.assertEqual(opener.request.get_header("Authorization"),"Bearer "+"g"*48)
    def test_dual_mode_prefers_live_synthesis(self):
        p=AIStudioGatewayProvider("https://gateway.example/orchestrate","g"*48,mode="both")
        op=Opener({"ok":True,"results":{"synthesis":{"status":"LIVE · verified response","text":"combined"}}})
        with patch("unexpected_runtime.providers.urllib.request.build_opener",return_value=op):
            self.assertIn("combined",p.generate(system_prompt="S",user_prompt="U",agent_id="a",task_id="t",timeout=5))
    def test_missing_token_and_non_live_result_fail_closed(self):
        p=AIStudioGatewayProvider("https://gateway.example/orchestrate","")
        with self.assertRaises(ProviderError): p.generate(system_prompt="S",user_prompt="U",agent_id="a",task_id="t",timeout=5)
        p=AIStudioGatewayProvider("https://gateway.example/orchestrate","g"*48)
        op=Opener({"ok":True,"results":{"openai":{"status":"MOCK","text":"fake"}}})
        with patch("unexpected_runtime.providers.urllib.request.build_opener",return_value=op):
            with self.assertRaises(ProviderError): p.generate(system_prompt="S",user_prompt="U",agent_id="a",task_id="t",timeout=5)
    def test_live_status_must_be_unambiguous_and_not_fallback(self):
        p=AIStudioGatewayProvider("https://gateway.example/orchestrate","g"*48,mode="openai")
        for status in ("NOT LIVE","MOCK (live provider unavailable)","DELIVERED","LIVE · fallback"):
            op=Opener({"ok":True,"results":{"openai":{"status":status,"text":"must not be accepted"}}})
            with patch("unexpected_runtime.providers.urllib.request.build_opener",return_value=op):
                with self.subTest(status=status), self.assertRaises(ProviderError):
                    p.generate(system_prompt="S",user_prompt="U",agent_id="a",task_id="t",timeout=5)

    def test_rejects_insecure_url_bad_mode_and_large_task(self):
        for url in ("http://gateway.example","https://u:p@gateway.example/x"):
            with self.assertRaises(ProviderError): AIStudioGatewayProvider(url,"g"*48)
        with self.assertRaises(ProviderError): AIStudioGatewayProvider("https://gateway.example","g"*48,mode="other")
        p=AIStudioGatewayProvider("https://gateway.example","g"*48)
        with patch("unexpected_runtime.providers.urllib.request.build_opener") as build:
            with self.assertRaises(ProviderError): p.generate(system_prompt="x"*15001,user_prompt="u",agent_id="a",task_id="t",timeout=5)
            build.assert_not_called()
    def test_openai_compatible_provider_requires_https_and_rejects_embedded_credentials(self):
        for url in ("http://provider.example/v1", "https://user:secret@provider.example/v1",
                    "https://provider.example/v1?token=secret", "https://provider.example/v1#fragment"):
            with self.subTest(url=url), self.assertRaises(ProviderError):
                OpenAICompatibleProvider(url, "test-model", "k" * 48)

    def test_openai_compatible_provider_uses_https_and_disables_redirects(self):
        from urllib.request import Request
        request = Request("https://provider.example/v1/chat/completions", data=b"{}",
                          headers={"Authorization": "Bearer " + "k" * 48}, method="POST")
        handler = _NoRedirect()
        for code in (301, 302, 303, 307, 308):
            self.assertIsNone(handler.redirect_request(request, None, code, "redirect", {},
                                                       "https://other.example/collect"))
        opener = Opener({"choices": [{"message": {"content": "direct provider response"}}]})
        provider = OpenAICompatibleProvider("https://provider.example/v1", "test-model", "k" * 48)
        with patch("unexpected_runtime.providers.urllib.request.build_opener", return_value=opener) as build:
            result = provider.generate(system_prompt="S", user_prompt="U", agent_id="a", task_id="t", timeout=5)
        self.assertIn("direct provider response", result)
        self.assertTrue(any(isinstance(item, _NoRedirect) for item in build.call_args.args))
        self.assertEqual(opener.request.get_header("Authorization"), "Bearer " + "k" * 48)

    def test_factory_uses_gateway_config(self):
        env={"UNEXPECTED_PROVIDER":"ai_studio_gateway","UNEXPECTED_GATEWAY_URL":"https://gateway.example","UNEXPECTED_GATEWAY_TOKEN":"g"*48}
        with patch.dict("os.environ",env,clear=True):
            self.assertIsInstance(provider_from_env(),AIStudioGatewayProvider)

class APITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.coord=Coordinator(state_dir=self.tmp.name,provider=__import__("unexpected_runtime.providers",fromlist=["DeterministicMockProvider"]).DeterministicMockProvider(),max_workers=1,max_retries=0)
        self.server=create_server(coordinator=self.coord,api_token="a"*48,host="127.0.0.1",port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.host,self.port=self.server.server_address
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2); self.coord.close(); self.tmp.cleanup()
    def request(self,method,path,body=None,token="a"*48):
        conn=http.client.HTTPConnection(self.host,self.port,timeout=8); headers={}
        if token: headers["Authorization"]="Bearer "+token
        if body is not None: headers["Content-Type"]="application/json"
        conn.request(method,path,json.dumps(body) if body is not None else None,headers)
        res=conn.getresponse(); data=res.read(); conn.close()
        return res.status,json.loads(data) if data else {}
    def test_health_is_public_without_secret_values(self):
        code,data=self.request("GET","/health",token="")
        self.assertEqual(code,200); self.assertNotIn("api_token",data); self.assertNotIn("state_db",data)
    def test_auth_and_status(self):
        self.assertEqual(self.request("GET","/v1/status",token="")[0],401)
        self.assertEqual(self.request("GET","/v1/status")[0],200)

    def test_non_ascii_bearer_header_is_rejected_without_server_error(self):
        conn=http.client.HTTPConnection(self.host,self.port,timeout=8)
        conn.putrequest("GET","/v1/status")
        conn.putheader("Authorization","Bearer "+"é"*48)
        conn.endheaders()
        response=conn.getresponse(); response.read(); conn.close()
        self.assertEqual(response.status,401)

    def test_non_ascii_configured_api_token_fails_closed(self):
        s=create_server(coordinator=self.coord,api_token="é"*48,host="127.0.0.1",port=0)
        t=threading.Thread(target=s.serve_forever,daemon=True); t.start()
        try:
            c=http.client.HTTPConnection(self.host,s.server_address[1],timeout=8)
            c.request("GET","/v1/status",headers={"Authorization":"Bearer "+"a"*48})
            response=c.getresponse(); response.read(); c.close()
            self.assertEqual(response.status,503)
        finally:
            s.shutdown(); s.server_close(); t.join(timeout=2)
    def test_unprivileged_invocation_succeeds(self):
        code,data=self.request("POST","/v1/invoke",{"agent_id":"orchestrator","objective":"Run a safe smoke test"})
        self.assertEqual(code,200); self.assertEqual(data["result"]["status"],"completed")
    def test_privileged_fields_and_bad_routes_are_rejected(self):
        for payload in ({"agent_id":"orchestrator","objective":"x","required_permissions":["publish"]},{"agent_id":"orchestrator","objective":"x","approval":{"approver":"owner"}}):
            self.assertEqual(self.request("POST","/v1/invoke",payload)[0],400)
        self.assertEqual(self.request("GET","/missing")[0],404)
    def test_locked_without_a_strong_api_token(self):
        s=create_server(coordinator=self.coord,api_token="short",host="127.0.0.1",port=0)
        t=threading.Thread(target=s.serve_forever,daemon=True); t.start()
        try:
            c=http.client.HTTPConnection("127.0.0.1",s.server_address[1]); c.request("GET","/v1/status")
            r=c.getresponse(); self.assertEqual(r.status,503); c.close()
        finally: s.shutdown(); s.server_close(); t.join(timeout=2)
    def test_http_rejects_objective_source_reference_deadline_and_step_limits(self):
        self.assertEqual(self.request("POST","/v1/invoke",{"agent_id":"orchestrator","objective":"x"*16001})[0],413)
        self.assertEqual(self.request("POST","/v1/invoke",{"agent_id":"orchestrator","objective":"x","source_refs":["r"]*33})[0],400)
        self.assertEqual(self.request("POST","/v1/invoke",{"agent_id":"orchestrator","objective":"x","source_refs":["r"*2049]})[0],400)
        self.assertEqual(self.request("POST","/v1/invoke",{"agent_id":"orchestrator","objective":"x","deadline_seconds":601})[0],400)
        self.assertEqual(self.request("POST","/v1/invoke",{"agent_id":"orchestrator","objective":"x","deadline_seconds":float("nan")})[0],400)
        self.assertEqual(self.request("POST","/v1/invoke",{"agent_id":"orchestrator","objective":"x","max_steps":13})[0],400)

    def test_http_missing_and_malformed_content_length_are_rejected(self):
        def raw_request(content_length=None):
            conn=http.client.HTTPConnection(self.host,self.port,timeout=8)
            conn.putrequest("POST","/v1/invoke")
            conn.putheader("Authorization","Bearer "+"a"*48)
            conn.putheader("Content-Type","application/json")
            if content_length is not None:
                conn.putheader("Content-Length",content_length)
            conn.endheaders()
            response=conn.getresponse()
            response.read()
            status=response.status
            conn.close()
            return status
        self.assertEqual(raw_request(),411)
        self.assertEqual(raw_request("not-a-number"),400)

    def test_http_body_limit_is_enforced(self):
        conn=http.client.HTTPConnection(self.host,self.port,timeout=8)
        conn.request("POST","/v1/invoke",b" "*(64*1024+1),{"Authorization":"Bearer "+"a"*48,"Content-Type":"application/json"})
        response=conn.getresponse(); response.read(); conn.close()
        self.assertEqual(response.status,413)

    def test_http_rate_limit_is_enforced(self):
        with patch("unexpected_runtime.http_api.RATE_LIMIT_PER_MINUTE",1):
            first=self.request("POST","/v1/invoke",{"agent_id":"orchestrator","objective":"rate limit test"})
            second=self.request("POST","/v1/invoke",{"agent_id":"orchestrator","objective":"rate limit test"})
        self.assertEqual(first[0],200)
        self.assertEqual(second[0],429)

    def test_http_invocation_reaches_gateway_provider(self):
        op=Opener({"ok":True,"results":{"openai":{"status":"LIVE · verified response","text":"end-to-end live-shaped result","model":"gpt-4.1"}}})
        p=AIStudioGatewayProvider("https://gateway.example/orchestrate","g"*48,mode="openai")
        with tempfile.TemporaryDirectory() as state:
            c=Coordinator(state_dir=state,provider=p,max_workers=1,max_retries=0)
            s=create_server(coordinator=c,api_token="a"*48,host="127.0.0.1",port=0)
            t=threading.Thread(target=s.serve_forever,daemon=True); t.start()
            try:
                with patch("unexpected_runtime.providers.urllib.request.build_opener",return_value=op):
                    conn=http.client.HTTPConnection("127.0.0.1",s.server_address[1],timeout=5)
                    conn.request("POST","/v1/invoke",json.dumps({"agent_id":"orchestrator","objective":"test"}),{"Authorization":"Bearer "+"a"*48,"Content-Type":"application/json"})
                    r=conn.getresponse(); result=json.loads(r.read()); conn.close()
                self.assertEqual(r.status,200,result); self.assertEqual(result["result"]["status"],"completed",result); self.assertIn("end-to-end live-shaped result",result["result"]["output"])
            finally: s.shutdown(); s.server_close(); t.join(timeout=2); c.close()

if __name__=="__main__": unittest.main(verbosity=2)
