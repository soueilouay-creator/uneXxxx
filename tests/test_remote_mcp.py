from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest

from unexpected_runtime.coordinator import Coordinator
from unexpected_runtime.http_api import create_server
from unexpected_runtime.providers import DeterministicMockProvider


class RemoteMCPHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.coordinator = Coordinator(
            state_dir=self.tmp.name,
            provider=DeterministicMockProvider(),
            max_workers=2,
            max_retries=0,
        )
        self.token = "remote-mcp-test-token-" + "x" * 32
        self.server = create_server(
            coordinator=self.coordinator,
            api_token=self.token,
            host="127.0.0.1",
            port=0,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.coordinator.close()
        self.tmp.cleanup()

    def request_mcp(self, method, params, *, token=None, tool_name=None, request_id=1):
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": {
                **params,
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                    "io.modelcontextprotocol/clientCapabilities": {},
                },
            },
        })
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Mcp-Method": method,
            "MCP-Protocol-Version": "2026-07-28",
        }
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        if tool_name is not None:
            headers["Mcp-Name"] = tool_name
        conn = http.client.HTTPConnection(self.host, self.port, timeout=8)
        conn.request("POST", "/mcp", payload, headers)
        response = conn.getresponse()
        raw = response.read()
        content_type = response.getheader("Content-Type", "")
        conn.close()
        if "application/json" in content_type and raw:
            return response.status, json.loads(raw)
        return response.status, raw.decode("utf-8", errors="replace")

    def test_remote_mcp_endpoint_requires_runtime_bearer_authentication(self):
        status, body = self.request_mcp("tools/list", {}, token=None)
        self.assertEqual(status, 401, body)

    def test_remote_mcp_lists_only_governed_runtime_tools(self):
        status, body = self.request_mcp("tools/list", {}, token=self.token)
        self.assertEqual(status, 200, body)
        names = {tool["name"] for tool in body["result"]["tools"]}
        self.assertTrue({
            "runtime_status",
            "list_agents",
            "list_tasks",
            "get_task",
            "get_task_events",
            "run_task",
            "run_sales_workflow",
        }.issubset(names))
        forbidden = {"send_email", "send_dm", "submit_form", "publish_post", "book_meeting", "issue_quote"}
        self.assertFalse(names & forbidden)

        sales_tool = next(tool for tool in body["result"]["tools"] if tool["name"] == "run_sales_workflow")
        description = sales_tool.get("description", "").lower()
        self.assertIn("draft-only", description)
        self.assertIn("commerce", description)
        self.assertNotIn("industrial-maintenance", description)

    def test_remote_mcp_runtime_status_tool_returns_safe_live_metadata(self):
        status, body = self.request_mcp(
            "tools/call",
            {"name": "runtime_status", "arguments": {}},
            token=self.token,
            tool_name="runtime_status",
        )
        self.assertEqual(status, 200, body)
        serialized = json.dumps(body)
        self.assertIn("8.0.0", serialized)
        self.assertIn("registered_agents", serialized)
        self.assertNotIn(self.token, serialized)
        self.assertNotIn("OPENROUTER_API_KEY", serialized)
        self.assertNotIn("DATABASE_URL", serialized)

    def test_remote_mcp_sales_tool_refuses_unverified_or_mock_provider(self):
        status, body = self.request_mcp(
            "tools/call",
            {
                "name": "run_sales_workflow",
                "arguments": {
                    "objective": "Prepare an internal synthetic sales qualification summary.",
                    "inputs": {"fictional_prospect": True},
                    "provider_route": "mock",
                },
            },
            token=self.token,
            tool_name="run_sales_workflow",
        )
        self.assertEqual(status, 200, body)
        self.assertTrue(body["result"].get("isError", False), body)
        self.assertIn("verified live provider", json.dumps(body).lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
