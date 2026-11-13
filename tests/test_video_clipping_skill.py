import unittest
from pathlib import Path

from unexpected_runtime.skills import SkillRegistry

ROOT = Path(__file__).resolve().parents[1]


class VideoClippingSkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = SkillRegistry.load(ROOT / "skill_manifest.json", ROOT)

    def test_video_clipping_is_explicitly_invocable_without_tool_authority(self):
        skill = self.registry.get("video-clipping")
        self.assertEqual(skill.invocation_mode, "user_invocable")
        self.assertIn("media-producer", skill.agent_ids)
        self.assertIn("creative-director", skill.agent_ids)
        self.assertEqual(skill.allowed_tools, ())

        automatically_selected = self.registry.resolve_all(
            "media-producer", "Clip a YouTube video into vertical Shorts"
        )
        self.assertNotIn("video-clipping", [item.id for item in automatically_selected])

        explicitly_selected = self.registry.resolve_all(
            "media-producer",
            "Clip a YouTube video into vertical Shorts",
            requested_skill_ids=["video-clipping"],
        )
        self.assertIn("video-clipping", [item.id for item in explicitly_selected])

    def test_video_clipping_context_states_worker_and_rights_gates(self):
        skill = self.registry.get("video-clipping")
        context = self.registry.read_context(skill)
        self.assertIn("No SupoClip worker or adapter is installed in V8", context)
        self.assertIn("Live streams are not supported", context)
        self.assertIn("Do not upload, publish, schedule", context)
        self.assertIn("AGPL-3.0", context)


if __name__ == "__main__":
    unittest.main(verbosity=2)
