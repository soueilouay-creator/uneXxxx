from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from unexpected_runtime.local_ai_supervisor import (
    LocalAISupervisor,
    LocalSupervisorError,
    detect_hardware,
)


class LocalAISupervisorTests(unittest.TestCase):
    def test_hardware_profiles_are_selected_from_detected_vram_and_ram(self):
        with patch("unexpected_runtime.local_ai_supervisor._nvidia_devices", return_value=[
            {"name": "Test GPU", "memory_bytes": 24 * 1024**3, "vendor": "nvidia"}
        ]), patch("unexpected_runtime.local_ai_supervisor._rocm_devices", return_value=[]), \
             patch("unexpected_runtime.local_ai_supervisor._mac_devices", return_value=[]), \
             patch("unexpected_runtime.local_ai_supervisor._ram_bytes", return_value=64 * 1024**3):
            report = detect_hardware()
        self.assertEqual(report["profile"], "high_vram")
        self.assertIn("video", report["hardware_candidate_tasks"])
        self.assertIn("image", report["hardware_candidate_tasks"])
        self.assertFalse(report["probe_network_used"])

    def test_intel_graphics_is_reported_without_assuming_acceleration_memory(self):
        intel = [{"name": "Intel UHD Graphics", "memory_bytes": 0,
                  "vendor": "intel", "memory_reported": False}]
        with patch("unexpected_runtime.local_ai_supervisor._nvidia_devices", return_value=[]), \\
             patch("unexpected_runtime.local_ai_supervisor._rocm_devices", return_value=[]), \\
             patch("unexpected_runtime.local_ai_supervisor._mac_devices", return_value=[]), \\
             patch("unexpected_runtime.local_ai_supervisor._intel_devices", return_value=intel), \\
             patch("unexpected_runtime.local_ai_supervisor._ram_bytes", return_value=16 * 1024**3):
            report = detect_hardware()
        self.assertEqual(report["gpu_count"], 1)
        self.assertEqual(report["gpus"][0]["vendor"], "intel")
        self.assertIsNone(report["gpu_vram_total_gb"])
        self.assertEqual(report["profile"], "cpu_only")
        self.assertIn("llm", report["hardware_candidate_tasks"])
        self.assertNotIn("image", report["hardware_candidate_tasks"])

    def test_cpu_only_profile_does_not_claim_video_generation(self):
        with patch("unexpected_runtime.local_ai_supervisor._nvidia_devices", return_value=[]), \
             patch("unexpected_runtime.local_ai_supervisor._rocm_devices", return_value=[]), \
             patch("unexpected_runtime.local_ai_supervisor._mac_devices", return_value=[]), \
             patch("unexpected_runtime.local_ai_supervisor._ram_bytes", return_value=16 * 1024**3):
            report = detect_hardware()
        self.assertEqual(report["profile"], "cpu_only")
        self.assertIn("llm", report["hardware_candidate_tasks"])
        self.assertNotIn("video", report["hardware_candidate_tasks"])
        self.assertNotIn("image", report["hardware_candidate_tasks"])

    def test_supervisor_preflight_is_read_only_and_reports_missing_weights(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = Path(__file__).resolve().parents[1] / "local_ai" / "model_registry.json"
            config = root / "runtime_config.json"
            config.write_text(json.dumps({"schema_version": 1, "services": {}}), encoding="utf-8")
            supervisor = LocalAISupervisor(
                model_root=root / "models", registry_path=registry,
                config_path=config, state_dir=root / "state",
            )
            with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
                report = supervisor.preflight()
            self.assertEqual(report["mode"], "local_only")
            self.assertEqual(report["services"], [])
            self.assertFalse(report["ready_to_generate"])
            self.assertEqual(report["external_ai_api"], "disabled")
            self.assertFalse((root / "models").exists())
            self.assertFalse((root / "state").exists())

    def test_comfyui_service_must_be_offline_and_loopback_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "runtime_config.json"
            config.write_text("{}", encoding="utf-8")
            supervisor = LocalAISupervisor(config_path=config, state_dir=root / "state")
            executable = os.path.realpath(os.sys.executable)
            spec = {
                "kind": "comfyui",
                "command": [executable, "main.py", "--listen", "0.0.0.0", "--port", "8188",
                            "--offline", "--disable-partner-nodes"],
                "cwd": str(root),
                "port": 8188,
            }
            registry = supervisor._registry()
            result = supervisor._service_check("comfyui", spec, registry)
            self.assertFalse(result["ready"])
            self.assertTrue(any("loopback" in issue for issue in result["problems"]))

    def test_llm_service_cannot_start_without_verified_model_weights(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "runtime_config.json"
            config.write_text("{}", encoding="utf-8")
            supervisor = LocalAISupervisor(model_root=root / "models", config_path=config)
            spec = {
                "kind": "llm",
                "command": [os.path.realpath(os.sys.executable), "-m", "llama_cpp.server",
                            "--model", str(root / "models" / "unverified.gguf"),
                            "--host", "127.0.0.1", "--port", "8080"],
                "port": 8080,
                "model_id": "llama-cpp-server",
            }
            result = supervisor._service_check("llm", spec, supervisor._registry())
            self.assertFalse(result["ready"])
            self.assertTrue(any("not verified locally" in issue for issue in result["problems"]))

    def test_offline_environment_strips_api_keys_and_proxies(self):
        with tempfile.TemporaryDirectory() as tmp:
            supervisor = LocalAISupervisor(state_dir=tmp)
            with patch.dict(os.environ, {
                "OPENAI_API_KEY": "must-not-leak",
                "ANTHROPIC_API_KEY": "must-not-leak",
                "HTTPS_PROXY": "http://proxy.invalid",
                "HTTP_PROXY": "http://proxy.invalid",
            }, clear=False):
                environment = supervisor._offline_environment({"OMP_NUM_THREADS": "4"})
            self.assertEqual(environment["UNEXPECTED_AI_MODE"], "local_only")
            self.assertEqual(environment["HF_HUB_OFFLINE"], "1")
            self.assertEqual(environment["OMP_NUM_THREADS"], "4")
            self.assertNotIn("OPENAI_API_KEY", environment)
            self.assertNotIn("ANTHROPIC_API_KEY", environment)
            self.assertNotIn("HTTPS_PROXY", environment)
            self.assertNotIn("HTTP_PROXY", environment)

    def test_unknown_service_config_and_unsafe_config_fields_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "runtime_config.json"
            config.write_text(json.dumps({
                "schema_version": 1,
                "services": {"remote": {"kind": "remote", "command": ["https://example.com"]}},
            }), encoding="utf-8")
            supervisor = LocalAISupervisor(config_path=config, state_dir=root / "state")
            with self.assertRaises(LocalSupervisorError):
                supervisor._read_config()

    def test_ready_to_generate_requires_all_core_models_and_both_local_services(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            supervisor = LocalAISupervisor(
                model_root=root / "models",
                registry_path=root / "registry.json",
                config_path=root / "runtime_config.json",
                state_dir=root / "state",
            )
            registry = {"models": [
                {"model_id": "text-model", "task": "llm"},
                {"model_id": "image-model", "task": "image"},
                {"model_id": "voice-model", "task": "tts"},
                {"model_id": "music-model", "task": "music"},
                {"model_id": "video-model", "task": "video"},
            ]}
            hardware = {"hardware_candidate_tasks": ["llm", "image", "tts", "music", "video", "asr"]}
            config = {"services": {"llm": {}, "comfyui": {}}}

            def report_for(available):
                return {"models": [
                    {"model_id": item["model_id"], "available": item["model_id"] in available}
                    for item in registry["models"]
                ]}

            with patch("unexpected_runtime.local_ai_supervisor.detect_hardware", return_value=hardware), \
                 patch("unexpected_runtime.local_ai_supervisor.inspect_local_ai", return_value=report_for({"text-model"})), \
                 patch.object(supervisor, "_registry", return_value=registry), \
                 patch.object(supervisor, "_read_config", return_value=config), \
                 patch.object(supervisor, "_service_check", return_value={"service": "llm", "ready": True}):
                report = supervisor.preflight()
            self.assertFalse(report["ready_to_generate"])
            self.assertEqual(report["pipeline_readiness"]["missing_model_tasks"],
                             ["image", "music", "tts", "video"])

            all_available = {item["model_id"] for item in registry["models"]}
            with patch("unexpected_runtime.local_ai_supervisor.detect_hardware", return_value=hardware), \
                 patch("unexpected_runtime.local_ai_supervisor.inspect_local_ai", return_value=report_for(all_available)), \
                 patch.object(supervisor, "_registry", return_value=registry), \
                 patch.object(supervisor, "_read_config", return_value=config), \
                 patch.object(supervisor, "_service_check", side_effect=lambda name, spec, reg: {"service": name, "ready": True}):
                report = supervisor.preflight()
            self.assertTrue(report["ready_to_generate"])
            self.assertEqual(report["pipeline_readiness"]["missing_services"], [])


    def test_illustrated_story_fallback_removes_native_video_model_from_readiness_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            supervisor = LocalAISupervisor(
                model_root=root / "models",
                registry_path=root / "registry.json",
                config_path=root / "runtime_config.json",
                state_dir=root / "state",
            )
            media_config = root / "media_workflows.json"
            media_config.write_text(json.dumps({
                "schema_version": 1,
                "tasks": {},
                "video_fallback": "illustrated_story",
            }), encoding="utf-8")
            registry = {"models": [
                {"model_id": "text-model", "task": "llm"},
                {"model_id": "image-model", "task": "image"},
                {"model_id": "voice-model", "task": "tts"},
                {"model_id": "music-model", "task": "music"},
                {"model_id": "video-model", "task": "video"},
            ]}
            hardware = {"hardware_candidate_tasks": ["llm", "image", "tts", "music", "asr"]}
            config = {"services": {"llm": {}, "comfyui": {}}}
            available = {"text-model", "image-model", "voice-model", "music-model"}
            model_report = {"models": [
                {"model_id": item["model_id"], "available": item["model_id"] in available}
                for item in registry["models"]
            ]}
            with (
                patch.dict(os.environ, {"UNEXPECTED_MEDIA_WORKFLOWS": str(media_config)}),
                patch("unexpected_runtime.local_ai_supervisor.detect_hardware", return_value=hardware),
                patch("unexpected_runtime.local_ai_supervisor.inspect_local_ai", return_value=model_report),
                patch.object(supervisor, "_registry", return_value=registry),
                patch.object(supervisor, "_read_config", return_value=config),
                patch.object(supervisor, "_service_check", side_effect=lambda name, spec, reg: {"service": name, "ready": True}),
            ):
                report = supervisor.preflight()
            self.assertTrue(report["ready_to_generate"])
            self.assertEqual(report["video_fallback_mode"], "illustrated_story")
            self.assertNotIn("video", report["pipeline_readiness"]["required_model_tasks"])
            self.assertFalse(next(item for item in report["model_tasks"] if item["task"] == "video")["ready"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
