from __future__ import annotations

import hashlib
import os
import threading
import unittest
import uuid

from unexpected_runtime.models import TaskRequest
from unexpected_runtime.postgres_storage import PostgresStateStore


class PostgresWorkflowStageApprovalProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ.get("TEST_POSTGRES_DSN")
        if not cls.dsn:
            raise unittest.SkipTest("TEST_POSTGRES_DSN is not configured.")

    def setUp(self):
        self.store = PostgresStateStore(self.dsn)
        self.workflow_id = "workflow-" + uuid.uuid4().hex
        self.stage_key = "0001:execute"
        self.execution_id = "execution-" + uuid.uuid4().hex
        self.task_id = "task-" + uuid.uuid4().hex
        self.permission = "publish"
        self.action_digest = hashlib.sha256(self.execution_id.encode()).hexdigest()
        request_hash = hashlib.sha256((self.workflow_id + self.stage_key).encode()).hexdigest()
        self.store.create_workflow_checkpoint(
            self.workflow_id, request_hash, 1,
            {"request": {"case": "postgres-stage-approval"}, "completed_stages": []},
        )
        self.store.create_approval_execution_intent(
            self.execution_id, self.task_id, request_hash, self.action_digest,
            self.permission, self.workflow_id, self.stage_key,
        )
        self.assertTrue(self.store.transition_approval_execution_intent(
            self.execution_id, "prepared", "awaiting_approval", 0
        ))
        self.stage = self.store.create_workflow_stage_approval_intent(
            self.workflow_id, self.stage_key, request_hash, self.execution_id,
            self.task_id, self.action_digest, self.permission,
        )

    def test_independent_connections_have_one_revision_checked_approval_winner(self):
        barrier = threading.Barrier(20)
        outcomes = []
        lock = threading.Lock()

        def attempt(index):
            independent = PostgresStateStore(self.dsn)
            barrier.wait(timeout=10)
            won = independent.transition_workflow_stage_approval_intent(
                self.workflow_id, self.stage_key, "awaiting_approval", "approved",
                0, "approval-" + str(index),
            )
            with lock:
                outcomes.append(won)

        threads = [threading.Thread(target=attempt, args=(i,)) for i in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(outcomes.count(True), 1)
        self.assertEqual(outcomes.count(False), 19)
        persisted = self.store.get_workflow_stage_approval_intent(self.workflow_id, self.stage_key)
        self.assertEqual(persisted["state"], "approved")
        self.assertTrue(persisted["approval_id"].startswith("approval-"))
        self.assertEqual(persisted["revision"], 1)

    def test_restart_readback_blocks_queued_consumed_approval_instead_of_replaying(self):
        self.assertTrue(self.store.transition_workflow_stage_approval_intent(
            self.workflow_id, self.stage_key, "awaiting_approval", "approved", 0, "approval-recovery"
        ))
        self.assertTrue(self.store.transition_approval_execution_intent(
            self.execution_id, "awaiting_approval", "approved", 1
        ))
        request = TaskRequest.create(
            "orchestrator", "recover this prepared operation only by explicit new approval",
            task_id=self.task_id, required_permissions=(self.permission,),
            execution_id=self.execution_id, approval_reference="approval-recovery",
        )
        self.store.enqueue_approved_task(request, self.execution_id, 2)
        self.assertTrue(self.store.transition_workflow_stage_approval_intent(
            self.workflow_id, self.stage_key, "approved", "enqueued", 1
        ))

        restarted = PostgresStateStore(self.dsn)
        stage = restarted.get_workflow_stage_approval_intent(self.workflow_id, self.stage_key)
        execution = restarted.get_approval_execution_intent(self.execution_id)
        task = restarted.get_task(self.task_id)
        self.assertEqual(stage["state"], "enqueued")
        self.assertEqual(execution["state"], "enqueued")
        self.assertEqual(task["status"], "queued")
        self.assertEqual(task["payload"]["execution_id"], self.execution_id)
        self.assertEqual(task["payload"]["approval_reference"], "approval-recovery")

        self.assertTrue(restarted.transition_approval_execution_intent(
            self.execution_id, "enqueued", "blocked", int(execution["revision"])
        ))
        self.assertTrue(restarted.transition_workflow_stage_approval_intent(
            self.workflow_id, self.stage_key, "enqueued", "blocked", int(stage["revision"])
        ))
        self.assertEqual(PostgresStateStore(self.dsn).get_approval_execution_intent(
            self.execution_id
        )["state"], "blocked")
        self.assertEqual(PostgresStateStore(self.dsn).get_workflow_stage_approval_intent(
            self.workflow_id, self.stage_key
        )["state"], "blocked")


if __name__ == "__main__":
    unittest.main(verbosity=2)
