import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from unexpected_runtime.coordinator import Coordinator
from unexpected_runtime.http_api import create_server
from unexpected_runtime.providers import DeterministicMockProvider
from unexpected_runtime.storage import StateStore


class TaskEventCursorStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = StateStore(Path(self.temp.name) / "state.sqlite3")
        self.store.log_event("task_started", "task-1", "maintenance-engineer", {"stage": "execute"})
        self.store.log_event("provider_started", "task-1", "maintenance-engineer", {"attempt": 1})
        self.store.log_event("provider_completed", "task-1", "maintenance-engineer", {"attempt": 1})
        self.store.log_event("unrelated_event", "task-2", "other-role", {})

    def tearDown(self):
        self.temp.cleanup()

    def test_task_events_are_ordered_and_cursor_pages_have_no_gaps(self):
        first = self.store.list_task_events("task-1", after_event_id=0, limit=2)
        self.assertEqual([row["event_type"] for row in first], ["task_started", "provider_started"])
        second = self.store.list_task_events("task-1", after_event_id=first[-1]["event_id"], limit=2)
        self.assertEqual([row["event_type"] for row in second], ["provider_completed"])
        self.assertGreater(second[0]["event_id"], first[-1]["event_id"])

    def test_task_event_cursor_is_scoped_to_task_and_rejects_invalid_limits(self):
        rows = self.store.list_task_events("task-1", after_event_id=0, limit=100)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row["task_id"] == "task-1" for row in rows))
        with self.assertRaises((TypeError, ValueError)):
            self.store.list_task_events("task-1", after_event_id=-1, limit=10)
        with self.assertRaises((TypeError, ValueError)):
            self.store.list_task_events("task-1", after_event_id=0, limit=0)


class TaskEventCursorAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.coordinator = Coordinator(
            manifest_path=Path(__file__).resolve().parents[1] / "agent_manifest.json",
            state_dir=Path(self.temp.name) / "state",
            provider=DeterministicMockProvider(),
            max_retries=0,
        )
        result = self.coordinator.invoke(
            "maintenance-engineer", "Review a preventive maintenance checklist",
            idempotency_key="trace-cursor-test",
        )
        self.task_id = result.task_id
        self.coordinator.store.log_event("trace_stage_one", self.task_id, "maintenance-engineer", {"stage": 1})
        self.coordinator.store.log_event("trace_stage_two", self.task_id, "maintenance-engineer", {"stage": 2})
        self.token = "trace-api-test-token-" + "x" * 32
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

    def request(self, path, token=None):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=8)
        headers = {"Authorization": "Bearer " + token} if token else {}
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        content_type = response.getheader("Content-Type", "")
        connection.close()
        return response.status, json.loads(raw) if "application/json" in content_type and raw else raw

    def test_authenticated_task_event_endpoint_supports_reconnect_cursor(self):
        path = f"/v1/tasks/{self.task_id}/events?after=0&limit=2"
        self.assertEqual(self.request(path)[0], 401)
        status, first = self.request(path, self.token)
        self.assertEqual(status, 200)
        self.assertEqual(len(first["items"]), 2)
        self.assertTrue(first["has_more"])
        cursor = first["next_cursor"]
        status, second = self.request(f"/v1/tasks/{self.task_id}/events?after={cursor}&limit=20", self.token)
        self.assertEqual(status, 200)
        first_ids = [item["event_id"] for item in first["items"]]
        second_ids = [item["event_id"] for item in second["items"]]
        self.assertTrue(first_ids)
        self.assertTrue(second_ids)
        self.assertGreater(min(second_ids), max(first_ids))
        self.assertEqual(set(item["task_id"] for item in first["items"] + second["items"]), {self.task_id})

    def test_task_event_endpoint_rejects_bad_cursor_and_unknown_task(self):
        self.assertEqual(self.request(f"/v1/tasks/{self.task_id}/events?after=-1", self.token)[0], 400)
        self.assertEqual(self.request("/v1/tasks/missing-task/events", self.token)[0], 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
