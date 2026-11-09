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
                or set(data) - {"schema_version", "comfyui_url", "workflow_root", "tasks", "video_fallback"}
                or not isinstance(data.get("tasks"), dict) or set(data["tasks"]) - set(EXTENSIONS)):
            raise LocalMediaError("Unsupported local media workflow config.")
        if data.get("video_fallback", "disabled") not in {"disabled", "illustrated_story"}:
            raise LocalMediaError("Unsupported local video fallback mode.")
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
            fallback_enabled = config.get("video_fallback", "disabled") == "illustrated_story"
            for task in EXTENSIONS:
                issues = self._check(task, config["tasks"].get(task), registry, hardware, root)
                if task == "video" and issues and fallback_enabled:
                    fallback_issues = []
                    if not shutil.which("ffmpeg"):
                        fallback_issues.append("FFmpeg is required for procedural illustrated motion")
                    tasks[task] = {
                        "ready": not fallback_issues,
                        "issues": fallback_issues,
                        "mode": "illustrated_story_procedural",
                        "fallback_reason": issues,
                    }
                else:
                    tasks[task] = {
                        "ready": not issues,
                        "issues": issues,
                        "mode": "model_generated" if task == "video" else "local_model",
                    }
            service = {"status": "not_checked", "local": True}
            if probe_service and all(v["ready"] for v in tasks.values()):
                try: service = self._client(config, root).probe()
                except LocalComfyUIError as exc: service = {"status": "unavailable", "local": True, "error": str(exc)}
            return {"mode": "local_only", "ready": all(v["ready"] for v in tasks.values())
                    and service["status"] in {"available", "not_checked"}, "tasks": tasks,
                    "video_mode": tasks["video"].get("mode"),
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

    def _procedural_motion_asset(self, project_id, scene_id, image_asset, duration_seconds, project):
        """Create labelled, deterministic motion from a verified local still when no video model fits."""
        root = self._project(project_id)
        relative = Path(image_asset.get("path", ""))
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise LocalMediaError("Storyboard image path is unsafe.")
        still = root / relative
        if still.is_symlink() or not still.is_file() or _digest(still) != image_asset.get("sha256"):
            raise LocalMediaError("Procedural motion requires a checksum-verified storyboard still.")
        try:
            still.resolve().relative_to(root.resolve())
        except ValueError:
            raise LocalMediaError("Storyboard image escapes its project directory.") from None
        duration = float(duration_seconds)
        if not math.isfinite(duration) or not 2 <= duration <= 180:
            raise LocalMediaError("Procedural motion duration is invalid.")
        channels = project.get("channel_profile", {})
        youtube = channels.get("youtube", {}) if isinstance(channels, dict) else {}
        wide = isinstance(youtube, dict) and (
            youtube.get("format") == "longform" or youtube.get("aspect_ratio") == "16:9")
        width, height = (1920, 1080) if wide else (1080, 1920)
        motion_spec = {
            "mode": "illustrated_story_procedural_v1",
            "still_sha256": image_asset["sha256"],
            "duration_seconds": round(duration, 3),
            "resolution": [width, height],
            "fps": 24,
        }
        prompt_hash = hashlib.sha256(json.dumps(
            motion_spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        workflow_hash = hashlib.sha256(b"uneXpected-ffmpeg-illustrated-motion-v1").hexdigest()
        state_path, state = self._state(root)
        key = "video:" + scene_id
        record = state["assets"].get(key, {})
        if record and (record.get("prompt_sha256") != prompt_hash
                       or record.get("workflow_sha256") != workflow_hash):
            raise LocalMediaError("Procedural video asset key was reused with different source or timing.")
        if record.get("status") == "completed":
            cached = root / record["path"]
            if cached.is_symlink() or not cached.is_file() or _digest(cached) != record.get("sha256"):
                raise LocalMediaError("Cached procedural motion checksum mismatch.")
            return {**record, "status": "reused"}
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise LocalMediaError("FFmpeg is required for illustrated-story motion.")
        output_dir = root / "assets" / "video" / scene_id
        output_dir.mkdir(parents=True, exist_ok=True)
        if output_dir.is_symlink():
            raise LocalMediaError("Procedural motion output directory cannot be a symbolic link.")
        output = output_dir / "illustrated-motion.mp4"
        temporary = output_dir / "illustrated-motion.part.mp4"
        if output.is_symlink() or temporary.is_symlink():
            raise LocalMediaError("Procedural motion output cannot be a symbolic link.")
        filter_graph = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},"
            f"zoompan=z='1+0.10*on/({duration:.3f}*24)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d=1:s={width}x{height}:fps=24,format=yuv420p"
        )
        try:
            self._run_local([
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-loop", "1", "-framerate", "24", "-i", str(still),
                "-vf", filter_graph, "-t", format(duration, ".3f"),
                "-an", "-r", "24", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "22", "-pix_fmt", "yuv420p", str(temporary),
            ], root, 900)
            if not temporary.is_file() or temporary.is_symlink() or temporary.stat().st_size < 4096:
                raise LocalMediaError("Procedural motion did not produce a valid MP4 segment.")
            os.replace(temporary, output)
        except Exception:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        completed = {
            "status": "completed", "task": "video",
            "path": str(output.relative_to(root)),
            "sha256": _digest(output), "byte_size": output.stat().st_size,
            "prompt_sha256": prompt_hash, "workflow_sha256": workflow_hash,
            "provider": "ffmpeg-local-procedural",
            "video_mode": "illustrated_story_procedural",
            "source_image_sha256": image_asset["sha256"],
            "completed_at": int(time.time()),
        }
        state["assets"][key] = completed
        _save(state_path, state)
        return completed

    def produce(self, project_id, project, storyboard_text, narration_text):
        if os.getenv("UNEXPECTED_AI_MODE", "").lower() not in {"local_only", "local-only"}:
            raise LocalMediaError("Production requires UNEXPECTED_AI_MODE=local_only.")
        preflight = self.preflight(probe_service=True)
        if not preflight.get("ready"):
            raise LocalMediaError("Local media preflight is blocked: " + str(preflight.get("reason") or
                preflight.get("tasks") or preflight.get("comfyui")))
        video_mode = preflight.get("video_mode", "model_generated")
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
            image_asset = self.generate_asset("image", project_id, scene_id, image_prompt)
            assets["images"].append(image_asset)
            if video_mode == "illustrated_story_procedural":
                video_asset = self._procedural_motion_asset(
                    project_id, scene_id, image_asset, float(duration), project)
            else:
                video_asset = self.generate_asset("video", project_id, scene_id, motion_prompt)
            assets["videos"].append(video_asset)
        assets["narration"] = self.generate_asset("tts", project_id, "narration", spoken)
        assets["music"] = self.generate_asset("music", project_id, "soundtrack", music_prompt)
        render = self._render(
            project_id, project, checked_scenes, assets, captions,
            motion_mode="illustrated_story" if video_mode == "illustrated_story_procedural" else "full_motion",
        )
        passed = render["qa"].get("status") == "passed"
        return {"status": "completed" if passed else "qa_failed", "project_id": project_id,
                "provider_route": "local", "assets": assets, "render": render,
                "video_mode": video_mode, "video_rendered": True, "qa_passed": passed,
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

    def _render(self, project_id, project, scenes, assets, captions, motion_mode="full_motion"):
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

        def verified_asset_path(asset, label):
            if not isinstance(asset, dict) or not isinstance(asset.get("path"), str):
                raise LocalMediaError(label + " asset metadata is invalid.")
            relative = Path(asset["path"])
            if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                raise LocalMediaError(label + " asset path is unsafe.")
            path = root / relative
            if path.is_symlink() or not path.is_file() or _digest(path) != asset.get("sha256"):
                raise LocalMediaError(label + " asset failed checksum verification.")
            try:
                path.resolve().relative_to(root.resolve())
            except ValueError:
                raise LocalMediaError(label + " asset escapes its project directory.") from None
            return path

        image_assets = assets.get("images", [])
        video_assets = assets.get("videos", [])
        if not isinstance(image_assets, list) or not isinstance(video_assets, list):
            raise LocalMediaError("Storyboard image and video assets must be lists.")
        if len(image_assets) != len(scenes) or len(video_assets) != len(scenes):
            raise LocalMediaError("Every scene requires one verified image and one verified video segment.")
        narration = verified_asset_path(assets.get("narration"), "Narration")
        music = verified_asset_path(assets.get("music"), "Music")
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
        for index, (scene, image_asset, asset) in enumerate(zip(scenes, image_assets, video_assets)):
            still = verified_asset_path(image_asset, "Storyboard image")
            source = verified_asset_path(asset, "Generated video segment")
            segment_name = "segment-" + str(index).zfill(3) + ".mp4"
            target = segment_dir / segment_name
            if target.is_symlink():
                raise LocalMediaError("A video segment cannot be a symbolic link.")
            duration_value = str(scene["duration_seconds"])
            scale = (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                     f"crop={width}:{height},setsar=1")
            filter_graph = (
                f"[0:v]{scale},format=rgba[still];"
                f"[1:v]{scale},format=rgba[motion];"
                "[motion][still]overlay=shortest=1:enable='lt(t,0.45)',"
                "fps=24,format=yuv420p[outv]"
            )
            self._run_local([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-loop", "1", "-framerate", "24", "-t", duration_value, "-i", str(still),
                "-stream_loop", "-1", "-i", str(source), "-t", duration_value,
                "-filter_complex", filter_graph, "-map", "[outv]", "-an",
                "-r", "24", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                "-pix_fmt", "yuv420p", str(target)], root, 900)
            if not target.is_file() or target.stat().st_size < 4096:
                raise LocalMediaError("A normalized video segment failed file verification.")
            concat_lines.append("file 'segments/" + segment_name + "'")
        concat = root / "segments.ffconcat"
        concat.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
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
                output, captions_path=caption_file, motion_mode=motion_mode)
        except CreatorVideoQAError as exc:
            raise LocalMediaError("Encoded local MP4 failed media QA (" + type(exc).__name__ + ").") from None
        return {"path": str(output.relative_to(root)), "sha256": qa["sha256"],
                "byte_size": qa["byte_size"], "profile": "youtube_longform" if wide else "youtube_shorts",
                "width": width, "height": height, "fps": 24,
                "storyboard_stills_count": len(scenes), "qa": qa}

__all__ = ["LocalMediaPipeline", "LocalMediaError"]
