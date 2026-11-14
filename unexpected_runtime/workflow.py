from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
import hashlib
import json
import uuid

from .permissions import PRIVILEGED


@dataclass
class WorkflowResult:
    status: str
    delivered: bool
    request: dict[str, Any]
    plan: Any = None
    execution: Any = None
    verified_output: Any = None
    delivery: Any = None
    corrections: int = 0
    improvements: int = 0
    verification_history: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    learning_error: str | None = None
    workflow_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            'status': self.status, 'delivered': self.delivered, 'request': self.request,
            'plan': self.plan, 'execution': self.execution, 'verified_output': self.verified_output,
            'delivery': self.delivery, 'corrections': self.corrections,
            'improvements': self.improvements, 'verification_history': list(self.verification_history), 'error': self.error,
            'learning_error': self.learning_error, 'workflow_id': self.workflow_id,
        }


class WorkflowCheckpointBlocked(RuntimeError):
    """A workflow stage cannot be replayed or checkpointed safely."""


class WorkflowRunner:
    '''Quality-gated lifecycle runner; host-specific stage adapters are injected.'''

    def __init__(self, *, plan: Callable[[dict[str, Any], str | None], Any],
                 execute: Callable[[Any], Any], verify: Callable[[Any, Any], dict[str, Any]],
                 improve: Callable[[Any, str], Any], deliver: Callable[[Any], Any],
                 learn: Callable[[dict[str, Any]], Any], max_corrections: int = 1,
                 max_improvements: int = 3, checkpoint_store: Any | None = None,
                 on_stage_result: Callable[[str, Any, bool], None] | None = None) -> None:
        if isinstance(max_corrections, bool) or not isinstance(max_corrections, int) or not 0 <= max_corrections <= 5:
            raise ValueError('max_corrections must be an integer between 0 and 5.')
        if isinstance(max_improvements, bool) or not isinstance(max_improvements, int) or not 1 <= max_improvements <= 5:
            raise ValueError('max_improvements must be an integer between 1 and 5.')
        self.plan_stage, self.execute_stage, self.verify_stage = plan, execute, verify
        self.improve_stage, self.deliver_stage, self.learn_stage = improve, deliver, learn
        self.max_corrections = max_corrections
        self.max_improvements = max_improvements
        self.checkpoint_store = checkpoint_store
        self.on_stage_result = on_stage_result

    @staticmethod
    def _canonical_hash(value: Any) -> str:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _stage_hash(stage_key: str, args: tuple[Any, ...]) -> str:
        return WorkflowRunner._canonical_hash({"stage_key": stage_key, "args": list(args)})


    @staticmethod
    def _task_request_hash(payload: dict[str, Any]) -> str:
        """Rebuild Coordinator.invoke's request hash from a persisted task payload."""
        if not isinstance(payload, dict):
            raise WorkflowCheckpointBlocked("The linked task payload is not an object.")
        agent_id = payload.get("agent_id")
        objective = payload.get("objective")
        inputs = payload.get("inputs", {})
        if not isinstance(agent_id, str) or not agent_id or not isinstance(objective, str) or not isinstance(inputs, dict):
            raise WorkflowCheckpointBlocked("The linked task identity is malformed.")
        list_fields = {}
        for field_name in ("required_permissions", "source_refs", "requested_skill_ids"):
            value = payload.get(field_name, [])
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise WorkflowCheckpointBlocked("The linked task payload has malformed " + field_name + ".")
            list_fields[field_name] = value
        identity = {
            "agent_id": agent_id,
            "objective": objective,
            "inputs": inputs or {},
            "required_permissions": list_fields["required_permissions"],
            "source_refs": list_fields["source_refs"],
            "provider_route": payload.get("provider_route"),
            "requested_skill_ids": list_fields["requested_skill_ids"],
            "parent_task_id": payload.get("parent_task_id"),
        }
        encoded = json.dumps(identity, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _validate_completed_stage_replay(self, stage_key: str, acquisition: dict[str, Any]) -> None:
        """Read-only consistency gate before a completed stage is reused."""
        task_id = acquisition.get("task_id")
        if task_id is None:
            return
        if not isinstance(task_id, str) or not task_id.strip():
            raise WorkflowCheckpointBlocked(
                f"Completed stage {stage_key} contains a malformed task reference."
            )
        get_task = getattr(self.checkpoint_store, "get_task", None)
        if not callable(get_task):
            raise WorkflowCheckpointBlocked(
                f"Completed stage {stage_key} cannot be reconciled because task lookup is unavailable."
            )
        try:
            task = get_task(task_id)
        except Exception as exc:
            raise WorkflowCheckpointBlocked(
                f"Completed stage {stage_key} task lookup failed; human review is required."
            ) from exc
        if not isinstance(task, dict) or task.get("task_id") != task_id:
            raise WorkflowCheckpointBlocked(
                f"Completed stage {stage_key} references a missing task record."
            )
        if task.get("status") != "completed":
            raise WorkflowCheckpointBlocked(
                f"Completed stage {stage_key} references a task that is not completed."
            )
        try:
            payload = json.loads(task.get("payload_json") or "")
            task_result = json.loads(task.get("result_json") or "")
        except (TypeError, ValueError):
            raise WorkflowCheckpointBlocked(
                f"Completed stage {stage_key} has malformed linked task evidence."
            ) from None
        if (not isinstance(payload, dict) or not isinstance(task_result, dict)
                or task_result.get("task_id") != task_id
                or task_result.get("status") != "completed"
                or task.get("agent_id") != payload.get("agent_id")):
            raise WorkflowCheckpointBlocked(
                f"Completed stage {stage_key} task result does not match its persisted task."
            )

        required_permissions = payload.get("required_permissions", [])
        if not isinstance(required_permissions, list) or any(
            not isinstance(permission, str) for permission in required_permissions
        ):
            raise WorkflowCheckpointBlocked(
                f"Completed stage {stage_key} has malformed permission evidence."
            )
        protected = sorted(set(required_permissions) & PRIVILEGED)
        if protected:
            raise WorkflowCheckpointBlocked(
                f"Completed stage {stage_key} requires privileged permission(s) "
                + ", ".join(protected)
                + "; approval consumption is not durably linked to this task, so human review is required."
            )

        idempotency_key = payload.get("idempotency_key")
        if idempotency_key:
            if not isinstance(idempotency_key, str) or not idempotency_key.strip():
                raise WorkflowCheckpointBlocked(
                    f"Completed stage {stage_key} has a malformed idempotency key."
                )
            get_claim = getattr(self.checkpoint_store, "get_idempotency_claim", None)
            if not callable(get_claim):
                raise WorkflowCheckpointBlocked(
                    f"Completed stage {stage_key} cannot verify its idempotency claim."
                )
            try:
                claim = get_claim(idempotency_key)
            except Exception as exc:
                raise WorkflowCheckpointBlocked(
                    f"Completed stage {stage_key} idempotency lookup failed; human review is required."
                ) from exc
            if not isinstance(claim, dict):
                raise WorkflowCheckpointBlocked(
                    f"Completed stage {stage_key} has no persisted idempotency claim."
                )
            if claim.get("task_id") != task_id or claim.get("state") != "completed":
                raise WorkflowCheckpointBlocked(
                    f"Completed stage {stage_key} idempotency claim is not completed for the same task."
                )
            if claim.get("request_hash") != self._task_request_hash(payload):
                raise WorkflowCheckpointBlocked(
                    f"Completed stage {stage_key} idempotency request hash does not match its task."
                )
            if claim.get("result") != task_result:
                raise WorkflowCheckpointBlocked(
                    f"Completed stage {stage_key} idempotency result does not match its task result."
                )

    def run(self, request: dict[str, Any], *, workflow_id: str | None = None,
            checkpoint_identity: dict[str, Any] | None = None) -> WorkflowResult:
        if not isinstance(request, dict):
            raise TypeError("request must be a dictionary.")
        if workflow_id is not None and (
            not isinstance(workflow_id, str) or not workflow_id.strip() or len(workflow_id) > 128
        ):
            raise ValueError("workflow_id must be a non-empty string of at most 128 characters.")

        checkpoint_store = self.checkpoint_store
        checkpoint_enabled = checkpoint_store is not None
        identity = checkpoint_identity if checkpoint_identity is not None else request
        if checkpoint_enabled:
            if workflow_id is None:
                workflow_id = uuid.uuid4().hex
            if not isinstance(identity, dict):
                raise TypeError("checkpoint_identity must be a dictionary.")
            request_hash = self._canonical_hash(identity)
            checkpoint = checkpoint_store.create_workflow_checkpoint(
                workflow_id, request_hash, 1,
                {"request": identity, "completed_stages": []},
            )
            if checkpoint.get("status") != "running":
                stored_result = (checkpoint.get("state") or {}).get("result")
                if isinstance(stored_result, dict):
                    try:
                        return WorkflowResult(**stored_result)
                    except TypeError as exc:
                        raise WorkflowCheckpointBlocked(
                            "The terminal workflow checkpoint contains an incompatible result."
                        ) from exc
                raise WorkflowCheckpointBlocked(
                    "This workflow checkpoint is terminal and has no replayable result."
                )

        result = WorkflowResult(
            status="running", delivered=False, request=dict(request), workflow_id=workflow_id
        )
        feedback = None
        stage_index = 0
        checkpoint_blocked = False

        def call_stage(name: str, callback: Callable[..., Any], *args: Any) -> Any:
            nonlocal stage_index, checkpoint_blocked
            stage_index += 1
            replayed = False
            if not checkpoint_enabled:
                value = callback(*args)
            else:
                stage_key = f"{stage_index:04d}:{name}"
                try:
                    stage_hash = self._stage_hash(stage_key, args)
                    attempt_token = uuid.uuid4().hex
                    acquisition = checkpoint_store.begin_workflow_stage(
                        workflow_id, stage_key, stage_index, stage_hash, attempt_token
                    )
                except Exception as exc:
                    checkpoint_blocked = True
                    raise WorkflowCheckpointBlocked(
                        f"Checkpoint acquisition failed for stage {stage_key}; execution stopped safely."
                    ) from exc

                if acquisition.get("status") == "completed":
                    self._validate_completed_stage_replay(stage_key, acquisition)
                    stored = acquisition.get("result")
                    if not isinstance(stored, dict) or "value" not in stored:
                        checkpoint_blocked = True
                        raise WorkflowCheckpointBlocked(
                            f"Completed stage {stage_key} has no valid stored result."
                        )
                    value = stored["value"]
                    replayed = True
                elif acquisition.get("can_execute") is True:
                    try:
                        value = callback(*args)
                        completed = checkpoint_store.complete_workflow_stage(
                            workflow_id, stage_key, attempt_token,
                            value.get("task_id") if isinstance(value, dict) else None,
                            {"value": value},
                        )
                        if not completed:
                            raise RuntimeError("Stage completion compare-and-set was rejected.")
                    except Exception as exc:
                        checkpoint_blocked = True
                        raise WorkflowCheckpointBlocked(
                            f"Stage {stage_key} may have started but has no committed result; automatic replay is refused."
                        ) from exc
                else:
                    checkpoint_blocked = True
                    raise WorkflowCheckpointBlocked(
                        f"Stage {stage_key} is already marked started; automatic replay is refused."
                    )

                try:
                    current = checkpoint_store.get_workflow_checkpoint(workflow_id)
                    if not current or current.get("status") != "running":
                        raise RuntimeError("Workflow checkpoint is not in a running state.")
                    current_state = current.get("state")
                    if not isinstance(current_state, dict):
                        raise RuntimeError("Workflow checkpoint state is malformed.")
                    stage_rows = checkpoint_store.list_workflow_stages(workflow_id)
                    completed_keys = [
                        item["stage_key"] for item in stage_rows
                        if item.get("status") == "completed"
                    ]
                    prior_keys = current_state.get("completed_stages", [])
                    if not isinstance(prior_keys, list):
                        raise RuntimeError("Workflow completed-stage index is malformed.")
                    merged_keys = list(dict.fromkeys([*prior_keys, *completed_keys]))
                    if merged_keys != prior_keys:
                        latest = next(
                            (item["stage_key"] for item in reversed(stage_rows)
                             if item.get("status") == "completed"),
                            stage_key,
                        )
                        next_state = dict(current_state)
                        next_state["completed_stages"] = merged_keys
                        next_state["last_completed_stage"] = latest
                        saved = checkpoint_store.save_workflow_checkpoint(
                            workflow_id, int(current["revision"]), "running", latest, next_state
                        )
                        if not saved:
                            raise RuntimeError("Workflow checkpoint revision conflict.")
                except Exception as exc:
                    checkpoint_blocked = True
                    raise WorkflowCheckpointBlocked(
                        f"Stage {stage_key} completed but checkpoint advancement could not be verified."
                    ) from exc

            if self.on_stage_result is not None:
                try:
                    self.on_stage_result(name, value, replayed)
                except Exception as exc:
                    if checkpoint_enabled:
                        checkpoint_blocked = True
                        raise WorkflowCheckpointBlocked(
                            f"Local workflow state could not be restored after stage {name}."
                        ) from exc
                    raise
            return value

        try:
            while True:
                result.plan = call_stage("plan", self.plan_stage, result.request, feedback)
                result.execution = call_stage("execute", self.execute_stage, result.plan)
                verification = call_stage("verify", self.verify_stage, result.execution, result.plan)
                if not isinstance(verification, dict) or type(verification.get("passed")) is not bool:
                    raise ValueError("verify must return a dictionary with a boolean passed field.")
                feedback = str(verification.get("feedback") or "")
                result.verification_history.append({
                    "phase": "before_improvement", "passed": verification["passed"], "feedback": feedback,
                    "attempt": len(result.verification_history) + 1,
                    "task_id": verification.get("task_id"), "verification_type": verification.get("verification_type"),
                    "reviewer_agent": verification.get("reviewer_agent"),
                })
                if not verification["passed"]:
                    if result.corrections >= self.max_corrections:
                        result.status = "blocked_verification"
                        result.error = feedback or "Verification failed; correction budget exhausted."
                        break
                    result.corrections += 1
                    continue

                candidate_output = result.execution
                for improvement_iteration in range(1, self.max_improvements + 1):
                    candidate_output = call_stage(
                        "improve", self.improve_stage, candidate_output, feedback
                    )
                    result.improvements += 1
                    final_verification = call_stage(
                        "verify", self.verify_stage, candidate_output, result.plan
                    )
                    if not isinstance(final_verification, dict) or type(final_verification.get("passed")) is not bool:
                        raise ValueError("verify must return a dictionary with a boolean passed field.")
                    final_feedback = str(final_verification.get("feedback") or "")
                    phase = "after_improvement" if improvement_iteration == 1 else f"after_improvement_{improvement_iteration}"
                    result.verification_history.append({
                        "phase": phase, "passed": final_verification["passed"], "feedback": final_feedback,
                        "attempt": len(result.verification_history) + 1,
                        "improvement_iteration": improvement_iteration,
                        "task_id": final_verification.get("task_id"),
                        "verification_type": final_verification.get("verification_type"),
                        "reviewer_agent": final_verification.get("reviewer_agent"),
                    })
                    if final_verification["passed"]:
                        result.verified_output = candidate_output
                        result.delivery = call_stage("deliver", self.deliver_stage, result.verified_output)
                        result.status, result.delivered = "delivered", True
                        break
                    feedback = "Post-improvement verification failed: " + (
                        final_feedback or "No reviewer feedback supplied."
                    )

                if result.delivered:
                    break
                if result.corrections >= self.max_corrections:
                    result.status = "blocked_verification"
                    result.error = (
                        f"Improvement budget exhausted after {self.max_improvements} round(s). "
                        + (feedback or "The final candidate did not pass independent verification.")
                    )
                    break
                result.corrections += 1
        except WorkflowCheckpointBlocked as exc:
            checkpoint_blocked = True
            result.status = "blocked_execution"
            result.error = str(exc)
        except Exception as exc:
            result.status = "blocked_execution"
            result.error = f"{type(exc).__name__}: workflow stage failed"
        finally:
            record = {
                "request": result.request, "status": result.status, "delivered": result.delivered,
                "corrections": result.corrections, "improvements": result.improvements,
                "verification_history": list(result.verification_history), "error": result.error,
            }
            try:
                if not checkpoint_blocked:
                    call_stage("learn", self.learn_stage, record)
            except Exception as exc:
                result.learning_error = f"{type(exc).__name__}: learning stage failed"
                result.status = "blocked_learning"
                result.delivered = False
                if checkpoint_enabled:
                    checkpoint_blocked = True

            if checkpoint_enabled and not checkpoint_blocked:
                try:
                    current = checkpoint_store.get_workflow_checkpoint(workflow_id)
                    if not current or current.get("status") != "running":
                        raise RuntimeError("Workflow checkpoint cannot be finalized.")
                    stage_rows = checkpoint_store.list_workflow_stages(workflow_id)
                    completed_keys = [
                        item["stage_key"] for item in stage_rows
                        if item.get("status") == "completed"
                    ]
                    state = dict(current.get("state") or {})
                    prior_keys = state.get("completed_stages", [])
                    if not isinstance(prior_keys, list):
                        raise RuntimeError("Workflow completed-stage index is malformed.")
                    state["completed_stages"] = list(dict.fromkeys([*prior_keys, *completed_keys]))
                    state["result"] = result.to_dict()
                    latest = next(
                        (item["stage_key"] for item in reversed(stage_rows)
                         if item.get("status") == "completed"),
                        current.get("current_stage"),
                    )
                    terminal_status = "completed" if result.delivered else "blocked"
                    saved = checkpoint_store.save_workflow_checkpoint(
                        workflow_id, int(current["revision"]), terminal_status, latest, state
                    )
                    if not saved:
                        raise RuntimeError("Workflow checkpoint terminal revision conflict.")
                except Exception:
                    result.status = "blocked_execution"
                    result.delivered = False
                    result.delivery = None
                    result.error = (
                        "Workflow result could not be committed to the durable checkpoint; "
                        "delivery is not confirmed."
                    )
        return result
