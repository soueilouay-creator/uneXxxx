from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from pathlib import Path

from unexpected_runtime.models import TaskRequest
from unexpected_runtime.postgres_storage import PostgresStateStore
from unexpected_runtime.workflow import WorkflowRunner


ROOT = Path(__file__).resolve().parents[1]


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

    def test_abrupt_process_exit_keeps_started_postgres_stage_blocked_after_reopen(self):
        workflow_id = "postgres-process-termination-" + uuid.uuid4().hex
        request = {"objective": "prove interrupted PostgreSQL stage is not replayed"}
        identity = {"request": request, "provider_route": "fixture"}
        with tempfile.TemporaryDirectory() as directory:
            marker_path = Path(directory) / "stage-entered.txt"
            child_script = r"""
import os
import sys
from pathlib import Path
from unexpected_runtime.postgres_storage import PostgresStateStore
from unexpected_runtime.workflow import WorkflowRunner

marker_path = sys.argv[1]
workflow_id = os.environ["TEST_WORKFLOW_ID"]
request = {"objective": "prove interrupted PostgreSQL stage is not replayed"}
identity = {"request": request, "provider_route": "fixture"}
store = PostgresStateStore(os.environ["TEST_POSTGRES_DSN"])

def terminate_after_stage_claim(*_args):
    Path(marker_path).write_text("stage callback entered", encoding="utf-8")
    os._exit(73)

runner = WorkflowRunner(
    plan=terminate_after_stage_claim,
    execute=lambda *_args: {"text": "must not execute"},
    verify=lambda *_args: {"passed": True, "feedback": ""},
    improve=lambda candidate, _feedback: candidate,
    deliver=lambda candidate: candidate,
    learn=lambda _record: None,
    checkpoint_store=store,
)
runner.run(request, workflow_id=workflow_id, checkpoint_identity=identity)
os._exit(74)
"""
            child_env = {
                key: os.environ[key]
                for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
                if key in os.environ
            }
            child_env["TEST_POSTGRES_DSN"] = self.dsn
            child_env["TEST_WORKFLOW_ID"] = workflow_id
            child_env["PYTHONPATH"] = os.pathsep.join(
                item for item in (str(ROOT), os.environ.get("PYTHONPATH", "")) if item
            )
            child_env["PYTHONIOENCODING"] = "utf-8"
            child = subprocess.run(
                [sys.executable, "-c", child_script, str(marker_path)],
                cwd=ROOT,
                env=child_env,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            self.assertEqual(
                child.returncode, 73,
                msg=f"child did not stop at the intended stage: stdout={child.stdout!r} stderr={child.stderr!r}",
            )
            self.assertEqual(marker_path.read_text(encoding="utf-8"), "stage callback entered")

        reopened = PostgresStateStore(self.dsn)
        checkpoint_before = reopened.get_workflow_checkpoint(workflow_id)
        stages_before = reopened.list_workflow_stages(workflow_id)
        self.assertIsNotNone(checkpoint_before)
        self.assertEqual(checkpoint_before["status"], "running")
        self.assertEqual(len(stages_before), 1)
        self.assertEqual(stages_before[0]["stage_key"], "0001:plan")
        self.assertEqual(stages_before[0]["status"], "started")
        original_attempt_token = stages_before[0]["attempt_token"]

        calls = []
        runner = WorkflowRunner(
            plan=lambda *_args: calls.append("plan") or {"text": "must remain blocked"},
            execute=lambda *_args: calls.append("execute"),
            verify=lambda *_args: calls.append("verify") or {"passed": True, "feedback": ""},
            improve=lambda *_args: calls.append("improve"),
            deliver=lambda *_args: calls.append("deliver"),
            learn=lambda *_args: calls.append("learn"),
            checkpoint_store=reopened,
        )
        result = runner.run(request, workflow_id=workflow_id, checkpoint_identity=identity)
        self.assertEqual(result.status, "blocked_execution")
        self.assertIn("already marked started", result.error or "")
        self.assertEqual(calls, [])
        checkpoint_after = reopened.get_workflow_checkpoint(workflow_id)
        stages_after = reopened.list_workflow_stages(workflow_id)
        self.assertEqual(checkpoint_after["status"], "running")
        self.assertEqual(checkpoint_after["revision"], checkpoint_before["revision"])
        self.assertEqual(stages_after[0]["status"], "started")
        self.assertEqual(stages_after[0]["attempt_token"], original_attempt_token)

    def test_generic_enqueue_preserves_optional_execution_binding_fields(self):
        request = TaskRequest.create(
            "orchestrator", "preserve optional approval binding metadata",
            required_permissions=(self.permission,),
            execution_id="generic-execution-" + uuid.uuid4().hex,
            approval_reference="generic-approval-reference",
        )
        self.store.enqueue(request)
        task = self.store.get_task(request.task_id)
        payload = json.loads(task["payload_json"])
        self.assertEqual(payload["execution_id"], request.execution_id)
        self.assertEqual(payload["approval_reference"], request.approval_reference)

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
        task_payload = json.loads(task["payload_json"])
        self.assertEqual(task_payload["execution_id"], self.execution_id)
        self.assertEqual(task_payload["approval_reference"], "approval-recovery")

        # The CI PostgreSQL database is shared by test cases. Make this fixture
        # the oldest queued row so run_queued cannot accidentally claim a
        # leftover task from an earlier test and give a misleading result.
        with self.store._session() as connection:
            connection.execute(
                "UPDATE tasks SET created_at=%s WHERE task_id=%s",
                (-1.0, self.task_id),
            )

        child_script = r"""
import json
import os
from unexpected_runtime.coordinator import Coordinator
from unexpected_runtime.postgres_storage import PostgresStateStore

store = PostgresStateStore(os.environ["TEST_POSTGRES_DSN"])
worker = Coordinator.__new__(Coordinator)
worker.store = store
results = worker.run_queued(max_tasks=1)
print(json.dumps([{"status": result.status, "error": result.error} for result in results]))
"""
        child_env = {
            key: os.environ[key]
            for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
            if key in os.environ
        }
        child_env["TEST_POSTGRES_DSN"] = self.dsn
        child_env["PYTHONPATH"] = os.pathsep.join(
            item for item in (str(ROOT), os.environ.get("PYTHONPATH", "")) if item
        )
        child_env["PYTHONIOENCODING"] = "utf-8"
        child = subprocess.run(
            [sys.executable, "-c", child_script],
            cwd=ROOT,
            env=child_env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(
            child.returncode, 0,
            msg=f"recovery worker failed: stdout={child.stdout!r} stderr={child.stderr!r}",
        )
        child_results = json.loads(child.stdout.strip().splitlines()[-1])
        self.assertEqual(len(child_results), 1)
        self.assertEqual(child_results[0]["status"], "failed")
        self.assertIn("automatic replay is forbidden", child_results[0]["error"])

        recovered = PostgresStateStore(self.dsn)
        self.assertEqual(recovered.get_task(self.task_id)["status"], "failed")
        self.assertEqual(recovered.get_approval_execution_intent(self.execution_id)["state"], "blocked")
        self.assertEqual(recovered.get_workflow_stage_approval_intent(
            self.workflow_id, self.stage_key
        )["state"], "blocked")


    def test_postgres_pause_approval_resume_completes_same_prepared_stage(self):
        workflow_id = "postgres-pause-resume-" + uuid.uuid4().hex
        request = {"objective": "resume only the exact prepared PostgreSQL stage"}
        identity = {"request": request, "provider_route": "postgres-fixture"}
        permission = "publish"
        preparations = []
        calls = []
        approval_id = "github-pr:fixture:" + uuid.uuid4().hex[:16]

        def build_runner(store, approvals=None):
            def prepare(wf_id, stage_key, stage_hash, args, requested_permission):
                self.assertEqual((wf_id, stage_key, requested_permission),
                                 (workflow_id, "0001:plan", permission))
                execution_id = "execution:" + uuid.uuid4().hex
                task_id = "task:" + uuid.uuid4().hex
                action_digest = hashlib.sha256(
                    (wf_id + stage_key + stage_hash + execution_id + task_id).encode("utf-8")
                ).hexdigest()
                prepared = store.create_approval_execution_intent(
                    execution_id, task_id, stage_hash, action_digest, permission, wf_id, stage_key
                )
                self.assertEqual(prepared["state"], "prepared")
                self.assertTrue(store.transition_approval_execution_intent(
                    execution_id, "prepared", "awaiting_approval", 0
                ))
                preparations.append((execution_id, task_id, action_digest, stage_hash))
                return {
                    "execution_id": execution_id, "task_id": task_id,
                    "action_digest": action_digest, "permission": permission,
                    "action_details": {"workflow_id": wf_id, "stage_key": stage_key},
                }

            def execute_approved(wf_id, stage_key, callback, args, intent, approval):
                binding = ApprovalExecutionBinding(
                    execution_id=intent["execution_id"], task_id=intent["task_id"],
                    workflow_id=wf_id, stage_key=stage_key,
                )
                ledger = PostgresApprovalLedger(self.dsn)
                self.assertTrue(ledger.consume_once_bound(
                    approval.approval_id, intent["action_digest"], permission, binding
                ))
                readback = ledger.get_consumed_binding(approval.approval_id)
                self.assertIsNotNone(readback)
                expected = {
                    "action_digest": intent["action_digest"], "permission": permission,
                    "execution_id": intent["execution_id"], "task_id": intent["task_id"],
                    "workflow_id": wf_id, "stage_key": stage_key,
                }
                for key, value in expected.items():
                    self.assertEqual(readback[key], value)
                execution = store.get_approval_execution_intent(intent["execution_id"])
                stage = store.get_workflow_stage_approval_intent(wf_id, stage_key)
                self.assertEqual((execution["state"], execution["revision"]), ("awaiting_approval", 1))
                self.assertEqual((stage["state"], stage["revision"]), ("awaiting_approval", 0))
                self.assertTrue(store.transition_approval_execution_intent(
                    intent["execution_id"], "awaiting_approval", "approved", 1
                ))
                self.assertTrue(store.transition_workflow_stage_approval_intent(
                    wf_id, stage_key, "awaiting_approval", "approved", 0, approval.approval_id
                ))
                self.assertTrue(store.transition_approval_execution_intent(
                    intent["execution_id"], "approved", "enqueued", 2
                ))
                self.assertTrue(store.transition_workflow_stage_approval_intent(
                    wf_id, stage_key, "approved", "enqueued", 1
                ))
                return callback(*args)

            def complete_approved(wf_id, stage_key, intent, approval, value):
                execution = store.get_approval_execution_intent(intent["execution_id"])
                stage = store.get_workflow_stage_approval_intent(wf_id, stage_key)
                if (not execution or not stage or execution["state"] != "enqueued"
                        or stage["state"] != "enqueued" or stage["approval_id"] != approval.approval_id
                        or execution["task_id"] != intent["task_id"] or stage["task_id"] != intent["task_id"]):
                    return False
                execution_done = store.transition_approval_execution_intent(
                    intent["execution_id"], "enqueued", "completed", int(execution["revision"])
                )
                stage_done = store.transition_workflow_stage_approval_intent(
                    wf_id, stage_key, "enqueued", "completed", int(stage["revision"])
                )
                return bool(execution_done and stage_done)

            def plan(req, feedback):
                calls.append("plan")
                return {"request": req, "text": "prepared plan"}

            def execute_stage(plan_value):
                calls.append("execute")
                return {"text": "completed work"}

            def verify(candidate, plan_value):
                calls.append("verify")
                return {"passed": True, "feedback": ""}

            def improve(candidate, feedback):
                calls.append("improve")
                return candidate

            def deliver(candidate):
                calls.append("deliver")
                return {"artifact": candidate}

            def learn(record):
                calls.append("learn")

            return WorkflowRunner(
                plan=plan, execute=execute_stage, verify=verify, improve=improve,
                deliver=deliver, learn=learn, max_corrections=0, max_improvements=1,
                checkpoint_store=store, stage_approval_permissions={"plan": permission},
                stage_approvals=approvals or {}, prepare_stage_approval=prepare,
                execute_stage_approval=execute_approved,
                complete_stage_approval=complete_approved,
            )

        first = build_runner(self.store).run(
            request, workflow_id=workflow_id, checkpoint_identity=identity
        )
        self.assertEqual(first.status, "waiting_approval")
        self.assertEqual(calls, [])
        pending = first.to_dict().get("pending_approval")
        self.assertIsInstance(pending, dict)
        self.assertEqual(self.store.list_workflow_stages(workflow_id), [])
        self.assertEqual(
            self.store.get_workflow_stage_approval_intent(workflow_id, "0001:plan")["state"],
            "awaiting_approval",
        )
        self.assertEqual(len(preparations), 1)

        approval = ApprovalContext(
            approval_id=approval_id, approver="trusted-reviewer",
            approved_permissions=frozenset({permission}),
            rationale="Isolated PostgreSQL CI approval fixture",
            action_digest=pending["action_digest"],
        )
        reopened = PostgresStateStore(self.dsn)
        resumed = build_runner(reopened, {"0001:plan": approval}).run(
            request, workflow_id=workflow_id, checkpoint_identity=identity
        )
        self.assertEqual(resumed.status, "delivered")
        self.assertEqual(calls.count("plan"), 1)
        self.assertEqual(len(preparations), 1)
        final_stage = reopened.get_workflow_stage_approval_intent(workflow_id, "0001:plan")
        final_execution = reopened.get_approval_execution_intent(preparations[0][0])
        self.assertEqual(final_stage["state"], "completed")
        self.assertEqual(final_stage["approval_id"], approval_id)
        self.assertEqual(final_execution["state"], "completed")
        self.assertEqual(reopened.get_workflow_checkpoint(workflow_id)["status"], "completed")
        binding = PostgresApprovalLedger(self.dsn).get_consumed_binding(approval_id)
        self.assertEqual(binding["task_id"], preparations[0][1])
        self.assertEqual(binding["execution_id"], preparations[0][0])
        self.assertEqual(binding["workflow_id"], workflow_id)
        self.assertEqual(binding["stage_key"], "0001:plan")


if __name__ == "__main__":
    unittest.main(verbosity=2)
