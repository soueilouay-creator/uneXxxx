import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from unexpected_runtime.coordinator import Coordinator
from unexpected_runtime.http_api import create_server
from unexpected_runtime.models import PermissionDenied
from unexpected_runtime.providers import DeterministicMockProvider
from unexpected_runtime.subagents import SubagentError


class SubagentDelegationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.provider = DeterministicMockProvider()
        self.coordinator = Coordinator(
            manifest_path=Path(__file__).resolve().parents[1] / "agent_manifest.json",
            state_dir=Path(self.temp.name) / "state",
            provider=self.provider,
            max_retries=0,
        )
        parent = self.coordinator.invoke(
            "orchestrator", "Coordinate a bounded review.",
            inputs={"request_label": "parent-only-context"},
            idempotency_key="subagent-parent-" + str(id(self)),
        )
        self.parent_task_id = parent.task_id
        self.parent_output = parent.output

    def tearDown(self):
        self.coordinator.close()
        self.temp.cleanup()

    def test_child_runs_have_isolated_context_and_persist_parent_lineage(self):
        children = [
            {"agent_id": "project-manager", "objective": "Create a small project plan.",
             "inputs": {"child_label": "planning-only"}},
            {"agent_id": "research-scout", "objective": "Research the supplied question.",
             "inputs": {"child_label": "research-only"}},
        ]
        result = self.coordinator.run_subagents(
            parent_task_id=self.parent_task_id,
            parent_agent_id="orchestrator",
            children=children,
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["children"]), 2)
        child_ids = [item["task_id"] for item in result["children"]]
        self.assertEqual(len(set(child_ids)), 2)
        tasks = {item["task_id"]: item for item in self.coordinator.store.list_tasks(100)}
        for child_id in child_ids:
            self.assertEqual(tasks[child_id]["parent_task_id"], self.parent_task_id)
        provider_payloads = [json.loads(request["user_prompt"]) for request in self.provider.requests[1:]]
        self.assertIn("planning-only", json.dumps(provider_payloads[0]))
        self.assertNotIn("research-only", json.dumps(provider_payloads[0]))
        self.assertNotIn("parent-only-context", json.dumps(provider_payloads))
        events = self.coordinator.store.events(100)
        self.assertIn("subagent_child_completed", {event["event_type"] for event in events})
        provider_calls = self.provider.calls
        replay = self.coordinator.run_subagents(
            parent_task_id=self.parent_task_id,
            parent_agent_id="orchestrator",
            children=children,
        )
        self.assertEqual([item["task_id"] for item in replay["children"]], child_ids)
        self.assertEqual(self.provider.calls, provider_calls)

    def test_handoff_scope_is_checked_before_any_child_task_is_created(self):
        before = len(self.coordinator.store.list_tasks(100))
        with self.assertRaises(PermissionDenied):
            self.coordinator.run_subagents(
                parent_task_id=self.parent_task_id,
                parent_agent_id="orchestrator",
                children=[{"agent_id": "maintenance-engineer", "objective": "Outside handoff scope."}],
            )
        self.assertEqual(len(self.coordinator.store.list_tasks(100)), before)

    def test_child_count_and_depth_budgets_fail_closed(self):
        with self.assertRaises(ValueError):
            self.coordinator.run_subagents(
                parent_task_id=self.parent_task_id,
                parent_agent_id="orchestrator",
                children=[{"agent_id": "project-manager", "objective": "Child"}] * 4,
            )
        child = self.coordinator.run_subagents(
            parent_task_id=self.parent_task_id,
            parent_agent_id="orchestrator",
            children=[{"agent_id": "code-reviewer", "objective": "Review the parent result."}],
            max_depth=1,
        )
        child_id = child["children"][0]["task_id"]
        with self.assertRaises(SubagentError):
            self.coordinator.run_subagents(
                parent_task_id=child_id,
                parent_agent_id="code-reviewer",
                children=[{"agent_id": "security-reviewer", "objective": "Review the child result."}],
                max_depth=1,
            )



class SubagentAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.coordinator = Coordinator(
            manifest_path=Path(__file__).resolve().parents[1] / "agent_manifest.json",
            state_dir=Path(self.temp.name) / "state",
            provider=DeterministicMockProvider(),
            max_retries=0,
        )
        parent = self.coordinator.invoke(
            "orchestrator", "Create a parent task for the API test.",
            idempotency_key="subagent-api-parent-" + str(id(self)),
        )
        self.parent_task_id = parent.task_id
        self.token = "subagent-api-test-token-" + "x" * 32
        self.server = create_server(coordinator=self.coordinator, api_token=self.token, host="127.0.0.1", port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.coordinator.close()
        self.temp.cleanup()

    def request(self, method, path, payload=None, token=None):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=8)
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        body = json.dumps(payload) if payload is not None else None
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        connection.close()
        return response.status, json.loads(raw) if raw else {}

    def test_subagent_run_api_is_authenticated_and_returns_child_lineage(self):
        payload = {
            "parent_task_id": self.parent_task_id,
            "parent_agent_id": "orchestrator",
            "children": [{"agent_id": "project-manager", "objective": "Prepare a concise plan."}],
        }
        self.assertEqual(self.request("POST", "/v1/subagents/run", payload)[0], 401)
        status, response = self.request("POST", "/v1/subagents/run", payload, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["result"]["status"], "completed")
        child = response["result"]["children"][0]
        self.assertEqual(child["status"], "completed")
        task = self.coordinator.store.get_task(child["task_id"])
        self.assertEqual(json.loads(task["payload_json"])["parent_task_id"], self.parent_task_id)

    def test_mcp_tool_catalog_is_authenticated_and_metadata_only(self):
        self.assertEqual(self.request("GET", "/v1/mcp/tools")[0], 401)
        status, response = self.request("GET", "/v1/mcp/tools", token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(response["count"], 0)
        self.assertEqual(response["items"], [])

if __name__ == "__main__":
    unittest.main(verbosity=2)
