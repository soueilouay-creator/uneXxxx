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

    def test_render_provider_preflight_allows_slow_successful_connection_checks(self):
        workflow = (ROOT / ".github" / "workflows" / "rebind-render-service.yml").read_text(encoding="utf-8")
        marker = "- name: Verify a real OpenRouter call through the hosted runtime"
        self.assertIn(marker, workflow)
        provider_step = workflow.split(marker, 1)[1]
        provider_test_request = provider_step.split('response="$(curl', 1)[1].split(')"', 1)[0]
        timeout_match = re.search(r"--max-time\s+(\d+)", provider_test_request)
        self.assertIsNotNone(timeout_match, "Provider preflight must define an explicit curl deadline.")
        self.assertGreaterEqual(
            int(timeout_match.group(1)),
            120,
            "The provider preflight deadline must accommodate successful hosted calls slower than 30 seconds.",
        )

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

if __name__ == "__main__":
    unittest.main(verbosity=2)
