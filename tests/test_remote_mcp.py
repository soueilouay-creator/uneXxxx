from __future__ import annotations

import http.client
import json
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

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

    def test_remote_mcp_agent_task_returns_task_id_without_waiting(self):
        started = threading.Event()
        release = threading.Event()
        response_box = []

        def delayed_execution(request, token):
            started.set()
            if not release.wait(timeout=4):
                raise RuntimeError("test release was not signalled")
            self.coordinator.store.mark_task(request.task_id, "running")
            self.coordinator.store.mark_task(
                request.task_id, "completed", {"status": "completed", "output": "synthetic result"}
            )
            return {"status": "completed", "output": "synthetic result"}

        self.coordinator._execute_with_deadline = delayed_execution
        request = {
            "name": "run_task",
            "arguments": {
                "agent_id": "project-manager",
                "objective": "Prepare a synthetic internal task result.",
                "inputs": {"synthetic_fixture": True},
                "provider_route": "synthetic-live",
                "deadline_seconds": 20,
                "max_steps": 1,
                "idempotency_key": "mcp-agent-task-replay-test",
            },
        }

        with patch("unexpected_runtime.mcp_server._live_route", return_value="synthetic-live"):
            client = threading.Thread(
                target=lambda: response_box.append(self.request_mcp(
                    "tools/call", request, token=self.token, tool_name="run_task"
                )),
                daemon=True,
            )
            client.start()
            try:
                self.assertTrue(started.wait(timeout=2), "agent task worker did not start")
                client.join(timeout=1)
                self.assertFalse(
                    client.is_alive(),
                    "MCP run_task must return the persisted task ID without waiting for provider work",
                )
                self.assertEqual(len(response_box), 1)
                status, body = response_box[0]
                self.assertEqual(status, 200, body)
                result = body["result"].get("structuredContent")
                if not isinstance(result, dict):
                    result = {}
                    for item in body["result"].get("content", []):
                        if item.get("type") == "text":
                            try:
                                candidate = json.loads(item.get("text", ""))
                            except (TypeError, ValueError):
                                continue
                            if isinstance(candidate, dict):
                                result = candidate
                                break
                task_id = result.get("task_id")
                self.assertIsInstance(task_id, str)
                self.assertTrue(task_id)

                replay_status, replay_body = self.request_mcp(
                    "tools/call", request, token=self.token, tool_name="run_task"
                )
                self.assertEqual(replay_status, 200, replay_body)
                replay = replay_body["result"].get("structuredContent")
                self.assertEqual(replay["task_id"], task_id)
                self.assertEqual(replay["status"], "in_progress")
            finally:
                release.set()
                client.join(timeout=3)

        deadline = time.monotonic() + 3
        row = self.coordinator.store.get_task(task_id)
        while row and row.get("status") not in {"completed", "failed", "cancelled", "timeout"} and time.monotonic() < deadline:
            time.sleep(0.01)
            row = self.coordinator.store.get_task(task_id)
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "completed", row)
        self.assertEqual(json.loads(row["result_json"])["output"], "synthetic result")
        with patch("unexpected_runtime.mcp_server._live_route", return_value="synthetic-live"):
            replay_status, replay_body = self.request_mcp(
                "tools/call", request, token=self.token, tool_name="run_task"
            )
        self.assertEqual(replay_status, 200, replay_body)
        replay = replay_body["result"].get("structuredContent")
        self.assertIsInstance(replay, dict, replay_body)
        self.assertEqual(replay["task_id"], task_id)
        self.assertEqual(replay["status"], "completed")
        self.assertTrue(replay["replayed"])

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


    def test_remote_mcp_sales_workflow_returns_task_id_before_work_and_survives_restart(self):
        started = threading.Event()
        release = threading.Event()
        response_box = []

        def delayed_lifecycle(agent_id, objective, inputs, **kwargs):
            started.set()
            if not release.wait(timeout=4):
                raise RuntimeError("test release was not signalled")
            return SimpleNamespace(to_dict=lambda: {
                "status": "delivered",
                "delivered": True,
                "verified_output": "synthetic workflow result",
            })

        self.coordinator.run_lifecycle = delayed_lifecycle
        request = {
            "name": "run_sales_workflow",
            "arguments": {
                "objective": "Prepare a synthetic internal commerce workflow summary.",
                "inputs": {"synthetic_fixture": True},
                "provider_route": "synthetic-live",
            },
        }

        with patch("unexpected_runtime.mcp_server._live_route", return_value="synthetic-live"):
            client = threading.Thread(
                target=lambda: response_box.append(self.request_mcp(
                    "tools/call", request, token=self.token, tool_name="run_sales_workflow"
                )),
                daemon=True,
            )
            client.start()
            try:
                self.assertTrue(started.wait(timeout=2), "workflow worker did not start")
                client.join(timeout=1)
                self.assertFalse(
                    client.is_alive(),
                    "MCP must return the persisted task ID without waiting for workflow completion",
                )
                self.assertEqual(len(response_box), 1)
                status, body = response_box[0]
                self.assertEqual(status, 200, body)
                result = body["result"].get("structuredContent")
                if not isinstance(result, dict):
                    result = {}
                    for item in body["result"].get("content", []):
                        if item.get("type") == "text":
                            try:
                                candidate = json.loads(item.get("text", ""))
                            except (TypeError, ValueError):
                                continue
                            if isinstance(candidate, dict):
                                result = candidate
                                break
                task_id = result.get("task_id")
                self.assertIsInstance(task_id, str)
                self.assertTrue(task_id)
            finally:
                release.set()
                client.join(timeout=3)

        deadline = time.monotonic() + 3
        row = self.coordinator.store.get_task(task_id)
        while row and row.get("status") not in {"completed", "failed", "cancelled", "timeout"} and time.monotonic() < deadline:
            time.sleep(0.01)
            row = self.coordinator.store.get_task(task_id)
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "completed", row)

        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.coordinator.close()
        self.coordinator = Coordinator(
            state_dir=self.tmp.name,
            provider=DeterministicMockProvider(),
            max_workers=2,
            max_retries=0,
        )
        self.server = create_server(
            coordinator=self.coordinator,
            api_token=self.token,
            host="127.0.0.1",
            port=0,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

        status, body = self.request_mcp(
            "tools/call",
            {"name": "get_task", "arguments": {"task_id": task_id}},
            token=self.token,
            tool_name="get_task",
        )
        self.assertEqual(status, 200, body)
        restored = body["result"].get("structuredContent")
        if not isinstance(restored, dict):
            restored = {}
            for item in body["result"].get("content", []):
                if item.get("type") == "text":
                    try:
                        candidate = json.loads(item.get("text", ""))
                    except (TypeError, ValueError):
                        continue
                    if isinstance(candidate, dict):
                        restored = candidate
                        break
        self.assertEqual(restored["task"]["task_id"], task_id)
        self.assertEqual(restored["task"]["status"], "completed")
        self.assertEqual(restored["task"]["result"]["verified_output"], "synthetic workflow result")


if __name__ == "__main__":
    unittest.main(verbosity=2)
