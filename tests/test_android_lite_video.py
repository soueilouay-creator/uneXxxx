from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from unexpected_runtime.android_lite_video import (
    AndroidLiteVideoCreator,
    AndroidLiteVideoError,
)


SCRIPT = (
    "A quiet town wakes to find every clock stopped at midnight. "
    "One curious mechanic follows a trail of blue lights beneath the old station. "
    "Behind a locked door, a forgotten machine is counting down to tomorrow. "
    "The mechanic must decide whether to stop it or discover what it remembers. "
    "At sunrise, the whole town will learn why time waited for one brave person."
)


class AndroidLiteVideoTests(unittest.TestCase):
    def test_renderer_preflight_is_explicit_about_local_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            creator = AndroidLiteVideoCreator(Path(tmp) / "videos")
            result = creator.preflight()
            self.assertIn("network", result)
            self.assertEqual(result["network"], "not used")
            self.assertIn("offline_speech_engine", result)
            self.assertIn("ready", result)

    def test_invalid_script_is_rejected_before_output_is_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "videos"
            creator = AndroidLiteVideoCreator(root)
            with self.assertRaisesRegex(AndroidLiteVideoError, "between 25 and 150 words"):
                creator.render("A short test", "Only five words are here.", narration="off")
            self.assertFalse(root.exists())

    def test_non_latin_text_is_rejected_without_mutating_the_original_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            creator = AndroidLiteVideoCreator(Path(tmp) / "videos")
            with self.assertRaisesRegex(AndroidLiteVideoError, "Latin-script"):
                creator.render("عنوان", "هذا نص عربي لا يمكن عرضه بهذا الخط.", narration="off")

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "FFmpeg and FFprobe are required for the real MP4 smoke test.")
    def test_real_local_render_produces_verified_vertical_mp4(self):
        with tempfile.TemporaryDirectory() as tmp:
            creator = AndroidLiteVideoCreator(Path(tmp) / "videos")
            readiness = creator.preflight()
            if not readiness.get("ready"):
                self.skipTest("Local FFmpeg build is not ready: " + str(readiness.get("issues")))
            result = creator.render(
                "The Clockwork Secret", SCRIPT, video_format="vertical", narration="off"
            )
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["qa"], "passed")
            self.assertEqual((result["width"], result["height"]), (720, 1280))
            self.assertGreaterEqual(result["duration_seconds"], 29.0)
            self.assertTrue(result["sha256"])
            self.assertGreater(result["byte_size"], 8192)
            video = creator.read_video(result["video_id"])
            self.assertEqual(len(video), result["byte_size"])
            self.assertEqual(result["audio_bed"], "original_synthesized_ambient")
            self.assertFalse(result["external_services_used"])

    def test_video_id_is_validated_before_file_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            creator = AndroidLiteVideoCreator(Path(tmp) / "videos")
            with self.assertRaisesRegex(AndroidLiteVideoError, "Invalid video ID"):
                creator.read_video("../outside")


if __name__ == "__main__":
    unittest.main(verbosity=2)
