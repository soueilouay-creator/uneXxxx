from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from unexpected_runtime.comfyui_local import LocalComfyUIClient, LocalComfyUIError


class FakeResponse:
    def __init__(self, body, content_type="application/json"):
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.headers = {"Content-Type": content_type}
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, size=-1): return self.body if size < 0 else self.body[:size]


class LocalComfyUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workflow_root = self.root / "workflows"
        self.workflow_root.mkdir()
        self.workflow_path = self.workflow_root / "image.json"
        self.workflow = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
            "2": {"class_type": "SaveImage", "inputs": {"filename_prefix": "creator/test"}},
        }
        self.workflow_path.write_text(json.dumps(self.workflow), encoding="utf-8")
        self.digest = hashlib.sha256(self.workflow_path.read_bytes()).hexdigest()
        self.client = LocalComfyUIClient(workflow_root=self.workflow_root)
    def tearDown(self):
        self.temp.cleanup()

    def test_only_literal_loopback_urls_are_accepted(self):
        for url in ("https://127.0.0.1:8188", "http://localhost:8188",
                    "http://192.168.1.4:8188", "http://user:pass@127.0.0.1:8188",
                    "http://127.0.0.1:8188/base"):
            with self.subTest(url=url):
                with self.assertRaises(LocalComfyUIError):
                    LocalComfyUIClient(url, workflow_root=self.workflow_root)
        ipv6 = LocalComfyUIClient("http://[::1]:8188", workflow_root=self.workflow_root)
        self.assertEqual(ipv6.base_url, "http://[::1]:8188")

    def test_workflow_must_be_pinned_inside_configured_root(self):
        with self.assertRaises(LocalComfyUIError):
            self.client.queue_workflow(self.workflow_path, expected_sha256="0" * 64,
                                       allowed_node_types={"CheckpointLoaderSimple", "SaveImage"})
        outside = self.root / "outside.json"
        outside.write_text(self.workflow_path.read_text(), encoding="utf-8")
        with self.assertRaises(LocalComfyUIError):
            self.client.queue_workflow(outside, expected_sha256=self.digest,
                                       allowed_node_types={"CheckpointLoaderSimple", "SaveImage"})

    def test_workflow_rejects_unapproved_or_cloud_nodes_and_remote_urls(self):
        with self.assertRaises(LocalComfyUIError):
            self.client.queue_workflow(self.workflow_path, expected_sha256=self.digest,
                                       allowed_node_types={"SaveImage"})
        bad = {"1": {"class_type": "PartnerVideoAPI", "inputs": {}}}
        self.workflow_path.write_text(json.dumps(bad), encoding="utf-8")
        digest = hashlib.sha256(self.workflow_path.read_bytes()).hexdigest()
        with self.assertRaises(LocalComfyUIError):
            self.client.queue_workflow(self.workflow_path, expected_sha256=digest,
                                       allowed_node_types={"PartnerVideoAPI"})
        bad = {"1": {"class_type": "LoadImage", "inputs": {"url": "https://example.com/a.png"}}}
        self.workflow_path.write_text(json.dumps(bad), encoding="utf-8")
        digest = hashlib.sha256(self.workflow_path.read_bytes()).hexdigest()
        with self.assertRaises(LocalComfyUIError):
            self.client.queue_workflow(self.workflow_path, expected_sha256=digest,
                                       allowed_node_types={"LoadImage"})

    def test_queue_request_has_no_proxy_or_auth_and_uses_only_loopback(self):
        response = FakeResponse({"prompt_id": "12345678-abcd"})
        opener = MagicMock()
        opener.open.return_value = response
        with patch("unexpected_runtime.comfyui_local.urllib.request.build_opener", return_value=opener) as factory:
            result = self.client.queue_workflow(
                self.workflow_path, expected_sha256=self.digest,
                allowed_node_types={"CheckpointLoaderSimple", "SaveImage"})
        self.assertEqual(result["prompt_id"], "12345678-abcd")
        req = opener.open.call_args.args[0]
        self.assertEqual(req.full_url, "http://127.0.0.1:8188/prompt")
        self.assertIsNone(req.get_header("Authorization"))
        handlers = factory.call_args.args
        self.assertTrue(any(type(item).__name__ == "ProxyHandler" and item.proxies == {} for item in handlers))
        self.assertTrue(any(type(item).__name__ == "_NoRedirect" for item in handlers))

    def test_history_wait_returns_completed_local_outputs(self):
        response = FakeResponse({"12345678-abcd": {"status": {"status_str": "success", "completed": True},
                                                   "outputs": {"2": {"images": [{"filename": "out.png", "type": "output"}]}}}})
        with patch.object(self.client, "_request", return_value=(response.body, "application/json")):
            result = self.client.wait_for_result("12345678-abcd", timeout_seconds=2, poll_interval=0.1)
        self.assertEqual(result["status"], "completed")
        self.assertIn("2", result["outputs"])

    def test_collect_outputs_saves_verified_file_and_rejects_path_traversal(self):
        dest = self.root / "project"
        image = b"valid-test-image-data"
        with patch.object(self.client, "_request", return_value=(image, "image/png")) as request:
            outputs = self.client.collect_outputs(
                {"outputs": {"2": {"images": [{"filename": "scene.png", "subfolder": "generated", "type": "output"}]}}},
                dest)
        saved = dest / "generated" / "node-2-scene.png"
        self.assertTrue(saved.is_file())
        self.assertEqual(outputs[0]["sha256"], hashlib.sha256(image).hexdigest())
        with self.assertRaises(LocalComfyUIError):
            self.client.collect_outputs(
                {"outputs": {"2": {"images": [{"filename": "../escape.png", "type": "output"}]}}},
                dest / "other")
        self.assertEqual(request.call_args.args[1].split("?")[0], "/view")

    def test_no_outputs_is_not_reported_as_success(self):
        with self.assertRaises(LocalComfyUIError):
            self.client.collect_outputs({"outputs": {}}, self.root / "empty")


if __name__ == "__main__":
    unittest.main(verbosity=2)
