from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DeploymentContractTests(unittest.TestCase):
    def test_dockerfile_runs_only_one_python_application(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8").lower()
        self.assertIn("from python:", dockerfile)
        self.assertIn('cmd ["python", "-m", "unexpected_runtime.http_api"]', dockerfile)
        self.assertIn("copy unexpected_runtime", dockerfile)
        self.assertIn("copy web", dockerfile)
        self.assertIn("copy agent_manifest.json", dockerfile)
        self.assertIn("copy agent_manifest.json skill_manifest.json ./", dockerfile)
        self.assertIn("copy skills", dockerfile)
        self.assertIn("copy self_improvement", dockerfile)
        self.assertIn("copy workflow_profiles", dockerfile)
        self.assertIn("copy migrations", dockerfile)
        self.assertNotIn("node server.js", dockerfile)
        self.assertNotIn("npm install", dockerfile)
        self.assertNotIn("mobile", dockerfile)
        self.assertNotIn("source.tar.gz.b64", dockerfile)

    def test_render_blueprint_defines_one_free_web_service_and_no_managed_database(self):
        render = (ROOT / "render.yaml").read_text(encoding="utf-8").lower()
        services = re.findall(r"(?m)^\s*-\s+type:\s*web\s*$", render)
        self.assertEqual(len(services), 1)
        self.assertIn("runtime: docker", render)
        self.assertIn("plan: free", render)
        self.assertIn("healthcheckpath: /health", render)
        self.assertIn("unexpected_storage_backend", render)
        self.assertIn("database_url", render)
        self.assertIn("sync: false", render)
        self.assertNotRegex(render, r"(?m)^\s*-\s+type:\s*postgres")
        self.assertNotRegex(render, r"(?m)^\s*plan:\s*(starter|standard|pro|plus)")
        self.assertIn("autoDeploy: false".lower(), render)

    def test_postgres_migrations_are_additive_and_versioned(self):
        baseline = (ROOT / "migrations" / "001_initial.sql").read_text(encoding="utf-8").lower()
        upgrade = (ROOT / "migrations" / "002_idempotency_claims.sql").read_text(encoding="utf-8").lower()
        self.assertIn("create table if not exists schema_migrations", baseline)
        self.assertIn("values (1, '001_initial.sql'", baseline)
        self.assertIn("create table if not exists idempotency_claims", upgrade)
        self.assertIn("values (2, '002_idempotency_claims.sql'", upgrade)
        self.assertNotIn("drop table", baseline + upgrade)
        self.assertNotIn("truncate", baseline + upgrade)

    def test_all_pinned_runtime_skills_are_copied_into_image(self):
        import json
        manifest = json.loads((ROOT / "skill_manifest.json").read_text(encoding="utf-8"))
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8").lower()
        for skill in manifest["skills"]:
            top_level = skill["path"].split("/", 1)[0]
            with self.subTest(skill=skill["id"], path=skill["path"]):
                self.assertIn("copy " + top_level.lower(), dockerfile)
                self.assertTrue((ROOT / skill["path"]).is_file())

    def test_v8_web_tree_has_no_phone_or_pwa_artifacts(self):
        forbidden = ("service-worker", "manifest.webmanifest", "/mobile/", "mobile-assets", "mobile-release")
        web_root = ROOT / "web"
        for path in web_root.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="ignore").lower()
                for marker in forbidden:
                    with self.subTest(path=str(path), marker=marker):
                        self.assertNotIn(marker, text)
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8").lower()
        for marker in ("mobile/", "mobile-release", "service-worker", "manifest.webmanifest"):
            self.assertNotIn(marker, dockerfile)

    def test_hosted_postgres_selection_fails_closed_without_dsn(self):
        from unittest.mock import patch
        import tempfile
        from unexpected_runtime.coordinator import Coordinator
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"UNEXPECTED_STORAGE_BACKEND": "postgres"}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "no SQLite fallback"):
                    Coordinator(state_dir=tmp)

    def test_python_entrypoint_uses_render_port_and_public_bind(self):
        source = (ROOT / "unexpected_runtime" / "http_api.py").read_text(encoding="utf-8")
        self.assertIn('os.getenv("PORT"', source)
        self.assertIn('os.getenv("UNEXPECTED_RUNTIME_BIND_HOST","0.0.0.0")', source)
        self.assertIn('ThreadingHTTPServer((host,int(port))', source)



    def test_project_license_and_third_party_boundaries_are_explicit(self):
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        upstream_license = ROOT / "third_party" / "licenses" / "awesome-llm-apps" / "LICENSE"
        self.assertIn("MIT License", license_text)
        self.assertIn("Apache License 2.0", notices)
        self.assertIn("THIRD_PARTY_NOTICES.md", (ROOT / "README.md").read_text(encoding="utf-8"))
        self.assertTrue(upstream_license.is_file())
        self.assertIn("Apache License", upstream_license.read_text(encoding="utf-8"))


    def test_render_blueprint_starts_without_optional_provider_secrets(self):
        render = (ROOT / "render.yaml").read_text(encoding="utf-8")
        self.assertIn("UNEXPECTED_DEFAULT_PROVIDER", render)
        self.assertIn("        value: mock", render)
        for key in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENOX_API_KEY"):
            with self.subTest(key=key):
                self.assertNotIn(key, render)


    def test_capability_matrix_matches_current_main_registries(self):
        agents = json.loads((ROOT / "agent_manifest.json").read_text(encoding="utf-8"))
        skills = json.loads((ROOT / "skill_manifest.json").read_text(encoding="utf-8"))
        workflows = json.loads((ROOT / "web" / "assets" / "workflow-catalog.json").read_text(encoding="utf-8"))
        matrix = (ROOT / "CAPABILITY_MATRIX.md").read_text(encoding="utf-8")
        self.assertEqual(agents["active_agent_count"], 38)
        self.assertEqual(len(skills["skills"]), 3)
        self.assertEqual(workflows["count"], 120)
        self.assertIn("38 canonical role profiles", matrix)
        self.assertIn("3 active Skills", matrix)
        self.assertIn("120 mapped workflow candidates", matrix)
        self.assertNotIn("draft PR #12 is not merged", matrix)
        self.assertNotIn("v8.1 Skills branch", matrix)

    def test_verified_workflow_documents_the_command_center_seven_stage_sequence(self):
        workflow = (ROOT / "docs" / "VERIFIED_WORKFLOW.md").read_text(encoding="utf-8")
        self.assertIn("Request → Plan → Route → Authorize → Execute → Verify → Deliver & learn", workflow)
        self.assertIn("bounded Improve → Verify loop", workflow)

    def test_deploy_runbook_documents_zero_spend_and_free_tier_limits(self):
        deploy = (ROOT / "DEPLOY.md").read_text(encoding="utf-8")
        self.assertIn("no render service is currently linked to this repository", deploy.lower())
        self.assertIn("5 GB of included outbound bandwidth", deploy)
        self.assertIn("$0.15/GB", deploy)
        self.assertIn("ephemeral filesystem", deploy)
        self.assertIn("6-hour restore window", deploy)
        self.assertIn("no automatic snapshot schedule", deploy)
        self.assertIn("do not deploy until the workspace billing guard is verified", deploy)

if __name__ == "__main__":
    unittest.main(verbosity=2)
