from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from unexpected_runtime.local_ai import (
    LocalAIError,
    inspect_local_ai,
    inspect_model_availability,
    load_model_registry,
    validate_model_registry,
)


class LocalAITests(unittest.TestCase):
    def base_model(self, **overrides):
        item = {
            "model_id": "local-llm-test",
            "task": "llm",
            "repository": "https://github.com/ggml-org/llama.cpp",
            "revision": "a" * 40,
            "runtime": "llama-server",
            "repository_license": "MIT",
            "weight_license_status": "unverified",
            "state": "discovered",
            "weight_files": [],
        }
        item.update(overrides)
        return item

    def test_registry_requires_unique_models_and_valid_model_task(self):
        registry = validate_model_registry({"schema_version": 1, "models": [self.base_model()]})
        self.assertEqual(registry["models"][0]["model_id"], "local-llm-test")
        self.assertEqual(validate_model_registry({"schema_version": 1, "models": [self.base_model(task="workflow")]})["models"][0]["task"], "workflow")
        with self.assertRaises(LocalAIError):
            validate_model_registry({"schema_version": 1, "models": [self.base_model(), self.base_model()]})
        with self.assertRaises(LocalAIError):
            validate_model_registry({"schema_version": 1, "models": [self.base_model(task="unknown")]})

    def test_verified_model_requires_weight_checksum_and_reviewed_licence(self):
        with self.assertRaises(LocalAIError):
            validate_model_registry({"schema_version": 1, "models": [
                self.base_model(state="verified", weight_license_status="verified")
            ]})
        model = self.base_model(
            state="verified", weight_license_status="verified",
            weight_files=[{"path": "llm/model.gguf", "sha256": "a" * 64, "license_status": "verified"}]
        )
        self.assertEqual(validate_model_registry({"schema_version": 1, "models": [model]})["models"][0]["state"], "verified")
        with self.assertRaises(LocalAIError):
            validate_model_registry({"schema_version": 1, "models": [self.base_model(
                state="verified", weight_license_status="verified",
                weight_files=[{"path": "llm/model.gguf", "sha256": "a" * 64, "license_status": "unverified"}]
            )]})

    def test_registry_rejects_path_traversal_and_invalid_hashes(self):
        with self.assertRaises(LocalAIError):
            validate_model_registry({"schema_version": 1, "models": [self.base_model(
                weight_files=[{"path": "../escape.gguf", "sha256": "a" * 64, "license_status": "verified"}]
            )]})
        with self.assertRaises(LocalAIError):
            validate_model_registry({"schema_version": 1, "models": [self.base_model(
                weight_files=[{"path": "model.gguf", "sha256": "not-a-sha", "license_status": "verified"}]
            )]})

    def test_model_files_are_verified_by_sha256_inside_local_model_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            weights = root / "llm" / "model.gguf"
            weights.parent.mkdir()
            payload = b"synthetic local model fixture"
            weights.write_bytes(payload)
            digest = hashlib.sha256(payload).hexdigest()
            model = self.base_model(
                state="verified", weight_license_status="verified",
                weight_files=[{"path": "llm/model.gguf", "sha256": digest, "license_status": "verified"}]
            )
            result = inspect_model_availability(model, root)
            self.assertTrue(result["available"])
            self.assertEqual(result["verified_files"], 1)
            tampered = self.base_model(state="verified", weight_license_status="verified", weight_files=[
                {"path": "llm/model.gguf", "sha256": "0" * 64, "license_status": "verified"}
            ])
            self.assertFalse(inspect_model_availability(tampered, root)["available"])

    def test_candidate_registry_is_unavailable_without_cached_reviewed_weights(self):
        root = Path(__file__).resolve().parents[1] / "local_ai" / "model_registry.json"
        registry = load_model_registry(root)
        results = inspect_local_ai(root.parent.parent / "models", registry)
        self.assertEqual(results["mode"], "local_only")
        self.assertFalse(any(x["available"] for x in results["models"]))
        self.assertEqual(results["ready_tasks"], [])
        self.assertFalse(results["external_network_used"])
        self.assertFalse(results["download_performed"])

    def test_inspection_is_read_only_and_does_not_use_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            model_root = Path(tmp) / "models-not-created"
            registry = {"schema_version": 1, "models": [self.base_model(state="discovered", weight_license_status="unverified")]}
            with patch("urllib.request.urlopen", side_effect=AssertionError("network access is forbidden")):
                report = inspect_local_ai(model_root, registry)
            self.assertFalse(model_root.exists())
            self.assertFalse(report["external_network_used"])
            self.assertFalse(report["download_performed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
