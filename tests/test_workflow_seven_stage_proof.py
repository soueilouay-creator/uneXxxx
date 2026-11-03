import json
import tempfile
import unittest
from pathlib import Path

from unexpected_runtime.coordinator import Coordinator
from unexpected_runtime.providers import DeterministicMockProvider, ProviderRouter
from unexpected_runtime.workflow import WorkflowRunner


ROOT = Path(__file__).resolve().parents[1]


class PassingLifecycleProvider:
    name = "openrouter"
    model = "fixture-live-model"
    configured = True
    verified = True
    retry_safe = False

    def __init__(self):
        self.calls = []

    def generate(self, *, system_prompt, user_prompt, agent_id, task_id, timeout):
        self.calls.append({"agent_id": agent_id, "task_id": task_id})
        payload = json.loads(user_prompt)
        if agent_id == "project-manager":
            return "Plan: prepare the report, check it against the request, refine it, and return it."
        if agent_id == "code-reviewer":
            return "VERDICT: PASS\nThe candidate satisfies the stated scope and acceptance criteria."
        if agent_id == "research-scout":
            if "review_feedback" in payload:
                return "Improved report: scope is explicit, assumptions are stated, and the requested result is complete."
            return "Initial report: scope and requested result are addressed."
        return "Fixture response."


class SevenStageWorkflowProofTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.mock = DeterministicMockProvider()
        self.live = PassingLifecycleProvider()
        self.router = ProviderRouter(
            {"mock": self.mock, "openrouter": self.live},
            default_route="openrouter",
        )
        self.coordinator = Coordinator(
            manifest_path=ROOT / "agent_manifest.json",
            state_dir=self.temp.name,
            provider=self.router,
            max_workers=3,
            max_retries=0,
        )

    def tearDown(self):
        self.coordinator.close()
        self.temp.cleanup()

    def test_verified_default_live_route_completes_and_records_all_seven_stages(self):
        result = self.coordinator.run_lifecycle(
            "research-scout",
            "Prepare a short report with scope, assumptions, and a clear conclusion.",
            {"scope": "bounded test fixture"},
            max_corrections=0,
            max_improvements=1,
            deadline_seconds=5,
        )

        self.assertEqual(result.status, "delivered")
        self.assertTrue(result.delivered)
        self.assertEqual(self.mock.calls, 0)
        self.assertEqual(len(self.live.calls), 5)

        result_data = result.to_dict()
        workflow_id = result_data.get("workflow_id")
        self.assertTrue(workflow_id, result_data)

        events = self.coordinator.store.events(200)
        decoded = []
        for event in events:
            payload = json.loads(event.get("payload_json") or "{}")
            if payload.get("workflow_id") == workflow_id:
                decoded.append((event["event_type"], payload))
        decoded.reverse()  # storage event APIs return newest-first; assert lifecycle order

        stage_results = [
            payload for event_type, payload in decoded
            if event_type == "workflow_stage_outcome"
        ]
        self.assertEqual(
            [item["stage"] for item in stage_results],
            ["request", "plan", "execute", "verify", "improve", "verify", "deliver", "learn"],
        )
        self.assertEqual(
            [item["status"] for item in stage_results],
            ["accepted", "completed", "completed", "passed", "completed", "passed", "delivered", "recorded"],
        )
        self.assertTrue(all(item["workflow_id"] == workflow_id for item in stage_results))

        task_rows = self.coordinator.store.list_tasks(100)
        workflow_tasks = [
            row for row in task_rows
            if "workflow:" + workflow_id in row.get("source_refs", [])
        ]
        self.assertEqual(len(workflow_tasks), 5)
        self.assertEqual({item.get("provider_route") for item in workflow_tasks}, {"openrouter"})
        workflow_task_ids = {item["task_id"] for item in workflow_tasks}

        provider_events = [
            json.loads(event["payload_json"])
            for event in events
            if event["event_type"] == "provider_used" and event.get("task_id") in workflow_task_ids
        ]
        self.assertEqual(len(provider_events), 5)
        self.assertEqual({item["route"] for item in provider_events}, {"openrouter"})
        self.assertTrue(all(item["mock"] is False for item in provider_events))

        learned = [
            payload for event_type, payload in decoded
            if event_type == "workflow_cycle_learned"
        ]
        self.assertEqual(len(learned), 1)
        self.assertEqual(learned[0]["stage_count"], 7)
        self.assertTrue(learned[0]["delivered"])

    def test_lifecycle_rejects_mock_or_unverified_router_before_creating_tasks(self):
        for route, provider in (
            ("mock", DeterministicMockProvider()),
            ("unverified", type("UnverifiedProvider", (), {
                "name": "unverified",
                "configured": True,
                "verified": False,
                "retry_safe": False,
                "generate": lambda self, **kwargs: "VERDICT: PASS",
            })()),
        ):
            with self.subTest(route=route), tempfile.TemporaryDirectory() as state:
                router = ProviderRouter(
                    {"mock": DeterministicMockProvider(), route: provider},
                    default_route=route,
                )
                coordinator = Coordinator(
                    manifest_path=ROOT / "agent_manifest.json",
                    state_dir=state,
                    provider=router,
                    max_workers=2,
                    max_retries=0,
                )
                try:
                    with self.assertRaises(ValueError):
                        coordinator.run_lifecycle(
                            "research-scout",
                            "Do not run without a verified live reviewer.",
                            {},
                            max_corrections=0,
                            deadline_seconds=5,
                        )
                    self.assertEqual(coordinator.store.list_tasks(20), [])
                finally:
                    coordinator.close()

    def test_learning_failure_does_not_report_the_lifecycle_as_delivered(self):
        runner = WorkflowRunner(
            plan=lambda request, feedback=None: {"steps": ["prepare"]},
            execute=lambda plan: "candidate",
            verify=lambda candidate, plan: {"passed": True, "feedback": "Pass."},
            improve=lambda candidate, feedback: candidate + " refined",
            deliver=lambda candidate: {"output": candidate},
            learn=lambda record: (_ for _ in ()).throw(RuntimeError("storage unavailable")),
            max_corrections=0,
            max_improvements=1,
        )

        result = runner.run({"objective": "exercise learning failure"})

        self.assertEqual(result.status, "blocked_learning")
        self.assertFalse(result.delivered)
        self.assertIsNotNone(result.delivery)
        self.assertIn("learning stage failed", result.learning_error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
