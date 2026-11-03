from __future__ import annotations

import json
import io
import urllib.error
import unittest
import tempfile
import http.client
import threading
from unittest.mock import patch

from unexpected_runtime.coordinator import Coordinator
from unexpected_runtime.http_api import create_server
from unexpected_runtime.providers import (
    AnthropicProvider,
    DeterministicMockProvider,
    OpenAICompatibleProvider,
    OpenOxResponsesProvider,
    ProviderError,
    ProviderRouter,
    provider_router_from_env,
)


class FakeResponse:
    def __init__(self, payload):
        self.raw = json.dumps(payload).encode("utf-8")
    def read(self, size=-1):
        return self.raw if size < 0 else self.raw[:size]
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class FakeOpener:
    def __init__(self, payload):
        self.response = FakeResponse(payload)
        self.request = None
        self.timeout = None
    def open(self, request, timeout):
        self.request = request
        self.timeout = timeout
        return self.response


class AnthropicProviderTests(unittest.TestCase):
    def test_anthropic_uses_messages_api_headers_and_bounded_payload(self):
        opener = FakeOpener({"content": [{"type": "text", "text": "Claude answer"}], "model": "claude-test"})
        provider = AnthropicProvider("anthropic-test-key", "claude-test-model")
        with patch("unexpected_runtime.providers.urllib.request.build_opener", return_value=opener):
            result = provider.generate(system_prompt="System", user_prompt="Task", agent_id="research-scout", task_id="task-1", timeout=9)
        self.assertEqual(result, "Claude answer")
        self.assertEqual(opener.request.full_url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(opener.request.get_header("X-api-key"), "anthropic-test-key")
        self.assertEqual(opener.request.get_header("Anthropic-version"), "2023-06-01")
        body = json.loads(opener.request.data)
        self.assertEqual(body["model"], "claude-test-model")
        self.assertEqual(body["max_tokens"], 1024)
        self.assertEqual(body["system"], "System")
        self.assertEqual(body["messages"][0]["content"], "Task")

    def test_anthropic_missing_key_malformed_response_and_http_failure_fail_closed(self):
        with self.assertRaises(ProviderError):
            AnthropicProvider("", "claude-test-model")
        provider = AnthropicProvider("anthropic-test-key", "claude-test-model")
        malformed = FakeOpener({"content": [{"type": "image", "source": {}}]})
        with patch("unexpected_runtime.providers.urllib.request.build_opener", return_value=malformed):
            with self.assertRaises(ProviderError):
                provider.generate(system_prompt="S", user_prompt="U", agent_id="a", task_id="t", timeout=5)

    def test_anthropic_disables_redirects_and_rejects_oversized_response(self):
        from unexpected_runtime.providers import _NoRedirect
        from urllib.request import Request
        handler = _NoRedirect()
        request = Request("https://api.anthropic.com/v1/messages", method="POST")
        self.assertIsNone(handler.redirect_request(request, None, 302, "redirect", {}, "https://attacker.example"))
        provider = AnthropicProvider("anthropic-test-key", "claude-test-model")
        opener = FakeOpener({"content": [{"type": "text", "text": "x" * 2000000}]})
        with patch("unexpected_runtime.providers.urllib.request.build_opener", return_value=opener):
            with self.assertRaises(ProviderError):
                provider.generate(system_prompt="S", user_prompt="U", agent_id="a", task_id="t", timeout=5)


class OpenOxResponsesProviderTests(unittest.TestCase):
    def test_openox_uses_responses_endpoint_auth_and_response_output_blocks(self):
        opener = FakeOpener({"id": "resp-test", "model": "gpt-6-astra", "output": [{
            "type": "message", "role": "assistant",
            "content": [{"type": "output_text", "text": "OpenOx answer"}],
        }]})
        provider = OpenOxResponsesProvider("https://api.openoxai.com/v1", "gpt-6-astra", "openox-test-key")
        with patch("unexpected_runtime.providers.urllib.request.build_opener", return_value=opener):
            result = provider.generate(system_prompt="Follow the system instructions.",
                user_prompt="Answer a test question.", agent_id="research-scout",
                task_id="task-openox-1", timeout=12)
        self.assertEqual(result, "OpenOx answer")
        self.assertEqual(opener.request.full_url, "https://api.openoxai.com/v1/responses")
        self.assertEqual(opener.request.get_header("Authorization"), "Bearer openox-test-key")
        body = json.loads(opener.request.data)
        self.assertEqual(body["model"], "gpt-6-astra")
        self.assertEqual(body["instructions"], "Follow the system instructions.")
        self.assertEqual(body["input"], "Answer a test question.")
        self.assertEqual(body["metadata"]["agent_id"], "research-scout")
        self.assertEqual(opener.timeout, 12)

    def test_openox_http_error_includes_safe_upstream_diagnostic(self):
        api_key = "openox-private-test-key"
        error_body = json.dumps({
            "error": {
                "type": "insufficient_balance",
                "code": "insufficient_balance",
                "message": "Balance too low for this request. Authorization: Bearer " + api_key,
            }
        }).encode("utf-8")
        upstream_error = urllib.error.HTTPError(
            "https://api.openoxai.com/v1/responses",
            402,
            "Payment Required",
            {},
            io.BytesIO(error_body),
        )

        class ErrorOpener:
            def open(self, request, timeout):
                raise upstream_error

        provider = OpenOxResponsesProvider(
            "https://api.openoxai.com/v1", "gpt-6-astra", api_key
        )
        with patch("unexpected_runtime.providers.urllib.request.build_opener", return_value=ErrorOpener()):
            with self.assertRaises(ProviderError) as caught:
                provider.generate(
                    system_prompt="S", user_prompt="U", agent_id="a", task_id="t", timeout=5
                )
        message = str(caught.exception)
        self.assertIn("HTTP 402", message)
        self.assertIn("insufficient_balance", message)
        self.assertIn("Balance too low", message)
        self.assertNotIn(api_key, message)
        self.assertNotIn("Bearer " + api_key, message)

    def test_openox_accepts_top_level_output_text(self):
        opener = FakeOpener({"output_text": "  Direct response  "})
        provider = OpenOxResponsesProvider("https://api.openoxai.com/v1", "gpt-6-astra", "openox-test-key")
        with patch("unexpected_runtime.providers.urllib.request.build_opener", return_value=opener):
            result = provider.generate(system_prompt="S", user_prompt="U", agent_id="a", task_id="t", timeout=5)
        self.assertEqual(result, "Direct response")

    def test_openox_rejects_missing_credentials_unsafe_urls_bad_output_and_large_responses(self):
        with self.assertRaises(ProviderError):
            OpenOxResponsesProvider("https://api.openoxai.com/v1", "gpt-6-astra", "")
        with self.assertRaises(ProviderError):
            OpenOxResponsesProvider("http://api.openoxai.com/v1", "gpt-6-astra", "key")
        with self.assertRaises(ProviderError):
            OpenOxResponsesProvider("https://user:password@api.openoxai.com/v1", "gpt-6-astra", "key")
        provider = OpenOxResponsesProvider("https://api.openoxai.com/v1", "gpt-6-astra", "openox-test-key")
        malformed = FakeOpener({"output": [{"type": "reasoning", "summary": []}]})
        with patch("unexpected_runtime.providers.urllib.request.build_opener", return_value=malformed):
            with self.assertRaises(ProviderError):
                provider.generate(system_prompt="S", user_prompt="U", agent_id="a", task_id="t", timeout=5)
        oversized = FakeOpener({"output_text": "x" * 2_000_000})
        with patch("unexpected_runtime.providers.urllib.request.build_opener", return_value=oversized):
            with self.assertRaises(ProviderError):
                provider.generate(system_prompt="S", user_prompt="U", agent_id="a", task_id="t", timeout=5)


class ProviderRouterTests(unittest.TestCase):
    def test_routes_resolve_only_registered_providers(self):
        mock = DeterministicMockProvider()
        openai = OpenAICompatibleProvider("https://api.openai.com/v1", "gpt-test", "o" * 48)
        router = ProviderRouter({"mock": mock, "openai": openai}, default_route="mock")
        self.assertIs(router.resolve("mock"), mock)
        self.assertIs(router.resolve("openai"), openai)
        with self.assertRaises(ProviderError):
            router.resolve("anthropic")

    def test_provider_status_never_exposes_credentials(self):
        mock = DeterministicMockProvider()
        router = ProviderRouter({"mock": mock}, default_route="mock")
        status = router.status()
        self.assertEqual(status[0]["id"], "mock")
        self.assertTrue(status[0]["configured"])
        self.assertFalse(status[0]["verified"])
        self.assertNotIn("api_key", json.dumps(status).lower())
        self.assertNotIn("secret", json.dumps(status).lower())

    def test_concurrent_route_resolution_does_not_mutate_default_provider(self):
        class TaggedProvider:
            def __init__(self, name):
                self.name = name
                self.configured = True
                self.retry_safe = False
            def generate(self, **kwargs):
                return self.name
        router = ProviderRouter(
            {"openai": TaggedProvider("openai"), "anthropic": TaggedProvider("anthropic")},
            default_route="openai",
        )
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(router.resolve, route) for route in ("openai", "anthropic")]
        self.assertEqual([future.result().name for future in futures], ["openai", "anthropic"])
        self.assertEqual(router.resolve(None).name, "openai")

    def test_factory_keeps_mock_default_and_registers_only_configured_providers(self):
        env = {
            "UNEXPECTED_PROVIDER": "mock",
            "OPENAI_API_KEY": "o" * 48,
            "OPENAI_MODEL": "gpt-test",
            "ANTHROPIC_API_KEY": "a" * 48,
            "ANTHROPIC_MODEL": "claude-test",
            "OPENROUTER_API_KEY": "",
        }
        with patch.dict("os.environ", env, clear=True):
            router = provider_router_from_env()
        self.assertEqual(router.default_route, "mock")
        self.assertEqual(set(router.providers), {"mock", "openai", "anthropic"})
        self.assertNotIn("openrouter", router.providers)

    def test_openox_is_registered_only_when_configured_and_uses_responses_endpoint(self):
        env = {
            "UNEXPECTED_PROVIDER": "mock",
            "OPENOX_API_KEY": "x" * 48,
            "OPENOX_MODEL": "gpt-6-astra",
            "OPENOX_BASE_URL": "https://api.openoxai.com/v1",
        }
        with patch.dict("os.environ", env, clear=True):
            router = provider_router_from_env()
        self.assertIn("openox", router.providers)
        provider = router.resolve("openox")
        self.assertEqual(provider.name, "openox")
        self.assertEqual(provider.model, "gpt-6-astra")
        self.assertEqual(provider.base_url, "https://api.openoxai.com/v1/responses")
        self.assertEqual(router.default_route, "mock")

    def test_openox_is_not_registered_without_a_key(self):
        env = {
            "UNEXPECTED_PROVIDER": "mock",
            "OPENOX_API_KEY": "",
            "OPENOX_MODEL": "gpt-6-astra",
        }
        with patch.dict("os.environ", env, clear=True):
            router = provider_router_from_env()
        self.assertNotIn("openox", router.providers)

    def test_openox_is_registered_only_when_configured_and_uses_responses_endpoint(self):
        env = {
            "UNEXPECTED_PROVIDER": "mock",
            "UNEXPECTED_DEFAULT_PROVIDER": "openox",
            "OPENOX_API_KEY": "x" * 48,
            "OPENOX_MODEL": "gpt-6-astra",
            "OPENOX_BASE_URL": "https://api.openoxai.com/v1",
        }
        with patch.dict("os.environ", env, clear=True):
            router = provider_router_from_env()
        provider = router.resolve("openox")
        self.assertIsInstance(provider, OpenOxResponsesProvider)
        self.assertEqual(provider.name, "openox")
        self.assertEqual(provider.model, "gpt-6-astra")
        self.assertEqual(provider.base_url, "https://api.openoxai.com/v1/responses")
        self.assertEqual(router.default_route, "openox")

    def test_openox_is_not_registered_without_a_key_and_default_fails_back_to_mock(self):
        env = {
            "UNEXPECTED_PROVIDER": "mock",
            "UNEXPECTED_DEFAULT_PROVIDER": "openox",
            "OPENOX_API_KEY": "",
            "OPENOX_MODEL": "gpt-6-astra",
        }
        with patch.dict("os.environ", env, clear=True):
            router = provider_router_from_env()
        self.assertNotIn("openox", router.providers)
        self.assertEqual(router.default_route, "mock")

    def test_openrouter_is_registered_only_when_configured_and_uses_openai_compatible_adapter(self):
        env = {
            "UNEXPECTED_PROVIDER": "mock",
            "OPENROUTER_API_KEY": "r" * 48,
            "OPENROUTER_MODEL": "openrouter/free",
        }
        with patch.dict("os.environ", env, clear=True):
            router = provider_router_from_env()
        provider = router.resolve("openrouter")
        self.assertIsInstance(provider, OpenAICompatibleProvider)
        self.assertIn("openrouter.ai", provider.base_url)
        self.assertEqual(provider.model, "openrouter/free")


class CoordinatorProviderRoutingTests(unittest.TestCase):
    class TaggedProvider:
        def __init__(self, name):
            self.name = name
            self.model = name + "-test-model"
            self.configured = True
            self.verified = False
            self.retry_safe = False
            self.calls = 0
            self.last_user_payload = None
        def generate(self, **kwargs):
            self.calls += 1
            try:
                self.last_user_payload = json.loads(kwargs["user_prompt"])
            except (TypeError, json.JSONDecodeError):
                self.last_user_payload = None
            return self.name + " route response"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.openai = self.TaggedProvider("openai")
        self.anthropic = self.TaggedProvider("anthropic")
        self.router = ProviderRouter(
            {"mock": DeterministicMockProvider(), "openai": self.openai, "anthropic": self.anthropic},
            default_route="openai",
        )
        self.coordinator = Coordinator(state_dir=self.tmp.name, provider=self.router, max_workers=2, max_retries=0)

    def tearDown(self):
        self.coordinator.close()
        self.tmp.cleanup()

    def test_invocation_uses_selected_route_without_mutating_default(self):
        result = self.coordinator.invoke("orchestrator", "route this task", provider_route="anthropic")
        self.assertEqual(result.status, "completed")
        self.assertIn("anthropic route response", result.output)
        self.assertEqual(self.openai.calls, 0)
        self.assertEqual(self.anthropic.calls, 1)
        self.assertEqual(self.router.resolve(None).name, "openai")
        task = self.coordinator.store.list_tasks(1)[0]
        self.assertEqual(task["provider_route"], "anthropic")

    def test_runtime_capabilities_are_not_also_reported_as_unavailable(self):
        openrouter = self.TaggedProvider("openrouter")
        self.router.providers["openrouter"] = openrouter

        result = self.coordinator.invoke(
            "orchestrator", "minimal provider capability check", provider_route="openrouter"
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(openrouter.calls, 1)
        payload = openrouter.last_user_payload
        self.assertIn("provider.chat", payload["runtime_capabilities"])
        self.assertFalse(
            set(payload["runtime_capabilities"]) & set(payload["unavailable_external_capabilities"]),
            "A capability cannot be simultaneously advertised as available and unavailable.",
        )

    def test_full_lifecycle_uses_one_explicit_provider_route_for_every_stage(self):
        class WorkflowProvider(self.TaggedProvider):
            def generate(self, **kwargs):
                self.calls += 1
                agent = kwargs["agent_id"]
                if agent == "project-manager":
                    return "Plan: research, produce, verify and deliver."
                if agent == "code-reviewer":
                    return "VERDICT: PASS\nReview passed with evidence."
                return "Research deliverable with sourced findings."
        openai = WorkflowProvider("openai")
        anthropic = WorkflowProvider("anthropic")
        router = ProviderRouter({"mock": DeterministicMockProvider(), "openai": openai, "anthropic": anthropic}, default_route="openai")
        router.mark_success("anthropic")  # Model routing test assumes a prior successful live connection check.
        coordinator = Coordinator(state_dir=self.tmp.name, provider=router, max_workers=4, max_retries=0)
        try:
            result = coordinator.run_lifecycle(
                "research-scout", "Prepare a safe research note", {"scope": "public"},
                max_corrections=0, max_improvements=1, provider_route="anthropic",
            )
            self.assertEqual(result.status, "delivered")
            self.assertGreater(anthropic.calls, 0)
            self.assertEqual(openai.calls, 0)
            events = coordinator.store.events(200)
            used = [event for event in events if event["event_type"] == "provider_used"]
            self.assertTrue(used)
            self.assertTrue(all(json.loads(event["payload_json"])["route"] == "anthropic" for event in used))
            self.assertEqual(router.resolve(None).name, "openai")
        finally:
            coordinator.close()

    def test_unknown_route_rejects_before_task_is_persisted(self):
        with self.assertRaises(ProviderError):
            self.coordinator.invoke("orchestrator", "invalid route", provider_route="not-installed")
        self.assertEqual(self.coordinator.store.list_tasks(10), [])

    def test_provider_test_endpoint_returns_sanitized_diagnostic(self):
        private_key = "openox-private-test-key"

        class RejectedProvider:
            name = "openox"
            model = "gpt-6-astra"
            configured = True
            verified = False
            _api_key = private_key
            retry_safe = False
            def generate(self, **kwargs):
                raise ProviderError(
                    "OpenOx rejected the request (HTTP 402; insufficient_balance): "
                    "Balance too low. Bearer " + private_key
                )

        self.router.providers["openox"] = RejectedProvider()
        token = "provider-router-diagnostic-token-" + "z" * 32
        server = create_server(coordinator=self.coordinator, api_token=token, host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=8)
            body = json.dumps({"provider_route": "openox"})
            conn.request("POST", "/v1/providers/test", body, {
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
            })
            response = conn.getresponse()
            payload = json.loads(response.read())
            self.assertEqual(response.status, 502)
            self.assertIn("HTTP 402", payload["error"])
            self.assertIn("insufficient_balance", payload["error"])
            self.assertNotIn(private_key, json.dumps(payload))
            self.assertNotIn("Bearer " + private_key, json.dumps(payload))
            conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_authenticated_provider_status_and_live_test_endpoint(self):
        token = "provider-router-test-token-" + "z" * 32
        server = create_server(coordinator=self.coordinator, api_token=token, host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=8)
            conn.request("GET", "/v1/providers")
            response = conn.getresponse()
            self.assertEqual(response.status, 401)
            response.read()
            conn.close()

            conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=8)
            conn.request("GET", "/v1/providers", headers={"Authorization": "Bearer " + token})
            response = conn.getresponse()
            payload = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual({item["id"] for item in payload["providers"]}, {"mock", "openai", "anthropic"})
            conn.close()

            conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=8)
            body = json.dumps({"provider_route": "anthropic"})
            conn.request("POST", "/v1/providers/test", body, {
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
            })
            response = conn.getresponse()
            tested = json.loads(response.read())
            self.assertEqual(response.status, 200, tested)
            self.assertTrue(tested["verified"])
            self.assertTrue(self.anthropic.verified)
            conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
