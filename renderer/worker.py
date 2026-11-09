#!/usr/bin/env python3
"""Networkless one-shot renderer. No uneXpected token, DB URL or provider is present."""
import argparse,hashlib,json,os,re,shutil,subprocess,sys,tempfile,time
from pathlib import Path
ENGINE="5c05490cc55dfb54f8f4c333f0f0e79cb6500564"
FFMPEG_SOURCE="3a0867c2bfda4a4d4309ca1a8cbdc6175e67f587"
PROFILES={"youtube_shorts":(1080,1920),"tiktok":(1080,1920),"youtube_longform":(1920,1080)}
def ffmpeg_major(version_output):
 for line in version_output.splitlines():
  match=re.match(r"^ffmpeg version n?(\d+)\.",line.strip())
  if match:return int(match.group(1))
 return 0
def write_json(p,d):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_name(p.name+".tmp");t.write_text(json.dumps(d,sort_keys=True,indent=2),encoding="utf-8");os.replace(t,p)
def digest(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1048576),b""):h.update(b)
 return h.hexdigest()
def validate(root):
 m=root/"manifest.json"
 if m.is_symlink() or not m.is_file():raise ValueError("manifest.json missing.")
 p=json.loads(m.read_text(encoding="utf-8"))
 allow={"job_id","engine_commit","project_dir","output_profile","fps","width","height","wall_time_seconds","audio_relpath","render_mode","timeline_relpath","captions_relpath"}
 required=allow-{"audio_relpath","render_mode","timeline_relpath","captions_relpath"}
 if not isinstance(p,dict) or set(p)-allow or required-set(p):raise ValueError("Unsupported manifest fields.")
 if p["engine_commit"]!=ENGINE or p["project_dir"]!="project":raise ValueError("Pinned engine or project path mismatch.")
 if p["output_profile"] not in PROFILES or (p["width"],p["height"])!=PROFILES[p["output_profile"]]:raise ValueError("Invalid platform profile.")
 mode=p.get("render_mode","opuscar")
 if mode not in {"opuscar","story_film"}:raise ValueError("Unsupported renderer mode.")
 if (mode=="story_film")!=(p["output_profile"]=="youtube_longform"):raise ValueError("Story-film mode is reserved for YouTube long-form profile.")
 if isinstance(p["fps"],bool) or not isinstance(p["fps"],int) or not 12<=p["fps"]<=60:raise ValueError("Invalid FPS.")
 if isinstance(p["wall_time_seconds"],bool) or not isinstance(p["wall_time_seconds"],int) or not 30<=p["wall_time_seconds"]<=3600:raise ValueError("Invalid wall-time.")
 if not isinstance(p["job_id"],str) or not 8<=len(p["job_id"])<=128:raise ValueError("Invalid job ID.")
 project=root/"project"
 if project.is_symlink() or not project.is_dir():raise ValueError("Project directory missing.")
 if mode=="opuscar" and not (project/"index.html").is_file():raise ValueError("Opuscar project index.html missing.")
 files=list(project.rglob("*"))
 if any(x.is_symlink() for x in files) or sum(x.is_file() for x in files)>2000 or sum(x.stat().st_size for x in files if x.is_file())>100*1024*1024:raise ValueError("Project size or file-count limit exceeded.")
 rel=Path(p.get("audio_relpath","audio/mix.wav"))
 if rel.is_absolute() or ".." in rel.parts or rel.suffix.lower()!=".wav" or not (project/rel).is_file():raise ValueError("A local WAV soundtrack is required.")
 if mode=="story_film":
  from story_film import validate_story_paths
  validate_story_paths(project,p.get("timeline_relpath","timeline.json"),p.get("captions_relpath","captions.srt"))
 return p,project
def run():
 ap=argparse.ArgumentParser();ap.add_argument("--input-root",default="/job/input");ap.add_argument("--output-root",default="/job/output");a=ap.parse_args()
 root,out=Path(a.input_root).resolve(),Path(a.output_root).resolve();engine=Path(os.environ.get("LEMO_OPUSCAR_HOME","/opt/lemo-opuscar")).resolve()
 out.mkdir(parents=True,exist_ok=True);start=time.monotonic();job="unknown"
 try:
  p,source=validate(root);job=p["job_id"]
  if p.get("render_mode","opuscar")=="opuscar" and not (engine/"core/render/video.mjs").is_file():raise RuntimeError("Pinned Opuscar installation is incomplete.")
  version_probe=subprocess.run(["ffmpeg","-version"],capture_output=True,text=True,check=True,timeout=5)
  vv=version_probe.stdout+"\n"+version_probe.stderr
  ffline=next((x for x in vv.splitlines() if x.startswith("ffmpeg version")),"")
  if ffmpeg_major(vv)<7:raise RuntimeError("FFmpeg 7+ is required.")
  def progress(stage):
   d={"status":"running","stage":stage,"engine_commit":ENGINE,"updated_at":time.time()};write_json(out/"progress.json",d);print(json.dumps(d),flush=True)
  with tempfile.TemporaryDirectory(prefix="creator-render-") as tmp:
   project=Path(tmp)/"project";shutil.copytree(source,project);audio=project/Path(p.get("audio_relpath","audio/mix.wav"))
   video,master=out/"picture.mp4",out/"master.mp4";deadline=start+p["wall_time_seconds"];story_result=None
   if p.get("render_mode","opuscar")=="story_film":
    progress("story-film-rendering")
    from story_film import render_story_film
    story_result=render_story_film(project,audio,master,fps=p["fps"],
     timeline_relpath=p.get("timeline_relpath","timeline.json"),
     captions_relpath=p.get("captions_relpath","captions.srt"),
     timeout_seconds=max(1,int(deadline-time.monotonic())))
   else:
    progress("rendering")
    try:
     rendered = subprocess.run(
      ["node","core/render/video.mjs",str(project),"--fps",str(p["fps"]),"--workers","2","--size",f'{p["width"]}x{p["height"]}',"--out",str(video)],
      cwd=engine,check=True,shell=False,capture_output=True,text=True,
      timeout=max(1,int(deadline-time.monotonic())),
      env={**os.environ,"HOME":"/tmp","PLAYWRIGHT_BROWSERS_PATH":"/ms-playwright"})
    except subprocess.CalledProcessError as exc:
     detail=(exc.stderr or exc.stdout or "No renderer diagnostic output").strip()
     raise RuntimeError("Opuscar video render failed: "+detail[-3000:]) from None
    progress("muxing")
    try:
     muxed = subprocess.run(
      ["sh","core/render/mux.sh",str(video),str(audio),str(master),str(p["fps"]),"0"],
      cwd=engine,check=True,shell=False,capture_output=True,text=True,
      timeout=max(1,int(deadline-time.monotonic())),env={**os.environ,"HOME":"/tmp"})
    except subprocess.CalledProcessError as exc:
     detail=(exc.stderr or exc.stdout or "No mux diagnostic output").strip()
     raise RuntimeError("Opuscar audio mux failed: "+detail[-3000:]) from None
   q=subprocess.run(["ffprobe","-v","error","-show_streams","-show_format","-of","json",str(master)],capture_output=True,text=True,check=True,timeout=15)
   info=json.loads(q.stdout);ss=info.get("streams",[]);v=next((s for s in ss if s.get("codec_type")=="video"),None);au=next((s for s in ss if s.get("codec_type")=="audio"),None)
   if not v or not au or (v.get("width"),v.get("height"))!=(p["width"],p["height"]):raise RuntimeError("Encoded MP4 stream/profile verification failed.")
   if not master.is_file() or master.stat().st_size<4096:raise RuntimeError("MP4 is empty or incomplete.")
   result={"status":"completed","job_id":job,"engine_commit":ENGINE,"ffmpeg_source_commit":FFMPEG_SOURCE,"ffmpeg_version":ffline,"file":"master.mp4",
    "byte_size":master.stat().st_size,"sha256":digest(master),"renderer_mode":p.get("render_mode","opuscar"),"thumbnail_file":story_result.get("thumbnail_file") if story_result else None,"media":{"width":v["width"],"height":v["height"],
    "aspect_ratio":"16:9" if (v["width"],v["height"])==(1920,1080) else "9:16","duration_seconds":float(info.get("format",{}).get("duration") or 0),"video_codec":v.get("codec_name"),"audio_codec":au.get("codec_name")}}
   write_json(out/"result.json",result);write_json(out/"progress.json",{"status":"completed","stage":"rendered","engine_commit":ENGINE,"updated_at":time.time()})
   print(json.dumps(result),flush=True)
  return 0
 except Exception as exc:
  msg=str(exc).splitlines()[0][:240];write_json(out/"failure.json",{"status":"failed","job_id":job,"error_type":type(exc).__name__,"message":msg,"elapsed_seconds":round(time.monotonic()-start,2)})
  print(json.dumps({"status":"failed","job_id":job,"error_type":type(exc).__name__,"message":msg}),file=sys.stderr,flush=True);return 1
if __name__=="__main__":raise SystemExit(run())
