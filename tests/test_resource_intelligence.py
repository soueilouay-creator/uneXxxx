from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from unexpected_runtime.resource_intelligence import ResourceRegistry


class ResourceIntelligenceTests(unittest.TestCase):
    def test_default_catalog_indexes_awesome_and_keeps_candidates_unapproved(self):
        registry = ResourceRegistry()
        report = registry.validate()
        self.assertTrue(report["valid"])
        self.assertGreaterEqual(report["source_count"], 1)
        self.assertGreaterEqual(report["resource_count"], 5)

        source = next(item for item in registry.sources if item["id"] == "sindresorhus-awesome")
        self.assertEqual(source["canonical_url"], "https://github.com/sindresorhus/awesome")
        self.assertEqual(source["license"]["identifier"], "CC0-1.0")
        self.assertEqual(source["license"]["status"], "verified")

        resources = registry.list_resources()
        self.assertTrue(all(item["adoption_status"] == "discovered" for item in resources))
        self.assertTrue(all(item["source_list_url"] for item in resources))
        self.assertTrue(all(item["license"]["status"] != "verified" for item in resources))
        self.assertTrue(all(item["maintenance_status"] == "not_assessed" for item in resources))

    def test_filters_are_deterministic_and_summary_does_not_claim_installation(self):
        registry = ResourceRegistry()
        all_items = registry.list_resources()
        self.assertEqual(registry.list_resources(), all_items)
        self.assertEqual(registry.list_resources(status="discovered"), all_items)
        self.assertEqual(registry.list_resources(status="integrated"), [])
        summary = registry.summary()
        self.assertEqual(summary["resource_count"], len(all_items))
        self.assertEqual(summary["adoption_counts"]["discovered"], len(all_items))
        self.assertNotIn("installed_count", summary)

    def _write_catalog(self, payload):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "catalog.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_duplicate_ids_and_canonical_urls_are_rejected(self):
        baseline = ResourceRegistry().document
        duplicate_id = copy.deepcopy(baseline)
        duplicate_id["resources"].append(copy.deepcopy(duplicate_id["resources"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate resource id"):
            ResourceRegistry(self._write_catalog(duplicate_id))

        duplicate_url = copy.deepcopy(baseline)
        duplicate_url["resources"][1]["canonical_url"] = duplicate_url["resources"][0]["canonical_url"]
        with self.assertRaisesRegex(ValueError, "duplicate canonical URL"):
            ResourceRegistry(self._write_catalog(duplicate_url))

    def test_unknown_status_and_missing_source_are_rejected(self):
        baseline = ResourceRegistry().document
        unknown_status = copy.deepcopy(baseline)
        unknown_status["resources"][0]["adoption_status"] = "auto-installed"
        with self.assertRaisesRegex(ValueError, "unsupported adoption status"):
            ResourceRegistry(self._write_catalog(unknown_status))

        missing_source = copy.deepcopy(baseline)
        missing_source["resources"][0]["source_id"] = "missing-source"
        with self.assertRaisesRegex(ValueError, "unknown source"):
            ResourceRegistry(self._write_catalog(missing_source))

    def test_verified_status_requires_resource_specific_evidence(self):
        baseline = ResourceRegistry().document
        candidate = copy.deepcopy(baseline["resources"][0])
        candidate["adoption_status"] = "verified"
        document = copy.deepcopy(baseline)
        document["resources"] = [candidate]
        with self.assertRaisesRegex(ValueError, "resource-specific license"):
            ResourceRegistry(self._write_catalog(document))

    def test_integrated_status_requires_approval_and_test_evidence(self):
        baseline = ResourceRegistry().document
        candidate = copy.deepcopy(baseline["resources"][0])
        candidate["adoption_status"] = "integrated"
        document = copy.deepcopy(baseline)
        document["resources"] = [candidate]
        with self.assertRaisesRegex(ValueError, "approved"):
            ResourceRegistry(self._write_catalog(document))


if __name__ == "__main__":
    unittest.main(verbosity=2)
