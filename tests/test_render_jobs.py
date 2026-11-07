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

    def test_unconfigured_dispatcher_fails_closed_without_local_fallback(self):
        from unexpected_runtime.render_jobs import DockerRenderDispatcher
        dispatcher = DockerRenderDispatcher(enabled=False)
        with self.assertRaises(RenderDispatcherUnavailable):
            dispatcher.run(self.input, self.output, self.manifest)


if __name__ == "__main__":
    unittest.main()
