from __future__ import annotations

import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path

from unexpected_runtime.models import TaskRequest
from unexpected_runtime.postgres_storage import PostgresStateStore
from unexpected_runtime.storage import StateStore
from unexpected_runtime.workflow import WorkflowRunner


def seed_completed_plan(
    store,
    workflow_id: str,
    *,
    task_id: str,
    task_status: str = "completed",
    idempotency_key: str | None = None,
    required_permissions: tuple[str, ...] = (),
    claim_state: str = "completed",
    claim_task_id: str | None = None,
    claim_hash_mismatch: bool = False,
    claim_result_override: dict | None = None,
    create_task: bool = True,
):
    request = {"objective": "resume a persisted plan"}
    identity = {"request": request, "provider_route": "fixture"}
    claim_owner = claim_task_id or task_id
    task_result = {"task_id": task_id, "status": task_status}

    if create_task:
        task_request = TaskRequest.create(
            "orchestrator",
            "Checkpoint recovery fixture",
            task_id=task_id,
            inputs={"fixture": True},
            required_permissions=required_permissions,
            idempotency_key=idempotency_key,
            source_refs=("fixture",),
            provider_route="fixture",
        )
        store.enqueue(task_request)
        payload = json.loads(store.get_task(task_id)["payload_json"])
        if idempotency_key:
            request_hash = WorkflowRunner._task_request_hash(payload)
            if claim_hash_mismatch:
                request_hash = "f" * 64
            store.claim_idempotency(idempotency_key, request_hash, claim_owner)
        store.mark_task(task_id, task_status, task_result)
        if idempotency_key and claim_state == "completed":
            store.complete_idempotency(
                idempotency_key,
                claim_owner,
                claim_result_override or task_result,
            )

    store.create_workflow_checkpoint(
        workflow_id,
        WorkflowRunner._canonical_hash(identity),
        1,
        {"request": identity, "completed_stages": []},
    )
    stage_key = "0001:plan"
    attempt_token = "attempt-" + workflow_id
    store.begin_workflow_stage(
        workflow_id,
        stage_key,
        1,
        WorkflowRunner._stage_hash(stage_key, (request, None)),
        attempt_token,
    )
    store.complete_workflow_stage(
        workflow_id,
        stage_key,
        attempt_token,
        task_id,
        {"value": {"task_id": task_id, "text": "persisted plan"}},
    )
    store.save_workflow_checkpoint(
        workflow_id,
        0,
        "running",
        stage_key,
        {"request": identity, "completed_stages": [stage_key]},
    )
    return request, identity


def resume_with_observation(store, workflow_id: str, request: dict, identity: dict):
    calls = []
    result = WorkflowRunner(
        plan=lambda *args: calls.append("plan") or {"text": "new plan"},
        execute=lambda plan: calls.append("execute") or "draft",
        verify=lambda candidate, plan: calls.append("verify") or {
            "passed": True, "feedback": ""
        },
        improve=lambda candidate, feedback: calls.append("improve") or candidate + "-improved",
        deliver=lambda candidate: calls.append("deliver") or {"artifact": candidate},
        learn=lambda record: calls.append("learn"),
        checkpoint_store=store,
    ).run(request, workflow_id=workflow_id, checkpoint_identity=identity)
    return result, calls


class SQLiteWorkflowRecoveryReconciliationTests(unittest.TestCase):
    def _blocked_case(self, **seed_options):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.sqlite3")
            workflow_id = "recovery-" + uuid.uuid4().hex
            request, identity = seed_completed_plan(
                store, workflow_id, task_id="task-" + uuid.uuid4().hex, **seed_options
            )
            result, calls = resume_with_observation(store, workflow_id, request, identity)
            return result, calls

    def test_completed_stage_replay_blocks_when_linked_task_is_missing(self):
        result, calls = self._blocked_case(create_task=False)
        self.assertEqual(result.status, "blocked_execution")
        self.assertIn("missing task record", result.error)
        self.assertEqual(calls, [])

    def test_completed_stage_replay_blocks_when_linked_task_is_not_completed(self):
        result, calls = self._blocked_case(task_status="running")
        self.assertEqual(result.status, "blocked_execution")
        self.assertIn("not completed", result.error)
        self.assertEqual(calls, [])

    def test_completed_stage_replay_blocks_when_idempotency_claim_is_still_running(self):
        result, calls = self._blocked_case(
            idempotency_key="recovery-running-" + uuid.uuid4().hex,
            claim_state="running",
        )
        self.assertEqual(result.status, "blocked_execution")
        self.assertIn("idempotency claim is not completed", result.error)
        self.assertEqual(calls, [])

    def test_completed_stage_replay_blocks_when_idempotency_claim_belongs_to_another_task(self):
        result, calls = self._blocked_case(
            idempotency_key="recovery-owner-" + uuid.uuid4().hex,
            claim_task_id="different-task-" + uuid.uuid4().hex,
        )
        self.assertEqual(result.status, "blocked_execution")
        self.assertIn("same task", result.error)
        self.assertEqual(calls, [])

    def test_completed_stage_replay_blocks_when_idempotency_request_hash_differs(self):
        result, calls = self._blocked_case(
            idempotency_key="recovery-hash-" + uuid.uuid4().hex,
            claim_hash_mismatch=True,
        )
        self.assertEqual(result.status, "blocked_execution")
        self.assertIn("request hash", result.error)
        self.assertEqual(calls, [])

    def test_completed_stage_replay_blocks_when_idempotency_result_differs(self):
        result, calls = self._blocked_case(
            idempotency_key="recovery-result-" + uuid.uuid4().hex,
            claim_result_override={"task_id": "different-result-task", "status": "completed"},
        )
        self.assertEqual(result.status, "blocked_execution")
        self.assertIn("result does not match", result.error)
        self.assertEqual(calls, [])

    def test_completed_stage_replay_blocks_privileged_task_without_durable_approval_link(self):
        result, calls = self._blocked_case(required_permissions=("publish",))
        self.assertEqual(result.status, "blocked_execution")
        self.assertIn("human review is required", result.error)
        self.assertEqual(calls, [])

    def test_completed_stage_replays_when_task_and_idempotency_claim_match(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.sqlite3")
            workflow_id = "recovery-valid-" + uuid.uuid4().hex
            key = "recovery-valid-key-" + uuid.uuid4().hex
            request, identity = seed_completed_plan(
                store,
                workflow_id,
                task_id="task-" + uuid.uuid4().hex,
                idempotency_key=key,
            )
            claim = store.get_idempotency_claim(key)
            self.assertEqual(claim["state"], "completed")
            result, calls = resume_with_observation(store, workflow_id, request, identity)
            self.assertEqual(result.status, "delivered")
            self.assertTrue(result.delivered)
            self.assertEqual(calls.count("plan"), 0)
            self.assertEqual(calls.count("execute"), 1)
            self.assertEqual(calls.count("deliver"), 1)
            self.assertEqual(calls.count("learn"), 1)


POSTGRES_DSN = os.getenv("TEST_POSTGRES_DSN")


@unittest.skipUnless(
    POSTGRES_DSN,
    "TEST_POSTGRES_DSN is only provided by the ephemeral CI PostgreSQL service",
)
class PostgresWorkflowRecoveryLookupTests(unittest.TestCase):
    def test_idempotency_claim_lookup_decodes_completed_result(self):
        store = PostgresStateStore(POSTGRES_DSN)
        task_id = "recovery-" + uuid.uuid4().hex
        key = "recovery-key-" + uuid.uuid4().hex
        request = TaskRequest.create(
            "orchestrator",
            "PostgreSQL recovery lookup fixture",
            task_id=task_id,
            inputs={"fixture": True},
            idempotency_key=key,
            source_refs=("fixture",),
            provider_route="fixture",
        )
        store.enqueue(request)
        payload = json.loads(store.get_task(task_id)["payload_json"])
        request_hash = WorkflowRunner._task_request_hash(payload)
        result = {"task_id": task_id, "status": "completed"}
        store.claim_idempotency(key, request_hash, task_id)
        store.mark_task(task_id, "completed", result)
        self.assertTrue(store.complete_idempotency(key, task_id, result))

        claim = store.get_idempotency_claim(key)
        self.assertEqual(claim["task_id"], task_id)
        self.assertEqual(claim["state"], "completed")
        self.assertEqual(claim["request_hash"], request_hash)
        self.assertEqual(claim["result"], result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
