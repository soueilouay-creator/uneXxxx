from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from threading import Event
from typing import Any, Protocol
import hashlib
import json
import re
import time

from .capabilities import CapabilityRecord, CapabilityRegistry, CapabilityRegistryError
from .models import ApprovalContext, PermissionDenied
from .permissions import PermissionPolicy, PRIVILEGED


class MCPToolError(RuntimeError):
    """A governed MCP adapter registration or invocation failed."""


@dataclass(frozen=True)
class MCPToolDescriptor:
    tool_id: str
    capability_id: str
    name: str
    description: str
    source_url: str
    source_publisher: str
    version: str
    content_sha256: str
    allowed_agent_ids: tuple[str, ...]
    required_permissions: tuple[str, ...]
    data_access: tuple[str, ...] = ()
    max_argument_bytes: int = 16 * 1024
    max_result_bytes: int = 32 * 1024
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        for field_name in ("allowed_agent_ids", "required_permissions", "data_access"):
            value = getattr(self, field_name)
            if isinstance(value, str):
                raise MCPToolError(f"{field_name} must be a collection of scope strings, not a single string.")
            object.__setattr__(self, field_name, tuple(value))
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,127}", self.tool_id):
            raise MCPToolError("MCP tool_id must be a bounded lowercase identifier.")
        if not self.capability_id.strip() or not self.name.strip() or not self.description.strip():
            raise MCPToolError("MCP tool identity and description are required.")
        if len(self.description) > 1000:
            raise MCPToolError("MCP tool description exceeds 1000 characters.")
        if not self.source_url.startswith("https://") or not self.source_publisher.strip():
            raise MCPToolError("MCP tool source URL and publisher provenance are required.")
        if not re.fullmatch(r"[0-9a-f]{64}", self.content_sha256.lower()):
            raise MCPToolError("MCP tool content_sha256 must be a SHA-256 digest.")
        if not self.version.strip() or not self.allowed_agent_ids or not self.required_permissions:
            raise MCPToolError("MCP tool version, role scope and permission scope are required.")
        if len(set(self.allowed_agent_ids)) != len(self.allowed_agent_ids):
            raise MCPToolError("MCP tool role scopes must be unique.")
        if len(set(self.required_permissions)) != len(self.required_permissions):
            raise MCPToolError("MCP tool permission scopes must be unique.")
        if any(not isinstance(value, str) or not value.strip()
               for value in self.allowed_agent_ids + self.required_permissions + self.data_access):
            raise MCPToolError("MCP tool scopes must contain non-empty strings.")
        for name, value in (("max_argument_bytes", self.max_argument_bytes),
                            ("max_result_bytes", self.max_result_bytes)):
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65536:
                raise MCPToolError(f"{name} must be an integer between 1 and 65536.")
        if (isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, (int, float))
                or not 0.1 <= float(self.timeout_seconds) <= 30.0):
            raise MCPToolError("timeout_seconds must be between 0.1 and 30 seconds.")

    def public_dict(self, *, capability_status: str) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "capability_id": self.capability_id,
            "name": self.name,
            "description": self.description,
            "source_url": self.source_url,
            "source_publisher": self.source_publisher,
            "version": self.version,
            "content_sha256": self.content_sha256,
            "allowed_agent_ids": list(self.allowed_agent_ids),
            "required_permissions": list(self.required_permissions),
            "data_access": list(self.data_access),
            "max_argument_bytes": self.max_argument_bytes,
            "max_result_bytes": self.max_result_bytes,
            "timeout_seconds": float(self.timeout_seconds),
            "capability_status": capability_status,
            "enabled": capability_status == "enabled",
        }


@dataclass
class MCPToolCallContext:
    task_id: str
    agent_id: str
    deadline_monotonic: float
    _cancel_event: Event = field(default_factory=Event)

    def cancel(self) -> None:
        self._cancel_event.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.deadline_monotonic - time.monotonic())


class MCPToolAdapter(Protocol):
    def describe(self) -> tuple[MCPToolDescriptor, ...]: ...
    def call(self, tool_id: str, arguments: dict[str, Any], context: MCPToolCallContext) -> Any: ...


class MCPToolGateway:
    """In-process, provenance-checked MCP adapter boundary; it does not open network connections."""

    def __init__(self, *, store, capabilities: CapabilityRegistry, permissions: PermissionPolicy,
                 agent_registry, max_workers: int = 2):
        self.store = store
        self.capabilities = capabilities
        self.permissions = permissions
        self.agent_registry = agent_registry
        self._adapters: dict[str, MCPToolAdapter] = {}
        self._tools: dict[str, tuple[str, MCPToolAdapter, MCPToolDescriptor]] = {}
        self._executor = ThreadPoolExecutor(max_workers=max(1, min(int(max_workers), 4)),
                                            thread_name_prefix="unexpected-mcp")
        # Preserve any verifier for other capability types; MCP enablement is verified here.
        previous_verifier = self.capabilities.adapter_verifier
        def verify_capability(record: CapabilityRecord) -> bool:
            if record.adapter_type == "mcp":
                return self.verify_adapter(record)
            return bool(previous_verifier and previous_verifier(record))
        self.capabilities.adapter_verifier = verify_capability

    @staticmethod
    def _matches_record(record: CapabilityRecord, descriptor: MCPToolDescriptor) -> bool:
        return (
            descriptor.capability_id == record.capability_id
            and descriptor.source_url == record.source_url
            and descriptor.source_publisher == record.source_publisher
            and descriptor.version == record.version
            and descriptor.content_sha256.lower() == record.content_sha256.lower()
            and tuple(descriptor.required_permissions) == tuple(record.required_permissions)
            and tuple(descriptor.data_access) == tuple(record.data_access)
        )

    @staticmethod
    def _describe(adapter: MCPToolAdapter) -> tuple[MCPToolDescriptor, ...]:
        describe = getattr(adapter, "describe", None)
        call = getattr(adapter, "call", None)
        if not callable(describe) or not callable(call):
            raise MCPToolError("MCP adapter must expose describe() and call().")
        try:
            descriptors = tuple(describe())
        except Exception as exc:
            raise MCPToolError(f"MCP adapter descriptor failed ({type(exc).__name__}).") from None
        if not descriptors or any(not isinstance(item, MCPToolDescriptor) for item in descriptors):
            raise MCPToolError("MCP adapter must return one or more validated MCPToolDescriptor records.")
        tool_ids = [item.tool_id for item in descriptors]
        if len(set(tool_ids)) != len(tool_ids):
            raise MCPToolError("MCP adapter returned duplicate tool IDs.")
        return descriptors

    def register_adapter(self, capability_id: str, adapter: MCPToolAdapter) -> tuple[MCPToolDescriptor, ...]:
        record = self.capabilities.get(capability_id)
        if record.status != "installed":
            raise MCPToolError("Only reviewed and installed MCP adapters may be registered.")
        descriptors = self._describe(adapter)
        if any(set(item.required_permissions) & PRIVILEGED for item in descriptors):
            raise MCPToolError("Privileged MCP tools remain disabled until durable approval/replay storage is verified.")
        if any(not self._matches_record(record, item) for item in descriptors):
            raise MCPToolError("MCP adapter provenance does not match its reviewed capability record.")
        if any(item.tool_id in self._tools for item in descriptors):
            raise MCPToolError("MCP tool IDs must be unique across registered adapters.")
        self._adapters[capability_id] = adapter
        for descriptor in descriptors:
            self._tools[descriptor.tool_id] = (capability_id, adapter, descriptor)
        self.store.log_event("mcp_adapter_registered", payload={
            "capability_id": capability_id,
            "tool_ids": [item.tool_id for item in descriptors],
            "source_url": record.source_url,
            "source_publisher": record.source_publisher,
            "version": record.version,
            "content_sha256": record.content_sha256,
        })
        return descriptors

    def verify_adapter(self, record: CapabilityRecord) -> bool:
        adapter = self._adapters.get(record.capability_id)
        if adapter is None:
            return False
        try:
            descriptors = self._describe(adapter)
        except MCPToolError:
            return False
        return bool(descriptors) and all(self._matches_record(record, item) for item in descriptors)

    def list_tools(self) -> list[dict[str, Any]]:
        items = []
        for tool_id in sorted(self._tools):
            capability_id, _adapter, descriptor = self._tools[tool_id]
            record = self.capabilities.get(capability_id)
            items.append(descriptor.public_dict(capability_status=record.status))
        return items

    @staticmethod
    def action_details(*, task_id: str, agent_id: str, capability_id: str,
                       tool_id: str, arguments: dict[str, Any],
                       required_permissions: tuple[str, ...]) -> dict[str, Any]:
        encoded = json.dumps(arguments, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        return {
            "action": "mcp.tool.call",
            "task_id": task_id,
            "agent_id": agent_id,
            "capability_id": capability_id,
            "tool_id": tool_id,
            "arguments_sha256": hashlib.sha256(encoded).hexdigest(),
            "required_permissions": sorted(set(required_permissions)),
        }

    def call(self, *, agent_id: str, task_id: str, tool_id: str,
             arguments: dict[str, Any], approval: ApprovalContext | None = None) -> Any:
        if not isinstance(task_id, str) or not task_id.strip():
            raise MCPToolError("A task_id is required for every MCP tool call.")
        entry = self._tools.get(tool_id)
        if entry is None:
            raise MCPToolError("Unknown MCP tool.")
        capability_id, adapter, descriptor = entry
        record = self.capabilities.get(capability_id)
        if record.status != "enabled":
            raise MCPToolError("MCP capability is not enabled.")
        if set(descriptor.required_permissions) & PRIVILEGED:
            raise MCPToolError("Privileged MCP tools remain disabled until durable approval/replay storage is verified.")
        if not self.verify_adapter(record):
            raise MCPToolError("MCP adapter provenance no longer matches its reviewed capability record.")
        agent = self.agent_registry.get(agent_id)
        if agent_id not in descriptor.allowed_agent_ids:
            raise PermissionDenied(f"Permission denied: role {agent_id} is outside MCP tool scope.")
        if not isinstance(arguments, dict):
            raise MCPToolError("MCP tool arguments must be a JSON object.")
        try:
            encoded = json.dumps(arguments, sort_keys=True, ensure_ascii=False,
                                 separators=(",", ":"), allow_nan=False).encode("utf-8")
        except (TypeError, ValueError, OverflowError):
            raise MCPToolError("MCP tool arguments must be finite JSON values.") from None
        if len(encoded) > descriptor.max_argument_bytes:
            raise MCPToolError("MCP tool arguments exceed the configured size limit.")
        details = self.action_details(
            task_id=task_id, agent_id=agent_id, capability_id=capability_id,
            tool_id=tool_id, arguments=arguments,
            required_permissions=descriptor.required_permissions,
        )
        for permission in descriptor.required_permissions:
            self.permissions.authorize(agent, permission, approval, action_details=details)

        started = time.monotonic()
        context = MCPToolCallContext(
            task_id=task_id, agent_id=agent_id,
            deadline_monotonic=started + float(descriptor.timeout_seconds),
        )
        self.store.log_event("mcp_tool_call_started", task_id, agent_id, {
            "capability_id": capability_id,
            "tool_id": tool_id,
            "arguments_sha256": hashlib.sha256(encoded).hexdigest(),
            "argument_bytes": len(encoded),
            "source_url": descriptor.source_url,
            "version": descriptor.version,
        })
        future = self._executor.submit(adapter.call, tool_id, dict(arguments), context)
        try:
            output = future.result(timeout=float(descriptor.timeout_seconds))
        except FutureTimeout:
            context.cancel()
            future.cancel()
            self.store.log_event("mcp_tool_call_timeout", task_id, agent_id, {
                "capability_id": capability_id, "tool_id": tool_id,
                "timeout_seconds": float(descriptor.timeout_seconds),
            })
            raise MCPToolError("MCP tool call timed out; no automatic retry was attempted.") from None
        except Exception as exc:
            self.store.log_event("mcp_tool_call_failed", task_id, agent_id, {
                "capability_id": capability_id, "tool_id": tool_id,
                "error_type": type(exc).__name__,
            })
            raise MCPToolError(f"MCP tool call failed ({type(exc).__name__}).") from None

        try:
            encoded_output = json.dumps(output, ensure_ascii=False, separators=(",", ":"),
                                         allow_nan=False).encode("utf-8")
        except (TypeError, ValueError, OverflowError):
            self.store.log_event("mcp_tool_call_failed", task_id, agent_id, {
                "capability_id": capability_id, "tool_id": tool_id,
                "error_type": "NonJSONResult",
            })
            raise MCPToolError("MCP adapter returned a non-JSON result.") from None
        if len(encoded_output) > descriptor.max_result_bytes:
            self.store.log_event("mcp_tool_call_failed", task_id, agent_id, {
                "capability_id": capability_id, "tool_id": tool_id,
                "error_type": "ResultTooLarge", "result_bytes": len(encoded_output),
            })
            raise MCPToolError("MCP adapter result exceeds the configured size limit.")
        self.store.log_event("mcp_tool_call_completed", task_id, agent_id, {
            "capability_id": capability_id,
            "tool_id": tool_id,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "result_bytes": len(encoded_output),
            "result_sha256": hashlib.sha256(encoded_output).hexdigest(),
            "source_url": descriptor.source_url,
            "version": descriptor.version,
        })
        return output

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
