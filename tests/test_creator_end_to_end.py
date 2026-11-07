from __future__ import annotations
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unexpected_runtime.creator_qa import CreatorVideoQA
from unexpected_runtime.platform_packages import CreatorPlatformPackager
from unexpected_runtime.render_jobs import DockerRenderDispatcher

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/"renderer"/"fixtures"/"creator-smoke"

@unittest.skipUnless(os.environ.get("UNEXPECTED_CREATOR_RENDERER_IMAGE"),"Dedicated renderer CI job only")
class CreatorEndToEndTests(unittest.TestCase):
    def test_real_opuscar_render_mp4_qa_and_platform_packages(self):
        image=os.environ["UNEXPECTED_CREATOR_RENDERER_IMAGE"]
        with tempfile.TemporaryDirectory(prefix="creator-e2e-") as temporary:
            root=Path(temporary)
            input_root,output_root=root/"input",root/"output"
            project=input_root/"project"
            project.mkdir(parents=True)
            output_root.mkdir()
            shutil.copy2(FIXTURE/"index.html",project/"index.html")
            shutil.copy2(FIXTURE/"captions.srt",project/"captions.srt")
            soundtrack=project/"audio"/"mix.wav"
            subprocess.run(["python3",str(FIXTURE/"make_audio.py"),str(soundtrack)],check=True,timeout=30)
            manifest={
                "job_id":"creator-opuscar-smoke-0001",
                "engine_commit":"5c05490cc55dfb54f8f4c333f0f0e79cb6500564",
                "project_dir":"project",
                "output_profile":"youtube_shorts",
                "fps":24,"width":1080,"height":1920,
                "wall_time_seconds":900,"audio_relpath":"audio/mix.wav",
            }
            (input_root/"manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
            dispatcher=DockerRenderDispatcher(enabled=True,image=image)
            result=dispatcher.run(input_root,output_root,manifest,
                limits={"cpu_seconds":240,"memory_mb":4096,"wall_time_seconds":900})
            master=output_root/"master.mp4"
            self.assertTrue(master.is_file())
            self.assertEqual(result["status"],"completed")
            self.assertEqual(result["engine_commit"],"5c05490cc55dfb54f8f4c333f0f0e79cb6500564")
            self.assertEqual(result["media"]["width"],1080)
            self.assertEqual(result["media"]["height"],1920)
            self.assertGreaterEqual(result["media"]["duration_seconds"],7.8)
            self.assertEqual(result["byte_size"],master.stat().st_size)
            self.assertEqual(result["sha256"],hashlib.sha256(master.read_bytes()).hexdigest())
            qa=CreatorVideoQA().inspect(master,captions_path=project/"captions.srt")
            self.assertEqual(qa["status"],"passed",qa)
            self.assertTrue(qa["human_review_required"])
            self.assertEqual(qa["checks"]["transitions"]["status"],"human_review_required")
            project_record={"title":"A Film Made from Code","topic":"An original eight-second code-rendered film","language":"English"}
            packages=CreatorPlatformPackager().build_both(project_record,
                {"sha256":result["sha256"],"mime_type":"video/mp4"},qa)
            self.assertEqual(set(packages),{"youtube","tiktok"})
            self.assertEqual(packages["youtube"]["platform"],"youtube")
            self.assertEqual(packages["tiktok"]["platform"],"tiktok")
            self.assertEqual(packages["youtube"]["video"]["aspect_ratio"],"9:16")
            self.assertEqual(packages["tiktok"]["video"]["aspect_ratio"],"9:16")
            self.assertFalse(packages["youtube"]["uploads_enabled"])
            self.assertFalse(packages["tiktok"]["uploads_enabled"])
            self.assertEqual(packages["youtube"]["publication_status"],"not_uploaded")
            self.assertEqual(packages["tiktok"]["publication_status"],"not_uploaded")

if __name__=="__main__":
    unittest.main(verbosity=2)
