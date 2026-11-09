from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from unexpected_runtime.local_bootstrap import LocalModelBootstrap, LocalModelBootstrapError


class FakeResponse:
    def __init__(self, body: bytes, *, status=200, headers=None, url="https://huggingface.co/model/file"):
        self.body = body
        self.status = status
        self.headers = headers or {}
        self.url = url

    def read(self, size=-1):
        if size < 0:
            value, self.body = self.body, b""
            return value
        value, self.body = self.body[:size], self.body[size:]
        return value

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class LocalModelBootstrapTests(unittest.TestCase):
    def _fixture(self, root: Path, *, hardware=None, license_status="verified", digest=None):
        payload = b"local-model-weights"
        expected = digest or hashlib.sha256(payload).hexdigest()
        model_root = root / "models"
        registry_path = root / "registry.json"
        url = "https://huggingface.co/org/model/resolve/0123456789abcdef0123456789abcdef01234567/model.gguf"
        import json
        registry_path.write_text(json.dumps({
            "schema_version": 1,
            "models": [{
                "model_id": "tiny-local-llm",
                "task": "llm",
                "repository": "https://github.com/ggml-org/llama.cpp",
                "revision": "0123456789abcdef0123456789abcdef01234567",
                "runtime": "llama-server",
                "repository_license": "MIT",
                "weight_license_status": license_status,
                "state": "verified",
                "hardware_requirements": {"ram_gb": 4, "vram_gb": 0, "disk_gb": 0.001},
                "weight_files": [{
                    "path": "llm/model.gguf",
                    "sha256": expected,
                    "license_status": license_status,
                    "source_url": url,
                    "size_bytes": len(payload),
                    "max_size_bytes": 1024,
                }],
            }],
        }), encoding="utf-8")
        probe = hardware or (lambda: {
            "platform": "test", "profile": "cpu_only", "ram_total_gb": 8,
            "gpu_vram_total_gb": None, "hardware_candidate_tasks": ["llm"],
        })
        return LocalModelBootstrap(model_root=model_root, registry_path=registry_path,
                                   hardware_probe=probe), model_root, payload, url

    def test_plan_is_read_only_and_selects_only_verified_hardware_compatible_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            bootstrap, _, _, _ = self._fixture(Path(tmp))
            report = bootstrap.plan()
            self.assertEqual(report["mode"], "bootstrap_plan")
            self.assertFalse(report["network_used"])
            self.assertEqual([x["model_id"] for x in report["models"] if x["installable"]],
                             ["tiny-local-llm"])

    def test_install_requires_explicit_network_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            bootstrap, _, _, _ = self._fixture(Path(tmp))
            calls = []
            bootstrap.opener = lambda request, timeout=0: calls.append(request)
            with self.assertRaises(LocalModelBootstrapError):
                bootstrap.install("tiny-local-llm")
            self.assertEqual(calls, [])

    def test_install_verifies_hash_and_atomically_places_model_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            bootstrap, model_root, payload, _ = self._fixture(Path(tmp))
            bootstrap.opener = lambda request, timeout=0: FakeResponse(
                payload, headers={"Content-Length": str(len(payload))})
            result = bootstrap.install("tiny-local-llm", allow_network=True)
            target = model_root / "llm" / "model.gguf"
            self.assertEqual(result["status"], "installed")
            self.assertTrue(target.is_file())
            self.assertEqual(target.read_bytes(), payload)
            self.assertFalse(target.with_suffix(".gguf.part").exists())

    def test_install_resumes_partial_download_with_range_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            bootstrap, model_root, payload, _ = self._fixture(Path(tmp))
            target = model_root / "llm" / "model.gguf"
            target.parent.mkdir(parents=True)
            partial = target.with_suffix(".gguf.part")
            partial.write_bytes(payload[:5])
            calls = []

            def opener(request, timeout=0):
                calls.append(request.get_header("Range"))
                return FakeResponse(payload[5:], status=206,
                    headers={"Content-Range": f"bytes 5-{len(payload)-1}/{len(payload)}",
                             "Content-Length": str(len(payload)-5)})

            bootstrap.opener = opener
            result = bootstrap.install("tiny-local-llm", allow_network=True)
            self.assertEqual(result["status"], "installed")
            self.assertEqual(calls, ["bytes=5-"])
            self.assertEqual(target.read_bytes(), payload)

    def test_unverified_licence_and_incompatible_hardware_fail_before_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            bootstrap, _, _, _ = self._fixture(Path(tmp), license_status="unverified")
            calls = []
            bootstrap.opener = lambda request, timeout=0: calls.append(request)
            with self.assertRaises(LocalModelBootstrapError):
                bootstrap.install("tiny-local-llm", allow_network=True)
            self.assertEqual(calls, [])

        with tempfile.TemporaryDirectory() as tmp:
            low_ram = lambda: {"platform": "test", "profile": "cpu_only",
                "ram_total_gb": 2, "gpu_vram_total_gb": None, "hardware_candidate_tasks": []}
            bootstrap, _, _, _ = self._fixture(Path(tmp), hardware=low_ram)
            calls = []
            bootstrap.opener = lambda request, timeout=0: calls.append(request)
            with self.assertRaises(LocalModelBootstrapError):
                bootstrap.install("tiny-local-llm", allow_network=True)
            self.assertEqual(calls, [])

    def test_checksum_mismatch_never_installs_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            bootstrap, model_root, payload, _ = self._fixture(Path(tmp), digest="0" * 64)
            bootstrap.opener = lambda request, timeout=0: FakeResponse(
                payload, headers={"Content-Length": str(len(payload))})
            with self.assertRaises(LocalModelBootstrapError):
                bootstrap.install("tiny-local-llm", allow_network=True)
            self.assertFalse((model_root / "llm" / "model.gguf").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
