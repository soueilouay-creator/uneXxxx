from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from unexpected_runtime.storage import StateStore
from unexpected_runtime.workflow import WorkflowRunner


class WorkflowApprovalPauseResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = StateStore(Path(self.temp.name) / "state.sqlite3")
        self.workflow_id = "workflow-approval-pause"
        self.request = {"objective": "prepare a protected stage before execution"}
        self.identity = {"request": self.request, "route": "test-fixture"}
        self.preparations, self.executions, self.completions, self.calls = [], [], [], []
        self.consumed_bindings = {}

    def tearDown(self):
        self.temp.cleanup()

    def runner(self, approvals=None, request=None):
        request = self.request if request is None else request
        approvals = approvals or {}

        def prepare(wf_id, stage_key, stage_hash, args, permission):
            self.preparations.append((wf_id, stage_key, stage_hash, permission))
            execution_id = "execution:" + wf_id + ":" + stage_key
            task_id = "task:" + wf_id + ":" + stage_key
            action_digest = "a" * 64
            self.store.create_approval_execution_intent(
                execution_id, task_id, "b" * 64, action_digest, permission, wf_id, stage_key
            )
            self.store.transition_approval_execution_intent(execution_id, "prepared", "awaiting_approval", 0)
            return {
                "execution_id": execution_id, "task_id": task_id,
                "action_digest": action_digest, "permission": permission,
                "action_details": {"execution_binding": {
                    "execution_id": execution_id, "task_id": task_id,
                    "workflow_id": wf_id, "stage_key": stage_key,
                }},
            }

        def execute(wf_id, stage_key, callback, args, intent, approval):
            self.executions.append((wf_id, stage_key, intent["execution_id"], intent["task_id"]))
            expected_binding = {
                "workflow_id": wf_id, "stage_key": stage_key,
                "execution_id": intent["execution_id"], "task_id": intent["task_id"],
                "action_digest": intent["action_digest"], "permission": intent["permission"],
            }
            if self.consumed_bindings.get(approval.approval_id) != expected_binding:
                raise PermissionError("approval binding does not match the prepared workflow stage")
            return callback(*args)

        def complete(wf_id, stage_key, intent, approval, value):
            self.completions.append((wf_id, stage_key, intent["execution_id"], approval.approval_id))
            current = self.store.get_workflow_stage_approval_intent(wf_id, stage_key)
            self.assertEqual((current["execution_id"], current["task_id"]),
                             (intent["execution_id"], intent["task_id"]))
            for expected, target in (("awaiting_approval", "approved"),
                                     ("approved", "enqueued"), ("enqueued", "completed")):
                current = self.store.get_workflow_stage_approval_intent(wf_id, stage_key)
                if current["state"] == expected:
                    self.assertTrue(self.store.transition_workflow_stage_approval_intent(
                        wf_id, stage_key, expected, target, current["revision"],
                        approval.approval_id if target == "approved" else None))
            return self.store.get_workflow_stage_approval_intent(wf_id, stage_key)["state"] == "completed"

        def plan(req, feedback):
            self.calls.append("plan")
            return {"request": req, "text": "prepared plan"}

        def execute_stage(plan_value):
            self.calls.append("execute")
            return {"text": "completed work"}

        def verify(candidate, plan_value):
            self.calls.append("verify")
            return {"passed": True, "feedback": ""}

        def improve(candidate, feedback):
            self.calls.append("improve")
            return candidate

        def deliver(candidate):
            self.calls.append("deliver")
            return {"artifact": candidate}

        def learn(record):
            self.calls.append("learn")

        return WorkflowRunner(
            plan=plan, execute=execute_stage, verify=verify, improve=improve,
            deliver=deliver, learn=learn, max_corrections=0, max_improvements=1,
            checkpoint_store=self.store, stage_approval_permissions={"plan": "publish"},
            stage_approvals=approvals, prepare_stage_approval=prepare,
            execute_stage_approval=execute, complete_stage_approval=complete,
        )

    def approval(self, pending):
        approval_id = "github-pr:fixture:approved"
        self.consumed_bindings[approval_id] = {
            key: pending[key] for key in (
                "workflow_id", "stage_key", "execution_id", "task_id", "action_digest", "permission"
            )
        }
        return SimpleNamespace(
            approval_id=approval_id, approver="trusted-reviewer",
            approved_permissions=frozenset({"publish"}), action_digest=pending["action_digest"],
        )

    def test_missing_approval_pauses_before_stage_start_or_callback(self):
        result = self.runner().run(self.request, workflow_id=self.workflow_id,
                                   checkpoint_identity=self.identity)
        self.assertEqual(result.status, "waiting_approval")
        self.assertEqual(self.calls, [])
        pending = result.to_dict().get("pending_approval")
        self.assertIsInstance(pending, dict)
        self.assertEqual((pending["workflow_id"], pending["stage_key"], pending["permission"]),
                         (self.workflow_id, "0001:plan", "publish"))
        self.assertEqual(self.store.get_workflow_checkpoint(self.workflow_id)["status"], "running")
        self.assertEqual(self.store.list_workflow_stages(self.workflow_id), [])
        stage_intent = self.store.get_workflow_stage_approval_intent(self.workflow_id, "0001:plan")
        self.assertEqual(stage_intent["state"], "awaiting_approval")
        self.assertEqual(stage_intent["action_digest"], pending["action_digest"])

    def test_same_workflow_and_stage_resume_the_same_prepared_task(self):
        first = self.runner().run(self.request, workflow_id=self.workflow_id,
                                  checkpoint_identity=self.identity)
        pending = first.to_dict()["pending_approval"]
        result = self.runner({"0001:plan": self.approval(pending)}).run(
            self.request, workflow_id=self.workflow_id, checkpoint_identity=self.identity)
        self.assertEqual(result.status, "delivered")
        self.assertEqual(len(self.preparations), 1)
        self.assertEqual(len(self.executions), 1)
        self.assertEqual(self.executions[0][2:], (pending["execution_id"], pending["task_id"]))
        self.assertEqual(self.store.get_workflow_stage_approval_intent(
            self.workflow_id, "0001:plan")["state"], "completed")
        self.assertEqual(self.store.get_workflow_checkpoint(self.workflow_id)["status"], "completed")
        self.assertEqual(self.calls.count("plan"), 1)

    def test_changed_stage_request_is_blocked_without_repreparing(self):
        self.runner().run(self.request, workflow_id=self.workflow_id,
                          checkpoint_identity=self.identity)
        changed = {"objective": "different protected stage request"}
        result = self.runner(request=changed).run(
            changed, workflow_id=self.workflow_id, checkpoint_identity=self.identity)
        self.assertEqual(result.status, "blocked_execution")
        self.assertEqual(len(self.preparations), 1)
        self.assertEqual(self.calls, [])

    def test_approval_from_another_workflow_and_wrong_stage_key_are_not_reused(self):
        first = self.runner().run(self.request, workflow_id=self.workflow_id,
                                  checkpoint_identity=self.identity)
        pending = first.to_dict()["pending_approval"]
        other_id = "different-workflow"
        other = self.runner({"0001:plan": self.approval(pending["action_digest"])}).run(
            self.request, workflow_id=other_id, checkpoint_identity=self.identity)
        self.assertEqual(other.status, "blocked_execution")
        self.assertEqual(self.calls, [])
        wrong_stage = self.runner({"0002:execute": self.approval(pending["action_digest"])}).run(
            self.request, workflow_id=self.workflow_id, checkpoint_identity=self.identity)
        self.assertEqual(wrong_stage.status, "waiting_approval")
        self.assertEqual(self.calls, [])

    def test_wrong_digest_and_ambiguous_started_stage_do_not_execute(self):
        first = self.runner().run(self.request, workflow_id=self.workflow_id,
                                  checkpoint_identity=self.identity)
        pending = first.to_dict()["pending_approval"]
        wrong = self.runner({"0001:plan": self.approval({**pending, "action_digest": "b" * 64})}).run(
            self.request, workflow_id=self.workflow_id, checkpoint_identity=self.identity)
        self.assertEqual(wrong.status, "blocked_execution")
        self.assertEqual(self.store.list_workflow_stages(self.workflow_id), [])
        self.assertEqual(self.calls, [])

        other_id = "ambiguous-workflow"
        self.store.create_workflow_checkpoint(
            other_id, WorkflowRunner._canonical_hash(self.identity), 1,
            {"request": self.identity, "completed_stages": []})
        self.store.begin_workflow_stage(
            other_id, "0001:plan", 1,
            WorkflowRunner._stage_hash("0001:plan", (self.request, None)), "abandoned")
        blocked = self.runner().run(self.request, workflow_id=other_id,
                                    checkpoint_identity=self.identity)
        self.assertEqual(blocked.status, "blocked_execution")
        self.assertIn("already marked started", blocked.error or "")
        self.assertIsNone(self.store.get_workflow_stage_approval_intent(other_id, "0001:plan"))
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
