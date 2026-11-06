import hashlib
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from unexpected_runtime.coordinator import Coordinator
from unexpected_runtime.providers import DeterministicMockProvider
from unexpected_runtime.http_api import create_server
from unexpected_runtime.skills import SkillRegistry, SkillRegistryError


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class AdvancedSkillBundleTests(unittest.TestCase):
    def _write_skill(self, root: Path, skill_id: str, body: str, *,
                     invocation_mode: str = "automatic", trigger_terms=None,
                     allowed_tools=None, resources=None):
        directory = root / "skills" / skill_id
        directory.mkdir(parents=True, exist_ok=True)
        main_path = directory / "SKILL.md"
        main_path.write_text(body, encoding="utf-8")
        entry = {
            "id": skill_id,
            "version": "1.0.0",
            "path": main_path.relative_to(root).as_posix(),
            "sha256": digest(body),
            "agent_ids": ["maintenance-engineer"],
            "trigger_terms": list(trigger_terms or []),
            "source_ref": f"fixture:{skill_id}",
            "status": "active",
            "invocation_mode": invocation_mode,
            "description": f"Reviewed {skill_id} workflow",
            "allowed_tools": list(allowed_tools or []),
            "resources": [],
        }
        for kind, relative, payload in resources or []:
            target = directory / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(payload, encoding="utf-8")
            entry["resources"].append({
                "path": target.relative_to(root).as_posix(),
                "sha256": digest(payload),
                "kind": kind,
            })
        return entry

    def _manifest(self, root: Path, entries):
        path = root / "skill_manifest.json"
        path.write_text(json.dumps({"schema_version": 2, "skills": entries}), encoding="utf-8")
        return path

    def test_v2_modes_resolve_always_automatic_and_explicit_manual_skills(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            always = self._write_skill(root, "always-skill", "# Always\n",
                                       invocation_mode="always_apply")
            automatic = self._write_skill(root, "auto-skill", "# Automatic\n",
                                          trigger_terms=["machine uptime"])
            manual = self._write_skill(root, "manual-skill", "# Manual\n",
                                       invocation_mode="user_invocable")
            registry = SkillRegistry.load(self._manifest(root, [always, automatic, manual]), root)

            resolved = registry.resolve_all("maintenance-engineer", "Improve machine uptime")
            self.assertEqual([item.id for item in resolved], ["always-skill", "auto-skill"])

            explicit = registry.resolve_all(
                "maintenance-engineer", "Improve machine uptime",
                requested_skill_ids=("manual-skill",),
            )
            self.assertEqual([item.id for item in explicit],
                             ["always-skill", "auto-skill", "manual-skill"])

    def test_manual_selection_cannot_bypass_role_scope_or_invocation_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            automatic = self._write_skill(root, "auto-skill", "# Auto\n",
                                          trigger_terms=["uptime"])
            registry = SkillRegistry.load(self._manifest(root, [automatic]), root)
            with self.assertRaises(SkillRegistryError):
                registry.resolve_all("maintenance-engineer", "uptime",
                                     requested_skill_ids=("auto-skill",))
            with self.assertRaises(SkillRegistryError):
                registry.resolve_all("coding-engineer", "uptime",
                                     requested_skill_ids=("auto-skill",))

    def test_bundle_loads_only_hash_verified_reference_text_and_never_scripts_or_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            entry = self._write_skill(
                root, "bundle-skill", "# Maintenance workflow\nUse the checklist.",
                invocation_mode="user_invocable",
                allowed_tools=["maintenance.read"],
                resources=[
                    ("reference", "references/checklist.md", "# Checklist\nCheck isolation."),
                    ("script", "scripts/verify.py", "raise RuntimeError('must never execute')"),
                    ("asset", "assets/diagram.svg", "<svg>asset bytes</svg>"),
                ],
            )
            registry = SkillRegistry.load(self._manifest(root, [entry]), root)
            skill = registry.resolve_all(
                "maintenance-engineer", "review",
                requested_skill_ids=("bundle-skill",),
            )[0]
            context = registry.read_context(skill)

            self.assertIn("Maintenance workflow", context)
            self.assertIn("Check isolation", context)
            self.assertNotIn("must never execute", context)
            self.assertNotIn("asset bytes", context)
            self.assertEqual(skill.allowed_tools, ("maintenance.read",))
            self.assertEqual({resource.kind for resource in skill.resources},
                             {"reference", "script", "asset"})

    def test_modified_reference_fails_closed_when_context_is_read(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            entry = self._write_skill(
                root, "bundle-skill", "# Main\n",
                invocation_mode="user_invocable",
                resources=[("reference", "references/ref.md", "# Original\n")],
            )
            registry = SkillRegistry.load(self._manifest(root, [entry]), root)
            selected = registry.resolve_all("maintenance-engineer", "nothing", requested_skill_ids=("bundle-skill",))[0]
            ref_path = root / "skills/bundle-skill/references/ref.md"
            ref_path.write_text("# Tampered\n", encoding="utf-8")
            with self.assertRaises(SkillRegistryError):
                registry.read_context(selected)

    def test_resource_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            entry = self._write_skill(
                root, "bundle-skill", "# Main\n",
                resources=[("reference", "../../../outside.md", "# Outside\n")],
            )
            manifest = self._manifest(root, [entry])
            with self.assertRaises(SkillRegistryError):
                SkillRegistry.load(manifest, root)

    def test_invalid_invocation_mode_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            entry = self._write_skill(root, "bad-skill", "# Main\n",
                                      invocation_mode="autonomous")
            with self.assertRaises(SkillRegistryError):
                SkillRegistry.load(self._manifest(root, [entry]), root)

    def test_legacy_v1_manifest_remains_automatic(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            body = "# Legacy skill\n"
            target = root / "skills/legacy.md"
            target.parent.mkdir(parents=True)
            target.write_text(body, encoding="utf-8")
            manifest = root / "skill_manifest.json"
            manifest.write_text(json.dumps({
                "schema_version": 1,
                "skills": [{
                    "id": "legacy", "version": "1.0.0", "path": "skills/legacy.md",
                    "sha256": digest(body), "agent_ids": ["maintenance-engineer"],
                    "trigger_terms": ["uptime"], "source_ref": "fixture:legacy", "status": "active",
                }],
            }), encoding="utf-8")
            registry = SkillRegistry.load(manifest, root)
            self.assertEqual(registry.resolve_all("maintenance-engineer", "uptime")[0].invocation_mode,
                             "automatic")

    def test_coordinator_attaches_explicit_skill_and_persists_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            package_root = temp_root / "package"
            package_root.mkdir()
            entry = self._write_skill(
                package_root, "manual-skill", "# Approved maintenance workflow\\n",
                invocation_mode="user_invocable",
            )
            manifest = self._manifest(package_root, [entry])
            provider = DeterministicMockProvider()
            coordinator = Coordinator(
                manifest_path=Path(__file__).resolve().parents[1] / "agent_manifest.json",
                state_dir=temp_root / "state",
                provider=provider,
                skill_manifest_path=manifest,
                skill_package_root=package_root,
                max_retries=0,
            )
            try:
                result = coordinator.invoke(
                    "maintenance-engineer",
                    "Review the maintenance checklist",
                    requested_skill_ids=("manual-skill",),
                    idempotency_key="manual-skill-selection",
                )
                self.assertEqual(result.status, "completed")
                self.assertIn("Approved maintenance workflow", provider.requests[-1]["system_prompt"])
                provider_payload = json.loads(provider.requests[-1]["user_prompt"])
                self.assertEqual(provider_payload["verified_skills"][0]["id"], "manual-skill")
                task = coordinator.store.get_task(result.task_id)
                persisted = json.loads(task["payload_json"])
                self.assertEqual(persisted["requested_skill_ids"], ["manual-skill"])
            finally:
                coordinator.close()

    def test_idempotency_digest_binds_explicit_skill_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            package_root = temp_root / "package"
            package_root.mkdir()
            first = self._write_skill(
                package_root, "manual-one", "# One\\n", invocation_mode="user_invocable"
            )
            second = self._write_skill(
                package_root, "manual-two", "# Two\\n", invocation_mode="user_invocable"
            )
            coordinator = Coordinator(
                manifest_path=Path(__file__).resolve().parents[1] / "agent_manifest.json",
                state_dir=temp_root / "state",
                provider=DeterministicMockProvider(),
                skill_manifest_path=self._manifest(package_root, [first, second]),
                skill_package_root=package_root,
                max_retries=0,
            )
            try:
                first_result = coordinator.invoke(
                    "maintenance-engineer", "Review checklist",
                    requested_skill_ids=("manual-one",),
                    idempotency_key="same-skill-selection-key",
                )
                self.assertEqual(first_result.status, "completed")
                with self.assertRaises(ValueError):
                    coordinator.invoke(
                        "maintenance-engineer", "Review checklist",
                        requested_skill_ids=("manual-two",),
                        idempotency_key="same-skill-selection-key",
                    )
            finally:
                coordinator.close()



    def test_requested_skill_ids_reject_strings_and_non_string_values(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            entry = self._write_skill(
                root, "manual", "# Manual\\n", invocation_mode="user_invocable"
            )
            registry = SkillRegistry.load(self._manifest(root, [entry]), root)
            for requested in ("manual", [None], [[]], ["  "]):
                with self.assertRaises(SkillRegistryError):
                    registry.validate_requested("maintenance-engineer", requested)


    def test_manifest_rejects_non_list_scope_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            entry = self._write_skill(
                root, "invalid-scope", "# Invalid scope\\n",
                invocation_mode="user_invocable",
            )
            entry["agent_ids"] = "maintenance-engineer"
            with self.assertRaises(SkillRegistryError):
                SkillRegistry.load(self._manifest(root, [entry]), root)


    def test_approval_action_digest_binds_selected_skill_ids(self):
        base = {
            "agent_id": "maintenance-engineer",
            "objective": "Review preventive maintenance",
            "required_permissions": ("maintenance.write",),
            "deadline_seconds": 30.0,
            "max_steps": 4,
        }
        first = Coordinator.invoke_action_details(
            **base, requested_skill_ids=("maintenance-checklist",)
        )
        second = Coordinator.invoke_action_details(
            **base, requested_skill_ids=("spare-parts-checklist",)
        )
        self.assertNotEqual(first, second)
        self.assertEqual(first["requested_skill_ids"], ["maintenance-checklist"])


class SkillAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.temp_root = Path(self.temp.name)
        self.package_root = self.temp_root / "package"
        self.package_root.mkdir()
        self.skill_dir = self.package_root / "skills" / "manual"
        self.skill_dir.mkdir(parents=True)
        self.skill_body = "# Approved maintenance checklist\n"
        (self.skill_dir / "SKILL.md").write_text(self.skill_body, encoding="utf-8")
        self.manual_skill = {
            "id": "manual-checklist",
            "version": "1.0.0",
            "path": "skills/manual/SKILL.md",
            "sha256": digest(self.skill_body),
            "agent_ids": ["maintenance-engineer"],
            "trigger_terms": [],
            "source_ref": "fixture:manual-checklist",
            "status": "active",
            "invocation_mode": "user_invocable",
            "description": "Manual maintenance checklist",
            "allowed_tools": ["maintenance.read"],
            "resources": [],
        }
        automatic_dir = self.package_root / "skills" / "automatic"
        automatic_dir.mkdir(parents=True)
        automatic_body = "# Automatic maintenance workflow\n"
        (automatic_dir / "SKILL.md").write_text(automatic_body, encoding="utf-8")
        automatic_skill = {
            "id": "automatic-checklist",
            "version": "1.0.0",
            "path": "skills/automatic/SKILL.md",
            "sha256": digest(automatic_body),
            "agent_ids": ["maintenance-engineer"],
            "trigger_terms": ["scheduled maintenance"],
            "source_ref": "fixture:automatic-checklist",
            "status": "active",
            "invocation_mode": "automatic",
            "description": "Trigger-matched maintenance workflow",
            "allowed_tools": [],
            "resources": [],
        }
        manifest = self.package_root / "skill_manifest.json"
        manifest.write_text(json.dumps({"schema_version": 2, "skills": [self.manual_skill, automatic_skill]}),
                            encoding="utf-8")
        self.provider = DeterministicMockProvider()
        self.coordinator = Coordinator(
            manifest_path=Path(__file__).resolve().parents[1] / "agent_manifest.json",
            state_dir=self.temp_root / "state",
            provider=self.provider,
            skill_manifest_path=manifest,
            skill_package_root=self.package_root,
            max_retries=0,
        )
        self.token = "skills-api-test-token-" + "x" * 32
        self.server = create_server(coordinator=self.coordinator, api_token=self.token, host="127.0.0.1", port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.coordinator.close()
        self.temp.cleanup()

    def request(self, method, path, body=None, token=None):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=8)
        headers = {}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        if body is not None:
            headers["Content-Type"] = "application/json"
        connection.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = connection.getresponse()
        raw = response.read()
        content_type = response.getheader("Content-Type", "")
        connection.close()
        return response.status, json.loads(raw) if "application/json" in content_type and raw else raw

    def test_skills_catalog_is_authenticated_and_exposes_metadata_only(self):
        self.assertEqual(self.request("GET", "/v1/skills")[0], 401)
        status, payload = self.request("GET", "/v1/skills", token=self.token)
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 2)
        skill = next(item for item in payload["items"] if item["id"] == "manual-checklist")
        self.assertEqual(skill["id"], "manual-checklist")
        self.assertEqual(skill["invocation_mode"], "user_invocable")
        serialized = json.dumps(payload)
        self.assertNotIn("Approved maintenance checklist", serialized)
        self.assertNotIn("api_key", serialized.lower())

    def test_authenticated_invoke_selects_skill_and_task_detail_persists_it(self):
        status, payload = self.request(
            "POST", "/v1/invoke",
            body={
                "agent_id": "maintenance-engineer",
                "objective": "Review planned maintenance work",
                "skill_ids": ["manual-checklist"],
                "idempotency_key": "manual-skill-api-run",
            },
            token=self.token,
        )
        self.assertEqual(status, 200, payload)
        result = payload["result"]
        self.assertEqual(result["status"], "completed")
        self.assertIn("Approved maintenance checklist", self.provider.requests[-1]["system_prompt"])
        detail_status, detail = self.request(
            "GET", "/v1/tasks/" + result["task_id"], token=self.token
        )
        self.assertEqual(detail_status, 200)
        self.assertEqual(detail["task"]["requested_skill_ids"], ["manual-checklist"])

    def test_api_rejects_oversized_duplicate_and_non_manual_skill_selection(self):
        invalid_payloads = [
            {"skill_ids": ["manual-checklist"] * 5},
            {"skill_ids": ["manual-checklist", "manual-checklist"]},
            {"skill_ids": ["unknown-skill"]},
            {"skill_ids": ["automatic-checklist"]},
            {"skill_ids": [" "]},
        ]
        for index, extra in enumerate(invalid_payloads):
            body = {"agent_id": "maintenance-engineer", "objective": "Check schedule",
                    "idempotency_key": f"invalid-skill-select-{index}", **extra}
            self.assertEqual(self.request("POST", "/v1/invoke", body=body, token=self.token)[0], 400)





class IndustrialMaintenanceSalesSkillTests(unittest.TestCase):
    def test_sales_intel_auto_loads_sales_skill_and_peer_roles_are_scoped(self):
        root = Path(__file__).resolve().parents[1]
        registry = SkillRegistry.load(package_root=root)
        sales = registry.resolve_all(
            "sales-intel",
            "industrial maintenance sales control center preventive maintenance tracker and spare-parts tracker",
        )
        self.assertIn("industrial-maintenance-sales", [item.id for item in sales])

        allowed = {
            "sales-intel", "business-strategist", "maintenance-engineer",
            "marketing-seo", "data-analyst", "project-manager",
            "code-reviewer", "self-improvement-governor",
        }
        for agent_id in allowed:
            resolved = registry.resolve_all(
                agent_id,
                "industrial maintenance sales control center preventive maintenance tracker",
            )
            self.assertIn("industrial-maintenance-sales", [item.id for item in resolved])

        unrelated = registry.resolve_all("sales-intel", "write a fantasy short story")
        self.assertNotIn("industrial-maintenance-sales", [item.id for item in unrelated])

    def test_sales_skill_context_contains_explicit_gates_and_does_not_claim_connectors(self):
        root = Path(__file__).resolve().parents[1]
        registry = SkillRegistry.load(package_root=root)
        skill = next(item for item in registry.resolve_all(
            "sales-intel", "industrial maintenance sales control center"
        ) if item.id == "industrial-maintenance-sales")
        context = registry.read_context(skill).lower()
        for token in (
            "human reply", "demo is booked only", "no automatic email sends",
            "change recipients by guess", "synthetic data", "test hypotheses",
            "not a remote mcp client", "approval",
        ):
            self.assertIn(token, context)

if __name__ == "__main__":
    unittest.main(verbosity=2)
