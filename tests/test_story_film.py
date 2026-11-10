import json
import tempfile
import unittest
from pathlib import Path

from renderer.story_film import StoryFilmError, validate_story_paths


class StoryFilmTimelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name) / "project"
        (self.project / "scenes").mkdir(parents=True)
        (self.project / "scenes" / "scene-01.png").write_bytes(b"png-one")
        (self.project / "scenes" / "scene-02.png").write_bytes(b"png-two")
        (self.project / "captions.srt").write_text(
            "1\n00:00:00,000 --> 00:00:04,000\nA forbidden bond.\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def write_timeline(self, scenes):
        path = self.project / "timeline.json"
        path.write_text(json.dumps({"version": 1, "scenes": scenes}), encoding="utf-8")
        return path

    def test_accepts_a_bounded_original_story_timeline(self):
        path = self.write_timeline([
            {"scene_id": "one", "image": "scenes/scene-01.png", "duration_seconds": 4},
            {"scene_id": "two", "image": "scenes/scene-02.png", "duration_seconds": 4},
        ])
        timeline, captions, scenes = validate_story_paths(self.project)
        self.assertEqual(timeline, path.resolve())
        self.assertEqual(captions.name, "captions.srt")
        self.assertEqual(len(scenes), 2)
        self.assertEqual(sum(scene["duration_seconds"] for scene in scenes), 8)

    def test_rejects_parent_traversal(self):
        self.write_timeline([
            {"image": "../escape.png", "duration_seconds": 4},
            {"image": "scenes/scene-02.png", "duration_seconds": 4},
        ])
        with self.assertRaises(StoryFilmError):
            validate_story_paths(self.project)

    def test_rejects_scene_duration_and_scene_count_out_of_bounds(self):
        self.write_timeline([
            {"image": "scenes/scene-01.png", "duration_seconds": 0.5},
            {"image": "scenes/scene-02.png", "duration_seconds": 4},
        ])
        with self.assertRaises(StoryFilmError):
            validate_story_paths(self.project)
        self.write_timeline([{"image": "scenes/scene-01.png", "duration_seconds": 4}])
        with self.assertRaises(StoryFilmError):
            validate_story_paths(self.project)


if __name__ == "__main__":
    unittest.main()
