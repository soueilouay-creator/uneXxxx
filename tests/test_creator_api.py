from __future__ import annotations
import http.client,json,tempfile,threading,unittest
from unittest.mock import patch
from unexpected_runtime.coordinator import Coordinator
from unexpected_runtime.http_api import create_server
from unexpected_runtime.providers import DeterministicMockProvider

class CreatorStudioAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.coordinator=Coordinator(state_dir=self.tmp.name,provider=DeterministicMockProvider(),max_workers=2,max_retries=0)
        self.token="creator-api-test-token-"+"z"*32
        self.server=create_server(coordinator=self.coordinator,api_token=self.token,host="127.0.0.1",port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.host,self.port=self.server.server_address
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2);self.coordinator.close();self.tmp.cleanup()
    def request(self,method,path,body=None,auth=True):
        conn=http.client.HTTPConnection(self.host,self.port,timeout=8);headers={}
        if auth: headers["Authorization"]="Bearer "+self.token
        if body is not None: headers["Content-Type"]="application/json"
        conn.request(method,path,json.dumps(body) if body is not None else None,headers)
        response=conn.getresponse();raw=response.read();ctype=response.getheader("Content-Type","");conn.close()
        return response.status,json.loads(raw) if raw and "application/json" in ctype else raw.decode("utf-8",errors="replace")
    @staticmethod
    def payload():
        return {"title":"A Film from Code","topic":"How a visual renderer turns a script into motion","language":"English",
            "channel_profile":{"youtube":{"format":"shorts","aspect_ratio":"9:16"},"tiktok":{"format":"vertical","aspect_ratio":"9:16"}}}
    def test_project_and_version_endpoints_require_auth_and_persist(self):
        self.assertEqual(self.request("GET","/v1/creator/projects",auth=False)[0],401)
        self.assertEqual(self.request("POST","/v1/creator/projects",self.payload(),auth=False)[0],401)
        status,body=self.request("POST","/v1/creator/projects",self.payload())
        self.assertEqual(status,201);project=body["project"];pid=project["project_id"]
        status,version=self.request("POST",f"/v1/creator/projects/{pid}/versions",{"kind":"treatment","content":{"script":"A film made from code."}})
        self.assertEqual(status,201);vid=version["version"]["version_id"]
        status,detail=self.request("GET",f"/v1/creator/projects/{pid}")
        self.assertEqual(status,200);self.assertEqual(detail["project"]["project_id"],pid)
        self.assertEqual(detail["versions"][0]["version_id"],vid)
    def test_render_request_is_persisted_blocked_and_exposes_progress(self):
        _,created=self.request("POST","/v1/creator/projects",self.payload());pid=created["project"]["project_id"]
        _,version=self.request("POST",f"/v1/creator/projects/{pid}/versions",{"kind":"storyboard","content":{"scenes":[{"title":"Opening","visual":"Shapes move"}]}})
        vid=version["version"]["version_id"]
        status,body=self.request("POST",f"/v1/creator/projects/{pid}/render-jobs",{
            "version_id":vid,"style_id":"minimal","idempotency_key":"render-api-test-0001",
            "resource_limits":{"cpu_seconds":60,"memory_mb":512,"wall_time_seconds":90},
            "request":{"profile":"youtube_shorts"}})
        self.assertEqual(status,503);self.assertTrue(body["blocked"]);self.assertEqual(body["job"]["status"],"blocked")
        job_id=body["job"]["job_id"]
        status,detail=self.request("GET",f"/v1/creator/render-jobs/{job_id}")
        self.assertEqual(status,200);self.assertEqual(detail["job"]["job_id"],job_id)
        self.assertEqual(detail["progress"]["code"],"renderer_unavailable")
    def test_creator_status_is_authenticated_and_reports_fail_closed_capabilities(self):
        self.assertEqual(self.request("GET","/v1/creator/status",auth=False)[0],401)
        status,body=self.request("GET","/v1/creator/status")
        self.assertEqual(status,200)
        self.assertEqual(body["engine_commit"],"5c05490cc55dfb54f8f4c333f0f0e79cb6500564")
        self.assertFalse(body["renderer_configured"])
        self.assertFalse(body["artifact_storage_configured"])
        self.assertFalse(body["publishing_enabled"])


    def test_android_lite_video_endpoints_are_authenticated_and_serve_verified_mp4(self):
        manifest={
            "status":"completed","video_id":"a"*32,"title":"Local story",
            "file_name":"master.mp4","byte_size":8,"sha256":"b"*64,
            "width":720,"height":1280,"duration_seconds":30.0,
            "qa":"passed","external_services_used":False,
        }
        class FakeAndroidLite:
            def render(self,title,script,*,video_format,narration):
                self.request=(title,script,video_format,narration)
                return manifest
            def get_video(self,video_id):
                self.asserted_id=video_id
                return manifest
            def read_video(self,video_id):
                self.asserted_file_id=video_id
                return b"fake-mp4"
        fake=FakeAndroidLite()
        with patch("unexpected_runtime.android_lite_video.AndroidLiteVideoCreator.from_environment",
                   return_value=fake):
            payload={"title":"Local story","script":"A short local video script with enough words for a test.",
                     "format":"vertical","narration":"off"}
            self.assertEqual(self.request("POST","/v1/creator/android-videos",payload,auth=False)[0],401)
            self.assertEqual(self.request("GET","/v1/creator/android-videos/"+"a"*32,auth=False)[0],401)
            status,created=self.request("POST","/v1/creator/android-videos",payload)
            self.assertEqual(status,201)
            self.assertEqual(created["video"]["qa"],"passed")
            self.assertEqual(fake.request[2:],("vertical","off"))
            status,detail=self.request("GET","/v1/creator/android-videos/"+"a"*32)
            self.assertEqual(status,200)
            self.assertEqual(detail["video"]["video_id"],"a"*32)
            status,mp4=self.request("GET","/v1/creator/android-videos/"+"a"*32+"/file")
            self.assertEqual(status,200)
            self.assertEqual(mp4,"fake-mp4")
            self.assertEqual(self.request("POST","/v1/creator/android-videos",{**payload,"publish":True})[0],400)

    def test_unknown_fields_and_non_platform_channels_are_rejected(self):
        payload=self.payload();payload["channel_profile"]["instagram"]={"format":"reels"}
        self.assertEqual(self.request("POST","/v1/creator/projects",payload)[0],400)
        payload=self.payload();payload["extra"]="not accepted"
        self.assertEqual(self.request("POST","/v1/creator/projects",payload)[0],400)
if __name__=="__main__":unittest.main()
