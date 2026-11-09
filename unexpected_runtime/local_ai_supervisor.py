from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from .local_ai import LocalAIError, _memory_bytes, inspect_local_ai, inspect_model_availability, load_model_registry

try:
    import psutil
except ImportError:  # Supervisor start/stop must fail closed without process identity checks.
    psutil = None


class LocalSupervisorError(RuntimeError):
    """A local runtime could not be started or safely managed."""


def _run_probe(command: list[str], timeout: float = 4.0) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                                check=False, shell=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _nvidia_devices() -> list[dict[str, Any]]:
    if not shutil.which("nvidia-smi"):
        return []
    output = _run_probe([
        "nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"
    ])
    devices = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",", 1)]
        if len(parts) != 2:
            continue
        try:
            memory_mib = int(parts[1])
        except ValueError:
            continue
        if memory_mib > 0:
            devices.append({"name": parts[0][:120], "memory_bytes": memory_mib * 1024 * 1024,
                            "vendor": "nvidia"})
    return devices


def _rocm_devices() -> list[dict[str, Any]]:
    if not shutil.which("rocm-smi"):
        return []
    output = _run_probe(["rocm-smi", "--showmeminfo", "vram", "--json"])
    try:
        data = json.loads(output)
    except (ValueError, TypeError):
        return []
    devices: list[dict[str, Any]] = []

    def visit(value: Any, label: str = "") -> None:
        if isinstance(value, dict):
            name = ""
            total = None
            for key, item in value.items():
                text = str(item)
                if "product" in str(key).lower() or "name" in str(key).lower():
                    name = text[:120]
                if "vram" in str(key).lower() and "total" in str(key).lower():
                    match = re.search(r"([0-9]+(?:\.[0-9]+)?)", text.replace(",", ""))
                    if match:
                        total = int(float(match.group(1)) * (1024 ** 2 if "mb" in text.lower() else 1))
            if total:
                devices.append({"name": name or label or "AMD GPU", "memory_bytes": total,
                                "vendor": "amd"})
            for key, item in value.items():
                visit(item, str(key))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{label}-{index}")

    visit(data)
    # Some ROCm releases report the same card at multiple nesting levels.
    unique = {}
    for device in devices:
        unique[(device["name"], device["memory_bytes"])] = device
    return list(unique.values())


def _mac_devices() -> list[dict[str, Any]]:
    if platform.system() != "Darwin" or not shutil.which("system_profiler"):
        return []
    output = _run_probe(["system_profiler", "SPDisplaysDataType", "-detailLevel", "mini"], timeout=8)
    devices = []
    current = "Apple GPU"
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.endswith(":") and not stripped.startswith("VRAM"):
            current = stripped[:-1][:120]
        match = re.search(r"(?:VRAM \(Total\)|VRAM|Memory):\s*([0-9]+)\s*(GB|MB)", stripped, re.I)
        if match:
            amount = int(match.group(1)) * (1024 ** 3 if match.group(2).upper() == "GB" else 1024 ** 2)
            devices.append({"name": current, "memory_bytes": amount, "vendor": "apple"})
    return devices


def _ram_bytes() -> int | None:
    value = _memory_bytes()
    if value:
        return value
    if psutil is not None:
        try:
            return int(psutil.virtual_memory().total)
        except Exception:
            return None
    return None


def detect_hardware() -> dict[str, Any]:
    """Read-only hardware survey. Does not download, install or call external services."""
    devices = _nvidia_devices() or _rocm_devices() or _mac_devices()
    total_vram = sum(item["memory_bytes"] for item in devices) if devices else None
    ram = _ram_bytes()
    vram_gb = (total_vram / (1024 ** 3)) if total_vram else 0.0
    ram_gb = (ram / (1024 ** 3)) if ram else 0.0
    if vram_gb >= 24:
        profile = "high_vram"
    elif vram_gb >= 12:
        profile = "mid_vram"
    elif vram_gb >= 6:
        profile = "low_vram"
    else:
        profile = "cpu_only"
    eligible = []
    if ram_gb >= 8:
        eligible.append("llm")
    if vram_gb >= 12 and ram_gb >= 16:
        eligible.append("image")
    if (vram_gb >= 8 and ram_gb >= 16) or ram_gb >= 32:
        eligible.append("tts")
    if vram_gb >= 4 and ram_gb >= 16:
        eligible.append("music")
    if vram_gb >= 24 and ram_gb >= 32:
        eligible.append("video")
    return {
        "platform": platform.platform(),
        "system": platform.system(),
        "architecture": platform.machine(),
        "cpu_count": os.cpu_count(),
        "ram_total_bytes": ram,
        "ram_total_gb": round(ram_gb, 2) if ram else None,
        "gpus": devices,
        "gpu_count": len(devices),
        "gpu_vram_total_bytes": total_vram,
        "gpu_vram_total_gb": round(vram_gb, 2) if total_vram else None,
        "profile": profile,
        "hardware_candidate_tasks": eligible,
        "probe_network_used": False,
    }


class LocalAISupervisor:
    """Manage user-installed local LLM and ComfyUI services without cloud fallback."""

    SERVICE_KINDS = {"llm", "comfyui"}
    OFFLINE_ENV = {
        "UNEXPECTED_AI_MODE": "local_only",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "DO_NOT_TRACK": "1",
        "NO_PROXY": "127.0.0.1,localhost,::1",
        "no_proxy": "127.0.0.1,localhost,::1",
    }
    ALLOWED_ENV = {"CUDA_VISIBLE_DEVICES", "ROCR_VISIBLE_DEVICES", "OMP_NUM_THREADS",
                   "PYTORCH_CUDA_ALLOC_CONF"}

    def __init__(self, *, model_root: str | Path = "./models",
                 registry_path: str | Path | None = None,
                 config_path: str | Path | None = None,
                 state_dir: str | Path | None = None):
        project_root = Path(__file__).resolve().parent.parent
        self.model_root = Path(model_root).expanduser().resolve()
        self.registry_path = Path(registry_path or project_root / "local_ai" / "model_registry.json").expanduser()
        default_root = Path.home() / ".unexpected" / "local-ai"
        self.config_path = Path(config_path or default_root / "runtime_config.json").expanduser()
        self.state_dir = Path(state_dir or default_root / "state").expanduser()
        self.state_file = self.state_dir / "processes.json"
        self.log_dir = self.state_dir / "logs"

    def _registry(self) -> dict[str, Any]:
        try:
            return load_model_registry(self.registry_path)
        except LocalAIError as exc:
            raise LocalSupervisorError(str(exc)) from None

    def _process_state(self) -> dict[str, Any]:
        if not self.state_file.exists():
            return {"schema_version": 1, "services": {}}
        try:
            if self.state_file.is_symlink():
                raise ValueError("symlink")
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            if data.get("schema_version") != 1 or not isinstance(data.get("services"), dict):
                raise ValueError("schema")
            return data
        except (OSError, ValueError, AttributeError):
            raise LocalSupervisorError("Local process-state file is invalid or unsafe; refusing to signal any process.") from None

    def _save_state(self, state: dict[str, Any]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        if self.state_dir.is_symlink():
            raise LocalSupervisorError("Supervisor state directory must not be a symbolic link.")
        temporary = self.state_file.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, self.state_file)

    def _read_config(self) -> dict[str, Any]:
        try:
            if self.config_path.is_symlink():
                raise ValueError("symlink")
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            raise LocalSupervisorError("Local runtime config is missing or invalid. Copy runtime_config.example.json and set local executable paths.") from None
        if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("services"), dict):
            raise LocalSupervisorError("Local runtime config must use schema_version 1 and a services object.")
        if set(data) - {"schema_version", "services"}:
            raise LocalSupervisorError("Local runtime config contains unsupported top-level fields.")
        if set(data["services"]) - self.SERVICE_KINDS:
            raise LocalSupervisorError("Only the local LLM and ComfyUI service types may be supervised.")
        return data

    def _service_check(self, name: str, spec: Any, registry: dict[str, Any]) -> dict[str, Any]:
        problems: list[str] = []
        if name not in self.SERVICE_KINDS or not isinstance(spec, dict):
            return {"service": name, "ready": False, "problems": ["unsupported service configuration"]}
        if set(spec) - {"kind", "command", "cwd", "port", "model_id", "environment", "startup_timeout_seconds"}:
            problems.append("unsupported service fields")
        kind = spec.get("kind")
        if kind != name:
            problems.append("service kind does not match its key")
        command = spec.get("command")
        if not isinstance(command, list) or not command or any(not isinstance(x, str) or not x for x in command):
            problems.append("command must be a non-empty argument array; shell execution is forbidden")
            command = []
        if command:
            executable = Path(command[0]).expanduser()
            if not executable.is_absolute() or not executable.is_file() or not os.access(executable, os.X_OK):
                problems.append("executable must be an installed absolute executable path")
            joined = " ".join(command).lower()
            if any(token in joined for token in ("--share", "0.0.0.0", "https://", "http://", "api_key", "api-key")):
                problems.append("command contains a public bind, remote URL, share flag or credential argument")
        cwd_value = spec.get("cwd")
        cwd = Path(cwd_value).expanduser() if isinstance(cwd_value, str) and cwd_value else None
        if cwd is not None and (not cwd.is_absolute() or not cwd.is_dir() or cwd.is_symlink()):
            problems.append("working directory must be an installed absolute regular directory")
        port = spec.get("port")
        if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
            problems.append("port must be an integer between 1024 and 65535")
        if kind == "comfyui":
            lower = [item.lower() for item in command]
            if "--offline" not in lower or "--disable-partner-nodes" not in lower:
                problems.append("ComfyUI must be launched with --offline and --disable-partner-nodes")
            try:
                listen_at = lower.index("--listen")
                if listen_at + 1 >= len(command) or command[listen_at + 1] not in {"127.0.0.1", "::1"}:
                    problems.append("ComfyUI must bind its API to a loopback address")
            except ValueError:
                problems.append("ComfyUI requires an explicit --listen 127.0.0.1")
        elif kind == "llm":
            lower = [item.lower() for item in command]
            try:
                host_at = lower.index("--host")
                if host_at + 1 >= len(command) or command[host_at + 1] not in {"127.0.0.1", "::1"}:
                    problems.append("llama-server must bind its API to a loopback address")
            except ValueError:
                problems.append("llama-server requires an explicit --host 127.0.0.1")
            model_id = spec.get("model_id")
            models = {item["model_id"]: item for item in registry["models"]}
            model = models.get(model_id)
            if model is None or model.get("task") != "llm":
                problems.append("LLM service must name a registered local LLM model")
            else:
                availability = inspect_model_availability(model, self.model_root)
                if not availability["available"]:
                    problems.append("LLM model is not verified locally: " + availability["reason"])
                model_files = {str((self.model_root / item["path"]).resolve()) for item in model.get("weight_files", [])}
                try:
                    model_arg = command[lower.index("--model") + 1]
                except (ValueError, IndexError):
                    model_arg = ""
                if model_arg not in model_files:
                    problems.append("--model must point to a checksum-verified model file from the registry")
        env = spec.get("environment", {})
        if not isinstance(env, dict) or set(env) - self.ALLOWED_ENV or any(not isinstance(v, str) for v in env.values()):
            problems.append("environment may contain only non-secret hardware tuning variables")
        timeout = spec.get("startup_timeout_seconds", 60)
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 5 <= timeout <= 600:
            problems.append("startup_timeout_seconds must be between 5 and 600")
        return {"service": name, "ready": not problems, "problems": problems,
                "port": port if isinstance(port, int) and not isinstance(port, bool) else None,
                "kind": kind}

    def preflight(self) -> dict[str, Any]:
        hardware = detect_hardware()
        registry = self._registry()
        model_report = inspect_local_ai(self.model_root, registry)
        available_by_id = {item["model_id"]: item["available"] for item in model_report["models"]}
        hardware_tasks = set(hardware["hardware_candidate_tasks"])
        available_tasks = {item["task"] for item in registry["models"]
                            if available_by_id.get(item["model_id"]) and item["task"] in hardware_tasks}
        try:
            config = self._read_config()
            service_checks = [self._service_check(name, spec, registry)
                              for name, spec in sorted(config["services"].items())]
            config_error = None
        except LocalSupervisorError as exc:
            service_checks = []
            config_error = str(exc)
        task_results = []
        for task in ("llm", "image", "tts", "music", "video", "asr"):
            candidates = [item for item in registry["models"] if item["task"] == task]
            ready_models = [item["model_id"] for item in candidates if available_by_id.get(item["model_id"])]
            task_results.append({
                "task": task,
                "hardware_eligible": task in hardware_tasks,
                "ready": task in available_tasks,
                "verified_models": ready_models,
                "reason": ("ready" if task in available_tasks else
                           "no compatible hardware profile" if task not in hardware_tasks else
                           "no locally cached model has a verified licence and checksum"),
            })
        required_model_tasks = {"llm", "image", "tts", "music", "video"}
        required_services = {"llm", "comfyui"}
        ready_services = {item["service"] for item in service_checks if item.get("ready")}
        missing_model_tasks = sorted(required_model_tasks - available_tasks)
        missing_services = sorted(required_services - ready_services)
        ready_to_generate = not missing_model_tasks and not missing_services
        return {
            "mode": "local_only",
            "hardware": hardware,
            "model_root": str(self.model_root),
            "model_tasks": task_results,
            "services": service_checks,
            "config_error": config_error,
            "external_ai_api": "disabled",
            "normal_generation_network": "blocked by policy; local workflow clients only",
            "downloads_performed": False,
            "pipeline_readiness": {
                "required_model_tasks": sorted(required_model_tasks),
                "missing_model_tasks": missing_model_tasks,
                "required_services": sorted(required_services),
                "missing_services": missing_services,
                "ready": ready_to_generate,
            },
            "ready_to_generate": ready_to_generate,
        }

    @staticmethod
    def _process_identity(pid: int) -> tuple[float, str] | None:
        if psutil is None:
            return None
        try:
            process = psutil.Process(pid)
            return float(process.create_time()), str(Path(process.exe()).resolve())
        except (psutil.Error, OSError, ValueError):
            return None

    def _offline_environment(self, configured: dict[str, str]) -> dict[str, str]:
        # Inherit only OS essentials. API keys, proxy credentials and provider tokens are excluded.
        env = {
            "PATH": os.environ.get("PATH", os.defpath),
            "HOME": str(Path.home()),
            "USERPROFILE": os.environ.get("USERPROFILE", str(Path.home())),
            "TEMP": os.environ.get("TEMP", "/tmp"),
            "TMP": os.environ.get("TMP", "/tmp"),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            **self.OFFLINE_ENV,
            **configured,
        }
        return {key: value for key, value in env.items() if value != ""}

    def start(self, service_name: str | None = None) -> dict[str, Any]:
        if psutil is None:
            raise LocalSupervisorError("psutil is required for safe process identity checks; install the pinned runtime requirements first.")
        config = self._read_config()
        registry = self._registry()
        names = [service_name] if service_name else sorted(config["services"])
        if not names:
            raise LocalSupervisorError("No local services are configured. Set local executable paths in runtime_config.json.")
        state = self._process_state()
        results = []
        for name in names:
            if name not in config["services"]:
                results.append({"service": name, "status": "blocked", "reason": "service is not configured"})
                continue
            spec = config["services"][name]
            check = self._service_check(name, spec, registry)
            if not check["ready"]:
                results.append({"service": name, "status": "blocked", "problems": check["problems"]})
                continue
            existing = state["services"].get(name)
            if existing:
                identity = self._process_identity(int(existing.get("pid", -1)))
                if identity and identity == (existing.get("create_time"), existing.get("executable")):
                    results.append({"service": name, "status": "already_running", "pid": existing["pid"]})
                    continue
                state["services"].pop(name, None)
            command = list(spec["command"])
            cwd = str(Path(spec["cwd"]).expanduser()) if spec.get("cwd") else None
            self.log_dir.mkdir(parents=True, exist_ok=True)
            log_path = self.log_dir / (name + ".log")
            try:
                with log_path.open("ab") as log:
                    process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL,
                                               stdout=log, stderr=subprocess.STDOUT,
                                               shell=False, close_fds=True,
                                               env=self._offline_environment(spec.get("environment", {})),
                                               start_new_session=(os.name != "nt"))
                deadline = time.monotonic() + spec.get("startup_timeout_seconds", 60)
                ready = False
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        break
                    try:
                        with socket.create_connection(("127.0.0.1", int(spec["port"])), timeout=0.4):
                            ready = True
                            break
                    except OSError:
                        time.sleep(0.25)
                if not ready:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=4)
                        except subprocess.TimeoutExpired:
                            process.kill()
                    results.append({"service": name, "status": "blocked",
                                    "reason": "local service did not become ready on its configured loopback port",
                                    "log_file": str(log_path)})
                    continue
                identity = self._process_identity(process.pid)
                if not identity:
                    process.terminate()
                    results.append({"service": name, "status": "blocked",
                                    "reason": "could not verify the started process identity"})
                    continue
                state["services"][name] = {
                    "pid": process.pid, "create_time": identity[0], "executable": identity[1],
                    "command_sha256": hashlib.sha256(json.dumps(command).encode()).hexdigest(),
                    "port": spec["port"], "started_at": int(time.time()), "log_file": str(log_path),
                }
                results.append({"service": name, "status": "running", "pid": process.pid,
                                "bind": "127.0.0.1", "network": "offline environment"})
            except (OSError, KeyError, ValueError) as exc:
                results.append({"service": name, "status": "blocked",
                                "reason": f"start failed ({type(exc).__name__})"})
        self._save_state(state)
        return {"mode": "local_only", "services": results, "external_ai_api": "disabled"}

    def stop(self, service_name: str | None = None) -> dict[str, Any]:
        if psutil is None:
            raise LocalSupervisorError("psutil is required for safe process identity checks.")
        state = self._process_state()
        names = [service_name] if service_name else sorted(state["services"])
        results = []
        for name in names:
            record = state["services"].get(name)
            if not record:
                results.append({"service": name, "status": "stopped"})
                continue
            identity = self._process_identity(int(record.get("pid", -1)))
            expected = (record.get("create_time"), record.get("executable"))
            if not identity or identity != expected:
                state["services"].pop(name, None)
                results.append({"service": name, "status": "stale_record_removed",
                                "signal_sent": False})
                continue
            try:
                process = psutil.Process(int(record["pid"]))
                process.terminate()
                try:
                    process.wait(timeout=8)
                except psutil.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=4)
                state["services"].pop(name, None)
                results.append({"service": name, "status": "stopped", "pid": record["pid"]})
            except (psutil.Error, OSError):
                results.append({"service": name, "status": "blocked",
                                "reason": "process ownership changed; no further signal was sent"})
        self._save_state(state)
        return {"mode": "local_only", "services": results, "external_ai_api": "disabled"}

    def status(self) -> dict[str, Any]:
        report = self.preflight()
        try:
            state = self._process_state()
        except LocalSupervisorError as exc:
            report["process_state_error"] = str(exc)
            return report
        current = []
        for name, record in state["services"].items():
            identity = self._process_identity(int(record.get("pid", -1)))
            alive = bool(identity and identity == (record.get("create_time"), record.get("executable")))
            current.append({"service": name, "status": "running" if alive else "stopped",
                            "pid": record.get("pid") if alive else None, "port": record.get("port")})
        report["running_services"] = current
        return report


__all__ = ["LocalAISupervisor", "LocalSupervisorError", "detect_hardware"]
