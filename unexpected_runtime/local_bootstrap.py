from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .local_ai import SHA256_RE, _safe_relative_path, inspect_model_availability, load_model_registry
from .local_ai_supervisor import detect_hardware


class LocalModelBootstrapError(RuntimeError):
    """A model bootstrap action was rejected or failed verification."""


ALLOWED_HOST = "huggingface.co"
MAX_ARTIFACT_BYTES = 50 * 1024 ** 3
CHUNK_BYTES = 1024 * 1024


def _validate_hf_url(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LocalModelBootstrapError("Model artifact has no pinned HTTPS source URL.")
    parsed = urllib.parse.urlsplit(value)
    host = (parsed.hostname or "").lower()
    allowed = host == ALLOWED_HOST or host.endswith(".huggingface.co") or host.endswith(".hf.co")
    try:
        port = parsed.port
    except ValueError:
        raise LocalModelBootstrapError("Model source URL has an invalid HTTPS port.") from None
    if (parsed.scheme != "https" or not allowed or parsed.username or parsed.password
            or port not in (None, 443) or parsed.fragment or parsed.query):
        raise LocalModelBootstrapError("Model source URL must be an immutable, credential-free HTTPS Hugging Face URL.")
    if not re.search(r"/resolve/[0-9a-f]{40}/", parsed.path):
        raise LocalModelBootstrapError("Model source URL must pin an immutable 40-character repository revision.")
    return value


class _HuggingFaceRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        resolved = urllib.parse.urljoin(req.full_url, newurl)
        _validate_redirect_url(resolved)
        return super().redirect_request(req, fp, code, msg, headers, resolved)


def _validate_redirect_url(value: str) -> None:
    parsed = urllib.parse.urlsplit(value)
    host = (parsed.hostname or "").lower()
    allowed = host == ALLOWED_HOST or host.endswith(".huggingface.co") or host.endswith(".hf.co")
    try:
        port = parsed.port
    except ValueError:
        raise LocalModelBootstrapError("A model download attempted a redirect with an invalid port.") from None
    if (parsed.scheme != "https" or not allowed or parsed.username or parsed.password
            or port not in (None, 443)):
        raise LocalModelBootstrapError("A model download attempted an unsafe or unapproved redirect.")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _nearest_existing(path: Path) -> Path:
    current = path
    while not current.exists() and current != current.parent:
        current = current.parent
    return current


class LocalModelBootstrap:
    """Explicit, resumable installer for checksum- and licence-locked local model files.

    Planning is read-only. Downloads happen only through install(..., allow_network=True),
    which is intended for a separately invoked bootstrap operation, never production.
    """

    def __init__(self, *, model_root: str | Path, registry_path: str | Path,
                 hardware_probe=detect_hardware, opener=None):
        raw_root = Path(model_root).expanduser()
        if raw_root.is_symlink():
            raise LocalModelBootstrapError("Model root cannot be a symbolic link.")
        self.model_root = raw_root.resolve()
        self.registry_path = Path(registry_path).expanduser()
        self.hardware_probe = hardware_probe
        self.opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), _HuggingFaceRedirectHandler()).open

    def _registry(self) -> dict[str, Any]:
        try:
            return load_model_registry(self.registry_path)
        except Exception as exc:
            raise LocalModelBootstrapError("Local model registry is invalid (" + type(exc).__name__ + ").") from None

    def _disk_free(self) -> int:
        probe = _nearest_existing(self.model_root)
        try:
            return shutil.disk_usage(probe).free
        except OSError:
            return 0

    def _model_checks(self, model: dict[str, Any], hardware: dict[str, Any], free_bytes: int) -> list[str]:
        problems: list[str] = []
        if model.get("state") != "verified" or model.get("weight_license_status") != "verified":
            problems.append("model weights or licence have not passed the verification gate")
        requirements = model.get("hardware_requirements", {})
        if not isinstance(requirements, dict) or set(requirements) - {"ram_gb", "vram_gb", "disk_gb"}:
            problems.append("model hardware requirements are missing or invalid")
            requirements = {}
        def finite_gb(value: Any) -> float | None:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return None
            number = float(value)
            return number if math.isfinite(number) and number >= 0 else None

        ram = finite_gb(hardware.get("ram_total_gb"))
        vram = finite_gb(hardware.get("gpu_vram_total_gb"))
        required_ram = finite_gb(requirements.get("ram_gb", 0))
        required_vram = finite_gb(requirements.get("vram_gb", 0))
        required_disk = finite_gb(requirements.get("disk_gb", 0))
        if None in (ram, vram, required_ram, required_vram, required_disk):
            problems.append("hardware report or model requirements contain invalid memory values")
        ram = ram or 0
        vram = vram or 0
        required_ram = required_ram if required_ram is not None else float("inf")
        required_vram = required_vram if required_vram is not None else float("inf")
        required_disk = required_disk if required_disk is not None else float("inf")
        if ram < required_ram:
            problems.append("insufficient system RAM for this model profile")
        if vram < required_vram:
            problems.append("insufficient GPU memory for this model profile")
        supported_tasks = hardware.get("hardware_candidate_tasks", [])
        if not isinstance(supported_tasks, list) or model.get("task") not in supported_tasks:
            problems.append("hardware profile has not marked this model task as compatible")
        weights = model.get("weight_files", [])
        if not isinstance(weights, list) or not weights:
            problems.append("no pinned model weight files are defined")
            weights = []
        total_bytes = 0
        for weight in weights:
            if not isinstance(weight, dict):
                problems.append("model contains an invalid weight lock")
                continue
            if weight.get("license_status") != "verified":
                problems.append("one or more model weight licences remain unverified")
            try:
                _safe_relative_path(weight.get("path"))
                _validate_hf_url(weight.get("source_url"))
            except LocalModelBootstrapError:
                problems.append("one or more model weight sources are not immutable, approved HTTPS URLs")
            if not isinstance(weight.get("sha256"), str) or not SHA256_RE.fullmatch(weight["sha256"]):
                problems.append("one or more model weight SHA-256 values are invalid")
            source_revision = weight.get("source_revision")
            if not isinstance(source_revision, str) or not re.fullmatch(r"[0-9a-f]{40}", source_revision):
                problems.append("one or more model source revisions are not pinned")
            elif isinstance(weight.get("source_url"), str) and source_revision not in weight["source_url"]:
                problems.append("model source URL does not match its pinned revision")
            max_bytes = weight.get("max_size_bytes", MAX_ARTIFACT_BYTES)
            if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or not 1 <= max_bytes <= MAX_ARTIFACT_BYTES:
                problems.append("model artifact size bound is invalid")
            expected = weight.get("size_bytes")
            if expected is not None:
                if isinstance(expected, bool) or not isinstance(expected, int) or not 1 <= expected <= max_bytes:
                    problems.append("model artifact expected size is invalid")
                else:
                    total_bytes += expected
            else:
                total_bytes += max_bytes
        minimum_disk = required_disk * (1024 ** 3)
        if free_bytes < max(minimum_disk, total_bytes):
            problems.append("insufficient free disk space for the locked model files")
        return sorted(set(problems))

    def plan(self) -> dict[str, Any]:
        registry = self._registry()
        try:
            hardware = self.hardware_probe()
        except Exception as exc:
            raise LocalModelBootstrapError("Hardware detection failed (" + type(exc).__name__ + ").") from None
        free_bytes = self._disk_free()
        models = []
        for model in registry["models"]:
            try:
                availability = inspect_model_availability(model, self.model_root)
            except Exception:
                availability = {"available": False, "reason": "local artifact verification failed"}
            problems = self._model_checks(model, hardware, free_bytes)
            installed = bool(availability.get("available"))
            models.append({
                "model_id": model["model_id"],
                "task": model["task"],
                "installed": installed,
                "installable": not installed and not problems,
                "status": "installed" if installed else "ready_to_install" if not problems else "blocked",
                "reason": availability.get("reason") if installed else "; ".join(problems) if problems
                          else "hardware, licence and immutable artifact locks verified",
            })
        return {
            "mode": "bootstrap_plan",
            "hardware": hardware,
            "model_root": str(self.model_root),
            "disk_free_bytes": free_bytes,
            "models": models,
            "network_used": False,
            "download_performed": False,
            "normal_generation_network": "blocked",
            "bootstrap_network": "explicit install action only",
        }

    def _target(self, relative: str) -> Path:
        safe = _safe_relative_path(relative)
        target = self.model_root / safe
        current = self.model_root
        if current.is_symlink():
            raise LocalModelBootstrapError("Model root cannot contain symbolic links.")
        for part in safe.parts:
            current = current / part
            if current.is_symlink():
                raise LocalModelBootstrapError("Model artifact path cannot contain symbolic links.")
        try:
            target.resolve(strict=False).relative_to(self.model_root)
        except ValueError:
            raise LocalModelBootstrapError("Model artifact path escapes the configured model root.") from None
        return target

    def _download(self, weight: dict[str, Any], target: Path) -> dict[str, Any]:
        url = _validate_hf_url(weight.get("source_url"))
        _validate_redirect_url(url)
        digest = weight["sha256"]
        max_bytes = weight.get("max_size_bytes", MAX_ARTIFACT_BYTES)
        expected_bytes = weight.get("size_bytes")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.parent.is_symlink():
            raise LocalModelBootstrapError("Model target directory cannot be a symbolic link.")
        if target.is_symlink():
            raise LocalModelBootstrapError("Model artifact target cannot be a symbolic link.")
        if target.is_file() and _sha256(target) == digest:
            return {"path": str(target.relative_to(self.model_root)), "status": "already_verified",
                    "sha256": digest, "byte_size": target.stat().st_size}
        partial = target.with_name(target.name + ".part")
        if partial.is_symlink():
            raise LocalModelBootstrapError("Partial model file cannot be a symbolic link.")
        offset = partial.stat().st_size if partial.exists() else 0
        if offset > max_bytes:
            partial.unlink()
            offset = 0
        headers = {"User-Agent": "uneXpected-local-model-bootstrap/1.0"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        request = urllib.request.Request(url, headers=headers)
        try:
            response = self.opener(request, timeout=60)
            with response:
                final_url = response.geturl() if hasattr(response, "geturl") else url
                _validate_redirect_url(final_url)
                status = getattr(response, "status", None) or response.getcode()
                append = bool(offset and status == 206)
                if offset and status not in {200, 206}:
                    raise LocalModelBootstrapError("Model server refused a safe resumable download.")
                if not offset and status != 200:
                    raise LocalModelBootstrapError("Model server returned an unexpected download status.")
                if append:
                    content_range = response.headers.get("Content-Range", "")
                    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+|\*)", content_range)
                    if not match or int(match.group(1)) != offset:
                        raise LocalModelBootstrapError("Resumed download did not begin at the verified partial-file offset.")
                mode = "ab" if append else "wb"
                written = offset if append else 0
                with partial.open(mode) as handle:
                    while True:
                        chunk = response.read(CHUNK_BYTES)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > max_bytes or (expected_bytes is not None and written > expected_bytes):
                            raise LocalModelBootstrapError("Model download exceeded its locked size bound.")
                        handle.write(chunk)
                    handle.flush()
                    os.fsync(handle.fileno())
        except LocalModelBootstrapError:
            raise
        except Exception as exc:
            raise LocalModelBootstrapError("Model download was interrupted (" + type(exc).__name__ + "); partial bytes were retained for resume.") from None
        actual_size = partial.stat().st_size
        if expected_bytes is not None and actual_size != expected_bytes:
            raise LocalModelBootstrapError("Model download is incomplete; partial bytes were retained for resume.")
        if actual_size <= 0 or _sha256(partial) != digest:
            try:
                partial.unlink()
            except OSError:
                pass
            raise LocalModelBootstrapError("Downloaded model SHA-256 did not match the approved lock.")
        os.replace(partial, target)
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
        return {"path": str(target.relative_to(self.model_root)), "status": "installed",
                "sha256": digest, "byte_size": actual_size}

    def install(self, model_id: str, *, allow_network: bool = False) -> dict[str, Any]:
        if allow_network is not True:
            raise LocalModelBootstrapError("Model downloads require the explicit --allow-network bootstrap flag.")
        registry = self._registry()
        model = next((item for item in registry["models"] if item["model_id"] == model_id), None)
        if model is None:
            raise LocalModelBootstrapError("Unknown model ID; no download was attempted.")
        plan = self.plan()
        selected = next(item for item in plan["models"] if item["model_id"] == model_id)
        if selected["installed"]:
            return {"model_id": model_id, "status": "already_installed", "files": [],
                    "external_ai_api": "disabled"}
        if not selected["installable"]:
            raise LocalModelBootstrapError("Model is not safe or compatible to install: " + selected["reason"])
        if self.model_root.exists() and self.model_root.is_symlink():
            raise LocalModelBootstrapError("Model root cannot be a symbolic link.")
        self.model_root.mkdir(parents=True, exist_ok=True)
        installed = []
        for weight in model["weight_files"]:
            target = self._target(weight["path"])
            installed.append(self._download(weight, target))
        check = inspect_model_availability(model, self.model_root)
        if not check.get("available"):
            raise LocalModelBootstrapError("Installed model failed the registry verification gate.")
        return {"model_id": model_id, "status": "installed", "files": installed,
                "available": True, "external_ai_api": "disabled",
                "production_network": "blocked; bootstrap was an explicit separate action"}


__all__ = ["LocalModelBootstrap", "LocalModelBootstrapError"]
