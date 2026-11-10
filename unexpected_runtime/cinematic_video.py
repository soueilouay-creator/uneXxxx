from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

MODEL_ID = "bytedance/seedance-2.5/text-to-video"
QUEUE_ROOT = "https://queue.fal.run"
FAL_API_ROOT = "https://fal.run"
PRICE_PER_1000_TOKENS = 0.0214
RESOLUTIONS = {
    "480p": (496, 864),
    "720p": (720, 1280),
}
MAX_SCENES = 12
MAX_PROMPT_CHARS = 5000
MAX_CHARACTER_BIBLE_CHARS = 3000
MAX_CLIP_BYTES = 250 * 1024 * 1024
MAX_TOTAL_SECONDS = 180
QUOTE_TTL_SECONDS = 900


class CinematicVideoError(RuntimeError):
    """A cinematic video request was rejected or could not be verified."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _SafeMediaRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if CinematicVideoCreator._trusted_media_url(newurl):
            return super().redirect_request(req, fp, code, msg, headers, newurl)
        raise CinematicVideoError("Generated media redirected to a non-allowlisted host.")


def estimate_cost_usd(duration_seconds: int, resolution: str, aspect_ratio: str = "9:16") -> float:
    if resolution not in RESOLUTIONS or aspect_ratio != "9:16":
        raise CinematicVideoError("The first cinematic profile supports vertical 9:16 at 480p or 720p.")
    width, height = RESOLUTIONS[resolution]
    tokens = (width * height * duration_seconds * 24) / 1024
    return round(tokens / 1000 * PRICE_PER_1000_TOKENS, 4)


def _private_key() -> str:
    key = os.getenv("FAL_KEY", "").strip()
    if key:
        return key
    path = Path(os.getenv(
        "UNEXPECTED_CINEMATIC_ENV_FILE",
        "~/.config/uneXpected-v8/cinematic.env",
    )).expanduser()
    if path.is_symlink() or not path.is_file():
        return ""
    try:
        if os.name != "nt" and path.stat().st_mode & 0o077:
            return ""
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""
    values = {}
    for line in raw.splitlines():
        item = line.strip()
        if not item or item.startswith("#"):
            continue
        if "=" not in item:
            return ""
        name, value = item.split("=", 1)
        if name.strip() != "FAL_KEY" or "FAL_KEY" in values:
            return ""
        values["FAL_KEY"] = value.strip().strip('"').strip("'")
    return values.get("FAL_KEY", "")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class CinematicVideoCreator:
    """Connected Seedance scene generator; all completed MP4s are stored locally.

    No provider call is made by status(), quote(), or preflight(). A paid queue
    submission is only made by submit() after a valid, single-use quote approval.
    """

    def __init__(
        self,
        *,
        root: str | Path,
        quote_secret: str,
        api_key: str | None = None,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        timeout_seconds: int = 60,
    ):
        if not isinstance(quote_secret, str) or len(quote_secret) < 32:
            raise CinematicVideoError("A runtime signing secret is required.")
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            self.root.chmod(0o700)
        except OSError:
            pass
        self.quote_secret = quote_secret.encode("utf-8")
        self.api_key = _private_key() if api_key is None else str(api_key).strip()
        self.ffmpeg = shutil.which(ffmpeg) or ffmpeg
        self.ffprobe = shutil.which(ffprobe) or ffprobe
        self.timeout = max(5, min(int(timeout_seconds), 180))

    @classmethod
    def from_environment(cls, *, quote_secret: str):
        root = os.getenv(
            "UNEXPECTED_CINEMATIC_VIDEO_ROOT",
            "~/.local/share/uneXpected-v8/cinematic-videos",
        )
        return cls(root=root, quote_secret=quote_secret)

    def status(self) -> dict[str, Any]:
        ffmpeg_ok = bool(shutil.which(self.ffmpeg) or Path(self.ffmpeg).is_file())
        ffprobe_ok = bool(shutil.which(self.ffprobe) or Path(self.ffprobe).is_file())
        font = self._find_font()
        filters = ""
        if ffmpeg_ok:
            try:
                probe = subprocess.run([self.ffmpeg, "-hide_banner", "-filters"],
                    capture_output=True, text=True, timeout=10, check=False)
                filters = (probe.stdout or "") + (probe.stderr or "")
            except (OSError, subprocess.TimeoutExpired):
                filters = ""
        filter_checks = {name: bool(re.search(r"\\b" + name + r"\\b", filters))
                         for name in ("drawtext", "xfade", "acrossfade")}
        filters_ok = all(filter_checks.values())
        return {
            "provider": "fal.ai",
            "model": MODEL_ID,
            "configured": bool(self.api_key),
            "ready": bool(self.api_key and ffmpeg_ok and ffprobe_ok and font and filters_ok),
            "ffmpeg": ffmpeg_ok,
            "ffprobe": ffprobe_ok,
            "subtitle_font_available": bool(font),
            "required_filters": filter_checks,
            "generation": "connected_provider",
            "storage": "local",
            "publishing": False,
            "paid_generation_started": False,
            "key_source": "environment_or_private_file" if self.api_key else "not_configured",
            "supported": {"resolutions": ["480p", "720p"], "aspect_ratio": "9:16",
                          "scene_duration_seconds": [4, 30], "max_scenes": MAX_SCENES},
        }

    def quote(self, payload: Any) -> dict[str, Any]:
        clean = self._validate_payload(payload)
        total_seconds = sum(x["duration_seconds"] for x in clean["scenes"])
        estimate = round(sum(
            estimate_cost_usd(scene["duration_seconds"], clean["resolution"])
            for scene in clean["scenes"]
        ), 2)
        quote_id = uuid.uuid4().hex
        now = int(time.time())
        signed = {
            "quote_id": quote_id,
            "title": clean["title"],
            "character_bible": clean["character_bible"],
            "scenes": clean["scenes"],
            "resolution": clean["resolution"],
            "aspect_ratio": "9:16",
            "total_seconds": total_seconds,
            "estimated_cost_usd": estimate,
            "issued_at": now,
            "expires_at": now + QUOTE_TTL_SECONDS,
        }
        body = _b64(json.dumps(signed, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())
        signature = _b64(hmac.new(self.quote_secret, body.encode("ascii"), hashlib.sha256).digest())
        return {
            "quote_id": quote_id,
            "quote_token": body + "." + signature,
            "provider": "fal.ai",
            "model": MODEL_ID,
            "resolution": clean["resolution"],
            "aspect_ratio": "9:16",
            "scene_count": len(clean["scenes"]),
            "total_seconds": total_seconds,
            "estimated_cost_usd": estimate,
            "price_basis": "fal published token formula; estimate can vary with provider pricing and output",
            "expires_at": signed["expires_at"],
            "paid_generation_started": False,
            "requires_explicit_approval": True,
        }

    @staticmethod
    def _validate_payload(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict) or set(payload) - {"title", "character_bible", "scenes", "resolution"}:
            raise CinematicVideoError("Cinematic brief contains unsupported fields.")
        title = payload.get("title")
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 160:
            raise CinematicVideoError("A title of 1–160 characters is required.")
        resolution = payload.get("resolution", "480p")
        if resolution not in RESOLUTIONS:
            raise CinematicVideoError("Choose 480p or 720p.")
        bible = payload.get("character_bible", "")
        if not isinstance(bible, str) or len(bible) > MAX_CHARACTER_BIBLE_CHARS:
            raise CinematicVideoError("Character bible must be plain text up to 3,000 characters.")
        scenes = payload.get("scenes")
        if not isinstance(scenes, list) or not 1 <= len(scenes) <= MAX_SCENES:
            raise CinematicVideoError(f"Provide between 1 and {MAX_SCENES} scenes.")
        clean_scenes = []
        total = 0
        for index, scene in enumerate(scenes, 1):
            if not isinstance(scene, dict) or set(scene) - {"scene_id", "prompt", "caption", "duration_seconds"}:
                raise CinematicVideoError(f"Scene {index} contains unsupported fields.")
            prompt = scene.get("prompt")
            caption = scene.get("caption")
            duration = scene.get("duration_seconds", 5)
            scene_id = scene.get("scene_id", f"scene-{index:02d}")
            if not isinstance(scene_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", scene_id):
                raise CinematicVideoError(f"Scene {index} has an invalid scene ID.")
            if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT_CHARS:
                raise CinematicVideoError(f"Scene {index} prompt must contain 1–5,000 characters.")
            if re.search(r"(?i)\b(?:https?|ftp|file)://", prompt):
                raise CinematicVideoError("Scene prompts must not contain external URLs.")
            if not isinstance(caption, str) or not caption.strip() or len(caption.strip()) > 84:
                raise CinematicVideoError(f"Scene {index} caption must contain 1–84 characters.")
            if isinstance(duration, bool) or not isinstance(duration, int) or not 4 <= duration <= 30:
                raise CinematicVideoError(f"Scene {index} duration must be 4–30 whole seconds.")
            total += duration
            if total > MAX_TOTAL_SECONDS:
                raise CinematicVideoError(f"A video project cannot exceed {MAX_TOTAL_SECONDS} generated seconds.")
            clean_scenes.append({
                "scene_id": scene_id,
                "prompt": prompt.strip(),
                "caption": caption.strip(),
                "duration_seconds": duration,
            })
        if len({s["scene_id"] for s in clean_scenes}) != len(clean_scenes):
            raise CinematicVideoError("Scene IDs must be unique.")
        return {"title": title.strip(), "character_bible": bible.strip(),
                "resolution": resolution, "scenes": clean_scenes}

    def _decode_quote(self, token: Any) -> dict[str, Any]:
        if not isinstance(token, str) or token.count(".") != 1 or len(token) > 40000:
            raise CinematicVideoError("A valid, unexpired cost quote is required.")
        body, signature = token.split(".", 1)
        expected = _b64(hmac.new(self.quote_secret, body.encode("ascii", "strict"), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise CinematicVideoError("The cost quote signature is invalid.")
        try:
            data = json.loads(_unb64(body).decode("utf-8"))
        except (ValueError, UnicodeError):
            raise CinematicVideoError("The cost quote could not be read.") from None
        if not isinstance(data, dict) or int(data.get("expires_at", 0)) < int(time.time()):
            raise CinematicVideoError("The cost quote has expired. Request a new quote.")
        return data

    def submit(self, payload: Any) -> dict[str, Any]:
        if not self.api_key:
            raise CinematicVideoError("fal.ai is not configured. Add FAL_KEY to the private cinematic.env file; the key is never sent to the browser.")
        preflight = self.status()
        if not preflight.get("ready"):
            raise CinematicVideoError("Cinematic preflight is blocked: configure FAL_KEY and verify FFmpeg, FFprobe, drawtext, xfade, acrossfade and a local font.")
        if not isinstance(payload, dict) or set(payload) != {"quote_token", "approved_max_usd"}:
            raise CinematicVideoError("Generation requires exactly a quote token and the explicitly approved maximum cost.")
        quote = self._decode_quote(payload["quote_token"])
        approved = payload["approved_max_usd"]
        if isinstance(approved, bool) or not isinstance(approved, (int, float)) or round(float(approved), 2) != quote.get("estimated_cost_usd"):
            raise CinematicVideoError("The approved maximum must exactly match the displayed quote.")
        quote_id = quote.get("quote_id")
        if not isinstance(quote_id, str) or not re.fullmatch(r"[a-f0-9]{32}", quote_id):
            raise CinematicVideoError("The quote ID is invalid.")
        used_dir = self.root / "used-quotes"
        used_dir.mkdir(mode=0o700, exist_ok=True)
        used = used_dir / (quote_id + ".used")
        try:
            fd = os.open(str(used), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w", encoding="ascii") as handle:
                handle.write(str(int(time.time())))
        except FileExistsError:
            raise CinematicVideoError("This quote has already been used. Request a fresh quote.") from None

        job_id = uuid.uuid4().hex
        folder = self.root / job_id
        folder.mkdir(mode=0o700)
        manifest = {
            "job_id": job_id, "title": quote["title"], "provider": "fal.ai",
            "model": MODEL_ID, "resolution": quote["resolution"], "aspect_ratio": "9:16",
            "estimated_cost_usd": quote["estimated_cost_usd"],
            "approved_max_usd": round(float(approved), 2), "total_seconds": quote["total_seconds"],
            "status": "submitting", "created_at": int(time.time()), "scenes": [],
            "publishing_performed": False,
        }
        for index, scene in enumerate(quote["scenes"], 1):
            prompt = scene["prompt"]
            if quote.get("character_bible"):
                prompt = ("CHARACTER AND WORLD CONTINUITY (preserve exactly across every scene):\n"
                          + quote["character_bible"] + "\n\nSCENE ACTION:\n" + prompt)
            body = {
                "prompt": prompt,
                "duration": str(scene["duration_seconds"]),
                "resolution": quote["resolution"],
                "aspect_ratio": "9:16",
                "generate_audio": True,
            }
            entry = {**scene, "status": "submission_pending"}
            manifest["scenes"].append(entry)
            self._save(folder, manifest)
            try:
                response = self._api_request("POST", QUEUE_ROOT + "/" + MODEL_ID, body)
                request_id = response.get("request_id")
                if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", request_id):
                    raise CinematicVideoError("Provider accepted a request without a valid request ID; status is uncertain.")
                entry.update({"request_id": request_id, "status": "queued"})
            except Exception as exc:
                entry.update({"status": "submission_uncertain", "error": type(exc).__name__})
                manifest["status"] = "partial_submission_uncertain"
                self._save(folder, manifest)
                break
        else:
            manifest["status"] = "queued"
        self._save(folder, manifest)
        return self._public_manifest(manifest)

    def get_job(self, job_id: str) -> dict[str, Any]:
        folder = self._job_folder(job_id)
        manifest = self._read_manifest(folder)
        if manifest["status"] in {"queued", "generating", "partial_submission_uncertain"}:
            self._advance(folder, manifest)
        return self._public_manifest(self._read_manifest(folder))

    def read_video(self, job_id: str) -> bytes:
        folder = self._job_folder(job_id)
        manifest = self._read_manifest(folder)
        if manifest.get("status") not in {"completed", "qa_failed"}:
            raise CinematicVideoError("The cinematic master is not assembled yet.")
        record = manifest.get("master") or {}
        path = folder / "master.mp4"
        if (not path.is_file() or path.is_symlink() or path.stat().st_size != record.get("byte_size")
                or self._sha(path) != record.get("sha256")):
            raise CinematicVideoError("The local cinematic master failed checksum verification.")
        return path.read_bytes()

    def _advance(self, folder: Path, manifest: dict[str, Any]) -> None:
        for scene in manifest["scenes"]:
            if scene.get("status") not in {"queued", "generating"}:
                continue
            request_id = scene["request_id"]
            try:
                status = self._api_request("GET", f"{QUEUE_ROOT}/{MODEL_ID}/requests/{request_id}/status")
                state = status.get("status")
                if state in {"IN_QUEUE", "IN_PROGRESS"}:
                    scene["status"] = "generating"
                    manifest["status"] = "generating"
                    self._save(folder, manifest)
                    continue
                if state != "COMPLETED":
                    scene["status"] = "failed"
                    scene["error"] = "provider_generation_failed"
                    manifest["status"] = "partial_failed"
                    self._save(folder, manifest)
                    continue
                result = self._api_request("GET", f"{QUEUE_ROOT}/{MODEL_ID}/requests/{request_id}")
                data = result.get("data", result)
                video = data.get("video") if isinstance(data, dict) else None
                url = video.get("url") if isinstance(video, dict) else None
                if not self._trusted_media_url(url):
                    raise CinematicVideoError("Provider result did not contain a trusted media URL.")
                target = folder / (scene["scene_id"] + ".mp4")
                self._download(url, target)
                scene["status"] = "downloaded"
                scene["file"] = target.name
                scene["byte_size"] = target.stat().st_size
                scene["sha256"] = self._sha(target)
                self._save(folder, manifest)
            except Exception as exc:
                scene["status"] = "failed"
                scene["error"] = type(exc).__name__
                manifest["status"] = "partial_failed"
                self._save(folder, manifest)
        statuses = [x.get("status") for x in manifest["scenes"]]
        if statuses and all(x == "downloaded" for x in statuses):
            self._assemble(folder, manifest)
        elif any(x == "failed" for x in statuses):
            manifest["status"] = "partial_failed"
            self._save(folder, manifest)

    def _assemble(self, folder: Path, manifest: dict[str, Any]) -> None:
        segments = []
        durations = []
        caption_path = folder / "captions.srt"
        for index, scene in enumerate(manifest["scenes"], 1):
            source = folder / scene["file"]
            probe = self._probe(source)
            source_duration = float(probe["format"]["duration"])
            streams = probe.get("streams", [])
            has_audio = any(x.get("codec_type") == "audio" for x in streams)
            segment = folder / f"normalized-{index:02d}.mp4"
            vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=24,setsar=1,format=yuv420p"
            cmd = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source)]
            if not has_audio:
                cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
            cmd += ["-map", "0:v:0", "-map", "0:a:0" if has_audio else "1:a:0",
                    "-vf", vf, "-af", "loudnorm=I=-14:TP=-1.0:LRA=11,aresample=48000",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-t", f"{source_duration:.3f}", "-movflags", "+faststart", str(segment)]
            self._run(cmd, timeout=max(180, int(source_duration * 30)))
            segments.append(segment)
            durations.append(source_duration)
        fade = 0.35 if len(segments) > 1 else 0.0
        cues = []
        cursor = 0.0
        for index, (scene, duration) in enumerate(zip(manifest["scenes"], durations), 1):
            end = cursor + duration
            caption_end = end - fade - 0.04 if index < len(durations) else end - 0.12
            cues.append((index, cursor, max(cursor + 0.5, caption_end), scene["caption"]))
            cursor = end - fade
        caption_path.write_text(self._srt(cues), encoding="utf-8")
        master = folder / "master.mp4"
        font = self._find_font()
        if not font:
            raise CinematicVideoError("A readable local font is required to burn subtitles into the cinematic master.")
        command = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
        for segment in segments:
            command.extend(["-i", str(segment)])
        graph = []
        current_video = "[0:v:0]"
        current_audio = "[0:a:0]"
        accumulated = durations[0]
        for index in range(1, len(segments)):
            video_out = f"[vx{index}]"
            audio_out = f"[ax{index}]"
            offset = max(0.0, accumulated - fade)
            graph.append(f"{current_video}[{index}:v:0]xfade=transition=fade:duration={fade:.3f}:offset={offset:.3f}{video_out}")
            graph.append(f"{current_audio}[{index}:a:0]acrossfade=d={fade:.3f}:c1=tri:c2=tri{audio_out}")
            current_video, current_audio = video_out, audio_out
            accumulated += durations[index] - fade
        draw_filters = []
        for index, (_, start, end, caption) in enumerate(cues, 1):
            lines, current = [], ""
            for word in caption.split():
                candidate = (current + " " + word).strip()
                if len(candidate) > 42 and current:
                    lines.append(current); current = word
                else:
                    current = candidate
            if current:
                lines.append(current)
            caption_file = folder / ("caption-" + str(index).zfill(2) + ".txt")
            caption_file.write_text("\n".join(lines[:2]), encoding="utf-8")
            draw_filters.append(
                "drawtext=fontfile='" + font.replace("'", "") + "'"
                + ":textfile='caption-" + str(index).zfill(2) + ".txt'"
                + ":fontcolor=white:fontsize=48:borderw=3:bordercolor=black"
                + ":box=1:boxcolor=black@0.52:boxborderw=16"
                + ":x=(w-text_w)/2:y=h-230"
                + ":enable='between(t\\," + format(start, ".3f") + "\\," + format(end, ".3f") + ")'"
            )
        graph.append(current_video + ",".join(draw_filters) + "[vout]")
        graph.append(current_audio + "loudnorm=I=-14:TP=-1.0:LRA=11[aout]")
        command.extend(["-filter_complex", ";".join(graph), "-map", "[vout]", "-map", "[aout]",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(master)])
        self._run(command, timeout=900, cwd=folder)
        qa = self._qa(master, caption_path)
        qa["burned_in_captions"] = True
        qa["transitions"] = {"status": "applied", "type": "crossfade", "duration_seconds": fade}
        manifest["status"] = "completed" if qa.get("status") == "passed" else "qa_failed"
        manifest["master"] = {"file": master.name, "byte_size": master.stat().st_size,
                              "sha256": self._sha(master)}
        manifest["qa"] = qa
        manifest["captions_file"] = caption_path.name
        self._save(folder, manifest)

    def _qa(self, master: Path, captions: Path) -> dict[str, Any]:
        from .creator_qa import CreatorVideoQA
        report = CreatorVideoQA(ffmpeg=self.ffmpeg, ffprobe=self.ffprobe).inspect(
            master, captions_path=captions, motion_mode="full_motion"
        )
        report["visual_review"] = "human_review_required"
        report["voice_naturalness"] = "human_review_required"
        report["scene_continuity"] = "human_review_required"
        return report

    @staticmethod
    def _srt(cues: list[tuple[int, float, float, str]]) -> str:
        def stamp(value: float) -> str:
            millis = max(0, round(value * 1000))
            hours, millis = divmod(millis, 3_600_000)
            minutes, millis = divmod(millis, 60_000)
            seconds, millis = divmod(millis, 1000)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"
        blocks = []
        for number, start, end, caption in cues:
            words = caption.split()
            lines, current = [], ""
            for word in words:
                candidate = (current + " " + word).strip()
                if len(candidate) > 42 and current:
                    lines.append(current); current = word
                else:
                    current = candidate
            if current:
                lines.append(current)
            if len(lines) > 2:
                lines = [lines[0][:42], " ".join(lines[1:])[:42]]
            blocks.append(f"{number}\n{stamp(start)} --> {stamp(end)}\n" + "\n".join(lines))
        return "\n\n".join(blocks) + "\n"

    def _api_request(self, method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in {"queue.fal.run", "fal.run"}:
            raise CinematicVideoError("Provider API endpoint was rejected.")
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            url, data=data, method=method,
            headers={"Authorization": "Key " + self.api_key, "Accept": "application/json",
                     "Content-Type": "application/json"},
        )
        try:
            with urllib.request.build_opener(_NoRedirect()).open(request, timeout=self.timeout) as response:
                raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise CinematicVideoError("Provider API response exceeded the configured size limit.")
            value = json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise CinematicVideoError(f"Provider request rejected (HTTP {exc.code}).") from None
        except CinematicVideoError:
            raise
        except Exception as exc:
            raise CinematicVideoError(f"Provider request failed ({type(exc).__name__}).") from None
        if not isinstance(value, dict):
            raise CinematicVideoError("Provider returned an invalid JSON response.")
        return value

    @staticmethod
    def _trusted_media_url(url: Any) -> bool:
        if not isinstance(url, str) or len(url) > 2048:
            return False
        parsed = urllib.parse.urlsplit(url)
        host = (parsed.hostname or "").lower()
        return parsed.scheme == "https" and (
            host == "fal.media" or host.endswith(".fal.media")
            or (host == "storage.googleapis.com" and parsed.path.startswith("/falserverless/"))
        )

    def _download(self, url: str, target: Path) -> None:
        if not self._trusted_media_url(url):
            raise CinematicVideoError("Media download host is not allowlisted.")
        request = urllib.request.Request(url, headers={"Accept": "video/mp4"})
        try:
            with urllib.request.build_opener(_SafeMediaRedirect()).open(request, timeout=90) as response:
                mime = response.headers.get("Content-Type", "").split(";", 1)[0]
                length = response.headers.get("Content-Length")
                if length and int(length) > MAX_CLIP_BYTES:
                    raise CinematicVideoError("Generated scene exceeds the 250 MB download limit.")
                if mime not in {"video/mp4", "application/octet-stream"}:
                    raise CinematicVideoError("Provider returned a non-MP4 scene.")
                payload = response.read(MAX_CLIP_BYTES + 1)
            if not payload or len(payload) > MAX_CLIP_BYTES:
                raise CinematicVideoError("Generated scene is empty or exceeds the download limit.")
            temp = target.with_suffix(".mp4.tmp")
            temp.write_bytes(payload)
            os.replace(temp, target)
        except CinematicVideoError:
            raise
        except Exception as exc:
            raise CinematicVideoError(f"Scene download failed ({type(exc).__name__}).") from None

    @staticmethod
    def _find_font() -> str:
        candidates = [
            os.getenv("UNEXPECTED_CINEMATIC_FONT", ""),
            "/system/fonts/Roboto-Regular.ttf",
            "/system/fonts/NotoSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]
        for value in candidates:
            if value and Path(value).is_file() and not Path(value).is_symlink():
                return value
        return ""

    def _probe(self, path: Path) -> dict[str, Any]:
        result = self._run([self.ffprobe, "-v", "error", "-show_streams", "-show_format",
                            "-of", "json", str(path)])
        value = json.loads(result.stdout)
        if not isinstance(value, dict) or not value.get("streams"):
            raise CinematicVideoError("Generated scene has no valid media streams.")
        duration = float(value.get("format", {}).get("duration") or 0)
        if not 0 < duration <= 35:
            raise CinematicVideoError("Generated scene duration is outside the accepted range.")
        return value

    def _run(self, command: list[str], *, timeout: int, cwd: Path | None = None) -> subprocess.CompletedProcess:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False, cwd=cwd)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CinematicVideoError(f"Local media command failed ({type(exc).__name__}).") from None
        if result.returncode != 0:
            detail = " ".join((result.stderr or "").split())[-700:]
            raise CinematicVideoError("Local media command failed: " + detail)
        return result

    def _job_folder(self, job_id: str) -> Path:
        if not isinstance(job_id, str) or not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise CinematicVideoError("Invalid cinematic job ID.")
        folder = self.root / job_id
        if folder.is_symlink() or not folder.is_dir():
            raise CinematicVideoError("Cinematic job was not found.")
        return folder

    @staticmethod
    def _read_manifest(folder: Path) -> dict[str, Any]:
        path = folder / "manifest.json"
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_000_000:
            raise CinematicVideoError("Cinematic manifest is missing or unsafe.")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            raise CinematicVideoError("Cinematic manifest is invalid.") from None
        if not isinstance(data, dict) or not isinstance(data.get("scenes"), list):
            raise CinematicVideoError("Cinematic manifest has an invalid schema.")
        return data

    @staticmethod
    def _save(folder: Path, manifest: dict[str, Any]) -> None:
        path = folder / "manifest.json"
        temp = folder / "manifest.json.tmp"
        raw = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8")
        temp.write_bytes(raw)
        try:
            temp.chmod(0o600)
        except OSError:
            pass
        os.replace(temp, path)

    @staticmethod
    def _sha(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _public_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
        copy = json.loads(json.dumps(manifest))
        for scene in copy.get("scenes", []):
            scene.pop("request_id", None)
        copy["publishing_performed"] = False
        return copy


__all__ = ["CinematicVideoCreator", "CinematicVideoError", "estimate_cost_usd"]
