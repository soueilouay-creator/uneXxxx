# Workflow recovery inspection — read-only foundation

**Status:** implemented as an additive diagnostic helper; not exposed as an HTTP route, CLI command, or automatic recovery action.

## Purpose

A persisted workflow stage marked **started** is ambiguous after process interruption. The external operation may have completed even though its result was not committed to the workflow ledger. Re-running its callback could duplicate an external side effect.

**unexpected_runtime.recovery_inspection.inspect_workflow_recovery(store, workflow_id)** provides a sanitized, read-only snapshot of:

- workflow checkpoint status, revision, current stage and checkpoint version;
- stage keys, indexes, statuses, linked task IDs/statuses, result presence and whether an attempt token exists;
- any stage approval intent associated with a persisted stage or the checkpoint's current stage;
- whether the approval execution intent still matches the immutable task, action digest, permission, workflow and stage binding.

It deliberately omits task payloads, task results, provider prompts, credentials and raw attempt tokens.

## Dispositions

| Disposition | Meaning |
|---|---|
| **not_found** | No checkpoint exists for the requested workflow ID. |
| **manual_review_required** | A stage is still **started**, evidence is inconsistent/unavailable, or a persisted state is unsupported. |
| **awaiting_human_approval** | A matching stage approval and execution intent are both awaiting approval. No stage callback has been authorized by this report. |
| **terminal_no_automatic_resume** | The checkpoint is completed, blocked or interrupted. |
| **runner_resume_requires_integrity_validation** | The checkpoint is running without an observed ambiguous stage; the normal runner must still perform its own hash, task, idempotency and approval checks. |

Every report has **automatic_replay_permitted: false** and **inspection_is_authorization: false**. The helper is not an approval verifier and cannot change workflow state.

## Operator handling of an interrupted stage

1. Stop any operator-initiated retry. Do not create a replacement workflow ID to bypass the original checkpoint.
2. Read the checkpoint and stage report. Record the workflow ID, checkpoint revision, stage key/index, request hash from the authoritative store, and whether a task or approval reference exists. The helper does not expose the raw attempt token.
3. Independently inspect the linked task, idempotency claim, provider/tool request identifier and the external system's authoritative audit/result record. Treat missing or conflicting evidence as unknown.
4. Classify the external effect only when evidence is authoritative:
   - **Unknown:** keep the workflow blocked for human review. Do not replay.
   - **Definitely completed:** preserve the external result and its provider/tool receipt; require matching task, idempotency and approval bindings before any future ledger reconciliation.
   - **Definitely not accepted:** retain evidence that the external system did not accept the operation. This alone does not currently release the started stage.
5. For a protected action, verify the original one-use approval is bound to the exact execution ID, task ID, action digest, permission, workflow ID and stage key. A new approval does not retroactively authorize an already attempted operation.
6. Do not edit rows manually, change the attempt token, expire a lease, clear a stage, mark it completed, or requeue the task. The current store contract has no supported operator reconciliation transition for **started** stages.
7. Keep the workflow blocked until a separately reviewed reconciliation API and immutable audit record exist.

## Current implementation boundary

- The helper performs only reads through the existing **StateStore** / **PostgresStateStore** contracts.
- It is not wired to the HTTP API, browser UI, scheduler or worker.
- It does not make a recovery decision, authorize a callback, consume an approval, or modify a checkpoint, task, idempotency claim or memory record.
- A report of **runner_resume_requires_integrity_validation** is not permission to bypass the runner's existing validation.
- No SQL repair, production database access, migration or hosted service action is included.

## Required next design before a write-capable reconciliation API

A future increment must define an additive, append-only reconciliation record and a transactionally revision-checked transition. It must bind the operator identity, exact workflow/stage identity, checkpoint and stage revisions, original attempt identity, external evidence reference, task/idempotency state, approval binding and selected disposition. It must reject stale revisions and duplicate reconciliation IDs, preserve the original stage/attempt history, and prove SQLite/PostgreSQL parity, concurrent operator races, rollback and old-record read-back.

No schema or transition is introduced by this inspection-only increment. Production recovery remains blocked for ambiguous started stages.
