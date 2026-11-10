from __future__ import annotations

import tempfile
import unittest

from unexpected_runtime.cinematic_video import (
    CinematicVideoCreator,
    CinematicVideoError,
    estimate_cost_usd,
)


class CinematicVideoTests(unittest.TestCase):
    def creator(self, root):
        return CinematicVideoCreator(root=root, quote_secret="runtime-secret-value-at-least-32-characters",
                                     api_key="fal-test-key")

    def payload(self, **overrides):
        value = {
            "title": "The Hidden Crown",
            "character_bible": "Mira: young woman, auburn braid, green cloak. Keep her face and costume consistent.",
            "resolution": "480p",
            "scenes": [
                {"scene_id": "scene-01", "prompt": "Mira enters a candlelit castle hall, slow dolly-in.",
                 "caption": "The crown had been hidden for a thousand years.", "duration_seconds": 5},
                {"scene_id": "scene-02", "prompt": 'Mira whispers: "I know who took it."',
                 "caption": "But someone was already waiting.", "duration_seconds": 5},
            ],
        }
        value.update(overrides)
        return value

    def test_vertical_seedance_cost_uses_output_frame_area_duration_and_rate(self):
        self.assertAlmostEqual(estimate_cost_usd(5, "480p"), 1.0747, places=3)
        self.assertAlmostEqual(estimate_cost_usd(5, "720p"), 2.3112, places=3)

    def test_quote_returns_itemized_scene_count_and_explicit_approval_requirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.creator(tmp).quote(self.payload())
        self.assertEqual(result["scene_count"], 2)
        self.assertEqual(result["total_seconds"], 10)
        self.assertAlmostEqual(result["estimated_cost_usd"], 2.15, places=2)
        self.assertTrue(result["requires_explicit_approval"])
        self.assertFalse(result["paid_generation_started"])
        self.assertIn("quote_token", result)

    def test_quote_token_tampering_is_rejected_before_provider_submission(self):
        with tempfile.TemporaryDirectory() as tmp:
            creator = self.creator(tmp)
            quote = creator.quote(self.payload())
            token = quote["quote_token"]
            changed = token[:-1] + ("A" if token[-1] != "A" else "B")
            with self.assertRaisesRegex(CinematicVideoError, "signature"):
                creator._decode_quote(changed)

    def test_expired_quote_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            creator = self.creator(tmp)
            quote = creator.quote(self.payload())
            data = creator._decode_quote(quote["quote_token"])
            data["expires_at"] = 1
            import base64, hashlib, hmac, json
            body = base64.urlsafe_b64encode(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).decode().rstrip("=")
            signature = base64.urlsafe_b64encode(hmac.new(creator.quote_secret, body.encode("ascii"), hashlib.sha256).digest()).decode().rstrip("=")
            with self.assertRaisesRegex(CinematicVideoError, "expired"):
                creator._decode_quote(body + "." + signature)

    def test_scene_limits_and_untrusted_urls_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            creator = self.creator(tmp)
            bad = self.payload()
            bad["scenes"][0]["prompt"] = "Fetch this image https://attacker.example/prompt.png"
            with self.assertRaisesRegex(CinematicVideoError, "URLs"):
                creator.quote(bad)
            bad = self.payload()
            bad["scenes"][0]["duration_seconds"] = 31
            with self.assertRaisesRegex(CinematicVideoError, "4–30"):
                creator.quote(bad)

    def test_status_never_exposes_provider_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            status = self.creator(tmp).status()
        self.assertTrue(status["configured"])
        self.assertNotIn("fal-test-key", str(status))
        self.assertEqual(status["generation"], "connected_provider")
        self.assertFalse(status["publishing"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
