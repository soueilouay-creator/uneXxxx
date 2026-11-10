from __future__ import annotations

import json
import math
import re
import subprocess
import tempfile
from pathlib import Path

_IMAGE = re.compile(r"scenes/[A-Za-z0-9][A-Za-z0-9._-]{0,100}\.(?:png|jpe?g|webp)", re.I)
_ROOT_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}\.(?:json|srt)", re.I)


class StoryFilmError(RuntimeError):
    pass


def _regular_project_file(project: Path, relative: str, *, pattern: re.Pattern,
                          max_bytes: int) -> Path:
    if not isinstance(relative, str) or not pattern.fullmatch(relative):
        raise StoryFilmError("Story-film asset path is not permitted.")
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or "\\" in relative:
        raise StoryFilmError("Story-film asset path escapes the project.")
    root = project.resolve(strict=True)
    candidate = project / rel
    if candidate.is_symlink() or not candidate.is_file():
        raise StoryFilmError("A required story-film asset is missing or unsafe.")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise StoryFilmError("Story-film asset resolves outside the project.") from exc
    if resolved.stat().st_size <= 0 or resolved.stat().st_size > max_bytes:
        raise StoryFilmError("Story-film asset is empty or exceeds its size limit.")
    return resolved


def validate_story_paths(project: str | Path, timeline_relpath: str = "timeline.json",
                         captions_relpath: str = "captions.srt") -> tuple[Path, Path, list[dict]]:
    """Validate a bounded, local-only illustrated-story timeline."""
    root = Path(project).resolve(strict=True)
    timeline_path = _regular_project_file(root, timeline_relpath, pattern=_ROOT_FILE,
                                          max_bytes=1_000_000)
    captions_path = _regular_project_file(root, captions_relpath, pattern=_ROOT_FILE,
                                          max_bytes=2_000_000)
    if timeline_path.suffix.lower() != ".json" or captions_path.suffix.lower() != ".srt":
        raise StoryFilmError("Story timeline must be JSON and captions must be SRT.")
    try:
        data = json.loads(timeline_path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise StoryFilmError("Story timeline is not valid UTF-8 JSON.") from exc
    if not isinstance(data, dict) or data.get("version") != 1:
        raise StoryFilmError("Unsupported story timeline version.")
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or not 2 <= len(scenes) <= 120:
        raise StoryFilmError("Story timeline needs 2 to 120 illustrated scenes.")
    checked = []
    for scene in scenes:
        if not isinstance(scene, dict) or set(scene) - {
            "scene_id", "image", "duration_seconds", "visual_prompt",
            "narration", "on_screen_text"
        }:
            raise StoryFilmError("Story scene contains unsupported fields.")
        image_path = _regular_project_file(root, scene.get("image"), pattern=_IMAGE,
                                           max_bytes=20_000_000)
        duration = scene.get("duration_seconds")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)):
            raise StoryFilmError("Scene duration must be a finite number.")
        duration = float(duration)
        if not math.isfinite(duration) or not 2 <= duration <= 180:
            raise StoryFilmError("Each illustrated scene must last 2 to 180 seconds.")
        scene_id = scene.get("scene_id", "")
        if not isinstance(scene_id, str) or len(scene_id) > 80:
            raise StoryFilmError("Scene ID must be bounded text.")
        checked.append({
            "image": image_path,
            "duration_seconds": duration,
            "scene_id": scene_id,
        })
    return timeline_path, captions_path, checked


def _run(command: list[str], timeout: int) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                check=False, timeout=max(10, min(int(timeout), 3600)))
    except subprocess.TimeoutExpired as exc:
        raise StoryFilmError("Story-film rendering exceeded its time limit.") from exc
    except OSError as exc:
        raise StoryFilmError("FFmpeg and ffprobe must be installed in the renderer.") from exc
    if result.returncode:
        message = (result.stderr or result.stdout or "FFmpeg failed").strip().splitlines()
        raise StoryFilmError(message[-1][:300] if message else "FFmpeg failed.")
    return result


def _probe_duration(audio: Path, ffprobe: str, timeout: int) -> float:
    result = _run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                   "-of", "default=noprint_wrappers=1:nokey=1", str(audio)], timeout)
    try:
        duration = float(result.stdout.strip())
    except ValueError as exc:
        raise StoryFilmError("Narration WAV duration could not be read.") from exc
    if not math.isfinite(duration) or not 5 <= duration <= 3600:
        raise StoryFilmError("Story-film narration must be between 5 seconds and 60 minutes.")
    return duration


def render_story_film(project: str | Path, audio: str | Path, output: str | Path, *,
                      fps: int = 24, timeline_relpath: str = "timeline.json",
                      captions_relpath: str = "captions.srt", ffmpeg: str = "ffmpeg",
                      ffprobe: str = "ffprobe", timeout_seconds: int = 3600) -> dict:
    """Compose a widescreen illustrated story from local stills, narration and subtitles.

    This deterministic compositor does not generate stories, artwork or narration.
    """
    root = Path(project).resolve(strict=True)
    audio_path = Path(audio).resolve(strict=True)
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not audio_path.is_file() or audio_path.suffix.lower() != ".wav":
        raise StoryFilmError("A local narration mix WAV is required.")
    if isinstance(fps, bool) or not isinstance(fps, int) or not 12 <= fps <= 60:
        raise StoryFilmError("Frame rate must be between 12 and 60 FPS.")
    _, captions_path, scenes = validate_story_paths(root, timeline_relpath, captions_relpath)
    duration = _probe_duration(audio_path, ffprobe, timeout_seconds)
    timeline_duration = sum(scene["duration_seconds"] for scene in scenes)
    if abs(timeline_duration - duration) > 1.5:
        raise StoryFilmError("Scene durations must cover the narration WAV within 1.5 seconds.")

    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".ffconcat",
                                     prefix="story-film-", dir=target.parent,
                                     delete=False) as handle:
        concat_path = Path(handle.name)
        handle.write("ffconcat version 1.0\n")
        for scene in scenes:
            handle.write("file '" + scene["image"].as_posix() + "'\n")
            handle.write("duration " + format(scene["duration_seconds"], ".6f") + "\n")
        handle.write("file '" + scenes[-1]["image"].as_posix() + "'\n")

    try:
        subtitle_file = captions_path.as_posix()
        subtitle_file = (subtitle_file.replace("\\", "\\\\").replace(":", "\\:")
                         .replace("'", "\\'").replace(",", "\\,"))
        vf = (
            "fps={fps},scale=2200:1238:force_original_aspect_ratio=increase,"
            "crop=2200:1238,"
            "zoompan=z='min(1+0.0000006*on,1.08)':"
            "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:"
            "s=1920x1080:fps={fps},setsar=1,"
            "subtitles=filename='{captions}':force_style='FontName=DejaVu Sans,"
            "FontSize=36,Outline=2,Shadow=1,MarginV=52,Alignment=2'"
        ).format(fps=fps, captions=subtitle_file)
        _run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_path),
            "-i", str(audio_path), "-t", format(duration, ".3f"),
            "-vf", vf, "-map", "0:v:0", "-map", "1:a:0",
            "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "22", "-pix_fmt", "yuv420p",
            "-af", "loudnorm=I=-14:TP=-1.2:LRA=11",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(target)
        ], timeout_seconds)
    finally:
        concat_path.unlink(missing_ok=True)

    poster = target.with_name("thumbnail.jpg")
    _run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", "1",
          "-i", str(target), "-frames:v", "1", "-q:v", "2", str(poster)],
         min(timeout_seconds, 120))
    probe = _run([ffprobe, "-v", "error", "-show_streams", "-show_format",
                  "-of", "json", str(target)], min(timeout_seconds, 60))
    try:
        info = json.loads(probe.stdout)
        streams = info.get("streams", [])
        video = next(item for item in streams if item.get("codec_type") == "video")
        audio_stream = next(item for item in streams if item.get("codec_type") == "audio")
        encoded_duration = float(info["format"]["duration"])
    except (ValueError, KeyError, StopIteration, TypeError) as exc:
        raise StoryFilmError("Encoded story-film MP4 failed stream inspection.") from exc
    if (int(video.get("width", 0)), int(video.get("height", 0))) != (1920, 1080):
        raise StoryFilmError("Story-film output must be 1920x1080 landscape.")
    if not 5 <= encoded_duration <= 3600:
        raise StoryFilmError("Encoded story-film duration is outside the supported range.")
    if not poster.is_file() or poster.stat().st_size < 1024:
        raise StoryFilmError("Story-film thumbnail extraction failed.")
    return {
        "duration_seconds": round(encoded_duration, 3),
        "width": 1920,
        "height": 1080,
        "fps": fps,
        "video_codec": video.get("codec_name"),
        "audio_codec": audio_stream.get("codec_name"),
        "thumbnail_file": poster.name,
        "scene_count": len(scenes),
    }


__all__ = ["StoryFilmError", "validate_story_paths", "render_story_film"]
