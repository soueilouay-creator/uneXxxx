from __future__ import annotations
import json, os, re, shutil, subprocess
from pathlib import Path
from typing import Any
ENGINE_COMMIT="5c05490cc55dfb54f8f4c333f0f0e79cb6500564"
FFMPEG_SOURCE_COMMIT="3a0867c2bfda4a4d4309ca1a8cbdc6175e67f587"
_IMAGE_RE=re.compile(r"^[a-z0-9][a-z0-9./:_@-]{0,180}$")
_ALLOWED_LIMITS={"cpu_seconds","memory_mb","wall_time_seconds"}
class RenderDispatcherUnavailable(RuntimeError): pass
class RenderExecutionError(RuntimeError): pass
def validate_render_bundle(input_dir:str|Path)->dict[str,Any]:
 root=Path(input_dir).resolve(strict=True)
 if not root.is_dir():raise ValueError("Render input must be a directory.")
 m=root/"manifest.json"
 if m.is_symlink() or not m.is_file():raise ValueError("A regular manifest.json is required.")
 p=json.loads(m.read_text(encoding="utf-8"))
 allowed={"job_id","engine_commit","project_dir","output_profile","fps","width","height","wall_time_seconds","audio_relpath","render_mode","timeline_relpath","captions_relpath"}
 required=allowed-{"audio_relpath","render_mode","timeline_relpath","captions_relpath"}
 if not isinstance(p,dict) or required-set(p) or set(p)-allowed:raise ValueError("Render manifest has missing or unsupported fields.")
 if p["engine_commit"]!=ENGINE_COMMIT:raise ValueError("Render manifest must use pinned Opuscar.")
 if p["project_dir"]!="project":raise ValueError("Only the fixed project directory is accepted.")
 mode=p.get("render_mode","opuscar")
 profiles={"youtube_shorts":(1080,1920),"tiktok":(1080,1920),"youtube_longform":(1920,1080)}
 if mode not in {"opuscar","story_film"} or p["output_profile"] not in profiles:raise ValueError("Unsupported renderer mode or output profile.")
 if (p["width"],p["height"])!=profiles[p["output_profile"]]:raise ValueError("Render dimensions do not match the selected profile.")
 if (mode=="story_film")!=(p["output_profile"]=="youtube_longform"):raise ValueError("Story-film mode is reserved for YouTube long-form.")
 if isinstance(p["fps"],bool) or not isinstance(p["fps"],int) or not 12<=p["fps"]<=60:raise ValueError("FPS must be 12–60.")
 wall=p["wall_time_seconds"]
 if isinstance(wall,bool) or not isinstance(wall,int) or not 30<=wall<=3600:raise ValueError("Wall time must be 30–3600 seconds.")
 if not isinstance(p["job_id"],str) or not 8<=len(p["job_id"])<=128 or not re.fullmatch(r"[A-Za-z0-9._:-]+",p["job_id"]):raise ValueError("Invalid render job ID.")
 ar=p.get("audio_relpath","audio/mix.wav");rel=Path(ar)
 if not isinstance(ar,str) or rel.is_absolute() or ".." in rel.parts or rel.suffix.lower()!=".wav":raise ValueError("Audio must be a relative WAV file inside project.")
 project=root/"project"
 if project.is_symlink() or not project.is_dir():raise ValueError("input/project is required.")
 if mode=="opuscar" and not (project/"index.html").is_file():raise ValueError("Opuscar input/project/index.html is required.")
 count=size=0
 for f in project.rglob("*"):
  if f.is_symlink():raise ValueError("Project symlinks are not allowed.")
  if f.is_file():
   count+=1;size+=f.stat().st_size
   if count>2000 or size>100*1024*1024:raise ValueError("Project exceeds 2,000 files or 100 MiB.")
 if (project/rel).is_symlink() or not (project/rel).is_file():raise ValueError("Project audio/mix.wav is required.")
 if mode=="story_film":
  from renderer.story_film import validate_story_paths
  validate_story_paths(project,p.get("timeline_relpath","timeline.json"),p.get("captions_relpath","captions.srt"))
 return p
def _inside(child:Path,parent:Path)->bool:
 try:child.relative_to(parent);return True
 except ValueError:return False
def build_docker_command(input_dir:str|Path,output_dir:str|Path,*,image:str,limits:dict[str,int]|None=None,docker_binary:str="docker")->list[str]:
 if not _IMAGE_RE.fullmatch(image or ""):raise ValueError("A fixed renderer image name is required.")
 src=Path(input_dir).resolve(strict=True);dst=Path(output_dir).resolve()
 if not src.is_dir():raise ValueError("Input must be an existing directory.")
 if src==dst or _inside(src,dst) or _inside(dst,src):raise ValueError("Renderer input/output mounts must not overlap.")
 if any("," in str(p) or "\n" in str(p) for p in (src,dst)):raise ValueError("Unsupported mount path characters.")
 dst.mkdir(parents=True,exist_ok=True)
 dst.chmod(0o777)  # dedicated disposable output mount; worker UID/GID is 10001
 policy=limits or {"cpu_seconds":240,"memory_mb":2048,"wall_time_seconds":900}
 if set(policy)!=_ALLOWED_LIMITS:raise ValueError("Limits must contain exactly cpu_seconds, memory_mb and wall_time_seconds.")
 cpu,mem,wall=(policy["cpu_seconds"],policy["memory_mb"],policy["wall_time_seconds"])
 if any(isinstance(v,bool) or not isinstance(v,int) for v in (cpu,mem,wall)):raise ValueError("Limits must be integers.")
 if not 1<=cpu<=600 or not 256<=mem<=8192 or not 30<=wall<=3600:raise ValueError("Limits exceed supported bounds.")
 cpus=max(1,min(4,(cpu+59)//60))
 return [docker_binary,"run","--rm","--network=none","--read-only","--user","10001:10001","--cap-drop=ALL",
 "--security-opt=no-new-privileges","--pids-limit","128","--memory",f"{mem}m","--cpus",str(cpus),
 "--tmpfs","/tmp:rw,nosuid,nodev,size=512m","--env","HOME=/tmp","--env","PLAYWRIGHT_BROWSERS_PATH=/ms-playwright",
 "--mount",f"type=bind,src={src},dst=/job/input,readonly","--mount",f"type=bind,src={dst},dst=/job/output",
 image,"--input-root","/job/input","--output-root","/job/output"]
class DockerRenderDispatcher:
 """Host-side Docker boundary. The authenticated API process never receives the Docker socket."""
 def __init__(self,*,enabled:bool=False,image:str|None=None,docker_binary:str="docker"):
  self.enabled=bool(enabled);self.image=image or "";self.docker_binary=docker_binary
 def run(self,input_dir:str|Path,output_dir:str|Path,manifest:dict[str,Any]|None=None,*,limits:dict[str,int]|None=None)->dict[str,Any]:
  if not self.enabled:raise RenderDispatcherUnavailable("Isolated rendering is disabled; no in-process fallback is permitted.")
  if shutil.which(self.docker_binary) is None:raise RenderDispatcherUnavailable("Docker CLI is not installed on this host.")
  checked=validate_render_bundle(input_dir)
  if manifest is not None and manifest!=checked:raise ValueError("Supplied manifest differs from persisted bundle.")
  cmd=build_docker_command(input_dir,output_dir,image=self.image,limits=limits,docker_binary=self.docker_binary)
  wall=(limits or {}).get("wall_time_seconds",checked["wall_time_seconds"])
  try:r=subprocess.run(cmd,shell=False,check=False,capture_output=True,text=True,timeout=wall+30,env={"PATH":os.environ.get("PATH","/usr/bin:/bin"),"HOME":os.environ.get("HOME","/tmp")})
  except subprocess.TimeoutExpired as exc:raise RenderExecutionError("Renderer exceeded host wall-time bound.") from exc
  if r.returncode:
   msg=(r.stderr or r.stdout or "Renderer failed").strip().splitlines()[-1][:300]
   raise RenderExecutionError(f"Renderer container failed ({r.returncode}): {msg}")
  out=Path(output_dir)/"result.json"
  if not out.is_file():raise RenderExecutionError("Renderer exited without result manifest.")
  result=json.loads(out.read_text(encoding="utf-8"))
  if result.get("status")!="completed" or result.get("engine_commit")!=ENGINE_COMMIT:raise RenderExecutionError("Pinned engine result verification failed.")
  return result
