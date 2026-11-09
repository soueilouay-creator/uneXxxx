from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from unexpected_runtime.local_media import LocalMediaPipeline


class OfflineMediaFixture:
    """Deterministic local fixture provider; it is not an AI model or inference claim."""

    def __init__(self, workflow_root: Path):
        self.workflow_root = workflow_root.resolve()
        self.current_task = None
        self.queued = 0

    def queue_workflow(self, workflow_path, **kwargs):
        self.current_task = Path(workflow_path).stem
        self.queued += 1
        return {"prompt_id": f"local-fixture-{self.queued:08d}"}

    def wait_for_result(self, prompt_id, **kwargs):
        return {"prompt_id": prompt_id}

    def collect_outputs(self, result, destination):
        folder = Path(destination)
        folder.mkdir(parents=True, exist_ok=True)
        task = self.current_task
        if task == "image":
            name, kind, mime = "frame.png", "images", "image/png"
            command = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=512x512:rate=1",
                "-frames:v", "1", str(folder / name),
            ]
        elif task == "video":
            name, kind, mime = "clip.mp4", "videos", "video/mp4"
            command = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=24",
                "-t", "4", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                str(folder / name),
            ]
        elif task in {"tts", "music"}:
            name, kind, mime = "track.wav", "audio", "audio/wav"
            frequency = "440" if task == "tts" else "220"
            command = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", f"sine=frequency={frequency}:sample_rate=44100",
                "-t", "8", "-c:a", "pcm_s16le", str(folder / name),
            ]
        else:
            raise AssertionError(f"Unexpected task: {task}")
        subprocess.run(command, check=True, capture_output=True, timeout=60)
        return [{"path": name, "kind": kind, "mime_type": mime}]

    def probe(self):
        return {"status": "available", "local": True}


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "FFmpeg and ffprobe are required for the offline media integration test")
class OfflineLocalMediaEndToEndTests(unittest.TestCase):
    def test_local_image_video_narration_music_assembly_and_mp4_qa(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_root = root / "local_ai"
            workflow_root = config_root / "workflows"
            workflow_root.mkdir(parents=True)
            model_root = root / "models"
            model_root.mkdir()
            tasks = {}
            models = []
            for task in ("image", "video", "tts", "music"):
                model_id = f"{task}-fixture"
                weight_path = model_root / f"{task}.bin"
                weight_path.write_bytes((task + "-fixture-weights").encode())
                workflow_path = workflow_root / f"{task}.json"
                workflow_path.write_text(json.dumps({
                    "3": {"class_type": "FixturePrompt", "inputs": {"text": "placeholder"}}
                }), encoding="utf-8")
                workflow_hash = hashlib.sha256(workflow_path.read_bytes()).hexdigest()
                weight_hash = hashlib.sha256(weight_path.read_bytes()).hexdigest()
                models.append({
                    "model_id": model_id,
                    "task": task,
                    "repository": "https://github.com/example/local-fixture",
                    "revision": "0123456789abcdef0123456789abcdef01234567",
                    "runtime": "deterministic-offline-test-fixture",
                    "repository_license": "MIT",
                    "weight_license_status": "verified",
                    "state": "verified",
                    "weight_files": [{
                        "path": weight_path.name,
                        "sha256": weight_hash,
                        "license_status": "verified",
                    }],
                })
                tasks[task] = {
                    "model_id": model_id,
                    "workflow_file": f"{task}.json",
                    "workflow_sha256": workflow_hash,
                    "allowed_node_types": ["FixturePrompt"],
                    "input_bindings": {"prompt": {"node_id": "3", "field": "text"}},
                    "minimum_hardware": {"ram_gb": 8, "vram_gb": 8, "disk_gb": 1},
                    "timeout_seconds": 60,
                }

            registry_path = root / "registry.json"
            registry_path.write_text(json.dumps({"schema_version": 1, "models": models}),
                                     encoding="utf-8")
            config_path = config_root / "media_workflows.json"
            config_path.write_text(json.dumps({
                "schema_version": 1,
                "comfyui_url": "http://127.0.0.1:8188",
                "workflow_root": "workflows",
                "tasks": tasks,
            }), encoding="utf-8")

            hardware = lambda: {
                "ram_total_gb": 32,
                "gpu_vram_total_gb": 12,
                "profile": "mid_vram",
                "hardware_candidate_tasks": ["llm", "image", "video", "tts", "music", "asr"],
            }
            client = OfflineMediaFixture(workflow_root)
            pipeline = LocalMediaPipeline(
                config_path=config_path,
                registry_path=registry_path,
                model_root=model_root,
                work_root=root / "creator",
                comfy_client=client,
                hardware_probe=hardware,
            )

            script = "A small light appears. The signal becomes a path."
            storyboard = {
                "narration_script": script,
                "music_prompt": "Original gentle ambient instrumental, no vocals.",
                "scenes": [
                    {"scene_id": "scene-001", "visual_prompt": "A small light in a dark room.",
                     "motion_prompt": "The light slowly moves.", "duration_seconds": 4},
                    {"scene_id": "scene-002", "visual_prompt": "A path of lights at dawn.",
                     "motion_prompt": "The camera glides forward.", "duration_seconds": 4},
                ],
            }
            voice = {
                "narration_text": script,
                "captions_srt": (
                    "1\n00:00:00,000 --> 00:00:03,800\nA small light appears.\n\n"
                    "2\n00:00:04,000 --> 00:00:07,800\nThe signal becomes a path.\n"
                ),
            }

            with patch.dict(os.environ, {"UNEXPECTED_AI_MODE": "local_only"}, clear=False):
                preflight = pipeline.preflight(probe_service=True)
                self.assertTrue(preflight["ready"], preflight)
                result = pipeline.produce("12345678-abcd", {
                    "channel_profile": {"youtube": {"format": "shorts", "aspect_ratio": "9:16"}}
                }, json.dumps(storyboard), json.dumps(voice))

            self.assertEqual(result["status"], "completed", result)
            self.assertTrue(result["video_rendered"])
            self.assertTrue(result["qa_passed"])
            self.assertEqual(result["external_ai_api"], "disabled")
            self.assertFalse(result["publishing_performed"])
            self.assertEqual(client.queued, 6)
            render = result["render"]
            master = root / "creator" / "projects" / "12345678-abcd" / render["path"]
            self.assertTrue(master.is_file())
            self.assertGreater(master.stat().st_size, 4096)
            self.assertEqual(render["profile"], "youtube_shorts")
            self.assertEqual((render["width"], render["height"]), (1080, 1920))
            self.assertEqual(render["storyboard_stills_count"], 2)
            self.assertEqual(render["qa"]["status"], "passed")
            self.assertEqual(render["qa"]["checks"]["captions"]["cue_count"], 2)
            self.assertEqual(render["qa"]["checks"]["audio_stream"]["status"], "passed")

            # A machine without a video diffusion model should still create an
            # explicitly labelled illustrated story using verified local stills.
            fallback_registry = {"schema_version": 1, "models": [
                model for model in models if model["task"] != "video"
            ]}
            registry_path.write_text(json.dumps(fallback_registry), encoding="utf-8")
            fallback_tasks = dict(tasks)
            fallback_tasks.pop("video")
            config_path.write_text(json.dumps({
                "schema_version": 1,
                "comfyui_url": "http://127.0.0.1:8188",
                "workflow_root": "workflows",
                "video_fallback": "illustrated_story",
                "tasks": fallback_tasks,
            }), encoding="utf-8")
            fallback_pipeline = LocalMediaPipeline(
                config_path=config_path,
                registry_path=registry_path,
                model_root=model_root,
                work_root=root / "creator",
                comfy_client=client,
                hardware_probe=hardware,
            )
            with patch.dict(os.environ, {"UNEXPECTED_AI_MODE": "local_only"}, clear=False):
                fallback_preflight = fallback_pipeline.preflight(probe_service=True)
                self.assertTrue(fallback_preflight["ready"], fallback_preflight)
                fallback_result = fallback_pipeline.produce(
                    "87654321-abcd",
                    {"channel_profile": {"youtube": {"format": "shorts", "aspect_ratio": "9:16"}}},
                    json.dumps(storyboard),
                    json.dumps(voice),
                )
            self.assertEqual(fallback_result["status"], "completed", fallback_result)
            self.assertEqual(fallback_result["video_mode"], "illustrated_story_procedural")
            self.assertEqual(fallback_result["render"]["storyboard_stills_count"], 2)
            self.assertTrue(fallback_result["qa_passed"])
            self.assertEqual(client.queued, 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
