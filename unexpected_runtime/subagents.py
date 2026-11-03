from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import PermissionDenied


class SubagentError(RuntimeError):
    """A bounded specialist delegation was rejected or could not be completed."""


class SubagentRunner:
    """Runs bounded child tasks with isolated role memory and persisted parent lineage."""

    MAX_CHILDREN = 3
    MAX_OBJECTIVE_CHARS = 2000
    MAX_INPUT_BYTES = 16 * 1024
    MAX_CHILD_STEPS = 4

    def __init__(self, coordinator):
        self.coordinator = coordinator

    def _task_depth(self, task_id: str, max_depth: int) -> int:
        current = task_id
        seen: set[str] = set()
        depth = 0
        while current:
            if current in seen:
                raise SubagentError("Parent task lineage contains a cycle.")
            seen.add(current)
            row = self.coordinator.store.get_task(current)
            if row is None:
                raise SubagentError("Parent task does not exist.")
            try:
                payload = json.loads(row.get("payload_json") or "{}")
            except (TypeError, ValueError):
                raise SubagentError("Parent task lineage is unreadable.") from None
            parent = payload.get("parent_task_id")
            if not parent:
                return depth
            depth += 1
            if depth > max_depth:
                raise SubagentError("Parent task lineage exceeds the configured depth.")
            current = parent
        return depth

    @staticmethod
    def _digest(value: Any) -> str:
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def run(self, *, parent_task_id: str, parent_agent_id: str,
            children: list[dict[str, Any]], max_depth: int = 2) -> dict[str, Any]:
        if not isinstance(parent_task_id, str) or not parent_task_id.strip():
            raise SubagentError("A parent task ID is required.")
        if not isinstance(parent_agent_id, str) or not parent_agent_id.strip():
            raise SubagentError("A parent role ID is required.")
        if isinstance(max_depth, bool) or not isinstance(max_depth, int) or not 1 <= max_depth <= 3:
            raise ValueError("max_depth must be an integer between 1 and 3.")
        if not isinstance(children, list) or not 1 <= len(children) <= self.MAX_CHILDREN:
            raise ValueError(f"Delegation requires between 1 and {self.MAX_CHILDREN} child requests.")

        parent_row = self.coordinator.store.get_task(parent_task_id)
        if parent_row is None or parent_row.get("agent_id") != parent_agent_id:
            raise SubagentError("Parent task does not match the supplied parent role.")
        if parent_row.get("status") not in {"running", "completed"}:
            raise SubagentError("Only a running or completed parent task may delegate children.")
        parent_depth = self._task_depth(parent_task_id, max_depth)
        if parent_depth >= max_depth:
            raise SubagentError("Maximum subagent delegation depth reached.")

        parent_spec = self.coordinator.registry.get(parent_agent_id)
        self.coordinator.permissions.authorize(parent_spec, "collaborate")
        prepared: list[dict[str, Any]] = []
        for child in children:
            if not isinstance(child, dict) or set(child) - {"agent_id", "objective", "inputs", "max_steps"}:
                raise SubagentError("Child requests may contain only agent_id, objective, inputs and max_steps.")
            agent_id = child.get("agent_id")
            objective = child.get("objective")
            inputs = child.get("inputs", {})
            max_steps = child.get("max_steps", self.MAX_CHILD_STEPS)
            if not isinstance(agent_id, str) or not agent_id.strip():
                raise SubagentError("Every child requires an agent_id.")
            if not isinstance(objective, str) or not objective.strip() or len(objective) > self.MAX_OBJECTIVE_CHARS:
                raise SubagentError("Every child requires a bounded, non-empty objective.")
            if not isinstance(inputs, dict):
                raise SubagentError("Child inputs must be a JSON object.")
            try:
                encoded_inputs = json.dumps(inputs, sort_keys=True, ensure_ascii=False,
                                            separators=(",", ":"), allow_nan=False).encode("utf-8")
            except (TypeError, ValueError, OverflowError):
                raise SubagentError("Child inputs must contain finite JSON values.") from None
            if len(encoded_inputs) > self.MAX_INPUT_BYTES:
                raise SubagentError("Child inputs exceed the configured size limit.")
            if isinstance(max_steps, bool) or not isinstance(max_steps, int) or not 1 <= max_steps <= self.MAX_CHILD_STEPS:
                raise SubagentError(f"Child max_steps must be between 1 and {self.MAX_CHILD_STEPS}.")
            child_spec = self.coordinator.registry.get(agent_id)
            if agent_id not in parent_spec.handoff_targets and agent_id != "orchestrator":
                raise PermissionDenied(f"Parent role is not authorized to delegate to {agent_id}.")
            self.coordinator.permissions.authorize(child_spec, "collaborate")
            identity = {
                "parent_task_id": parent_task_id,
                "agent_id": agent_id,
                "objective": objective,
                "inputs": dict(inputs),
                "max_steps": max_steps,
            }
            idempotency_key = "subagent-" + self._digest(identity)
            prepared.append({
                "agent_id": agent_id,
                "objective": objective,
                "inputs": dict(inputs),
                "max_steps": max_steps,
                "inputs_sha256": hashlib.sha256(encoded_inputs).hexdigest(),
                "idempotency_key": idempotency_key,
            })

        summaries = []
        for child in prepared:
            objective_hash = hashlib.sha256(child["objective"].encode("utf-8")).hexdigest()
            self.coordinator.store.log_event("subagent_child_started", parent_task_id, parent_agent_id, {
                "child_agent_id": child["agent_id"],
                "objective_sha256": objective_hash,
                "inputs_sha256": child["inputs_sha256"],
                "max_steps": child["max_steps"],
                "depth": parent_depth + 1,
            })
            try:
                result = self.coordinator.invoke(
                    child["agent_id"],
                    child["objective"],
                    child["inputs"],
                    deadline_seconds=30.0,
                    max_steps=child["max_steps"],
                    idempotency_key=child["idempotency_key"],
                    source_refs=(f"task:{parent_task_id}",),
                    parent_task_id=parent_task_id,
                )
                output = str(result.output or "")
                summary = {
                    "task_id": result.task_id,
                    "agent_id": result.agent_id,
                    "status": result.status,
                    "summary": output[:1500],
                    "summary_truncated": len(output) > 1500,
                    "provenance": list(result.provenance)[:16],
                }
                self.coordinator.store.log_event("subagent_child_completed", parent_task_id, parent_agent_id, {
                    "child_task_id": result.task_id,
                    "child_agent_id": result.agent_id,
                    "status": result.status,
                    "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
                    "output_length": len(output),
                })
                summaries.append(summary)
            except Exception as exc:
                self.coordinator.store.log_event("subagent_child_failed", parent_task_id, parent_agent_id, {
                    "child_agent_id": child["agent_id"],
                    "error_type": type(exc).__name__,
                })
                summaries.append({
                    "task_id": None,
                    "agent_id": child["agent_id"],
                    "status": "failed",
                    "summary": f"Child run failed ({type(exc).__name__}).",
                    "summary_truncated": False,
                    "provenance": [f"task:{parent_task_id}"],
                })

        status = "completed" if all(item["status"] == "completed" for item in summaries) else "partial"
        self.coordinator.store.log_event("subagent_delegation_completed", parent_task_id, parent_agent_id, {
            "child_count": len(summaries),
            "completed_count": sum(item["status"] == "completed" for item in summaries),
            "status": status,
            "child_task_ids": [item["task_id"] for item in summaries if item["task_id"]],
        })
        return {"status": status, "parent_task_id": parent_task_id, "children": summaries}
