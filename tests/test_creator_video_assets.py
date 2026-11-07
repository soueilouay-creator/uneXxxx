import tempfile,unittest
from pathlib import Path
from unexpected_runtime.creator_qa import CreatorVideoQA,CreatorVideoQAError
from unexpected_runtime.platform_packages import CreatorPlatformPackager,CreatorPlatformPackageError
class CreatorMediaTests(unittest.TestCase):
 def test_detection_and_loudness_parsers(self):
  x=CreatorVideoQA.parse_black_freeze("black_duration:0.42\nfreeze_duration:1.4")
  self.assertEqual(x["black_longest_seconds"],.42);self.assertEqual(x["freeze_longest_seconds"],1.4)
  self.assertEqual(CreatorVideoQA.parse_loudness("Integrated loudness:\n I: -14.2 LUFS\nTrue peak:\n Peak: -1.1 dBFS"),{"integrated_lufs":-14.2,"true_peak_dbfs":-1.1})
 def test_captions_reject_overlap(self):
  with tempfile.TemporaryDirectory() as t:
   f=Path(t)/"captions.srt";f.write_text("1\n00:00:00,000 --> 00:00:02,000\nOpening.\n\n2\n00:00:02,100 --> 00:00:04,000\nNext scene.\n")
   self.assertEqual(CreatorVideoQA.parse_caption_file(f,5)["cue_count"],2)
   f.write_text("1\n00:00:00,000 --> 00:00:03,000\nFirst.\n\n2\n00:00:02,500 --> 00:00:04,000\nOverlap.\n")
   with self.assertRaises(CreatorVideoQAError):CreatorVideoQA.parse_caption_file(f,5)
 def test_youtube_longform_package_requires_landscape_and_30_to_45_minutes(self):
  p={"title":"The Moonbound Vow","topic":"Original paranormal romance fantasy story","language":"English"}
  a={"mime_type":"video/mp4","sha256":"c"*64}
  q={"status":"passed","sha256":"d"*64,"media":{"width":1920,"height":1080,"aspect_ratio":"16:9","duration_seconds":2400}}
  package=CreatorPlatformPackager().build_youtube_longform(p,a,q)
  self.assertEqual(package["platform"],"youtube")
  self.assertEqual(package["video"]["aspect_ratio"],"16:9")
  self.assertFalse(package["uploads_enabled"])
  with self.assertRaises(CreatorPlatformPackageError):
   CreatorPlatformPackager().build_youtube_longform(p,a,{**q,"media":{**q["media"],"duration_seconds":1200}})

 def test_packages_require_qa_and_never_enable_upload(self):
  p={"title":"Original Film","topic":"How code creates motion","language":"English"};a={"mime_type":"video/mp4","sha256":"a"*64};q={"status":"passed","sha256":"b"*64,"media":{"width":1080,"height":1920,"duration_seconds":10}}
  x=CreatorPlatformPackager().build_both(p,a,q)
  self.assertEqual(set(x),{"youtube","tiktok"});self.assertFalse(x["youtube"]["uploads_enabled"]);self.assertEqual(x["tiktok"]["platform"],"tiktok")
  with self.assertRaises(CreatorPlatformPackageError):CreatorPlatformPackager().build_both(p,a,{**q,"status":"failed"})
if __name__=="__main__":unittest.main()
