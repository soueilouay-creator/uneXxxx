from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import os
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


class LocalComfyUIError(RuntimeError):
    """A local ComfyUI workflow or generated artifact failed validation."""


_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")
_SAFE_NODE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_REMOTE_SCHEME = re.compile(r"(?i)\b(?:https?|ftp|file)://")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LocalComfyUIClient:
    """Strict loopback-only client for locally installed ComfyUI workflows.

    Workflow execution is disabled unless the caller supplies a pinned workflow
    file, its exact SHA-256 digest and the node classes explicitly approved for
    that project. The client does not use proxy variables or follow redirects.
    """

    local = True
    service_name = "comfyui-local"

    def __init__(self, base_url: str = "http://127.0.0.1:8188", *,
                 workflow_root: str | Path, timeout: float = 10.0,
                 max_response_bytes: int = 1_000_000,
                 max_output_bytes: int = 512 * 1024 * 1024):
        try:
            parsed = urllib.parse.urlsplit(base_url)
            if (parsed.scheme != "http" or not parsed.hostname
                    or parsed.username is not None or parsed.password is not None
                    or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
                raise ValueError("unsafe local service URL")
            if parsed.hostname.lower() == "localhost":
                raise ValueError("use a literal loopback IP")
            address = ipaddress.ip_address(parsed.hostname)
            if not address.is_loopback:
                raise ValueError("service URL is not loopback")
            if not 0 < float(timeout) <= 600:
                raise ValueError("timeout out of range")
            if not 1024 <= int(max_response_bytes) <= 16 * 1024 * 1024:
                raise ValueError("JSON response limit out of range")
            if not 1024 <= int(max_output_bytes) <= 2 * 1024 * 1024 * 1024:
                raise ValueError("media output limit out of range")
        except (ValueError, TypeError):
            raise LocalComfyUIError("ComfyUI URL must be HTTP on a literal loopback IP, with no credentials, path, query or fragment.") from None
        self.base_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        self.workflow_root = Path(workflow_root).expanduser().resolve()
        self.timeout = float(timeout)
        self.max_response_bytes = int(max_response_bytes)
        self.max_output_bytes = int(max_output_bytes)

    def _opener(self):
        return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None,
                 *, max_bytes: int | None = None) -> tuple[bytes, str]:
        if not path.startswith("/") or path.startswith("//") or ".." in Path(path).parts:
            raise LocalComfyUIError("Invalid local ComfyUI API path.")
        url = self.base_url + path
        headers = {"Accept": "application/json"}
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        limit = self.max_response_bytes if max_bytes is None else min(int(max_bytes), self.max_output_bytes)
        try:
            with self._opener().open(request, timeout=self.timeout) as response:
                content_type = response.headers.get("Content-Type", "")
                raw = response.read(limit + 1)
            if len(raw) > limit:
                raise LocalComfyUIError("Local ComfyUI response exceeded its configured size limit.")
            return raw, content_type
        except urllib.error.HTTPError as exc:
            raise LocalComfyUIError(f"Local ComfyUI rejected the request (HTTP {exc.code}).") from None
        except LocalComfyUIError:
            raise
        except Exception as exc:
            raise LocalComfyUIError(f"Local ComfyUI request failed ({type(exc).__name__}).") from None

    @staticmethod
    def _json(raw: bytes) -> dict[str, Any]:
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            raise LocalComfyUIError("Local ComfyUI returned invalid JSON.") from None
        if not isinstance(value, dict):
            raise LocalComfyUIError("Local ComfyUI returned an unexpected JSON object.")
        return value

    def probe(self) -> dict[str, Any]:
        raw, _ = self._request("GET", "/system_stats")
        result = self._json(raw)
        if not isinstance(result.get("system"), dict) or not isinstance(result.get("devices"), list):
            raise LocalComfyUIError("ComfyUI system status does not match the expected local service schema.")
        return {"status": "available", "local": True, "base_url": self.base_url,
                "system": result["system"], "devices": result["devices"]}

    def _load_workflow(self, workflow_path: str | Path, expected_sha256: str,
                       allowed_node_types: set[str] | list[str] | tuple[str, ...]) -> dict[str, Any]:
        if not isinstance(expected_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
            raise LocalComfyUIError("A pinned workflow SHA-256 is required.")
        if not isinstance(allowed_node_types, (set, list, tuple)) or not allowed_node_types:
            raise LocalComfyUIError("An explicit allowlist of local ComfyUI node classes is required.")
        allow = set(allowed_node_types)
        if any(not isinstance(x, str) or not x.strip() for x in allow):
            raise LocalComfyUIError("Workflow node allowlist contains an invalid entry.")
        path = Path(workflow_path).expanduser()
        if path.is_symlink() or not path.is_file():
            raise LocalComfyUIError("Pinned local workflow file is missing or unsafe.")
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(self.workflow_root)
        except (OSError, ValueError):
            raise LocalComfyUIError("Workflow file must remain inside the configured local workflow directory.") from None
        raw = resolved.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise LocalComfyUIError("Local ComfyUI workflow checksum does not match its lock.")
        try:
            workflow = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            raise LocalComfyUIError("Local ComfyUI workflow must be valid UTF-8 JSON.") from None
        if not isinstance(workflow, dict) or not workflow:
            raise LocalComfyUIError("Local ComfyUI workflow must be a non-empty node object.")
        for node_id, node in workflow.items():
            if not isinstance(node_id, str) or not isinstance(node, dict):
                raise LocalComfyUIError("Local ComfyUI workflow contains an invalid node record.")
            class_type = node.get("class_type")
            if not isinstance(class_type, str) or class_type not in allow:
                raise LocalComfyUIError(f"ComfyUI node {node_id} is not explicitly allowlisted.")
            if re.search(r"(?i)(partner|remote|cloud|api)", class_type):
                raise LocalComfyUIError(f"ComfyUI node {class_type} is prohibited in local-only mode.")
            self._validate_local_node_data(node.get("inputs", {}))
        return workflow

    @classmethod
    def _validate_local_node_data(cls, value: Any, key: str | None = None) -> None:
        if isinstance(value, str):
            if _REMOTE_SCHEME.search(value):
                raise LocalComfyUIError("ComfyUI workflow contains a remote URL; local-only workflows cannot use remote assets.")
            path_keys = {"filename", "image", "video", "audio", "path", "directory",
                         "ckpt_name", "unet_name", "vae_name", "clip_name", "model_path"}
            if key in path_keys:
                normal = value.replace("\\\\", "/")
                if normal.startswith("/") or re.match(r"^[A-Za-z]:/", normal) or ".." in Path(normal).parts:
                    raise LocalComfyUIError("ComfyUI workflow contains a model or asset path outside the local model directory.")
            return
        if isinstance(value, list):
            for item in value:
                cls._validate_local_node_data(item, key)
            return
        if isinstance(value, dict):
            for child_key, item in value.items():
                cls._validate_local_node_data(item, str(child_key))
            return
        if value is None or isinstance(value, (int, float, bool)):
            return
        raise LocalComfyUIError("ComfyUI workflow contains an unsupported input value.")

    @staticmethod
    def _apply_input_overrides(workflow: dict[str, Any], bindings: Any, values: Any) -> None:
        """Apply only explicitly mapped prompt/control inputs from a pinned workflow."""
        if values is None:
            values = {}
        if bindings is None:
            bindings = {}
        if not isinstance(bindings, dict) or not isinstance(values, dict):
            raise LocalComfyUIError("Workflow input bindings and values must be JSON objects.")
        if len(bindings) > 32 or len(values) > 32 or set(values) - set(bindings):
            raise LocalComfyUIError("Workflow inputs exceed the binding limit or contain an unbound value.")
        safe_fields = {
            "text", "prompt", "positive", "positive_prompt", "negative", "negative_prompt",
            "seed", "steps", "cfg", "width", "height", "denoise", "strength",
            "frames", "fps", "frame_rate", "duration",
        }
        for name, value in values.items():
            if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", name):
                raise LocalComfyUIError("Workflow input binding names must be bounded identifiers.")
            binding = bindings.get(name)
            if not isinstance(binding, dict) or set(binding) != {"node_id", "field"}:
                raise LocalComfyUIError("Every workflow binding must identify exactly one node ID and input field.")
            node_id, field = binding.get("node_id"), binding.get("field")
            if (not isinstance(node_id, str) or not _SAFE_NODE_ID.fullmatch(node_id)
                    or not isinstance(field, str) or field not in safe_fields):
                raise LocalComfyUIError("Workflow binding targets an unapproved node input.")
            node = workflow.get(node_id)
            inputs = node.get("inputs") if isinstance(node, dict) else None
            if not isinstance(inputs, dict) or field not in inputs:
                raise LocalComfyUIError("Workflow binding target is missing from the pinned workflow.")
            prior = inputs[field]
            if isinstance(value, str):
                if (not isinstance(prior, str) or not value.strip() or len(value) > 8000
                        or _REMOTE_SCHEME.search(value)
                        or value.startswith(("/", "\\\\"))
                        or re.match(r"^[A-Za-z]:[\\\\/]", value)):
                    raise LocalComfyUIError("Prompt input must be bounded plain text without URLs or file paths.")
            elif isinstance(value, bool):
                if not isinstance(prior, bool):
                    raise LocalComfyUIError("Workflow input value type does not match the pinned input.")
            elif isinstance(value, (int, float)):
                if isinstance(value, float) and not math.isfinite(value):
                    raise LocalComfyUIError("Workflow numeric inputs must be finite.")
                if isinstance(prior, bool) or not isinstance(prior, (int, float)):
                    raise LocalComfyUIError("Workflow input value type does not match the pinned input.")
                if abs(float(value)) > 1_000_000_000:
                    raise LocalComfyUIError("Workflow numeric input exceeds the supported bound.")
            else:
                raise LocalComfyUIError("Workflow input overrides must be bounded strings or numbers.")
            inputs[field] = value

    def queue_workflow(self, workflow_path: str | Path, *, expected_sha256: str,
                       allowed_node_types: set[str] | list[str] | tuple[str, ...],
                       client_id: str = "uneXpected-local-creator",
                       input_bindings: dict[str, dict[str, str]] | None = None,
                       input_values: dict[str, Any] | None = None) -> dict[str, str]:
        workflow = self._load_workflow(workflow_path, expected_sha256, allowed_node_types)
        self._apply_input_overrides(workflow, input_bindings, input_values)
        if not isinstance(client_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", client_id):
            raise LocalComfyUIError("Local ComfyUI client ID is invalid.")
        raw, _ = self._request("POST", "/prompt", {"prompt": workflow, "client_id": client_id})
        data = self._json(raw)
        prompt_id = data.get("prompt_id")
        if not isinstance(prompt_id, str) or not re.fullmatch(r"[A-Za-z0-9-]{8,128}", prompt_id):
            raise LocalComfyUIError("ComfyUI did not return a valid prompt ID.")
        return {"prompt_id": prompt_id, "provider": self.service_name, "workflow_sha256": expected_sha256}

    def wait_for_result(self, prompt_id: str, *, timeout_seconds: float = 900.0,
                        poll_interval: float = 1.0) -> dict[str, Any]:
        if not isinstance(prompt_id, str) or not re.fullmatch(r"[A-Za-z0-9-]{8,128}", prompt_id):
            raise LocalComfyUIError("Invalid local ComfyUI prompt ID.")
        if not 1 <= float(timeout_seconds) <= 7200 or not 0.1 <= float(poll_interval) <= 10:
            raise LocalComfyUIError("Local ComfyUI polling limits are outside the allowed range.")
        deadline = time.monotonic() + float(timeout_seconds)
        while time.monotonic() < deadline:
            raw, _ = self._request("GET", "/history/" + prompt_id)
            data = self._json(raw)
            item = data.get(prompt_id)
            if item is not None:
                if not isinstance(item, dict):
                    raise LocalComfyUIError("ComfyUI history response contains an invalid job.")
                status = item.get("status", {})
                if isinstance(status, dict) and status.get("status_str") == "error":
                    raise LocalComfyUIError("Local ComfyUI workflow failed; inspect the local ComfyUI job history.")
                outputs = item.get("outputs")
                if isinstance(outputs, dict) and outputs:
                    return {"prompt_id": prompt_id, "status": "completed", "outputs": outputs,
                            "provider": self.service_name}
            time.sleep(float(poll_interval))
        raise LocalComfyUIError("Local ComfyUI workflow exceeded its bounded execution deadline.")

    @staticmethod
    def _safe_subfolder(value: Any) -> Path:
        if value is None or value == "":
            return Path()
        if not isinstance(value, str):
            raise LocalComfyUIError("ComfyUI output subfolder is invalid.")
        path = Path(value)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise LocalComfyUIError("ComfyUI output subfolder escapes the local project.")
        return path

    def collect_outputs(self, result: dict[str, Any], destination: str | Path) -> list[dict[str, Any]]:
        outputs = result.get("outputs") if isinstance(result, dict) else None
        if not isinstance(outputs, dict):
            raise LocalComfyUIError("Completed ComfyUI result has no output manifest.")
        root = Path(destination).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        root = root.resolve()
        saved: list[dict[str, Any]] = []
        for node_id, node_output in outputs.items():
            if not isinstance(node_id, str) or not _SAFE_NODE_ID.fullmatch(node_id):
                raise LocalComfyUIError("ComfyUI output node identifier is invalid.")
            if not isinstance(node_output, dict):
                continue
            for kind in ("images", "videos", "gifs", "audio"):
                records = node_output.get(kind, [])
                if not isinstance(records, list):
                    continue
                for record in records:
                    if not isinstance(record, dict):
                        continue
                    filename = record.get("filename")
                    subfolder = self._safe_subfolder(record.get("subfolder", ""))
                    output_type = record.get("type", "output")
                    if (not isinstance(filename, str) or not _SAFE_NAME.fullmatch(filename)
                            or output_type != "output"):
                        raise LocalComfyUIError("ComfyUI output file reference is unsafe or not a local output.")
                    query = urllib.parse.urlencode({"filename": filename, "subfolder": subfolder.as_posix(),
                                                    "type": "output"})
                    raw, content_type = self._request("GET", "/view?" + query, max_bytes=self.max_output_bytes)
                    target_dir = root / subfolder
                    target_dir.mkdir(parents=True, exist_ok=True)
                    target_dir = target_dir.resolve()
                    try:
                        target_dir.relative_to(root)
                    except ValueError:
                        raise LocalComfyUIError("ComfyUI output path escapes the local project directory.") from None
                    suffix = Path(filename).suffix.lower()
                    allowed_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm", ".wav", ".mp3", ".flac"}
                    if suffix not in allowed_suffixes or not raw:
                        raise LocalComfyUIError("ComfyUI generated an unsupported or empty media file.")
                    target = target_dir / (f"node-{node_id}-{filename}")
                    if target.exists() or target.is_symlink():
                        raise LocalComfyUIError("ComfyUI output would overwrite an existing project artifact.")
                    temporary = target.with_name(target.name + ".tmp")
                    temporary.write_bytes(raw)
                    os.replace(temporary, target)
                    saved.append({
                        "path": str(target.relative_to(root)),
                        "kind": kind,
                        "mime_type": content_type.split(";", 1)[0] or _mime_for_suffix(suffix),
                        "byte_size": len(raw),
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "provider": self.service_name,
                    })
        if not saved:
            raise LocalComfyUIError("Local ComfyUI job completed without a supported image, video or audio artifact.")
        return saved


def _mime_for_suffix(suffix: str) -> str:
    return {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif",
        ".mp4": "video/mp4", ".webm": "video/webm", ".wav": "audio/wav", ".mp3": "audio/mpeg",
        ".flac": "audio/flac",
    }.get(suffix, "application/octet-stream")


__all__ = ["LocalComfyUIClient", "LocalComfyUIError"]
