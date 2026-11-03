from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from unexpected_runtime.coordinator import Coordinator
from unexpected_runtime.http_api import create_server
from unexpected_runtime.providers import DeterministicMockProvider
from unexpected_runtime.models import EvaluationReport
from unexpected_runtime.improvement import ImprovementGovernor


ROOT = Path(__file__).resolve().parents[1]


class CommandCenterAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.coordinator = Coordinator(
            state_dir=self.tmp.name,
            provider=DeterministicMockProvider(),
            max_workers=2,
            max_retries=0,
        )
        self.token = "command-center-test-token-" + "x" * 32
        self.server = create_server(
            coordinator=self.coordinator,
            api_token=self.token,
            host="127.0.0.1",
            port=0,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.coordinator.close()
        self.tmp.cleanup()

    def request(self, method, path, body=None, token=None):
        conn = http.client.HTTPConnection(self.host, self.port, timeout=8)
        headers = {}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        if body is not None:
            headers["Content-Type"] = "application/json"
        conn.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = conn.getresponse()
        raw = response.read()
        content_type = response.getheader("Content-Type", "")
        conn.close()
        if "application/json" in content_type and raw:
            return response.status, json.loads(raw)
        return response.status, raw.decode("utf-8", errors="replace")

    def test_root_serves_command_center_without_phone_app(self):
        status, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("<html", body.lower())
        self.assertIn("uneXpected", body)
        self.assertNotIn("/mobile/", body)
        self.assertNotIn("service-worker", body.lower())
        self.assertNotIn("manifest.webmanifest", body.lower())

    def test_static_assets_are_served_from_fixed_web_root(self):
        css_status, css = self.request("GET", "/assets/styles.css")
        js_status, js = self.request("GET", "/assets/app.js")
        self.assertEqual(css_status, 200)
        self.assertEqual(js_status, 200)
        self.assertIn("text/css", self._content_type("/assets/styles.css"))
        self.assertIn("javascript", self._content_type("/assets/app.js"))
        self.assertIn("fetch(", js)
        self.assertEqual(self.request("GET", "/assets/../../.env")[0], 404)
        self.assertEqual(self.request("GET", "/assets/%2e%2e/%2e%2e/.env")[0], 404)
        self.assertEqual(self.request("GET", "/mobile/")[0], 404)

    def _content_type(self, path):
        conn = http.client.HTTPConnection(self.host, self.port, timeout=8)
        conn.request("GET", path)
        response = conn.getresponse()
        value = response.getheader("Content-Type", "")
        response.read()
        conn.close()
        return value

    def test_command_center_read_apis_require_bearer_auth(self):
        routes = (
            "/v1/agents",
            "/v1/tasks",
            "/v1/events",
            "/v1/capabilities",
            "/v1/improvements",
            "/v1/providers",
            "/v1/approvals",
            "/v1/resources",
            "/v1/quality-evaluations",
        )
        for route in routes:
            with self.subTest(route=route):
                self.assertEqual(self.request("GET", route)[0], 401)

    def test_command_center_read_apis_return_structured_data(self):
        routes = (
            "/v1/agents",
            "/v1/tasks",
            "/v1/events",
            "/v1/capabilities",
            "/v1/improvements",
            "/v1/providers",
            "/v1/approvals",
        )
        for route in routes:
            with self.subTest(route=route):
                status, body = self.request("GET", route, token=self.token)
                self.assertEqual(status, 200)
                self.assertIsInstance(body, dict)
                self.assertIn("items" if route != "/v1/providers" else "providers", body)

    def test_web_ui_exposes_provider_selection_and_connection_test(self):
        html_status, html = self.request("GET", "/")
        js_status, js = self.request("GET", "/assets/app.js")
        self.assertEqual(html_status, 200)
        self.assertEqual(js_status, 200)
        self.assertIn('id="task-provider"', html)
        self.assertIn('id="proposal-form"', html)
        self.assertIn('provider_route', js)
        self.assertIn('/v1/providers/test', js)
        self.assertIn('data-test-provider', js)

    def test_task_detail_and_task_filtered_events_are_available(self):
        result = self.coordinator.invoke("orchestrator", "command center task detail", source_refs=("test-source",))
        status, body = self.request("GET", "/v1/tasks/" + result.task_id, token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body["task"]["task_id"], result.task_id)
        self.assertEqual(body["task"]["result"]["status"], "completed")
        event_status, events = self.request("GET", "/v1/events?task_id=" + result.task_id, token=self.token)
        self.assertEqual(event_status, 200)
        self.assertTrue(events["items"])
        self.assertTrue(all(item.get("task_id") == result.task_id for item in events["items"]))

    def test_improvement_proposal_endpoint_is_authenticated_and_never_promotes(self):
        report = EvaluationReport(
            benchmark_id="command-center-baseline",
            scenario_ids=("scenario-one",),
            score=0.7,
            critical_checks={"safety": True},
            noncritical_passed=1,
            noncritical_total=1,
            required_critical_check_ids=("safety",),
            acceptance_check_ids=("safety", "clarity"),
            provider_mode="mock",
            rubric_id="command-center-test-rubric",
        )
        ImprovementGovernor(self.coordinator).set_baseline("orchestrator", report)
        payload = {
            "agent_id": "orchestrator",
            "benchmark_id": "command-center-baseline",
            "candidate_instruction": "Produce clearer source-linked plans.",
            "changes": "Improve source citation quality and explicit uncertainty.",
            "protected_fields": [],
        }
        self.assertEqual(self.request("POST", "/v1/improvements/propose", body=payload)[0], 401)
        status, body = self.request("POST", "/v1/improvements/propose", body=payload, token=self.token)
        self.assertEqual(status, 201, body)
        proposal_id = body["proposal"]["proposal_id"]
        self.assertEqual(body["proposal"]["status"], "pending")
        detail_status, detail = self.request("GET", "/v1/improvements/" + proposal_id, token=self.token)
        self.assertEqual(detail_status, 200)
        self.assertEqual(detail["proposal"]["proposal_id"], proposal_id)
        self.assertEqual(self.request("POST", "/v1/improvements/promote", body={}, token=self.token)[0], 404)

    def test_health_is_minimal_and_never_discloses_secret_or_internal_paths(self):
        status, body = self.request("GET", "/health")
        self.assertEqual(status, 200)
        serialized = json.dumps(body).lower()
        for forbidden in (
            "api_token",
            "database_url",
            "openai_api_key",
            "anthropic_api_key",
            "state_db",
            "/tmp/",
            "approval_ledger_path",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_agent_registry_reports_exactly_38_roles(self):
        status, body = self.request("GET", "/v1/agents", token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(body.get("count"), 38)
        self.assertEqual(len(body.get("items", [])), 38)


    def test_lifecycle_requires_live_provider_before_creating_stage_tasks(self):
        payload = {
            "agent_id": "research-scout",
            "objective": "Check runtime plumbing only",
        }
        status, body = self.request(
            "POST", "/v1/lifecycle", body=payload, token=self.token
        )
        self.assertEqual(status, 409, body)
        self.assertIn("requires a configured live AI provider", body.get("error", ""))

        tasks_status, tasks = self.request("GET", "/v1/tasks", token=self.token)
        self.assertEqual(tasks_status, 200)
        self.assertEqual(tasks.get("count"), 0)

    def test_mock_mode_ui_defaults_to_runtime_invocation_and_gates_lifecycle(self):
        html_status, html = self.request("GET", "/")
        js_status, js = self.request("GET", "/assets/app.js")
        self.assertEqual(html_status, 200)
        self.assertEqual(js_status, 200)
        self.assertIn(
            '<option value="invoke" selected>Single governed invocation (runtime test)</option>',
            html,
        )
        self.assertIn(
            '<option value="lifecycle" disabled>Full verified lifecycle (requires a live AI provider)</option>',
            html,
        )
        self.assertIn("lifecycleOption.disabled=!hasConfiguredLiveProvider;", js)
        self.assertIn("body?.result?.status", js)


    def test_resource_catalog_and_quality_history_are_authenticated_and_discovery_only(self):
        status, body = self.request("GET", "/v1/resources", token=self.token)
        self.assertEqual(status, 200)
        self.assertGreaterEqual(body["count"], 5)
        self.assertTrue(body["summary"]["valid"])
        self.assertTrue(all(item["adoption_status"] == "discovered" for item in body["items"]))
        self.assertTrue(all(item["license"]["status"] != "verified" for item in body["items"]))

        status, body = self.request("POST", "/v1/quality-evaluations",
                                    body={"provider_route": "mock"}, token=self.token)
        self.assertEqual(status, 409, body)
        self.assertEqual(body["report"]["status"], "blocked")
        self.assertEqual(body["report"]["execution_mode"], "live")
        tasks_status, tasks = self.request("GET", "/v1/tasks", token=self.token)
        self.assertEqual(tasks_status, 200)
        self.assertEqual(tasks["count"], 0)

        history_status, history = self.request("GET", "/v1/quality-evaluations", token=self.token)
        self.assertEqual(history_status, 200)
        self.assertEqual(history["count"], 1)
        serialized = json.dumps(history)
        self.assertNotIn("api_key", serialized.lower())
        self.assertNotIn("authorization", serialized.lower())
        self.assertNotIn("MOCK_OK", serialized)

    def test_quality_evaluation_api_rejects_missing_route_unknown_fields_and_oversized_selection(self):
        self.assertEqual(
            self.request("POST", "/v1/quality-evaluations", body={}, token=self.token)[0],
            400,
        )
        self.assertEqual(
            self.request("POST", "/v1/quality-evaluations",
                         body={"provider_route": "mock", "execute": True}, token=self.token)[0],
            400,
        )
        self.assertEqual(
            self.request("POST", "/v1/quality-evaluations",
                         body={"provider_route": "mock", "scenario_ids": ["case"] * 9},
                         token=self.token)[0],
            400,
        )
        self.assertEqual(self.request("GET", "/v1/resources", token=None)[0], 401)
        self.assertEqual(self.request("GET", "/v1/quality-evaluations", token=None)[0], 401)

    def test_command_center_exposes_existing_intelligence_view(self):
        html_status, html = self.request("GET", "/")
        js_status, js = self.request("GET", "/assets/app.js")
        self.assertEqual(html_status, 200)
        self.assertEqual(js_status, 200)
        self.assertIn('data-view="intelligence"', html)
        self.assertIn('id="resource-list"', html)
        self.assertIn('id="quality-evaluation-form"', html)
        self.assertIn('/v1/resources', js)
        self.assertIn('/v1/quality-evaluations', js)


    def test_workflow_studio_and_skills_views_are_exposed(self):
        status, html = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn('data-view="workflows"', html)
        self.assertIn('data-view="skills"', html)
        self.assertIn('id="workflow-grid"', html)
        self.assertIn('id="skill-grid"', html)

    def test_workflow_catalogue_contains_all_120_mapped_records(self):
        status, body = self.request("GET", "/assets/workflow-catalog.json")
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 120)
        self.assertEqual(body["status"], "mapped_candidates_not_runnable")
        self.assertEqual(len(body["workflows"]), 120)
        self.assertTrue(all(item["disposition"] == "merged-as-workflow-capability-not-separate-agent"
                            for item in body["workflows"]))

    def test_skills_and_mcp_tools_are_authenticated_live_runtime_catalogues(self):
        self.assertEqual(self.request("GET", "/v1/skills")[0], 401)
        self.assertEqual(self.request("GET", "/v1/mcp/tools")[0], 401)
        status, skills = self.request("GET", "/v1/skills", token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(skills["count"], 3)
        self.assertTrue(all(item["status"] == "active" for item in skills["items"]))
        self.assertTrue(all("trigger_terms" in item for item in skills["items"]))
        tools_status, tools = self.request("GET", "/v1/mcp/tools", token=self.token)
        self.assertEqual(tools_status, 200)
        self.assertEqual(tools["items"], [])


    def test_optional_inventory_failures_cannot_block_core_refresh(self):
        source = (ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")
        start = source.index("async function refresh()")
        end = source.index("function showView", start)
        refresh_source = source[start:end]
        core_start = refresh_source.index("const [status,agents")
        core_end = refresh_source.index("]);", core_start)
        core_requests = refresh_source[core_start:core_end]
        self.assertNotIn('/v1/skills', core_requests)
        self.assertNotIn('/v1/mcp/tools', core_requests)
        self.assertNotIn('/assets/workflow-catalog.json', core_requests)
        self.assertIn("Promise.allSettled", source)
        self.assertIn("state.inventoryErrors.workflowCatalog", source)
        self.assertIn("state.inventoryErrors.skills", source)
        self.assertIn("state.inventoryErrors.mcpTools", source)



if __name__ == "__main__":
    unittest.main(verbosity=2)
