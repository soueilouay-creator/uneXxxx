from __future__ import annotations
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class CreatorStudioUIContractTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.html=(ROOT/"web"/"index.html").read_text(encoding="utf-8")
  cls.js=(ROOT/"web"/"assets"/"app.js").read_text(encoding="utf-8")
  cls.css=(ROOT/"web"/"assets"/"styles.css").read_text(encoding="utf-8")
 def test_one_creator_studio_view_and_authenticated_api_routes(self):
  self.assertIn('data-view="creator"',self.html)
  self.assertIn('id="view-creator"',self.html)
  self.assertIn('/v1/creator/projects',self.js)
  self.assertIn('/render-jobs',self.js)
  self.assertIn('/v1/creator/render-jobs/',self.js)
  self.assertIn('Authorization',''.join(self.js.splitlines()[:30]))
 def test_script_scenes_progress_preview_qa_and_platform_handoff_are_visible(self):
  for marker in ("creator-hook","creator-script","creator-scenes","creator-render-state","creator-render-result","creator-preview","creator-qa","creator-youtube-state","creator-tiktok-state"):
   self.assertIn(f'id="{marker}"',self.html)
  self.assertIn("creator-render",self.js)
  self.assertIn("creator-job-refresh",self.js)
  self.assertIn(".creator-preview",self.css)
 def test_longform_story_format_is_primary_and_vertical_is_secondary(self):
  self.assertIn('id="creator-format"',self.html)
  self.assertIn("YouTube story film",self.html)
  self.assertIn("30–45 minutes",self.html)
  self.assertIn("maxlength=\"100000\"",self.html)
  self.assertIn('profile:"youtube_longform"',self.js)
  self.assertIn('render_mode:"story_film"',self.js)
  self.assertIn("creator-format-note",self.js)


 def test_android_lite_creator_has_script_format_preview_and_download_controls(self):
  for marker in ("android-video-form","android-video-title","android-video-script","android-video-format","android-video-narration","android-video-output"):
   self.assertIn(f'id="{marker}"',self.html)
  self.assertIn('/v1/creator/android-videos',self.js)
  self.assertIn('/file',self.js)
  self.assertIn("URL.createObjectURL",self.js)
  self.assertIn("android-video-output",self.css)
  self.assertIn("No model downloads",self.html)

 def test_no_publish_or_schedule_control_is_added(self):
  self.assertNotIn('id="creator-publish"',self.html)
  self.assertNotIn('id="creator-schedule"',self.html)
  self.assertIn("publishing disabled",self.html.lower())
if __name__=="__main__":unittest.main()
