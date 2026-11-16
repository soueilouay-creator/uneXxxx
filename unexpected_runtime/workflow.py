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
    pending_approval: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            'status': self.status, 'delivered': self.delivered, 'request': self.request,
            'plan': self.plan, 'execution': self.execution, 'verified_output': self.verified_output,
            'delivery': self.delivery, 'corrections': self.corrections,
            'improvements': self.improvements, 'verification_history': list(self.verification_history), 'error': self.error,
            'learning_error': self.learning_error, 'workflow_id': self.workflow_id,
            'pending_approval': self.pending_approval,
        }


class WorkflowAwaitingApproval(RuntimeError):
    """A protected workflow stage is durably prepared but awaits human approval."""

    def __init__(self, pending: dict[str, Any]):
        super().__init__("Workflow stage is waiting for an execution-bound approval.")
        self.pending = dict(pending)


class WorkflowCheckpointBlocked(RuntimeError):
    """A workflow stage cannot be replayed or checkpointed safely."""


class WorkflowRunner:
    '''Quality-gated lifecycle runner; host-specific stage adapters are injected.'''

    def __init__(self, *, plan: Callable[[dict[str, Any], str | None], Any],
                 execute: Callable[[Any], Any], verify: Callable[[Any, Any], dict[str, Any]],
                 improve: Callable[[Any, str], Any], deliver: Callable[[Any], Any],
                 learn: Callable[[dict[str, Any]], Any], max_corrections: int = 1,
                 max_improvements: int = 3, checkpoint_store: Any | None = None,
                 on_stage_result: Callable[[str, Any, bool], None] | None = None,
                 stage_approval_permissions: dict[str, str] | None = None,
                 stage_approvals: dict[str, Any] | None = None,
                 prepare_stage_approval: Callable[..., dict[str, Any]] | None = None,
                 execute_stage_approval: Callable[..., Any] | None = None,
                 complete_stage_approval: Callable[..., bool] | None = None) -> None:
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
        permissions = dict(stage_approval_permissions or {})
        if any(stage not in {"plan", "execute", "verify", "improve"} for stage in permissions):
            raise ValueError("Only plan, execute, verify and improve stages can require approval.")
        if any(not isinstance(scope, str) or scope not in PRIVILEGED for scope in permissions.values()):
            raise ValueError("Workflow stage approvals must use a privileged permission scope.")
        if permissions and checkpoint_store is None:
            raise ValueError("Execution-bound stage approvals require durable workflow checkpoints.")
        if permissions and not all(callable(callback) for callback in (
            prepare_stage_approval, execute_stage_approval, complete_stage_approval
        )):
            raise ValueError("Execution-bound stage approvals require prepare, execute and complete callbacks.")
        self.stage_approval_permissions = permissions
        self.stage_approvals = dict(stage_approvals or {})
        self.prepare_stage_approval = prepare_stage_approval
        self.execute_stage_approval = execute_stage_approval
        self.complete_stage_approval = complete_stage_approval

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

    def _validate_completed_stage_replay(self, workflow_id: str, stage_key: str, acquisition: dict[str, Any]) -> None:
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
            if len(protected) != 1:
                raise WorkflowCheckpointBlocked(f"Completed stage {stage_key} has multiple privileged scopes.")
            execution_id = payload.get("execution_id")
            approval_reference = payload.get("approval_reference")
            get_execution = getattr(self.checkpoint_store, "get_approval_execution_intent", None)
            get_stage = getattr(self.checkpoint_store, "get_workflow_stage_approval_intent", None)
            if not execution_id or not approval_reference or not callable(get_execution) or not callable(get_stage):
                raise WorkflowCheckpointBlocked(
                    f"Completed protected stage {stage_key} lacks durable approval evidence; human review is required."
                )
            execution = get_execution(execution_id)
            stage = get_stage(workflow_id, stage_key)
            if (not isinstance(execution, dict) or not isinstance(stage, dict)
                    or execution.get("state") != "completed" or execution.get("task_id") != task_id
                    or execution.get("permission") != protected[0]
                    or execution.get("workflow_id") != workflow_id or execution.get("stage_key") != stage_key
                    or stage.get("state") != "completed" or stage.get("execution_id") != execution_id
                    or stage.get("task_id") != task_id or stage.get("permission") != protected[0]
                    or stage.get("approval_id") != approval_reference
                    or stage.get("action_digest") != execution.get("action_digest")):
                raise WorkflowCheckpointBlocked(f"Completed protected stage {stage_key} approval binding does not reconcile.")

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
                    protected_permission = self.stage_approval_permissions.get(name)
                    stage_rows = checkpoint_store.list_workflow_stages(workflow_id)
                    existing_stage = next((row for row in stage_rows if row.get("stage_key") == stage_key), None)
                    stage_approval_intent = None
                    stage_approval = None
                    if protected_permission and existing_stage is None:
                        stage_approval_intent = checkpoint_store.get_workflow_stage_approval_intent(workflow_id, stage_key)
                        if stage_approval_intent is None:
                            prepared = self.prepare_stage_approval(workflow_id, stage_key, stage_hash, args, protected_permission)
                            required = ("execution_id", "task_id", "action_digest", "permission")
                            if (not isinstance(prepared, dict)
                                    or any(not isinstance(prepared.get(k), str) or not prepared[k].strip() for k in required)
                                    or prepared["permission"] != protected_permission):
                                raise RuntimeError("Stage approval preparation returned an incomplete binding.")
                            stage_approval_intent = checkpoint_store.create_workflow_stage_approval_intent(
                                workflow_id, stage_key, stage_hash, prepared["execution_id"], prepared["task_id"],
                                prepared["action_digest"], protected_permission
                            )
                            stage_approval_intent = dict(stage_approval_intent)
                            if isinstance(prepared.get("action_details"), dict):
                                stage_approval_intent["action_details"] = prepared["action_details"]
                        elif (stage_approval_intent.get("stage_request_hash") != stage_hash
                              or stage_approval_intent.get("permission") != protected_permission):
                            raise RuntimeError("The prepared approval belongs to different stage inputs.")
                        stage_approval = self.stage_approvals.get(stage_key)
                        if stage_approval is None:
                            pending = {
                                "workflow_id": workflow_id, "stage_key": stage_key,
                                "execution_id": stage_approval_intent["execution_id"],
                                "task_id": stage_approval_intent["task_id"],
                                "action_digest": stage_approval_intent["action_digest"],
                                "permission": protected_permission, "state": stage_approval_intent["state"],
                            }
                            if isinstance(stage_approval_intent.get("action_details"), dict):
                                pending["action_details"] = stage_approval_intent["action_details"]
                            raise WorkflowAwaitingApproval(pending)
                        if (getattr(stage_approval, "action_digest", None) != stage_approval_intent["action_digest"]
                                or protected_permission not in getattr(stage_approval, "approved_permissions", ())
                                or stage_approval_intent.get("state") != "awaiting_approval"):
                            raise RuntimeError("Approval does not match this exact workflow stage digest, permission and state.")
                    attempt_token = uuid.uuid4().hex
                    acquisition = checkpoint_store.begin_workflow_stage(
                        workflow_id, stage_key, stage_index, stage_hash, attempt_token
                    )
                except WorkflowAwaitingApproval:
                    raise
                except Exception as exc:
                    checkpoint_blocked = True
                    raise WorkflowCheckpointBlocked(
                        f"Checkpoint acquisition failed for stage {stage_key}; execution stopped safely."
                    ) from exc

                if acquisition.get("status") == "completed":
                    self._validate_completed_stage_replay(workflow_id, stage_key, acquisition)
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
                        if protected_permission and stage_approval_intent is not None:
                            value = self.execute_stage_approval(
                                workflow_id, stage_key, callback, args, stage_approval_intent, stage_approval
                            )
                            if not self.complete_stage_approval(
                                workflow_id, stage_key, stage_approval_intent, stage_approval, value
                            ):
                                raise RuntimeError("Stage approval completion could not be verified.")
                        else:
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
                        next_state.pop("pending_approval", None)
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
        except WorkflowAwaitingApproval as exc:
            checkpoint_blocked = True
            result.status = "waiting_approval"
            result.pending_approval = dict(exc.pending)
            try:
                current = checkpoint_store.get_workflow_checkpoint(workflow_id)
                if not current or current.get("status") != "running" or not isinstance(current.get("state"), dict):
                    raise RuntimeError("Workflow checkpoint is unavailable while pausing.")
                state = dict(current["state"])
                state["pending_approval"] = dict(exc.pending)
                if not checkpoint_store.save_workflow_checkpoint(
                    workflow_id, int(current["revision"]), "running", exc.pending.get("stage_key"), state
                ):
                    raise RuntimeError("Workflow checkpoint revision changed while recording pending approval.")
            except Exception:
                result.status = "blocked_execution"
                result.pending_approval = None
                result.error = "Approval was prepared, but the workflow pause could not be durably recorded."
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
                    state.pop("pending_approval", None)
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
