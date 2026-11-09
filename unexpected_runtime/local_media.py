from __future__ import annotations
import hashlib, json, math, os, re, shutil, subprocess, time
from pathlib import Path
from .comfyui_local import LocalComfyUIClient, LocalComfyUIError
from .local_ai import LocalAIError, inspect_model_availability, load_model_registry
from .local_ai_supervisor import detect_hardware

class LocalMediaError(RuntimeError):
    """Local-only media task blocked or failed validation."""

EXTENSIONS = {"image": {".png", ".jpg", ".jpeg", ".webp"},
              "video": {".mp4", ".webm"}, "tts": {".wav"}, "music": {".wav", ".flac"}}
SHA = re.compile(r"^[a-f0-9]{64}$")
IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
REMOTE = re.compile(r"(?i)\b(?:https?|ftp|file)://")

def _digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def _save(path, value):
    path = Path(path)
    if path.is_symlink():
        raise LocalMediaError("Local media state cannot be a symbolic link.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False), encoding="utf-8")
    try:
        os.chmod(temp, 0o600)
    except OSError:
        pass
    os.replace(temp, path)

class LocalMediaPipeline:
    """Local ComfyUI media stages with durable queue IDs and output checksums."""
    def __init__(self, *, config_path, registry_path, model_root, work_root,
                 comfy_client=None, hardware_probe=detect_hardware):
        self.config_path = Path(config_path).expanduser()
        self.registry_path = Path(registry_path).expanduser()
        self.model_root = Path(model_root).expanduser().resolve()
        self.work_root = Path(work_root).expanduser().resolve()
        self.comfy_client = comfy_client
        self.hardware_probe = hardware_probe

    @classmethod
    def from_environment(cls):
        root = Path(__file__).resolve().parent.parent
        return cls(config_path=os.getenv("UNEXPECTED_MEDIA_WORKFLOWS", str(root / "local_ai" / "media_workflows.json")),
                   registry_path=os.getenv("UNEXPECTED_MODEL_REGISTRY", str(root / "local_ai" / "model_registry.json")),
                   model_root=os.getenv("UNEXPECTED_MODEL_ROOT", str(root / "models")),
                   work_root=os.getenv("UNEXPECTED_CREATOR_ROOT", str(Path.home() / ".unexpected" / "creator")))

    def _config(self):
        try:
            if self.config_path.is_symlink(): raise ValueError("symlink")
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
            raise LocalMediaError("Local media workflow config is missing or invalid.") from None
        if (not isinstance(data, dict) or data.get("schema_version") != 1
                or set(data) - {"schema_version", "comfyui_url", "workflow_root", "tasks"}
                or not isinstance(data.get("tasks"), dict) or set(data["tasks"]) - set(EXTENSIONS)):
            raise LocalMediaError("Unsupported local media workflow config.")
        return data

    def _registry(self):
        try:
            return load_model_registry(self.registry_path)
        except LocalAIError as exc:
            raise LocalMediaError(str(exc)) from None

    def _workflow_root(self, config):
        relative = Path(config.get("workflow_root", "workflows"))
        if relative.is_absolute() or ".." in relative.parts:
            raise LocalMediaError("Workflow root must remain local.")
        root = (self.config_path.parent / relative).resolve()
        try: root.relative_to(self.config_path.parent.resolve())
        except ValueError: raise LocalMediaError("Workflow root escapes local AI directory.") from None
        return root

    def _client(self, config, root):
        if self.comfy_client is None:
            try:
                self.comfy_client = LocalComfyUIClient(config.get("comfyui_url", "http://127.0.0.1:8188"),
                    workflow_root=root, timeout=20, max_output_bytes=512 * 1024 * 1024)
            except LocalComfyUIError as exc: raise LocalMediaError(str(exc)) from None
        if self.comfy_client.workflow_root.resolve() != root.resolve():
            raise LocalMediaError("ComfyUI workflow root mismatch.")
        return self.comfy_client

    def _check(self, task, spec, registry, hardware, workflow_root):
        problems = []
        if not isinstance(spec, dict): return ["no local workflow configured"]
        allowed = {"model_id", "workflow_file", "workflow_sha256", "allowed_node_types",
                   "input_bindings", "minimum_hardware", "timeout_seconds"}
        if set(spec) - allowed: problems.append("unsupported workflow config fields")
        model = next((m for m in registry["models"] if m["model_id"] == spec.get("model_id")), None)
        if model is None or model.get("task") != task:
            problems.append("task must reference matching model registry entry")
        elif not inspect_model_availability(model, self.model_root)["available"]:
            problems.append("local model weights, checksums or licence are not verified")
        minimum = spec.get("minimum_hardware", {})
        if not isinstance(minimum, dict) or set(minimum) - {"ram_gb", "vram_gb", "disk_gb"}:
            problems.append("invalid minimum hardware")
        else:
            ram, vram = hardware.get("ram_total_gb") or 0, hardware.get("gpu_vram_total_gb") or 0
            disk_root = self.model_root if self.model_root.exists() else self.model_root.parent
            disk = shutil.disk_usage(disk_root).free / (1024 ** 3) if disk_root.exists() else 0
            if ram < float(minimum.get("ram_gb", 0)): problems.append("insufficient system RAM")
            if vram < float(minimum.get("vram_gb", 0)): problems.append("insufficient GPU memory")
            if disk < float(minimum.get("disk_gb", 0)): problems.append("insufficient free disk")
        file, digest = spec.get("workflow_file"), spec.get("workflow_sha256")
        if not isinstance(file, str) or not file or Path(file).is_absolute() or ".." in Path(file).parts:
            problems.append("workflow file must be a safe relative path")
        elif not isinstance(digest, str) or not SHA.fullmatch(digest):
            problems.append("workflow hash must be pinned")
        else:
            path = workflow_root / file
            if path.is_symlink() or not path.is_file() or _digest(path) != digest:
                problems.append("workflow missing, unsafe or checksum-mismatched")
        nodes, bindings = spec.get("allowed_node_types"), spec.get("input_bindings")
        if not isinstance(nodes, list) or not nodes or len(nodes) > 128:
            problems.append("explicit node allowlist required")
        if not isinstance(bindings, dict) or "prompt" not in bindings:
            problems.append("prompt input binding required")
        timeout = spec.get("timeout_seconds", 900)
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 5 <= timeout <= 7200:
            problems.append("invalid task timeout")
        return problems

    def preflight(self, probe_service=False):
        if os.getenv("UNEXPECTED_AI_MODE", "").lower() not in {"local_only", "local-only"}:
            return {"mode": "local_only", "ready": False, "external_ai_api": "disabled",
                    "reason": "UNEXPECTED_AI_MODE=local_only is required"}
        try:
            config, registry, hardware = self._config(), self._registry(), self.hardware_probe()
            root = self._workflow_root(config)
            tasks = {}
            for task in EXTENSIONS:
                issues = self._check(task, config["tasks"].get(task), registry, hardware, root)
                tasks[task] = {"ready": not issues, "issues": issues}
            service = {"status": "not_checked", "local": True}
            if probe_service and all(v["ready"] for v in tasks.values()):
                try: service = self._client(config, root).probe()
                except LocalComfyUIError as exc: service = {"status": "unavailable", "local": True, "error": str(exc)}
            return {"mode": "local_only", "ready": all(v["ready"] for v in tasks.values())
                    and service["status"] in {"available", "not_checked"}, "tasks": tasks,
                    "hardware": hardware, "comfyui": service, "external_ai_api": "disabled",
                    "downloads_performed": False}
        except LocalMediaError as exc:
            return {"mode": "local_only", "ready": False, "external_ai_api": "disabled",
                    "downloads_performed": False, "reason": str(exc)}

    def _project(self, project_id):
        if not isinstance(project_id, str) or not re.fullmatch(r"[a-f0-9-]{8,64}", project_id, re.I):
            raise LocalMediaError("Invalid Creator project ID.")
        root = self.work_root / "projects"
        if root.is_symlink(): raise LocalMediaError("Projects root cannot be a symbolic link.")
        root.mkdir(parents=True, exist_ok=True)
        path = root / project_id
        if path.is_symlink(): raise LocalMediaError("Project cannot be a symbolic link.")
        path.mkdir(parents=True, exist_ok=True)
        path.resolve().relative_to(root.resolve())
        return path.resolve()

    def _state(self, project):
        path = project / "media_state.json"
        if path.is_symlink(): raise LocalMediaError("Media state cannot be a symbolic link.")
        if not path.exists(): return path, {"schema_version": 1, "assets": {}}
        try: state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError): raise LocalMediaError("Media state is corrupt.") from None
        if state.get("schema_version") != 1 or not isinstance(state.get("assets"), dict):
            raise LocalMediaError("Invalid media state schema.")
        return path, state

    def generate_asset(self, task, project_id, asset_key, prompt):
        if os.getenv("UNEXPECTED_AI_MODE", "").lower() not in {"local_only", "local-only"}:
            raise LocalMediaError("Local media generation requires UNEXPECTED_AI_MODE=local_only.")
        if task not in EXTENSIONS or not isinstance(asset_key, str) or not IDENT.fullmatch(asset_key):
            raise LocalMediaError("Invalid task or asset key.")
        if (not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 8000
                or REMOTE.search(prompt) or prompt.startswith(("/", chr(92)))):
            raise LocalMediaError("Prompt must be local text without URLs or file paths.")
        prompt = prompt.strip()
        config, registry, hardware = self._config(), self._registry(), self.hardware_probe()
        root = self._workflow_root(config)
        spec = config["tasks"].get(task)
        problems = self._check(task, spec, registry, hardware, root)
        if problems: raise LocalMediaError(task + " blocked: " + "; ".join(problems))
        client, project = self._client(config, root), self._project(project_id)
        state_path, state = self._state(project)
        key = task + ":" + asset_key
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
        workflow_hash = spec["workflow_sha256"]
        record = state["assets"].get(key, {})
        if record and (record.get("prompt_sha256") != prompt_hash or record.get("workflow_sha256") != workflow_hash):
            raise LocalMediaError("Asset key reused with different prompt or workflow.")
        if record.get("status") == "completed":
            cached = project / record["path"]
            if cached.is_symlink() or not cached.is_file() or _digest(cached) != record["sha256"]:
                raise LocalMediaError("Cached asset checksum mismatch.")
            return {**record, "status": "reused"}
        if record.get("status") == "queued":
            prompt_id = record.get("prompt_id")
            if not isinstance(prompt_id, str): raise LocalMediaError("Queued job has no prompt ID.")
        else:
            values = {"prompt": prompt}
            if "seed" in spec["input_bindings"]:
                values["seed"] = int(hashlib.sha256((project_id + key).encode()).hexdigest()[:8], 16)
            queued = client.queue_workflow(root / spec["workflow_file"], expected_sha256=workflow_hash,
                allowed_node_types=spec["allowed_node_types"], input_bindings=spec["input_bindings"],
                input_values=values)
            prompt_id = queued["prompt_id"]
            state["assets"][key] = {"status": "queued", "task": task, "prompt_id": prompt_id,
                "prompt_sha256": prompt_hash, "workflow_sha256": workflow_hash,
                "provider": "comfyui-local", "queued_at": int(time.time())}
            _save(state_path, state)
        try:
            result = client.wait_for_result(prompt_id, timeout_seconds=spec.get("timeout_seconds", 900))
            outputs = client.collect_outputs(result, project / "assets" / task / asset_key)
        except LocalComfyUIError as exc:
            raise LocalMediaError("Task remains queued and can resume (" + type(exc).__name__ + ").") from None
        kind = {"image": "images", "video": "videos", "tts": "audio", "music": "audio"}[task]
        selected = None
        for item in outputs:
            path = project / "assets" / task / asset_key / item["path"]
            if item["kind"] == kind and path.suffix.lower() in EXTENSIONS[task]:
                selected = (path, item); break
        if selected is None: raise LocalMediaError("ComfyUI returned no supported " + task + " output.")
        path, item = selected
        if path.is_symlink() or not path.is_file() or path.stat().st_size < 1024:
            raise LocalMediaError("Generated asset is unsafe or too small.")
        completed = {"status": "completed", "task": task, "path": str(path.resolve().relative_to(project)),
            "sha256": _digest(path), "byte_size": path.stat().st_size,
            "prompt_sha256": prompt_hash, "workflow_sha256": workflow_hash, "prompt_id": prompt_id,
            "mime_type": item["mime_type"], "provider": "comfyui-local", "completed_at": int(time.time())}
        state["assets"][key] = completed
        _save(state_path, state)
        return completed



    @staticmethod
    def _json_output(value, label):
        if not isinstance(value, str) or not value.strip():
            raise LocalMediaError(label + " output is empty.")
        raw = value.strip()
        fence = chr(96) * 3
        if raw.startswith(fence):
            raw = raw[len(fence):]
            if raw.lower().startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
            if raw.endswith(fence):
                raw = raw[:-len(fence)].strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise LocalMediaError(label + " output must be strict JSON.") from None
        if not isinstance(data, dict):
            raise LocalMediaError(label + " output must be a JSON object.")
        return data

    def produce(self, project_id, project, storyboard_text, narration_text):
        if os.getenv("UNEXPECTED_AI_MODE", "").lower() not in {"local_only", "local-only"}:
            raise LocalMediaError("Production requires UNEXPECTED_AI_MODE=local_only.")
        storyboard = self._json_output(storyboard_text, "Storyboard")
        voice = self._json_output(narration_text, "Voice")
        script = storyboard.get("narration_script")
        spoken = voice.get("narration_text")
        captions = voice.get("captions_srt")
        music_prompt = storyboard.get("music_prompt")
        scenes = storyboard.get("scenes")
        if not isinstance(script, str) or not script.strip() or spoken != script:
            raise LocalMediaError("Voice narration must exactly match the storyboard script.")
        if not isinstance(captions, str) or not captions.strip() or len(captions.encode("utf-8")) > 2000000:
            raise LocalMediaError("Voice stage must return a bounded SRT caption file.")
        if not isinstance(music_prompt, str) or not music_prompt.strip():
            raise LocalMediaError("Storyboard must include an original local music prompt.")
        if not isinstance(scenes, list) or not 2 <= len(scenes) <= 120:
            raise LocalMediaError("Storyboard must contain 2–120 structured scenes.")
        assets = {"images": [], "videos": []}
        checked_scenes = []
        for index, scene in enumerate(scenes, 1):
            if not isinstance(scene, dict):
                raise LocalMediaError("Storyboard scenes must be objects.")
            scene_id = scene.get("scene_id", "scene-" + str(index).zfill(3))
            image_prompt, motion_prompt = scene.get("visual_prompt"), scene.get("motion_prompt")
            duration = scene.get("duration_seconds")
            if (not isinstance(scene_id, str) or not IDENT.fullmatch(scene_id)
                    or not isinstance(image_prompt, str) or not image_prompt.strip()
                    or not isinstance(motion_prompt, str) or not motion_prompt.strip()
                    or isinstance(duration, bool) or not isinstance(duration, (int, float))
                    or not math.isfinite(float(duration)) or not 2 <= float(duration) <= 180):
                raise LocalMediaError("Storyboard scene " + str(index) + " is invalid.")
            checked_scenes.append({"scene_id": scene_id, "duration_seconds": float(duration)})
            assets["images"].append(self.generate_asset("image", project_id, scene_id, image_prompt))
            assets["videos"].append(self.generate_asset("video", project_id, scene_id, motion_prompt))
        assets["narration"] = self.generate_asset("tts", project_id, "narration", spoken)
        assets["music"] = self.generate_asset("music", project_id, "soundtrack", music_prompt)
        render = self._render(project_id, project, checked_scenes, assets, captions)
        passed = render["qa"].get("status") == "passed"
        return {"status": "completed" if passed else "qa_failed", "project_id": project_id,
                "provider_route": "local", "assets": assets, "render": render,
                "video_rendered": True, "qa_passed": passed,
                "publishing_performed": False, "external_ai_api": "disabled"}

    def _run_local(self, command, cwd, timeout=900):
        env = {"PATH": os.environ.get("PATH", os.defpath), "HOME": str(Path.home()),
               "TMP": os.environ.get("TMP", "/tmp"), "TEMP": os.environ.get("TEMP", "/tmp"),
               "UNEXPECTED_AI_MODE": "local_only", "HF_HUB_OFFLINE": "1",
               "TRANSFORMERS_OFFLINE": "1", "DO_NOT_TRACK": "1",
               "NO_PROXY": "127.0.0.1,localhost,::1", "no_proxy": "127.0.0.1,localhost,::1"}
        try:
            result = subprocess.run(command, cwd=str(cwd), env=env, shell=False,
                capture_output=True, text=True, timeout=max(10, min(int(timeout), 3600)),
                check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise LocalMediaError("Offline media command failed (" + type(exc).__name__ + ").") from None
        if result.returncode:
            lines = (result.stderr or result.stdout or "local renderer failed").strip().splitlines()
            raise LocalMediaError((lines[-1] if lines else "local renderer failed")[:400])
        return result

    def _render(self, project_id, project, scenes, assets, captions):
        ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
        if not ffmpeg or not ffprobe:
            raise LocalMediaError("Local FFmpeg and ffprobe are required.")
        root = self._project(project_id)
        caption_file = root / "captions.srt"
        if caption_file.is_symlink():
            raise LocalMediaError("Caption file cannot be a symbolic link.")
        caption_file.write_text(captions, encoding="utf-8")
        channels = project.get("channel_profile", {})
        youtube = channels.get("youtube", {}) if isinstance(channels, dict) else {}
        wide = isinstance(youtube, dict) and (youtube.get("format") == "longform" or youtube.get("aspect_ratio") == "16:9")
        width, height = (1920, 1080) if wide else (1080, 1920)
        narration = root / assets["narration"]["path"]
        music = root / assets["music"]["path"]
        probe = self._run_local([ffprobe, "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(narration)], root, 30)
        try:
            duration = float(probe.stdout.strip())
        except ValueError:
            raise LocalMediaError("Narration duration could not be read.") from None
        if not math.isfinite(duration) or not 5 <= duration <= 3600:
            raise LocalMediaError("Narration duration is outside supported bounds.")
        if abs(sum(scene["duration_seconds"] for scene in scenes) - duration) > 1.5:
            raise LocalMediaError("Scene timing does not cover the narration.")
        segment_dir = root / "segments"
        segment_dir.mkdir(exist_ok=True)
        concat_lines = ["ffconcat version 1.0"]
        for index, (scene, asset) in enumerate(zip(scenes, assets["videos"])):
            source = root / asset["path"]
            if source.is_symlink() or not source.is_file() or _digest(source) != asset["sha256"]:
                raise LocalMediaError("A generated video segment failed checksum verification.")
            segment_name = "segment-" + str(index).zfill(3) + ".mp4"
            target = segment_dir / segment_name
            if target.is_symlink():
                raise LocalMediaError("A video segment cannot be a symbolic link.")
            self._run_local([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-stream_loop", "-1", "-i", str(source), "-t", str(scene["duration_seconds"]),
                "-an", "-vf", f"fps=24,scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,format=yuv420p",
                "-r", "24", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                "-pix_fmt", "yuv420p", str(target)], root, 900)
            if not target.is_file() or target.stat().st_size < 4096:
                raise LocalMediaError("A normalized video segment failed file verification.")
            concat_lines.append("file 'segments/" + segment_name + "'")
        concat = root / "segments.ffconcat"
        concat.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
        for audio in (narration, music):
            if audio.is_symlink() or not audio.is_file():
                raise LocalMediaError("Narration or music asset is missing.")
        output = root / "master.mp4"
        if output.is_symlink():
            raise LocalMediaError("Master MP4 cannot be a symbolic link.")
        if output.exists():
            output = root / ("master-" + str(int(time.time())) + ".mp4")
        self._run_local([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat), "-i", str(narration),
            "-stream_loop", "-1", "-i", str(music), "-filter_complex",
            "[1:a]volume=1.0[n];[2:a]volume=0.13[m];[n][m]amix=inputs=2:duration=first:dropout_transition=2,loudnorm=I=-14:TP=-1.2:LRA=11[a]",
            "-map", "0:v:0", "-map", "[a]", "-vf",
            "subtitles=captions.srt:force_style='FontName=DejaVu Sans,FontSize=34,Outline=2,Shadow=1,MarginV=72,Alignment=2'",
            "-t", format(duration, ".3f"), "-r", "24", "-c:v", "libx264", "-preset",
            "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(output)], root, 1800)
        from .creator_qa import CreatorVideoQA, CreatorVideoQAError
        try:
            qa = CreatorVideoQA(ffmpeg=ffmpeg, ffprobe=ffprobe, timeout_seconds=600).inspect(
                output, captions_path=caption_file, motion_mode="full_motion")
        except CreatorVideoQAError as exc:
            raise LocalMediaError("Encoded local MP4 failed media QA (" + type(exc).__name__ + ").") from None
        return {"path": str(output.relative_to(root)), "sha256": qa["sha256"],
                "byte_size": qa["byte_size"], "profile": "youtube_longform" if wide else "youtube_shorts",
                "width": width, "height": height, "fps": 24, "qa": qa}

__all__ = ["LocalMediaPipeline", "LocalMediaError"]
