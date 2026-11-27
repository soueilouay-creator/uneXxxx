"""Read-only inspection of persisted workflow recovery state.

This module deliberately does not release, retry, mutate, or authorize a workflow.
"""
from __future__ import annotations

from typing import Any

from .workflow_reconciliation import attempt_token_sha256


SCHEMA = "uneXpected.workflow-recovery-inspection/v1"


def inspect_workflow_recovery(store: Any, workflow_id: str) -> dict[str, Any]:
    """Return a sanitized, read-only view of checkpoint and approval evidence.

    A report is diagnostic only. automatic_replay_permitted is always false:
    only the workflow runner and a future separately approved reconciliation
    operation may decide whether execution can continue.
    """
    if not isinstance(workflow_id, str) or not workflow_id.strip():
        raise ValueError("workflow_id must be a non-empty string.")

    get_checkpoint = getattr(store, "get_workflow_checkpoint", None)
    list_stages = getattr(store, "list_workflow_stages", None)
    if not callable(get_checkpoint) or not callable(list_stages):
        raise TypeError("The store does not expose the workflow checkpoint read contract.")

    try:
        checkpoint = get_checkpoint(workflow_id)
    except Exception:
        raise RuntimeError("Workflow checkpoint inspection failed; no recovery decision was made.") from None

    if checkpoint is None:
        return {
            "schema": SCHEMA,
            "workflow_id": workflow_id,
            "disposition": "not_found",
            "automatic_replay_permitted": False,
            "inspection_is_authorization": False,
            "checkpoint": None,
            "stages": [],
            "approval_intents": [],
            "findings": [{"code": "workflow_not_found", "message": "No workflow checkpoint exists for this ID."}],
        }
    if not isinstance(checkpoint, dict):
        raise RuntimeError("Workflow checkpoint inspection returned an invalid record.")

    try:
        stage_rows = list_stages(workflow_id)
    except Exception:
        raise RuntimeError("Workflow stage inspection failed; no recovery decision was made.") from None
    if not isinstance(stage_rows, list) or any(not isinstance(item, dict) for item in stage_rows):
        raise RuntimeError("Workflow stage inspection returned an invalid collection.")

    findings: list[dict[str, str]] = []
    stages: list[dict[str, Any]] = []
    approval_intents: list[dict[str, Any]] = []
    evidence_conflict = False
    ambiguous_started_stage = False
    awaiting_human_approval = False

    get_task = getattr(store, "get_task", None)
    for row in stage_rows:
        stage_key = row.get("stage_key")
        status = row.get("status")
        task_id = row.get("task_id")
        if not isinstance(stage_key, str) or not stage_key.strip():
            evidence_conflict = True
            findings.append({
                "code": "malformed_stage_identity",
                "message": "A persisted stage has no valid stage key.",
            })
            stage_key = None

        task_status = None
        if task_id is not None:
            if not isinstance(task_id, str) or not task_id.strip():
                evidence_conflict = True
                task_status = "malformed_reference"
                findings.append({
                    "code": "malformed_task_reference",
                    "message": "A workflow stage contains a malformed task reference.",
                })
            elif not callable(get_task):
                task_status = "lookup_unavailable"
                findings.append({
                    "code": "task_lookup_unavailable",
                    "message": "The store cannot verify the linked task record.",
                })
                if status == "completed":
                    evidence_conflict = True
            else:
                try:
                    task = get_task(task_id)
                except Exception:
                    task = None
                    task_status = "lookup_failed"
                    findings.append({
                        "code": "task_lookup_failed",
                        "message": "The linked task could not be read; human review is required.",
                    })
                    evidence_conflict = True
                else:
                    if not isinstance(task, dict) or task.get("task_id") != task_id:
                        task_status = "missing"
                        findings.append({
                            "code": "task_reference_missing",
                            "message": "The linked task record is missing or does not match its ID.",
                        })
                        if status == "completed":
                            evidence_conflict = True
                    else:
                        value = task.get("status")
                        task_status = value if isinstance(value, str) else "unknown"
                        if status == "completed" and task_status != "completed":
                            evidence_conflict = True
                            findings.append({
                                "code": "completed_stage_task_not_completed",
                                "message": "A completed stage references a task that is not completed.",
                            })

        if status == "started":
            ambiguous_started_stage = True
            findings.append({
                "code": "ambiguous_started_stage",
                "message": "The stage may have caused an external effect; automatic replay is forbidden.",
            })
        elif status in {"interrupted", "failed"}:
            ambiguous_started_stage = True
            findings.append({
                "code": "interrupted_or_failed_stage",
                "message": "The stage requires explicit review and cannot be replayed automatically.",
            })
        elif status != "completed":
            evidence_conflict = True
            findings.append({
                "code": "unknown_stage_state",
                "message": "The stage has an unsupported persisted state.",
            })

        stages.append({
            "stage_key": stage_key,
            "stage_index": row.get("stage_index"),
            "status": status if isinstance(status, str) else "unknown",
            "task_id": task_id if isinstance(task_id, str) else None,
            "task_status": task_status,
            "stage_request_hash": row.get("request_hash") if isinstance(row.get("request_hash"), str) else None,
            "result_present": row.get("result") is not None,
            "attempt_token_present": bool(row.get("attempt_token")),
            "attempt_token_sha256": (
                attempt_token_sha256(row["attempt_token"])
                if isinstance(row.get("attempt_token"), str) and row["attempt_token"] else None
            ),
        })

    stage_keys = [item["stage_key"] for item in stages if item.get("stage_key")]
    current_stage = checkpoint.get("current_stage")
    if isinstance(current_stage, str) and current_stage.strip():
        stage_keys.append(current_stage)
    stage_keys = list(dict.fromkeys(stage_keys))

    get_stage_approval = getattr(store, "get_workflow_stage_approval_intent", None)
    get_execution_intent = getattr(store, "get_approval_execution_intent", None)
    for stage_key in stage_keys:
        if not callable(get_stage_approval):
            continue
        try:
            intent = get_stage_approval(workflow_id, stage_key)
        except Exception:
            evidence_conflict = True
            findings.append({
                "code": "stage_approval_lookup_failed",
                "message": "A stage approval record could not be read; human review is required.",
            })
            continue
        if not isinstance(intent, dict):
            continue

        execution_state = None
        execution = None
        execution_id = intent.get("execution_id")
        if not isinstance(execution_id, str) or not execution_id.strip() or not callable(get_execution_intent):
            evidence_conflict = True
            findings.append({
                "code": "approval_execution_lookup_unavailable",
                "message": "A stage approval has no verifiable execution-intent lookup.",
            })
        else:
            try:
                execution = get_execution_intent(execution_id)
            except Exception:
                execution = None
                evidence_conflict = True
                findings.append({
                    "code": "approval_execution_lookup_failed",
                    "message": "The linked approval execution intent could not be read.",
                })
            if not isinstance(execution, dict):
                evidence_conflict = True
                findings.append({
                    "code": "approval_execution_missing",
                    "message": "The stage approval references a missing execution intent.",
                })
            else:
                execution_state = execution.get("state")
                for field in ("task_id", "action_digest", "permission", "workflow_id", "stage_key"):
                    if execution.get(field) != intent.get(field):
                        evidence_conflict = True
                        findings.append({
                            "code": "approval_execution_binding_mismatch",
                            "message": "The stage approval and execution intent do not share the same immutable binding.",
                        })
                        break
                if execution_state != intent.get("state"):
                    evidence_conflict = True
                    findings.append({
                        "code": "approval_execution_state_mismatch",
                        "message": "The stage approval and execution intent states do not match.",
                    })

        intent_state = intent.get("state")
        if intent_state == "awaiting_approval":
            awaiting_human_approval = True
        elif intent_state not in {"approved", "enqueued", "completed", "blocked"}:
            evidence_conflict = True
            findings.append({
                "code": "unknown_approval_state",
                "message": "The stage approval has an unsupported state.",
            })
        if intent_state == "approved" and not (
            isinstance(intent.get("approval_id"), str) and intent["approval_id"].strip()
        ):
            evidence_conflict = True
            findings.append({
                "code": "approved_intent_missing_approval_id",
                "message": "An approved stage intent has no persisted approval reference.",
            })

        approval_intents.append({
            "stage_key": stage_key,
            "state": intent_state if isinstance(intent_state, str) else "unknown",
            "revision": intent.get("revision"),
            "execution_id": execution_id if isinstance(execution_id, str) else None,
            "task_id": intent.get("task_id") if isinstance(intent.get("task_id"), str) else None,
            "approval_id": intent.get("approval_id") if isinstance(intent.get("approval_id"), str) else None,
            "execution_state": execution_state if isinstance(execution_state, str) else None,
        })

    checkpoint_status = checkpoint.get("status")
    if evidence_conflict or ambiguous_started_stage:
        disposition = "manual_review_required"
    elif awaiting_human_approval:
        disposition = "awaiting_human_approval"
    elif checkpoint_status in {"completed", "blocked", "interrupted"}:
        disposition = "terminal_no_automatic_resume"
    elif checkpoint_status == "running":
        disposition = "runner_resume_requires_integrity_validation"
    else:
        disposition = "manual_review_required"
        findings.append({
            "code": "unknown_checkpoint_state",
            "message": "The workflow checkpoint has an unsupported lifecycle state.",
        })

    return {
        "schema": SCHEMA,
        "workflow_id": workflow_id,
        "disposition": disposition,
        "automatic_replay_permitted": False,
        "inspection_is_authorization": False,
        "checkpoint": {
            "status": checkpoint_status if isinstance(checkpoint_status, str) else "unknown",
            "revision": checkpoint.get("revision"),
            "current_stage": current_stage if isinstance(current_stage, str) else None,
            "checkpoint_version": checkpoint.get("checkpoint_version"),
        },
        "stages": stages,
        "approval_intents": approval_intents,
        "findings": findings,
    }
