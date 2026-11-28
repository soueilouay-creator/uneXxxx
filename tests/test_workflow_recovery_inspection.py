from __future__ import annotations

import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path

from unexpected_runtime.recovery_inspection import inspect_workflow_recovery
from unexpected_runtime.postgres_storage import PostgresStateStore
from unexpected_runtime.storage import StateStore


class WorkflowRecoveryInspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = StateStore(Path(self.temp.name) / "state.sqlite3")
        self.workflow_id = "inspection-" + uuid.uuid4().hex
        self.identity = {"request": {"objective": "synthetic recovery inspection"}, "provider_route": "fixture"}

    def _checkpoint(self):
        return self.store.create_workflow_checkpoint(
            self.workflow_id,
            "a" * 64,
            1,
            {"request": self.identity, "completed_stages": []},
        )

    def test_missing_workflow_returns_read_only_not_found_report(self):
        report = inspect_workflow_recovery(self.store, "missing-" + uuid.uuid4().hex)
        self.assertEqual(report["disposition"], "not_found")
        self.assertFalse(report["automatic_replay_permitted"])
        self.assertFalse(report["inspection_is_authorization"])
        self.assertEqual(report["stages"], [])

    def test_started_stage_is_manual_review_and_inspection_does_not_mutate(self):
        self._checkpoint()
        self.store.begin_workflow_stage(
            self.workflow_id, "0001:execute", 1, "b" * 64, "private-attempt-token"
        )
        before_checkpoint = self.store.get_workflow_checkpoint(self.workflow_id)
        before_stages = self.store.list_workflow_stages(self.workflow_id)

        report = inspect_workflow_recovery(self.store, self.workflow_id)

        after_checkpoint = self.store.get_workflow_checkpoint(self.workflow_id)
        after_stages = self.store.list_workflow_stages(self.workflow_id)
        self.assertEqual(report["disposition"], "manual_review_required")
        self.assertFalse(report["automatic_replay_permitted"])
        self.assertEqual(report["stages"][0]["status"], "started")
        self.assertTrue(report["stages"][0]["attempt_token_present"])
        self.assertNotIn("private-attempt-token", json.dumps(report))
        self.assertEqual(after_checkpoint, before_checkpoint)
        self.assertEqual(after_stages, before_stages)

    def test_completed_stage_with_missing_task_evidence_requires_review(self):
        self._checkpoint()
        self.store.begin_workflow_stage(
            self.workflow_id, "0001:execute", 1, "b" * 64, "attempt-token"
        )
        self.assertTrue(self.store.complete_workflow_stage(
            self.workflow_id, "0001:execute", "attempt-token", "missing-task",
            {"value": {"synthetic": True}},
        ))

        report = inspect_workflow_recovery(self.store, self.workflow_id)

        self.assertEqual(report["disposition"], "manual_review_required")
        self.assertIn("task_reference_missing", [item["code"] for item in report["findings"]])
        self.assertFalse(report["automatic_replay_permitted"])

    def test_waiting_approval_is_detected_before_stage_start(self):
        checkpoint = self._checkpoint()
        stage_key = "0001:execute"
        execution_id = "execution-" + uuid.uuid4().hex
        task_id = "task-" + uuid.uuid4().hex
        self.store.create_approval_execution_intent(
            execution_id, task_id, "c" * 64, "d" * 64, "publish", self.workflow_id, stage_key
        )
        self.assertTrue(self.store.transition_approval_execution_intent(
            execution_id, "prepared", "awaiting_approval", 0
        ))
        self.store.create_workflow_stage_approval_intent(
            self.workflow_id, stage_key, "e" * 64, execution_id, task_id, "d" * 64, "publish"
        )
        self.assertTrue(self.store.save_workflow_checkpoint(
            self.workflow_id, checkpoint["revision"], "running", stage_key,
            {"request": self.identity, "completed_stages": [], "pending_approval": {"stage_key": stage_key}},
        ))

        report = inspect_workflow_recovery(self.store, self.workflow_id)

        self.assertEqual(report["disposition"], "awaiting_human_approval")
        self.assertEqual(report["approval_intents"][0]["state"], "awaiting_approval")
        self.assertEqual(report["approval_intents"][0]["execution_state"], "awaiting_approval")
        self.assertEqual(report["stages"], [])
        self.assertFalse(report["automatic_replay_permitted"])

    def test_invalid_workflow_id_is_rejected(self):
        for value in ("", "  ", None, 1):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    inspect_workflow_recovery(self.store, value)


class PostgresWorkflowRecoveryInspectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ.get("TEST_POSTGRES_DSN")
        if not cls.dsn:
            raise unittest.SkipTest("TEST_POSTGRES_DSN is not configured.")

    def setUp(self):
        self.store = PostgresStateStore(self.dsn)
        self.workflow_id = "inspection-postgres-" + uuid.uuid4().hex
        self.stage_key = "0001:execute"
        self.identity = {"request": {"objective": "synthetic postgres recovery inspection"}, "provider_route": "fixture"}
        self.store.create_workflow_checkpoint(
            self.workflow_id, "a" * 64, 1,
            {"request": self.identity, "completed_stages": []},
        )

    def test_started_stage_inspection_is_read_only_on_postgres(self):
        self.store.begin_workflow_stage(
            self.workflow_id, self.stage_key, 1, "b" * 64, "private-postgres-attempt"
        )
        before_checkpoint = self.store.get_workflow_checkpoint(self.workflow_id)
        before_stages = self.store.list_workflow_stages(self.workflow_id)

        report = inspect_workflow_recovery(self.store, self.workflow_id)

        self.assertEqual(report["disposition"], "manual_review_required")
        self.assertFalse(report["automatic_replay_permitted"])
        self.assertNotIn("private-postgres-attempt", json.dumps(report))
        self.assertEqual(self.store.get_workflow_checkpoint(self.workflow_id), before_checkpoint)
        self.assertEqual(self.store.list_workflow_stages(self.workflow_id), before_stages)

    def test_pending_approval_binding_is_inspected_on_postgres(self):
        execution_id = "execution-" + uuid.uuid4().hex
        task_id = "task-" + uuid.uuid4().hex
        self.store.create_approval_execution_intent(
            execution_id, task_id, "c" * 64, "d" * 64, "publish",
            self.workflow_id, self.stage_key,
        )
        self.assertTrue(self.store.transition_approval_execution_intent(
            execution_id, "prepared", "awaiting_approval", 0
        ))
        self.store.create_workflow_stage_approval_intent(
            self.workflow_id, self.stage_key, "e" * 64, execution_id,
            task_id, "d" * 64, "publish",
        )
        checkpoint = self.store.get_workflow_checkpoint(self.workflow_id)
        self.assertTrue(self.store.save_workflow_checkpoint(
            self.workflow_id, checkpoint["revision"], "running", self.stage_key,
            {"request": self.identity, "completed_stages": [], "pending_approval": {"stage_key": self.stage_key}},
        ))

        report = inspect_workflow_recovery(self.store, self.workflow_id)

        self.assertEqual(report["disposition"], "awaiting_human_approval")
        self.assertEqual(report["approval_intents"][0]["state"], "awaiting_approval")
        self.assertEqual(report["approval_intents"][0]["execution_state"], "awaiting_approval")
        self.assertFalse(report["automatic_replay_permitted"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
