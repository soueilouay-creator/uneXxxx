import unittest

from renderer.worker import PROFILES, ffmpeg_major


class RendererWorkerTests(unittest.TestCase):
    def test_ffmpeg_version_parser_accepts_upstream_n_tag_banner(self):
        self.assertEqual(ffmpeg_major("ffmpeg version n7.1.5 Copyright (c)"), 7)
        self.assertEqual(ffmpeg_major("ffmpeg version 8.0 Copyright (c)"), 8)

    def test_ffmpeg_version_parser_rejects_unsupported_or_unreadable_banner(self):
        self.assertEqual(ffmpeg_major("ffmpeg version 6.1.2 Copyright (c)"), 6)
        self.assertEqual(ffmpeg_major("not an ffmpeg banner"), 0)

    def test_vertical_render_profiles_remain_locked(self):
        self.assertEqual(PROFILES["youtube_shorts"], (1080, 1920))
        self.assertEqual(PROFILES["tiktok"], (1080, 1920))


if __name__ == "__main__":
    unittest.main()
