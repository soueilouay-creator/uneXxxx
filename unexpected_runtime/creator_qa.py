from __future__ import annotations
import hashlib,json,math,re,subprocess
from pathlib import Path
class CreatorVideoQAError(RuntimeError): pass
class CreatorVideoQA:
 def __init__(self,*,ffmpeg="ffmpeg",ffprobe="ffprobe",timeout_seconds=180): self.ffmpeg,self.ffprobe,self.timeout=ffmpeg,ffprobe,max(10,min(int(timeout_seconds),600))
 @staticmethod
 def parse_black_freeze(log):
  b=[float(x) for x in re.findall(r"black_duration:\s*([0-9.]+)",log)];f=[float(x) for x in re.findall(r"freeze_duration:\s*([0-9.]+)",log)]
  return {"black_longest_seconds":max(b,default=0.0),"freeze_longest_seconds":max(f,default=0.0)}
 @staticmethod
 def parse_loudness(log):
  i=re.search(r"(?:Integrated loudness:\s*(?:I:\s*)?|\bI:\s*)(-?[0-9]+(?:\.[0-9]+)?)\s*LUFS",log,re.I);p=re.search(r"(?:True peak:\s*)?Peak:\s*(-?[0-9]+(?:\.[0-9]+)?)\s*dBFS",log,re.I)
  if not i or not p: raise CreatorVideoQAError("FFmpeg ebur128 did not report loudness and true peak.")
  return {"integrated_lufs":float(i.group(1)),"true_peak_dbfs":float(p.group(1))}
 @staticmethod
 def parse_caption_file(path,duration):
  f=Path(path)
  if not f.is_file() or f.stat().st_size>2_000_000: raise CreatorVideoQAError("Caption file is missing or too large.")
  blocks=re.split(r"\r?\n\s*\r?\n",f.read_text(encoding="utf-8-sig").strip());rx=re.compile(r"(?m)^\s*(?:(\d+)\s*\r?\n)?(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})(?:\s+.*)?\s*$");cues=[]
  for block in blocks:
   if not block.strip() or block.strip().upper()=="WEBVTT": continue
   m=rx.search(block)
   if not m: raise CreatorVideoQAError("Subtitle cue has an invalid SRT timecode.")
   g=[int(x or 0) for x in m.groups()];start=((g[1]*60+g[2])*60+g[3])+g[4]/1000;end=((g[5]*60+g[6])*60+g[7])+g[8]/1000
   lines=[re.sub(r"<[^>]+>","",x).strip() for x in block[m.end():].strip().splitlines() if x.strip()]
   if not lines or start<0 or end<=start or end>duration+.25: raise CreatorVideoQAError("Caption cue is empty or outside the video duration.")
   if len(lines)>2 or any(len(x)>42 for x in lines): raise CreatorVideoQAError("Captions exceed the two-line / 42-character readability target.")
   cues.append((start,end))
  if not cues: raise CreatorVideoQAError("No subtitle cues were found.")
  cues.sort()
  if any(b[0]<a[1]-.01 for a,b in zip(cues,cues[1:])): raise CreatorVideoQAError("Subtitle cues overlap.")
  return {"status":"passed","cue_count":len(cues),"last_end_seconds":cues[-1][1]}
 def _run(self,cmd):
  try: return subprocess.run(cmd,capture_output=True,text=True,timeout=self.timeout,check=False)
  except subprocess.TimeoutExpired as e: raise CreatorVideoQAError("Encoded-media analysis timed out.") from e
  except OSError as e: raise CreatorVideoQAError("FFmpeg and ffprobe are required.") from e
 def inspect(self,mp4_path,*,captions_path=None):
  f=Path(mp4_path).resolve(strict=True)
  if not f.is_file() or f.suffix.lower()!=".mp4" or f.stat().st_size<4096: raise CreatorVideoQAError("A complete encoded MP4 master is required.")
  p=self._run([self.ffprobe,"-v","error","-show_streams","-show_format","-of","json",str(f)])
  if p.returncode: raise CreatorVideoQAError("ffprobe could not inspect the MP4.")
  try: data=json.loads(p.stdout)
  except ValueError as e: raise CreatorVideoQAError("ffprobe returned invalid JSON.") from e
  s=data.get("streams",[]);v=next((x for x in s if x.get("codec_type")=="video"),None);a=next((x for x in s if x.get("codec_type")=="audio"),None);duration=float(data.get("format",{}).get("duration") or 0)
  if not v or not a or not math.isfinite(duration) or duration<=0: raise CreatorVideoQAError("MP4 must contain video, audio and finite duration.")
  w,h=int(v.get("width") or 0),int(v.get("height") or 0)
  if (w,h)!=(1080,1920): raise CreatorVideoQAError("Master must be vertical 1080x1920.")
  if v.get("codec_name") not in {"h264","av1","hevc"}: raise CreatorVideoQAError("Unsupported MP4 video codec.")
  try: n,d=v.get("avg_frame_rate","0/1").split("/",1);fps=float(n)/float(d)
  except (ValueError,ZeroDivisionError): fps=0
  if not 12<=fps<=60: raise CreatorVideoQAError("Frame rate must be 12–60 FPS.")
  d=self._run([self.ffmpeg,"-hide_banner","-nostats","-i",str(f),"-vf","blackdetect=d=0.15:pix_th=0.10,freezedetect=n=-50dB:d=1","-an","-f","null","-"])
  if d.returncode: raise CreatorVideoQAError("FFmpeg black-frame / freeze analysis failed.")
  defects=self.parse_black_freeze(d.stderr+"\n"+d.stdout)
  l=self._run([self.ffmpeg,"-hide_banner","-nostats","-i",str(f),"-vn","-af","ebur128=peak=true","-f","null","-"])
  if l.returncode: raise CreatorVideoQAError("FFmpeg audio analysis failed.")
  levels=self.parse_loudness(l.stderr+"\n"+l.stdout);caps=self.parse_caption_file(captions_path,duration) if captions_path else None
  checks={"dimensions":{"status":"passed","width":w,"height":h},"duration":{"status":"passed","seconds":round(duration,3)},"frame_rate":{"status":"passed","fps":round(fps,3)},
   "audio_stream":{"status":"passed","codec":a.get("codec_name")},"black_frames":{"status":"passed" if defects["black_longest_seconds"]<=.35 else "failed",**defects},
   "freezes":{"status":"passed" if defects["freeze_longest_seconds"]<1 else "failed","longest_seconds":defects["freeze_longest_seconds"]},
   "audio_loudness":{"status":"passed" if -16<=levels["integrated_lufs"]<=-12 and levels["true_peak_dbfs"]<=-1 else "failed",**levels},
   "captions":{"status":caps["status"] if caps else "failed",**(caps or {"reason":"Caption sidecar is required."})},
   "transitions":{"status":"human_review_required"},"narration_sync":{"status":"human_review_required"}}
  keys=("dimensions","duration","frame_rate","audio_stream","black_frames","freezes","audio_loudness","captions")
  return {"status":"passed" if all(checks[k]["status"]=="passed" for k in keys) else "failed","file":f.name,"sha256":hashlib.sha256(f.read_bytes()).hexdigest(),"byte_size":f.stat().st_size,
   "media":{"width":w,"height":h,"duration_seconds":round(duration,3),"fps":round(fps,3),"video_codec":v.get("codec_name"),"audio_codec":a.get("codec_name")},"checks":checks,"human_review_required":True}
__all__=["CreatorVideoQA","CreatorVideoQAError"]
