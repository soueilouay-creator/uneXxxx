from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import platform
import re
import shutil
from pathlib import Path
from typing import Any

MODEL_STATES = {"discovered", "reviewed", "download-approved", "cached", "verified", "disabled"}
MODEL_TASKS = {"llm", "image", "video", "tts", "music", "asr"}
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


class LocalAIError(ValueError):
    """Invalid local model registry or an unsafe/missing local model artifact."""


def _safe_relative_path(value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise LocalAIError("Model artifact path must be non-empty relative text.")
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise LocalAIError("Model artifact paths must remain inside the configured model directory.")
    return path


def validate_model_registry(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise LocalAIError("Unsupported local model registry schema.")
    models = data.get("models")
    if not isinstance(models, list):
        raise LocalAIError("Local model registry must contain a models array.")
    seen: set[str] = set()
    checked: list[dict[str, Any]] = []
    for item in models:
        if not isinstance(item, dict):
            raise LocalAIError("Every model registry entry must be an object.")
        model_id = item.get("model_id")
        if not isinstance(model_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,100}", model_id):
            raise LocalAIError("Model IDs must be bounded lowercase identifiers.")
        if model_id in seen:
            raise LocalAIError(f"Duplicate model ID: {model_id}")
        seen.add(model_id)
        if item.get("task") not in MODEL_TASKS:
            raise LocalAIError(f"Unsupported model task for {model_id}.")
        for field in ("repository", "revision", "runtime", "repository_license"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise LocalAIError(f"Model {model_id} is missing {field}.")
        if not item["repository"].startswith("https://github.com/"):
            raise LocalAIError(f"Model {model_id} must identify a GitHub source repository.")
        if item.get("state") not in MODEL_STATES:
            raise LocalAIError(f"Model {model_id} has an unsupported availability state.")
        if item.get("weight_license_status") not in {"unverified", "verified", "prohibited"}:
            raise LocalAIError(f"Model {model_id} has an invalid weight licence status.")
        weight_files = item.get("weight_files", [])
        if not isinstance(weight_files, list):
            raise LocalAIError(f"Model {model_id} weight_files must be an array.")
        for weight in weight_files:
            if not isinstance(weight, dict):
                raise LocalAIError(f"Model {model_id} contains an invalid weight record.")
            _safe_relative_path(weight.get("path"))
            if not isinstance(weight.get("sha256"), str) or not SHA256_RE.fullmatch(weight["sha256"]):
                raise LocalAIError(f"Model {model_id} contains a missing or invalid SHA-256.")
            if weight.get("license_status") not in {"unverified", "verified", "prohibited"}:
                raise LocalAIError(f"Model {model_id} contains an invalid per-file licence status.")
        if item["state"] == "verified":
            if not weight_files or item["weight_license_status"] != "verified":
                raise LocalAIError(f"Model {model_id} cannot be verified without pinned weights and reviewed terms.")
            if any(x["license_status"] != "verified" for x in weight_files):
                raise LocalAIError(f"Model {model_id} has unreviewed weight licences.")
        checked.append(dict(item))
    return {"schema_version": 1, "models": checked}


def load_model_registry(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LocalAIError(f"Could not read local model registry ({type(exc).__name__}).") from None
    return validate_model_registry(data)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_model_availability(model: dict[str, Any], model_root: str | Path) -> dict[str, Any]:
    root = Path(model_root).expanduser().resolve()
    state = model["state"]
    if state == "disabled":
        return {"model_id": model["model_id"], "available": False, "reason": "disabled by policy", "verified_files": 0}
    files = model.get("weight_files", [])
    if not files:
        return {"model_id": model["model_id"], "available": False,
                "reason": "no weight files are pinned in the local lock", "verified_files": 0}
    if model.get("weight_license_status") != "verified":
        return {"model_id": model["model_id"], "available": False,
                "reason": "model-weight licence has not been verified", "verified_files": 0}
    verified = 0
    for record in files:
        relative = _safe_relative_path(record.get("path"))
        candidate = root / relative
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                return {"model_id": model["model_id"], "available": False,
                        "reason": "model path contains a symbolic link", "verified_files": verified}
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError):
            return {"model_id": model["model_id"], "available": False,
                    "reason": "model file is missing or escapes the model directory", "verified_files": verified}
        if not resolved.is_file() or _sha256(resolved) != record["sha256"]:
            return {"model_id": model["model_id"], "available": False,
                    "reason": "model file checksum verification failed", "verified_files": verified}
        if record.get("license_status") != "verified":
            return {"model_id": model["model_id"], "available": False,
                    "reason": "one or more model-file licences remain unverified", "verified_files": verified}
        verified += 1
    if state != "verified":
        return {"model_id": model["model_id"], "available": False,
                "reason": "model is cached but has not passed the verification gate", "verified_files": verified}
    return {"model_id": model["model_id"], "available": True, "reason": "weights, checksums and licences verified",
            "verified_files": verified}


def _memory_bytes() -> int | None:
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        try:
            for line in meminfo.read_text(encoding="ascii").splitlines():
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
        except (OSError, ValueError, IndexError):
            return None
    return None


def inspect_local_ai(model_root: str | Path, registry: dict[str, Any]) -> dict[str, Any]:
    checked = validate_model_registry(registry)
    root = Path(model_root).expanduser()
    disk_probe = root if root.exists() else root.parent
    while not disk_probe.exists() and disk_probe != disk_probe.parent:
        disk_probe = disk_probe.parent
    disk_free = shutil.disk_usage(disk_probe).free if disk_probe.exists() else None
    tools = {name: shutil.which(name) for name in
             ("llama-server", "ffmpeg", "ffprobe", "whisper-cli", "python")}
    nvidia_smi = shutil.which("nvidia-smi")
    models = [inspect_model_availability(item, root) for item in checked["models"]]
    ready_tasks = sorted({checked_model["task"] for checked_model, result
                          in zip(checked["models"], models) if result["available"]})
    return {
        "mode": "local_only",
        "network_policy": "offline_required_for_generation",
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "cpu_count": os.cpu_count(),
        "ram_total_bytes": _memory_bytes(),
        "model_root": str(root),
        "disk_free_bytes": disk_free,
        "runtime_tools": tools,
        "nvidia_smi_available": bool(nvidia_smi),
        "models": models,
        "ready_tasks": ready_tasks,
        "external_network_used": False,
        "download_performed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect uneXpected's offline local AI model cache.")
    parser.add_argument("command", choices=("status", "preflight"))
    parser.add_argument("--model-root", default=os.getenv("UNEXPECTED_MODEL_ROOT", "./models"))
    parser.add_argument("--registry", default=str(Path(__file__).resolve().parent.parent / "local_ai" / "model_registry.json"))
    args = parser.parse_args(argv)
    try:
        registry = load_model_registry(args.registry)
        report = inspect_local_ai(args.model_root, registry)
    except LocalAIError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    if args.command == "preflight" and "llm" not in report["ready_tasks"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
