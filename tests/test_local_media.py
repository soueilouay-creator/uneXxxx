from __future__ import annotations
import hashlib, json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from unexpected_runtime.local_media import LocalMediaError, LocalMediaPipeline

class FakeComfy:
    def __init__(self, workflow_root):
        self.workflow_root = Path(workflow_root).resolve()
        self.queued = 0
        self.waited = []
    def queue_workflow(self, *args, **kwargs):
        self.queued += 1
        return {"prompt_id": "12345678-abcd"}
    def wait_for_result(self, prompt_id, **kwargs):
        self.waited.append(prompt_id)
        return {"prompt_id": prompt_id, "outputs": {"3": {"images": [{"filename": "img.png", "subfolder": "", "type": "output"}]}}}
    def collect_outputs(self, result, destination):
        folder = Path(destination)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "node-3-img.png"
        path.write_bytes(b"image-pixels" * 400)
        return [{"path": path.name, "kind": "images", "mime_type": "image/png"}]
    def probe(self):
        return {"status": "available", "local": True}

class LocalMediaTests(unittest.TestCase):
    def _fixture(self, root):
        config_dir = root / "config"
        workflow_root = config_dir / "workflows"
        workflow_root.mkdir(parents=True)
        models = root / "models"
        models.mkdir()
        weights = models / "test.gguf"
        weights.write_bytes(b"verified-local-weight")
        workflow = {"3": {"class_type": "CLIPTextEncode", "inputs": {"text": "placeholder"}}}
        workflow_path = workflow_root / "image.json"
        workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
        wf_hash = hashlib.sha256(workflow_path.read_bytes()).hexdigest()
        weight_hash = hashlib.sha256(weights.read_bytes()).hexdigest()
        model = {
            "model_id": "image-test", "task": "image",
            "repository": "https://github.com/example/image-runtime",
            "revision": "0123456789abcdef0123456789abcdef01234567",
            "runtime": "test-local", "repository_license": "MIT",
            "weight_license_status": "verified", "state": "verified",
            "weight_files": [{"path": "test.gguf", "sha256": weight_hash, "license_status": "verified"}],
        }
        registry = root / "registry.json"
        registry.write_text(json.dumps({"schema_version": 1, "models": [model]}), encoding="utf-8")
        config = config_dir / "media_workflows.json"
        config.write_text(json.dumps({
            "schema_version": 1, "comfyui_url": "http://127.0.0.1:8188",
            "workflow_root": "workflows",
            "tasks": {"image": {
                "model_id": "image-test", "workflow_file": "image.json",
                "workflow_sha256": wf_hash, "allowed_node_types": ["CLIPTextEncode"],
                "input_bindings": {"prompt": {"node_id": "3", "field": "text"}},
                "minimum_hardware": {"ram_gb": 8, "vram_gb": 8, "disk_gb": 1},
                "timeout_seconds": 30,
            }},
        }), encoding="utf-8")
        hardware = lambda: {"ram_total_gb": 32, "gpu_vram_total_gb": 12, "profile": "mid_vram"}
        client = FakeComfy(workflow_root)
        pipeline = LocalMediaPipeline(config_path=config, registry_path=registry,
            model_root=models, work_root=root / "creator", comfy_client=client,
            hardware_probe=hardware)
        return pipeline, client, config, wf_hash, root

    def test_render_rejects_missing_video_segments_instead_of_truncating_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            pipeline, *_ = self._fixture(Path(tmp))
            with patch("unexpected_runtime.local_media.shutil.which",
                       side_effect=["/usr/bin/ffmpeg", "/usr/bin/ffprobe"]):
                with self.assertRaisesRegex(LocalMediaError, "one verified image and one verified video segment"):
                    pipeline._render(
                        "12345678-abcd", {},
                        [{"duration_seconds": 5.0}, {"duration_seconds": 5.0}],
                        {"images": [{}], "videos": []},
                        "1\\n00:00:00,000 --> 00:00:01,000\\nTest.\\n",
                        motion_mode="illustrated_story",
                    )


    def test_render_rejects_parent_symlink_before_reading_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pipeline, *_ = self._fixture(root)
            project = pipeline._project("12345678-abcd")
            outside = root / "outside"
            outside.mkdir()
            (outside / "narration.wav").write_bytes(b"outside narration")
            try:
                (project / "linked").symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Directory symlinks are unavailable on this platform.")
            with patch("unexpected_runtime.local_media.shutil.which",
                       side_effect=["/usr/bin/ffmpeg", "/usr/bin/ffprobe"]), \
                 patch("unexpected_runtime.local_media._digest",
                       side_effect=AssertionError("Escaping file must be rejected before it is read")) as digest:
                with self.assertRaisesRegex(LocalMediaError, "symbolic link"):
                    pipeline._render(
                        "12345678-abcd", {}, [],
                        {"images": [], "videos": [],
                         "narration": {"path": "linked/narration.wav", "sha256": "0" * 64},
                         "music": {"path": "music.wav", "sha256": "0" * 64}},
                        "1\\n00:00:00,000 --> 00:00:01,000\\nTest.\\n",
                        motion_mode="illustrated_story",
                    )
                digest.assert_not_called()

    def test_render_rejects_audio_assets_with_wrong_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pipeline, *_ = self._fixture(root)
            project = pipeline._project("12345678-abcd")
            (project / "narration.wav").write_bytes(b"not-audio")
            (project / "music.wav").write_bytes(b"not-audio")
            with patch("unexpected_runtime.local_media.shutil.which",
                       side_effect=["/usr/bin/ffmpeg", "/usr/bin/ffprobe"]):
                with self.assertRaisesRegex(LocalMediaError, "Narration asset failed checksum verification"):
                    pipeline._render(
                        "12345678-abcd", {}, [],
                        {"images": [], "videos": [],
                         "narration": {"path": "narration.wav", "sha256": "0" * 64},
                         "music": {"path": "music.wav", "sha256": "0" * 64}},
                        "1\\n00:00:00,000 --> 00:00:01,000\\nTest.\\n",
                        motion_mode="illustrated_story",
                    )

    def test_local_mode_is_mandatory_and_never_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            pipeline, client, *_ = self._fixture(Path(tmp))
            with patch.dict(os.environ, {"UNEXPECTED_AI_MODE": "cloud"}, clear=False):
                result = pipeline.preflight()
                self.assertFalse(result["ready"])
                self.assertEqual(result["external_ai_api"], "disabled")
                with self.assertRaises(LocalMediaError):
                    pipeline.generate_asset("image", "12345678-abcd", "scene-1", "An old lighthouse")

    def test_queued_generation_resumes_and_cached_asset_is_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            pipeline, client, config, workflow_hash, root = self._fixture(Path(tmp))
            project_id, prompt = "12345678-abcd", "An original lighthouse at sunrise"
            project = pipeline._project(project_id)
            state_path = project / "media_state.json"
            prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
            state_path.write_text(json.dumps({"schema_version": 1, "assets": {
                "image:scene-1": {"status": "queued", "task": "image",
                    "prompt_id": "12345678-abcd", "prompt_sha256": prompt_hash,
                    "workflow_sha256": workflow_hash, "provider": "comfyui-local"}
            }}), encoding="utf-8")
            with patch.dict(os.environ, {"UNEXPECTED_AI_MODE": "local_only"}, clear=False):
                first = pipeline.generate_asset("image", project_id, "scene-1", prompt)
                second = pipeline.generate_asset("image", project_id, "scene-1", prompt)
            self.assertEqual(first["status"], "completed")
            self.assertEqual(second["status"], "reused")
            self.assertEqual(client.queued, 0)
            self.assertEqual(client.waited, ["12345678-abcd"])
            self.assertTrue((project / first["path"]).is_file())

    def test_unverified_model_weights_block_generation_before_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            pipeline, client, config, workflow_hash, root = self._fixture(Path(tmp))
            registry = json.loads(pipeline.registry_path.read_text())
            registry["models"][0]["weight_license_status"] = "unverified"
            pipeline.registry_path.write_text(json.dumps(registry), encoding="utf-8")
            with patch.dict(os.environ, {"UNEXPECTED_AI_MODE": "local_only"}, clear=False):
                with self.assertRaises(LocalMediaError):
                    pipeline.generate_asset("image", "12345678-abcd", "scene-2", "A mountain village")
            self.assertEqual(client.queued, 0)

if __name__ == "__main__":
    unittest.main(verbosity=2)
