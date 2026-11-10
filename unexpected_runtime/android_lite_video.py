from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import time
import unicodedata
import uuid
import wave
from pathlib import Path
from typing import Any


class AndroidLiteVideoError(RuntimeError):
    """A local Android Lite video request could not be completed safely."""


_ID = re.compile(r"^[0-9a-f]{32}$")
_ALLOWED_FORMATS = {"vertical": (720, 1280), "landscape": (1280, 720)}
MAX_SCRIPT_WORDS = 150
MIN_SCRIPT_WORDS = 25
MAX_TITLE_CHARS = 120


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_text(value: str, label: str, limit: int) -> str:
    if not isinstance(value, str):
        raise AndroidLiteVideoError(label + " must be text.")
    value = " ".join(value.split()).strip()
    if not value or len(value) > limit:
        raise AndroidLiteVideoError(label + " is empty or exceeds its length limit.")
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    if not ascii_text or len(ascii_text) / max(1, len(value)) < 0.88:
        raise AndroidLiteVideoError(
            "Android Lite's built-in title renderer currently supports Latin-script text. "
            "The original script is not changed or uploaded."
        )
    return ascii_text


def _wrap(text: str, width: int) -> str:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if len(word) > width:
            if current:
                lines.append(current)
                current = ""
            lines.extend(word[i:i + width] for i in range(0, len(word), width))
            continue
        candidate = word if not current else current + " " + word
        if len(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\n".join(lines)


def _make_scenes(script: str) -> list[str]:
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", script) if part.strip()]
    chunks: list[str] = []
    current: list[str] = []
    count = 0
    for sentence in sentences:
        words = sentence.split()
        while words:
            room = max(1, 15 - count)
            current.extend(words[:room])
            words = words[room:]
            count = len(current)
            if count >= 15:
                chunks.append(" ".join(current))
                current, count = [], 0
    if current:
        chunks.append(" ".join(current))
    return chunks[:12]


def _write_ambient_wav(path: Path, duration: float, sample_rate: int = 22050) -> None:
    """Create a quiet original two-tone ambient bed; no licensed track is bundled."""
    total = max(1, int(sample_rate * duration))
    chunk_size = 4096
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        for start in range(0, total, chunk_size):
            values = bytearray()
            stop = min(total, start + chunk_size)
            for index in range(start, stop):
                t = index / sample_rate
                edge = min(1.0, t / 1.2, max(0.0, (duration - t) / 1.8))
                swell = 0.72 + 0.28 * math.sin(2 * math.pi * 0.035 * t)
                sample = (
                    math.sin(2 * math.pi * 110.0 * t) * 0.032
                    + math.sin(2 * math.pi * 164.81 * t) * 0.018
                ) * edge * swell
                value = max(-32767, min(32767, int(sample * 32767)))
                values.extend(value.to_bytes(2, "little", signed=True))
            output.writeframesraw(values)


def _filter_path(path: Path) -> str:
    value = str(path.resolve())
    return value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


class AndroidLiteVideoCreator:
    """Script-to-MP4 creator using only local FFmpeg, text files and generated audio."""

    def __init__(self, output_root: str | Path | None = None, *,
                 runner=subprocess.run, which=shutil.which):
        self.output_root = Path(
            output_root or os.getenv(
                "UNEXPECTED_ANDROID_VIDEO_ROOT",
                str(Path.home() / ".unexpected" / "creator" / "android-lite"),
            )
        ).expanduser()
        self.runner = runner
        self.which = which

    @classmethod
    def from_environment(cls) -> "AndroidLiteVideoCreator":
        return cls()

    def _font(self) -> Path | None:
        prefix = os.getenv("PREFIX", "")
        candidates = [
            Path("/system/fonts/Roboto-Regular.ttf"),
            Path("/system/fonts/NotoSans-Regular.ttf"),
            Path(prefix) / "share/fonts/TTF/DejaVuSans.ttf" if prefix else Path("/nonexistent"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
        ]
        return next((item for item in candidates if item.is_file() and not item.is_symlink()), None)

    def _run(self, command: list[str], *, timeout: int = 120, input_text: str | None = None):
        env = {
            "PATH": os.environ.get("PATH", os.defpath),
            "HOME": str(Path.home()),
            "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
            "NO_PROXY": "127.0.0.1,localhost,::1",
            "no_proxy": "127.0.0.1,localhost,::1",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "DO_NOT_TRACK": "1",
        }
        try:
            result = self.runner(
                command, shell=False, capture_output=True, text=True,
                timeout=timeout, check=False, cwd=str(self.output_root if self.output_root.exists() else Path.home()),
                env=env, input=input_text,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AndroidLiteVideoError(
                "Local media command failed (" + type(exc).__name__ + ")."
            ) from None
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "local media command failed").strip()
            detail = " ".join(detail.splitlines())[-360:]
            raise AndroidLiteVideoError(detail or "Local media command failed.")
        return result

    def preflight(self) -> dict[str, Any]:
        ffmpeg, ffprobe = self.which("ffmpeg"), self.which("ffprobe")
        if not ffmpeg or not ffprobe:
            return {
                "ready": False,
                "ffmpeg": bool(ffmpeg),
                "ffprobe": bool(ffprobe),
                "reason": "FFmpeg and FFprobe must both be installed.",
                "network": "not used",
            }
        try:
            filters = self._run([ffmpeg, "-hide_banner", "-filters"], timeout=20)
            encoders = self._run([ffmpeg, "-hide_banner", "-encoders"], timeout=20)
        except AndroidLiteVideoError as exc:
            return {"ready": False, "reason": str(exc), "network": "not used"}
        filter_text = filters.stdout + filters.stderr
        encoder_text = encoders.stdout + encoders.stderr
        drawtext = "drawtext" in filter_text
        encoder = "libx264" if re.search(r"\blibx264\b", encoder_text) else (
            "mpeg4" if re.search(r"\bmpeg4\b", encoder_text) else None
        )
        font = self._font()
        issues = []
        if not drawtext:
            issues.append("This FFmpeg build does not include the drawtext filter.")
        if not encoder:
            issues.append("This FFmpeg build has no supported H.264/MPEG-4 video encoder.")
        if not font:
            issues.append("No readable local font was found for text rendering.")
        speech = self.which("espeak-ng")
        return {
            "ready": not issues,
            "ffmpeg": True,
            "ffprobe": True,
            "drawtext": drawtext,
            "font_available": bool(font),
            "video_encoder": encoder,
            "offline_speech_engine": bool(speech),
            "speech_mode": "espeak-ng" if speech else "ambient-audio-only",
            "issues": issues,
            "network": "not used",
            "model_downloads": "none",
        }

    def _project_dir(self, video_id: str) -> Path:
        if not isinstance(video_id, str) or not _ID.fullmatch(video_id):
            raise AndroidLiteVideoError("Invalid video ID.")
        if self.output_root.is_symlink():
            raise AndroidLiteVideoError("Android Lite output root cannot be a symbolic link.")
        self.output_root.mkdir(parents=True, exist_ok=True)
        root = self.output_root.resolve()
        project = root / video_id
        if project.is_symlink():
            raise AndroidLiteVideoError("Video project directory cannot be a symbolic link.")
        project.mkdir(parents=True, exist_ok=True)
        if project.resolve().parent != root:
            raise AndroidLiteVideoError("Video project escaped its output directory.")
        return project.resolve()

    def render(self, title: str, script: str, *, video_format: str = "vertical",
               narration: str = "auto") -> dict[str, Any]:
        if not isinstance(video_format, str) or video_format not in _ALLOWED_FORMATS:
            raise AndroidLiteVideoError("Format must be vertical or landscape.")
        if not isinstance(narration, str) or narration not in {"auto", "off"}:
            raise AndroidLiteVideoError("Narration mode must be auto or off.")
        safe_title = _safe_text(title, "Title", MAX_TITLE_CHARS)
        safe_script = _safe_text(script, "Script", 12000)
        original_words = script.split()
        word_count = len(original_words)
        if not MIN_SCRIPT_WORDS <= word_count <= MAX_SCRIPT_WORDS:
            raise AndroidLiteVideoError(
                "Script must contain between 25 and 150 words for a 30–60 second video."
            )
        scenes = _make_scenes(safe_script)
        if not scenes:
            raise AndroidLiteVideoError("The script could not be divided into scenes.")
        readiness = self.preflight()
        if not readiness.get("ready"):
            raise AndroidLiteVideoError(
                "Android Lite preflight is blocked: " + "; ".join(readiness.get("issues", []))
                + (readiness.get("reason") or "")
            )
        ffmpeg, ffprobe = self.which("ffmpeg"), self.which("ffprobe")
        font = self._font()
        encoder = readiness["video_encoder"]
        width, height = _ALLOWED_FORMATS[video_format]
        duration = max(30, min(60, int(math.ceil(word_count / 2.35))))
        video_id = uuid.uuid4().hex
        project = self._project_dir(video_id)
        work = project / "work"
        work.mkdir()
        title_file = work / "title.txt"
        title_file.write_text("uneXpected | " + safe_title, encoding="utf-8")
        voice_file = work / "narration.wav"
        voice_status = "disabled"
        if narration == "auto" and self.which("espeak-ng"):
            try:
                self._run(
                    [self.which("espeak-ng"), "-v", "en-us", "-s", "155",
                     "-w", str(voice_file), "--stdin"],
                    timeout=90, input_text=safe_script,
                )
                if voice_file.is_file() and voice_file.stat().st_size > 44:
                    voice_status = "generated_offline"
                else:
                    voice_status = "unavailable"
            except AndroidLiteVideoError:
                voice_status = "unavailable"
        ambient_file = work / "ambient.wav"
        _write_ambient_wav(ambient_file, duration)
        accent = ["0x70E1D4", "0x9B8CFF", "0xFFB86B", "0x78A8FF"]
        parts = [
            "drawbox=x='w*0.08+20*sin(t*0.28)':y='h*0.19':w='w*0.84':h=5:"
            "color=0x70E1D4@0.82:t=fill",
            "drawtext=fontfile='" + _filter_path(font) + "':textfile='"
            + _filter_path(title_file) + "':fontcolor=0x70E1D4:fontsize="
            + ("30" if video_format == "vertical" else "34")
            + ":x=(w-text_w)/2:y=h*0.10:shadowcolor=black@0.7:shadowx=2:shadowy=2",
        ]
        scene_duration = duration / len(scenes)
        for index, scene in enumerate(scenes):
            start = index * scene_duration
            end = (index + 1) * scene_duration
            scene_file = work / ("scene-" + str(index + 1).zfill(2) + ".txt")
            scene_width = 23 if video_format == "vertical" else 38
            scene_file.write_text(_wrap(scene, scene_width), encoding="utf-8")
            color = accent[index % len(accent)]
            parts.append(
                "drawbox=x='w*0.08':y='h*0.30':w='w*0.84':h='h*0.40':"
                "color=" + color + "@0.10:t=fill:enable='between(t,"
                + format(start, ".3f") + "," + format(end, ".3f") + ")'"
            )
            parts.append(
                "drawtext=fontfile='" + _filter_path(font) + "':textfile='"
                + _filter_path(scene_file) + "':fontcolor=white:fontsize="
                + ("47" if video_format == "vertical" else "43")
                + ":line_spacing=18:borderw=1:bordercolor=0x10162B@0.95:"
                "x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=0x111A30@0.72:"
                "boxborderw=34:alpha='if(lt(t,"
                + format(start + 0.35, ".3f") + "),(t-"
                + format(start, ".3f") + ")/0.35,if(gt(t,"
                + format(end - 0.35, ".3f") + "),("
                + format(end, ".3f") + "-t)/0.35,1))':enable='between(t,"
                + format(start, ".3f") + "," + format(end, ".3f") + ")'"
            )
            counter = work / ("counter-" + str(index + 1).zfill(2) + ".txt")
            counter.write_text(
                "SCENE " + str(index + 1).zfill(2) + " / " + str(len(scenes)).zfill(2),
                encoding="ascii",
            )
            parts.append(
                "drawtext=fontfile='" + _filter_path(font) + "':textfile='"
                + _filter_path(counter) + "':fontcolor=" + color
                + ":fontsize=22:x=(w-text_w)/2:y=h*0.84:"
                "enable='between(t," + format(start, ".3f") + ","
                + format(end, ".3f") + ")'"
            )
        parts.append(
            "drawbox=x=0:y=h-14:w='w*min(t/" + format(duration, ".3f")
            + ",1)':h=14:color=0x70E1D4@0.95:t=fill"
        )
        graph = "[0:v]" + ",".join(parts) + "[v];"
        if voice_status == "generated_offline":
            graph += (
                "[1:a]volume=1.0[voice];[2:a]volume=0.13[bed];"
                "[voice][bed]amix=inputs=2:duration=longest:dropout_transition=1,"
                "atrim=duration=" + format(duration, ".3f") + "[a]"
            )
        else:
            graph += "[1:a]volume=0.18,anull[a]"
        graph_file = work / "render.filter"
        graph_file.write_text(graph, encoding="utf-8")
        temp_output = project / "master.part.mp4"
        output = project / "master.mp4"
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i",
            "color=c=0x10162B:s=" + str(width) + "x" + str(height)
            + ":r=24:d=" + format(duration, ".3f"),
        ]
        if voice_status == "generated_offline":
            command.extend(["-i", str(voice_file)])
        command.extend([
            "-i", str(ambient_file), "-filter_complex_script", str(graph_file),
            "-map", "[v]", "-map", "[a]", "-t", format(duration, ".3f"),
            "-r", "24", "-c:v", encoder, "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart",
            str(temp_output),
        ])
        if encoder == "libx264":
            command[-7:-7] = ["-preset", "ultrafast", "-crf", "24"]
        else:
            command[-7:-7] = ["-q:v", "5"]
        try:
            self._run(command, timeout=900)
            if not temp_output.is_file() or temp_output.is_symlink() or temp_output.stat().st_size < 8192:
                raise AndroidLiteVideoError("FFmpeg did not create a valid MP4 file.")
            os.replace(temp_output, output)
            probe = self._run([
                ffprobe, "-v", "error", "-show_entries",
                "format=duration:stream=codec_type,codec_name,width,height",
                "-of", "json", str(output),
            ], timeout=30)
            report = json.loads(probe.stdout)
            streams = report.get("streams", [])
            video = next((item for item in streams if item.get("codec_type") == "video"), None)
            audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
            measured = float(report.get("format", {}).get("duration", 0))
            if (video is None or audio is None or video.get("width") != width
                    or video.get("height") != height
                    or not math.isfinite(measured) or abs(measured - duration) > 1.0):
                raise AndroidLiteVideoError("Encoded MP4 failed duration, resolution or audio-stream QA.")
            manifest = {
                "status": "completed",
                "video_id": video_id,
                "title": safe_title,
                "format": video_format,
                "width": width,
                "height": height,
                "fps": 24,
                "duration_seconds": round(measured, 3),
                "word_count": word_count,
                "scene_count": len(scenes),
                "video_codec": video.get("codec_name"),
                "audio_codec": audio.get("codec_name"),
                "narration": voice_status,
                "audio_bed": "original_synthesized_ambient",
                "visual_mode": "animated_kinetic_typography",
                "ai_models_used": [],
                "external_services_used": False,
                "network_used": False,
                "publishing_performed": False,
                "file_name": "master.mp4",
                "byte_size": output.stat().st_size,
                "sha256": _sha256(output),
                "qa": "passed",
                "created_at": int(time.time()),
                "script": script,
                "notes": (
                    "Procedural motion-graphics video. Offline speech is included only when "
                    "espeak-ng is installed; otherwise the video has on-screen script and "
                    "an original ambient audio bed. This is not AI-generated footage."
                ),
            }
            manifest_path = project / "manifest.json"
            temporary_manifest = project / "manifest.json.tmp"
            temporary_manifest.write_text(
                json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2),
                encoding="utf-8",
            )
            try:
                os.chmod(temporary_manifest, 0o600)
            except OSError:
                pass
            os.replace(temporary_manifest, manifest_path)
            return manifest
        except Exception:
            try:
                temp_output.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        finally:
            try:
                shutil.rmtree(work)
            except OSError:
                pass

    def _existing_project_dir(self, video_id: str) -> Path:
        if not isinstance(video_id, str) or not _ID.fullmatch(video_id):
            raise AndroidLiteVideoError("Invalid video ID.")
        if self.output_root.is_symlink() or not self.output_root.is_dir():
            raise AndroidLiteVideoError("Video record was not found.")
        root = self.output_root.resolve()
        project = root / video_id
        if project.is_symlink() or not project.is_dir() or project.resolve().parent != root:
            raise AndroidLiteVideoError("Video record was not found.")
        return project.resolve()

    def get_video(self, video_id: str) -> dict[str, Any]:
        project = self._existing_project_dir(video_id)
        manifest_path = project / "manifest.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise AndroidLiteVideoError("Video record was not found.")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            raise AndroidLiteVideoError("Video record is invalid.") from None
        if manifest.get("video_id") != video_id or manifest.get("file_name") != "master.mp4":
            raise AndroidLiteVideoError("Video record failed identity validation.")
        return manifest

    def read_video(self, video_id: str) -> bytes:
        manifest = self.get_video(video_id)
        project = self._existing_project_dir(video_id)
        output = project / "master.mp4"
        if output.is_symlink() or not output.is_file():
            raise AndroidLiteVideoError("Encoded MP4 file is missing or unsafe.")
        if output.stat().st_size != manifest.get("byte_size") or _sha256(output) != manifest.get("sha256"):
            raise AndroidLiteVideoError("Encoded MP4 failed checksum verification.")
        return output.read_bytes()


__all__ = ["AndroidLiteVideoCreator", "AndroidLiteVideoError"]
