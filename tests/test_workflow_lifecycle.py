import unittest
import tempfile
from pathlib import Path

from unexpected_runtime.workflow import WorkflowRunner
from unexpected_runtime.coordinator import Coordinator
from unexpected_runtime.providers import DeterministicMockProvider

ROOT = Path(__file__).resolve().parents[1]


class WorkflowRunnerTests(unittest.TestCase):
    def test_delivers_only_after_verify_and_improve(self):
        events = []
        runner = WorkflowRunner(
            plan=lambda request, feedback=None: events.append("plan") or {"steps": ["work"]},
            execute=lambda plan: events.append("execute") or "draft",
            verify=lambda result, plan: events.append("verify") or {"passed": True, "feedback": ""},
            improve=lambda result, feedback: events.append("improve") or result + "-improved",
            deliver=lambda result: events.append("deliver") or {"artifact": result},
            learn=lambda record: events.append("learn"),
        )
        result = runner.run({"objective": "make a report"})
        self.assertEqual(events, ["plan", "execute", "verify", "improve", "verify", "deliver", "learn"])
        self.assertTrue(result.delivered)
        self.assertEqual(result.delivery, {"artifact": "draft-improved"})
        self.assertEqual(result.status, "delivered")

    def test_failed_verification_replans_before_retry_and_never_delivers_failed_output(self):
        events = []
        checks = iter([
            {"passed": False, "feedback": "missing source evidence"},
            {"passed": True, "feedback": ""},
            {"passed": True, "feedback": "final output is ready"},
        ])
        def plan(request, feedback=None):
            events.append(("plan", feedback))
            return {"feedback": feedback}
        runner = WorkflowRunner(
            plan=plan,
            execute=lambda plan: events.append("execute") or "verified-draft",
            verify=lambda result, plan: events.append("verify") or next(checks),
            improve=lambda result, feedback: events.append("improve") or result + "-fixed",
            deliver=lambda result: events.append("deliver") or result,
            learn=lambda record: events.append("learn"),
            max_corrections=1,
        )
        result = runner.run({"objective": "research"})
        self.assertEqual(result.status, "delivered")
        self.assertEqual(events[0], ("plan", None))
        self.assertEqual(events[3], ("plan", "missing source evidence"))
        self.assertEqual(result.verified_output, "verified-draft-fixed")
        self.assertEqual(result.delivery, "verified-draft-fixed")
        self.assertEqual(events.count("deliver"), 1)
        self.assertEqual(result.corrections, 1)

    def test_exhausted_verification_blocks_delivery_but_still_learns(self):
        events = []
        runner = WorkflowRunner(
            plan=lambda request, feedback=None: {},
            execute=lambda plan: "draft",
            verify=lambda result, plan: {"passed": False, "feedback": "not ready"},
            improve=lambda result, feedback: self.fail("must not improve unverified output"),
            deliver=lambda result: self.fail("must not deliver unverified output"),
            learn=lambda record: events.append(record),
            max_corrections=0,
        )
        result = runner.run({"objective": "unsafe task"})
        self.assertEqual(result.status, "blocked_verification")
        self.assertFalse(result.delivered)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["verification_history"][-1]["passed"], False)



    def test_exhausted_improvement_rounds_replan_when_correction_budget_remains(self):
        plans = []
        executions = []
        checks = iter([
            {'passed': True, 'feedback': 'Initial candidate is sound.'},
            {'passed': False, 'feedback': 'The first revision is still incomplete.'},
            {'passed': True, 'feedback': 'Second execution meets the criteria.'},
            {'passed': True, 'feedback': 'The improved second execution passes.'},
        ])

        def plan(request, feedback=None):
            plans.append(feedback)
            return {'iteration': len(plans)}

        def execute(current_plan):
            executions.append(current_plan['iteration'])
            return 'draft-' + str(current_plan['iteration'])

        runner = WorkflowRunner(
            plan=plan, execute=execute,
            verify=lambda candidate, current_plan: next(checks),
            improve=lambda candidate, feedback: candidate + '-improved',
            deliver=lambda candidate: candidate, learn=lambda record: None,
            max_corrections=1, max_improvements=1,
        )
        result = runner.run({'objective': 'prepare a report'})

        self.assertEqual(result.status, 'delivered')
        self.assertEqual(result.corrections, 1)
        self.assertEqual(result.improvements, 2)
        self.assertEqual(plans[0], None)
        self.assertIn('Post-improvement verification failed', plans[1])
        self.assertEqual(executions, [1, 2])
        self.assertEqual(result.verified_output, 'draft-2-improved')

    def test_improvement_budget_must_be_a_bounded_integer(self):
        kwargs = dict(
            plan=lambda request, feedback=None: {},
            execute=lambda plan: "draft",
            verify=lambda candidate, plan: {"passed": True, "feedback": ""},
            improve=lambda candidate, feedback: candidate,
            deliver=lambda candidate: candidate,
            learn=lambda record: None,
        )
        for invalid in (0, 6, True, 1.5):
            with self.subTest(max_improvements=invalid):
                with self.assertRaises(ValueError):
                    WorkflowRunner(**kwargs, max_improvements=invalid)

    def test_improves_and_reverifies_same_candidate_until_it_passes(self):
        events = []
        checks = iter([
            {"passed": True, "feedback": "Initial candidate meets the baseline."},
            {"passed": False, "feedback": "Add missing evidence and tighten the conclusion."},
            {"passed": True, "feedback": "The revised candidate now meets every criterion."},
        ])

        def improve(candidate, feedback):
            events.append(("improve", candidate, feedback))
            return candidate + "-v" + str(sum(1 for event in events if event[0] == "improve"))

        runner = WorkflowRunner(
            plan=lambda request, feedback=None: events.append("plan") or {"steps": ["work"]},
            execute=lambda plan: events.append("execute") or "draft",
            verify=lambda candidate, plan: events.append(("verify", candidate)) or next(checks),
            improve=improve,
            deliver=lambda candidate: events.append(("deliver", candidate)) or candidate,
            learn=lambda record: events.append(("learn", record)),
            max_improvements=3,
        )
        result = runner.run({"objective": "prepare a sourced report"})

        self.assertEqual(result.status, "delivered")
        self.assertTrue(result.delivered)
        self.assertEqual(result.improvements, 2)
        self.assertEqual(result.to_dict()["improvements"], 2)
        self.assertEqual(result.verified_output, "draft-v1-v2")
        self.assertEqual(result.delivery, "draft-v1-v2")
        self.assertEqual(
            [item["phase"] for item in result.verification_history],
            ["before_improvement", "after_improvement", "after_improvement_2"],
        )
        self.assertEqual([item["passed"] for item in result.verification_history],
                         [True, False, True])
        self.assertEqual([event[1] for event in events if isinstance(event, tuple) and event[0] == "verify"],
                         ["draft", "draft-v1", "draft-v1-v2"])

    def test_exhausted_improvement_budget_blocks_delivery_and_records_count(self):
        events = []
        checks = iter([
            {"passed": True, "feedback": "Initial baseline passed."},
            {"passed": False, "feedback": "Still missing citations."},
            {"passed": False, "feedback": "Citation coverage remains incomplete."},
        ])
        runner = WorkflowRunner(
            plan=lambda request, feedback=None: {},
            execute=lambda plan: "draft",
            verify=lambda candidate, plan: next(checks),
            improve=lambda candidate, feedback: candidate + "-revised",
            deliver=lambda candidate: self.fail("must not deliver after exhausted improvement budget"),
            learn=lambda record: events.append(record),
            max_improvements=2,
            max_corrections=0,
        )
        result = runner.run({"objective": "prepare a sourced report"})

        self.assertEqual(result.status, "blocked_verification")
        self.assertFalse(result.delivered)
        self.assertEqual(result.improvements, 2)
        self.assertEqual(len(result.verification_history), 3)
        self.assertEqual(events[0]["improvements"], 2)


class CheckpointedWorkflowRunnerTests(unittest.TestCase):
    def test_completed_stage_is_replayed_and_remaining_stages_continue(self):
        from unexpected_runtime.storage import StateStore

        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.sqlite3")
            request = {"objective": "resume from a completed plan"}
            identity = {"request": request, "provider_route": "fixture"}
            workflow_id = "resume-completed-plan"
            store.create_workflow_checkpoint(
                workflow_id, WorkflowRunner._canonical_hash(identity), 1,
                {"request": identity, "completed_stages": []},
            )
            stage_key = "0001:plan"
            stage_hash = WorkflowRunner._stage_hash(stage_key, (request, None))
            acquired = store.begin_workflow_stage(
                workflow_id, stage_key, 1, stage_hash, "plan-attempt"
            )
            self.assertTrue(acquired["can_execute"])
            persisted_plan = {"steps": ["persisted plan"]}
            self.assertTrue(store.complete_workflow_stage(
                workflow_id, stage_key, "plan-attempt", "plan-task",
                {"value": persisted_plan},
            ))
            self.assertTrue(store.save_workflow_checkpoint(
                workflow_id, 0, "running", stage_key,
                {"request": identity, "completed_stages": [stage_key]},
            ))

            calls = []
            runner = WorkflowRunner(
                plan=lambda *args: self.fail("completed plan must be restored, not rerun"),
                execute=lambda plan: calls.append("execute") or "draft",
                verify=lambda candidate, plan: calls.append("verify") or {
                    "passed": True, "feedback": ""
                },
                improve=lambda candidate, feedback: calls.append("improve") or candidate + "-improved",
                deliver=lambda candidate: calls.append("deliver") or {"artifact": candidate},
                learn=lambda record: calls.append("learn"),
                checkpoint_store=store,
            )
            result = runner.run(request, workflow_id=workflow_id, checkpoint_identity=identity)
            self.assertEqual(result.status, "delivered")
            self.assertTrue(result.delivered)
            self.assertEqual(result.plan, persisted_plan)
            self.assertEqual(calls.count("execute"), 1)
            self.assertEqual(calls.count("verify"), 2)
            self.assertEqual(calls.count("improve"), 1)
            self.assertEqual(calls.count("deliver"), 1)
            self.assertEqual(calls.count("learn"), 1)
            checkpoint = store.get_workflow_checkpoint(workflow_id)
            self.assertEqual(checkpoint["status"], "completed")
            self.assertEqual(checkpoint["state"]["result"]["status"], "delivered")

            replay_calls = []
            replay = WorkflowRunner(
                plan=lambda *args: replay_calls.append("plan"),
                execute=lambda *args: replay_calls.append("execute"),
                verify=lambda *args: replay_calls.append("verify"),
                improve=lambda *args: replay_calls.append("improve"),
                deliver=lambda *args: replay_calls.append("deliver"),
                learn=lambda *args: replay_calls.append("learn"),
                checkpoint_store=store,
            ).run(request, workflow_id=workflow_id, checkpoint_identity=identity)
            self.assertEqual(replay.status, "delivered")
            self.assertTrue(replay.delivered)
            self.assertEqual(replay_calls, [])

    def test_started_stage_is_never_reexecuted_and_blocks_following_stages(self):
        from unexpected_runtime.storage import StateStore

        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.sqlite3")
            request = {"objective": "do not repeat an ambiguous stage"}
            identity = {"request": request}
            workflow_id = "ambiguous-stage"
            store.create_workflow_checkpoint(
                workflow_id, WorkflowRunner._canonical_hash(identity), 1,
                {"request": identity, "completed_stages": []},
            )
            stage_key = "0001:plan"
            store.begin_workflow_stage(
                workflow_id, stage_key, 1,
                WorkflowRunner._stage_hash(stage_key, (request, None)),
                "abandoned-attempt",
            )
            calls = []
            runner = WorkflowRunner(
                plan=lambda *args: calls.append("plan"),
                execute=lambda *args: calls.append("execute"),
                verify=lambda *args: calls.append("verify"),
                improve=lambda *args: calls.append("improve"),
                deliver=lambda *args: calls.append("deliver"),
                learn=lambda *args: calls.append("learn"),
                checkpoint_store=store,
            )
            result = runner.run(request, workflow_id=workflow_id, checkpoint_identity=identity)
            self.assertEqual(result.status, "blocked_execution")
            self.assertFalse(result.delivered)
            self.assertIn("already marked started", result.error)
            self.assertEqual(calls, [])
            self.assertEqual(store.list_workflow_stages(workflow_id)[0]["status"], "started")
            self.assertEqual(store.get_workflow_checkpoint(workflow_id)["status"], "running")


class CoordinatorLifecycleTests(unittest.TestCase):
    def _coordinator(self, reviewer_verdicts):
        import tempfile
        from pathlib import Path
        from unexpected_runtime.coordinator import Coordinator

        class LifecycleProvider:
            name = "test-lifecycle-provider"
            configured = True
            verified = True
            retry_safe = False
            def __init__(self):
                self.review_calls = 0
            def generate(self, **kwargs):
                agent = kwargs["agent_id"]
                if agent == "project-manager":
                    return "1. Define the task. 2. Produce the requested output. 3. Review it."
                if agent == "code-reviewer":
                    verdict = reviewer_verdicts[self.review_calls]
                    self.review_calls += 1
                    return f"VERDICT: {verdict}" + chr(10) + f"Review evidence for {verdict.lower()}."
                if agent == "research-scout":
                    return "Research deliverable, version " + str(self.review_calls)
                return "Test response."

        temp = tempfile.TemporaryDirectory()
        provider = LifecycleProvider()
        coordinator = Coordinator(manifest_path=Path(__file__).resolve().parents[1] / "agent_manifest.json",
                                  state_dir=temp.name, provider=provider)
        self.addCleanup(temp.cleanup)
        self.addCleanup(coordinator.close)
        return coordinator, provider

    def test_native_lifecycle_routes_through_plan_execute_review_improve_and_learning(self):
        coordinator, provider = self._coordinator(["PASS", "PASS"])
        result = coordinator.run_lifecycle(
            "research-scout", "Research a sample topic", {"scope": "public sources"},
            max_corrections=0,
        )
        self.assertEqual(result.status, "delivered")
        self.assertTrue(result.delivered)
        self.assertEqual(provider.review_calls, 2)
        self.assertEqual([item["phase"] for item in result.verification_history],
                         ["before_improvement", "after_improvement"])
        events = {event["event_type"] for event in coordinator.store.events(100)}
        self.assertIn("outcome_recorded", events)

    def test_native_lifecycle_blocks_delivery_when_improvement_fails_final_review(self):
        coordinator, provider = self._coordinator(["PASS", "FAIL"])
        result = coordinator.run_lifecycle(
            "research-scout", "Research a sample topic", {"scope": "public sources"},
            max_corrections=0,
            max_improvements=1,
        )
        self.assertEqual(result.status, "blocked_verification")
        self.assertFalse(result.delivered)
        self.assertEqual(provider.review_calls, 2)
        self.assertIsNone(result.delivery)
        self.assertIsNone(result.verified_output)
        events = {event["event_type"] for event in coordinator.store.events(100)}
        self.assertIn("outcome_recorded", events)

    def test_native_lifecycle_repeats_improvement_until_review_passes(self):
        coordinator, provider = self._coordinator(["PASS", "FAIL", "PASS"])
        result = coordinator.run_lifecycle(
            "research-scout", "Research a sample topic", {"scope": "public sources"},
            max_corrections=0, max_improvements=2,
        )
        self.assertEqual(result.status, "delivered")
        self.assertEqual(provider.review_calls, 3)
        self.assertEqual(result.improvements, 2)
        self.assertEqual([item["phase"] for item in result.verification_history],
                         ["before_improvement", "after_improvement", "after_improvement_2"])
        self.assertTrue(result.delivered)

    def test_authenticated_http_lifecycle_endpoint_uses_native_workflow(self):
        import json
        import threading
        import urllib.request
        from unexpected_runtime.http_api import create_server

        coordinator, provider = self._coordinator(["PASS", "PASS"])
        token = "t" * 40
        server = create_server(coordinator=coordinator, api_token=token, host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = "http://127.0.0.1:{}/v1/lifecycle".format(server.server_address[1])
            body = json.dumps({
                "agent_id": "research-scout",
                "objective": "Run a safe test workflow",
                "inputs": {"scope": "fixture"},
                "max_corrections": 0,
                "max_improvements": 2,
                "deadline_seconds": 5,
                "workflow_id": "http-lifecycle-checkpoint-fixture",
            }).encode("utf-8")
            request = urllib.request.Request(
                url, data=body,
                headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
                self.assertEqual(response.status, 200)
                self.assertEqual(payload["result"]["status"], "delivered")
                self.assertEqual(payload["result"]["workflow_id"], "http-lifecycle-checkpoint-fixture")
                checkpoint = coordinator.store.get_workflow_checkpoint("http-lifecycle-checkpoint-fixture")
                self.assertEqual(checkpoint["status"], "completed")
            replay_request = urllib.request.Request(
                url, data=body,
                headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(replay_request, timeout=10) as response:
                replay_payload = json.loads(response.read().decode("utf-8"))
                self.assertEqual(response.status, 200)
                self.assertEqual(replay_payload["result"]["status"], "delivered")
                self.assertEqual(replay_payload["result"]["workflow_id"], "http-lifecycle-checkpoint-fixture")
                self.assertEqual(provider.review_calls, 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_authenticated_http_lifecycle_endpoint_rejects_unverified_live_provider(self):
        import json
        import threading
        import urllib.error
        import urllib.request
        from unexpected_runtime.http_api import create_server

        coordinator, provider = self._coordinator(["PASS", "PASS"])
        provider.verified = False
        token = "u" * 40
        server = create_server(coordinator=coordinator, api_token=token,
                               host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = "http://127.0.0.1:{}/v1/lifecycle".format(server.server_address[1])
            body = json.dumps({
                "agent_id": "research-scout",
                "objective": "Reject an unverified live provider",
                "inputs": {},
                "max_corrections": 0,
                "max_improvements": 1,
                "deadline_seconds": 5,
            }).encode("utf-8")
            request = urllib.request.Request(
                url, data=body,
                headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request, timeout=10)
            self.assertEqual(caught.exception.code, 409)
            payload = json.loads(caught.exception.read().decode("utf-8"))
            self.assertIn("Test connection", payload["error"])
            self.assertEqual(provider.review_calls, 0)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_lifecycle_concurrency_guard_preserves_capacity_for_invoke(self):
        import json
        import threading
        import urllib.error
        import urllib.request
        from unexpected_runtime.http_api import create_server

        class Result:
            def __init__(self, status):
                self.status = status
            def to_dict(self):
                return {"status": self.status, "delivered": self.status == "delivered"}

        class BlockingCoordinator:
            max_workers = 2
            provider = type("VerifiedProvider", (), {"name": "test-live-provider", "verified": True})()
            def __init__(self):
                self.started = threading.Event()
                self.release = threading.Event()
            def run_lifecycle(self, *args, **kwargs):
                if self.started.is_set():
                    return Result("delivered")
                self.started.set()
                self.release.wait(timeout=5)
                return Result("delivered")
            def invoke(self, *args, **kwargs):
                return Result("completed")

        coordinator = BlockingCoordinator()
        token = "c" * 40
        server = create_server(coordinator=coordinator, api_token=token,
                               host="127.0.0.1", port=0)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        base_url = "http://127.0.0.1:{}".format(server.server_address[1])

        def post(route):
            payload = {
                "agent_id": "research-scout",
                "objective": "Exercise the worker-capacity guard",
                "inputs": {},
                "deadline_seconds": 5,
            }
            if route == "/v1/lifecycle":
                payload["max_corrections"] = 0
            body = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                base_url + route, data=body,
                headers={"Authorization": "Bearer " + token,
                         "Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=3) as response:
                    return response.status, json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                return exc.code, json.loads(exc.read().decode("utf-8"))

        first_result = []
        lifecycle_thread = threading.Thread(
            target=lambda: first_result.append(post("/v1/lifecycle")), daemon=True
        )
        lifecycle_thread.start()
        try:
            self.assertTrue(coordinator.started.wait(timeout=2))
            busy_status, busy_payload = post("/v1/lifecycle")
            self.assertEqual(busy_status, 503, busy_payload)
            invoke_status, invoke_payload = post("/v1/invoke")
            self.assertEqual(invoke_status, 200, invoke_payload)
        finally:
            coordinator.release.set()
            lifecycle_thread.join(timeout=4)
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=2)

        self.assertEqual(len(first_result), 1)
        self.assertEqual(first_result[0][0], 200)

    def test_default_deterministic_mock_cannot_pass_verification_gate(self):
        import tempfile
        from pathlib import Path
        from unexpected_runtime.coordinator import Coordinator
        from unexpected_runtime.providers import DeterministicMockProvider

        with tempfile.TemporaryDirectory() as state:
            coordinator = Coordinator(
                manifest_path=Path(__file__).resolve().parents[1] / "agent_manifest.json",
                state_dir=state, provider=DeterministicMockProvider(),
            )
            try:
                result = coordinator.run_lifecycle(
                    "research-scout", "Research a test topic", {"scope": "fixture"},
                    max_corrections=0,
                )
                self.assertEqual(result.status, "blocked_verification")
                self.assertFalse(result.delivered)
                self.assertIsNone(result.delivery)
                self.assertFalse(result.verification_history[0]["passed"])
            finally:
                coordinator.close()


if __name__ == "__main__":
    unittest.main()
