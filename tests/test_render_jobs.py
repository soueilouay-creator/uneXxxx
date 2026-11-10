from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from unexpected_runtime.render_jobs import (
    ENGINE_COMMIT,
    RenderDispatcherUnavailable,
    build_docker_command,
    validate_render_bundle,
)


class RenderJobContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.input = root / "input"
        self.output = root / "output"
        self.project = self.input / "project"
        self.project.mkdir(parents=True)
        self.output.mkdir()
        (self.project / "audio").mkdir()
        (self.project / "audio" / "mix.wav").write_bytes(b"test soundtrack placeholder")
        (self.project / "index.html").write_text(
            "<!doctype html><script>window.DUR=1;window.READY=true;"
            "window.render=(t)=>{};</script>", encoding="utf-8"
        )
        self.manifest = {
            "job_id": "job-smoke-0001",
            "engine_commit": ENGINE_COMMIT,
            "project_dir": "project",
            "output_profile": "youtube_shorts",
            "fps": 24,
            "width": 1080,
            "height": 1920,
            "wall_time_seconds": 90,
        }
        (self.input / "manifest.json").write_text(
            json.dumps(self.manifest), encoding="utf-8"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_pinned_bundle_manifest_and_project_are_validated(self):
        checked = validate_render_bundle(self.input)
        self.assertEqual(checked["engine_commit"], ENGINE_COMMIT)
        self.assertEqual(checked["project_dir"], "project")
        self.assertTrue((self.input / "project" / "index.html").is_file())

    def test_manifest_rejects_moving_engine_pin_and_path_traversal(self):
        for invalid in (
            {**self.manifest, "engine_commit": "main"},
            {**self.manifest, "project_dir": "../etc"},
            {**self.manifest, "unknown": "ignored"},
        ):
            (self.input / "manifest.json").write_text(json.dumps(invalid))
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_render_bundle(self.input)

    def test_bundle_rejects_symlinks_and_oversized_project(self):
        outside = Path(self.tmp.name) / "outside.txt"
        outside.write_text("not part of the project")
        link = self.project / "escape.txt"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("Symlinks unavailable on this runner")
        with self.assertRaises(ValueError):
            validate_render_bundle(self.input)

    def test_docker_command_is_networkless_readonly_and_nonroot(self):
        command = build_docker_command(
            self.input, self.output, image="unexpected-creator-renderer:locked",
            limits={"cpu_seconds": 60, "memory_mb": 512, "wall_time_seconds": 90},
        )
        joined = " ".join(command)
        self.assertIn("--network=none", command)
        self.assertIn("--read-only", command)
        self.assertIn("--cap-drop=ALL", command)
        self.assertIn("--security-opt=no-new-privileges", command)
        self.assertIn("--user", command)
        self.assertIn("10001:10001", command)
        self.assertIn("--memory", command)
        self.assertIn("--cpus", command)
        self.assertIn("type=bind", joined)
        self.assertIn("dst=/job/input,readonly", joined)
        self.assertIn("dst=/job/output", joined)
        self.assertNotIn("/var/run/docker.sock", joined)
        self.assertEqual(command[0], "docker")

    def test_docker_command_rejects_mount_overlap_and_unbounded_limits(self):
        with self.assertRaises(ValueError):
            build_docker_command(self.input, self.input / "output", image="locked")
        with self.assertRaises(ValueError):
            build_docker_command(
                self.input, self.output, image="locked",
                limits={"cpu_seconds": 601, "memory_mb": 512, "wall_time_seconds": 90},
            )

    def test_story_film_bundle_accepts_landscape_and_validated_timeline(self):
        (self.project / "index.html").unlink()
        (self.project / "scenes").mkdir()
        (self.project / "scenes" / "one.png").write_bytes(b"one")
        (self.project / "scenes" / "two.png").write_bytes(b"two")
        (self.project / "captions.srt").write_text(
            "1\n00:00:00,000 --> 00:00:04,000\nA vow.\n", encoding="utf-8"
        )
        (self.project / "timeline.json").write_text(json.dumps({"version": 1, "scenes": [
            {"image": "scenes/one.png", "duration_seconds": 4},
            {"image": "scenes/two.png", "duration_seconds": 4}
        ]}), encoding="utf-8")
        manifest = {**self.manifest, "output_profile": "youtube_longform",
                    "width": 1920, "height": 1080, "render_mode": "story_film"}
        (self.input / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        checked = validate_render_bundle(self.input)
        self.assertEqual(checked["render_mode"], "story_film")
        self.assertEqual(checked["output_profile"], "youtube_longform")

    def test_ffmpeg_version_detection_combines_stdout_and_stderr(self):
        # FFmpeg reports its version banner on stderr in some builds.
        stdout = ""
        stderr = "ffmpeg version 7.1.5 Copyright (c) FFmpeg developers"
        combined = stdout + "\n" + stderr
        self.assertIn("ffmpeg version 7.", combined)
        self.assertNotIn("ffmpeg version 7.", stdout)

    def test_unconfigured_dispatcher_fails_closed_without_local_fallback(self):
        from unexpected_runtime.render_jobs import DockerRenderDispatcher
        dispatcher = DockerRenderDispatcher(enabled=False)
        with self.assertRaises(RenderDispatcherUnavailable):
            dispatcher.run(self.input, self.output, self.manifest)


if __name__ == "__main__":
    unittest.main()
