from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from unexpected_runtime.storage import StateStore
from unexpected_runtime.workflow import WorkflowRunner


ROOT = Path(__file__).resolve().parents[1]


class SQLiteWorkflowProcessTerminationTests(unittest.TestCase):
    def test_abrupt_process_exit_leaves_started_stage_blocked_after_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "workflow.sqlite3"
            marker_path = Path(directory) / "stage-entered.txt"
            workflow_id = "process-termination-fixture"
            request = {"objective": "prove interrupted stage is not replayed"}
            identity = {"request": request, "provider_route": "fixture"}

            child_script = r"""
import os
import sys
from pathlib import Path

from unexpected_runtime.storage import StateStore
from unexpected_runtime.workflow import WorkflowRunner

database_path, marker_path = sys.argv[1], sys.argv[2]
store = StateStore(database_path)
request = {"objective": "prove interrupted stage is not replayed"}
identity = {"request": request, "provider_route": "fixture"}

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
runner.run(
    request,
    workflow_id="process-termination-fixture",
    checkpoint_identity=identity,
)
os._exit(74)
"""
            child_env = {
                key: os.environ[key]
                for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
                if key in os.environ
            }
            inherited_pythonpath = child_env.get("PYTHONPATH", "")
            child_env["PYTHONPATH"] = os.pathsep.join(
                item for item in (str(ROOT), inherited_pythonpath) if item
            )
            child_env["PYTHONIOENCODING"] = "utf-8"
            child = subprocess.run(
                [sys.executable, "-c", child_script, str(database_path), str(marker_path)],
                cwd=ROOT,
                env=child_env,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            self.assertEqual(
                child.returncode,
                73,
                msg=f"child process did not exit at the intended interruption point: "
                    f"stdout={child.stdout!r} stderr={child.stderr!r}",
            )
            self.assertEqual(marker_path.read_text(encoding="utf-8"), "stage callback entered")

            # Opening a new store in the parent process proves the checkpoint was committed
            # before the child was terminated, rather than merely retained in process memory.
            store = StateStore(database_path)
            checkpoint_before = store.get_workflow_checkpoint(workflow_id)
            stages_before = store.list_workflow_stages(workflow_id)
            self.assertIsNotNone(checkpoint_before)
            self.assertEqual(checkpoint_before["status"], "running")
            self.assertEqual(len(stages_before), 1)
            self.assertEqual(stages_before[0]["stage_key"], "0001:plan")
            self.assertEqual(stages_before[0]["status"], "started")
            original_attempt_token = stages_before[0]["attempt_token"]

            calls = []

            def observed_plan(*_args):
                calls.append("plan")
                return {"text": "must remain blocked"}

            runner = WorkflowRunner(
                plan=observed_plan,
                execute=lambda *_args: calls.append("execute"),
                verify=lambda *_args: calls.append("verify") or {"passed": True, "feedback": ""},
                improve=lambda *_args: calls.append("improve"),
                deliver=lambda *_args: calls.append("deliver"),
                learn=lambda *_args: calls.append("learn"),
                checkpoint_store=store,
            )
            result = runner.run(
                request,
                workflow_id=workflow_id,
                checkpoint_identity=identity,
            )

            self.assertEqual(result.status, "blocked_execution")
            self.assertIn("already marked started", result.error or "")
            self.assertEqual(calls, [])
            checkpoint_after = store.get_workflow_checkpoint(workflow_id)
            stages_after = store.list_workflow_stages(workflow_id)
            self.assertEqual(checkpoint_after["status"], "running")
            self.assertEqual(checkpoint_after["revision"], checkpoint_before["revision"])
            self.assertEqual(stages_after[0]["status"], "started")
            self.assertEqual(stages_after[0]["attempt_token"], original_attempt_token)


if __name__ == "__main__":
    unittest.main(verbosity=2)
