from __future__ import annotations

import importlib.util
import unittest


class AndroidLiteVideoModuleTests(unittest.TestCase):
    def test_android_lite_renderer_is_part_of_the_runtime(self):
        spec = importlib.util.find_spec("unexpected_runtime.android_lite_video")
        self.assertIsNotNone(
            spec,
            "The phone-friendly FFmpeg renderer must ship with the unified runtime.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
