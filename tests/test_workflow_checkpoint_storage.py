from __future__ import annotations

import os
import tempfile
import unittest
import uuid

from unexpected_runtime.storage import StateStore
from unexpected_runtime.models import TaskRequest
from unexpected_runtime.postgres_storage import PostgresStateStore


class SQLiteWorkflowCheckpointTests(unittest.TestCase):
    def test_checkpoint_ledger_is_additive_persistent_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = directory + "/state.sqlite3"
            store = StateStore(path)

            # Seed pre-existing application state before adding checkpoint records.
            request = TaskRequest.create(
                "orchestrator", "Preserve this existing task", inputs={"keep": True}
            )
            store.enqueue(request)
            store.set_memory("orchestrator", "preservation-fixture", {"keep": "yes"})
            store.log_event("preservation_fixture", request.task_id, "orchestrator", {"keep": True})
            before_task = store.get_task(request.task_id)

            checkpoint = store.create_workflow_checkpoint(
                "workflow-fixture", "a" * 64, 1,
                {"request": {"objective": "synthetic fixture"}, "completed_stages": []},
            )
            self.assertEqual(checkpoint["revision"], 0)
            self.assertEqual(checkpoint["status"], "running")

            first = store.begin_workflow_stage(
                "workflow-fixture", "execute:1", 1, "b" * 64, "attempt-one"
            )
            duplicate = store.begin_workflow_stage(
                "workflow-fixture", "execute:1", 1, "b" * 64, "attempt-two"
            )
            self.assertTrue(first["can_execute"])
            self.assertFalse(duplicate["can_execute"])
            self.assertEqual(duplicate["status"], "started")
            self.assertEqual(duplicate["attempt_token"], "attempt-one")

            result = {"output": "synthetic result", "side_effects": 0}
            self.assertFalse(store.complete_workflow_stage(
                "workflow-fixture", "execute:1", "wrong-token", "task-fixture", result
            ))
            self.assertTrue(store.complete_workflow_stage(
                "workflow-fixture", "execute:1", "attempt-one", "task-fixture", result
            ))
            self.assertFalse(store.complete_workflow_stage(
                "workflow-fixture", "execute:1", "attempt-one", "task-fixture", result
            ))

            stages = store.list_workflow_stages("workflow-fixture")
            self.assertEqual(len(stages), 1)
            self.assertEqual(stages[0]["status"], "completed")
            self.assertEqual(stages[0]["result"], result)

            self.assertTrue(store.save_workflow_checkpoint(
                "workflow-fixture", 0, "completed", "execute",
                {"request": {"objective": "synthetic fixture"}, "completed_stages": ["execute"]},
            ))
            self.assertFalse(store.save_workflow_checkpoint(
                "workflow-fixture", 0, "blocked", "execute", {"stale": True}
            ))

            # Reopening the same local store proves the new ledger and old records coexist.
            reopened = StateStore(path)
            after = reopened.get_workflow_checkpoint("workflow-fixture")
            self.assertEqual(after["revision"], 1)
            self.assertEqual(after["status"], "completed")
            self.assertEqual(after["state"]["completed_stages"], ["execute"])
            self.assertEqual(reopened.get_task(request.task_id)["payload_json"], before_task["payload_json"])
            self.assertEqual(
                reopened.get_memory("orchestrator", "preservation-fixture"),
                {"keep": "yes"},
            )
            self.assertTrue(any(
                event["event_type"] == "preservation_fixture"
                for event in reopened.events(100)
            ))

    def test_checkpoint_and_stage_hash_mismatches_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(directory + "/state.sqlite3")
            store.create_workflow_checkpoint("workflow-hash", "a" * 64, 1, {"safe": True})
            with self.assertRaises(ValueError):
                store.create_workflow_checkpoint("workflow-hash", "c" * 64, 1, {"safe": False})
            store.begin_workflow_stage("workflow-hash", "plan:1", 1, "b" * 64, "attempt-one")
            with self.assertRaises(ValueError):
                store.begin_workflow_stage("workflow-hash", "plan:1", 1, "d" * 64, "attempt-two")
            with self.assertRaises(ValueError):
                store.begin_workflow_stage("workflow-hash", "other-stage", 1, "b" * 64, "attempt-three")


POSTGRES_DSN = os.getenv("TEST_POSTGRES_DSN")


@unittest.skipUnless(POSTGRES_DSN, "TEST_POSTGRES_DSN is only provided by the ephemeral CI PostgreSQL service")
class PostgresWorkflowCheckpointTests(unittest.TestCase):
    def test_checkpoint_ledger_persists_and_refuses_automatic_stage_replay(self):
        store = PostgresStateStore(POSTGRES_DSN)
        workflow_id = "ci-" + uuid.uuid4().hex
        checkpoint = store.create_workflow_checkpoint(
            workflow_id, "a" * 64, 1,
            {"request": {"objective": "postgres fixture"}, "completed_stages": []},
        )
        self.assertEqual(checkpoint["status"], "running")

        first = store.begin_workflow_stage(
            workflow_id, "execute:1", 1, "b" * 64, "attempt-one"
        )
        duplicate = store.begin_workflow_stage(
            workflow_id, "execute:1", 1, "b" * 64, "attempt-two"
        )
        self.assertTrue(first["can_execute"])
        self.assertFalse(duplicate["can_execute"])
        self.assertEqual(duplicate["attempt_token"], "attempt-one")

        result = {"output": "postgres synthetic result", "side_effects": 0}
        self.assertTrue(store.complete_workflow_stage(
            workflow_id, "execute:1", "attempt-one", "task-fixture", result
        ))
        self.assertFalse(store.complete_workflow_stage(
            workflow_id, "execute:1", "attempt-one", "task-fixture", result
        ))
        self.assertTrue(store.save_workflow_checkpoint(
            workflow_id, 0, "completed", "execute",
            {"request": {"objective": "postgres fixture"}, "completed_stages": ["execute"]},
        ))

        restored = store.get_workflow_checkpoint(workflow_id)
        self.assertEqual(restored["revision"], 1)
        self.assertEqual(restored["status"], "completed")
        self.assertEqual(store.list_workflow_stages(workflow_id)[0]["result"], result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
