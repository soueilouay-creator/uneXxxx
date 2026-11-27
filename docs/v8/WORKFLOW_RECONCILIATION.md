# Workflow reconciliation — audited manual-review block

**Status:** additive store transition implemented; not exposed through the HTTP API, CLI, scheduler or Studio UI.  
**Date:** 2026-11-27  
**Owner:** uneXpected V8 workflow control plane

## Safety boundary

A persisted workflow stage marked `started` is ambiguous after interruption. The external operation may have completed even if the workflow ledger did not commit its result. Automatic replay remains forbidden.

`StateStore.record_workflow_reconciliation_block(...)` and its PostgreSQL counterpart perform one narrow operation:

1. Verify the exact checkpoint revision and stage identity.
2. Verify the persisted stage is still `started`, including its stage index, request hash and attempt-token fingerprint.
3. Change that stage from `started` to `interrupted`, preserving its original attempt token and result fields.
4. Change the parent checkpoint from `running` or `interrupted` to `blocked`, incrementing its revision exactly once.
5. Append an immutable audit event in the same database transaction.

The operation does **not** resume a workflow, requeue a task, execute a callback, consume an approval, change an idempotency claim, add a task result, or assert that an external effect succeeded or failed.

The stage row is locked before the checkpoint row in PostgreSQL. This prevents a late `complete_workflow_stage` update from completing a stage after the manual-review block wins. SQLite uses `BEGIN IMMEDIATE` to serialize writers. Both backends use a checkpoint revision compare-and-set and a stage fingerprint check.

## Required request binding

- Stable `reconciliation_id` (idempotency key)
- Exact `workflow_id` and `stage_key`
- Expected checkpoint revision
- Expected stage index and stage request hash
- SHA-256 fingerprint of the stored attempt token
- Operator identifier and bounded reason code
- Opaque evidence reference and SHA-256 digest of separately retained evidence

The attempt-token digest is an identity fingerprint only. It is not the token, a credential, or authorization to execute anything. Evidence contents are not copied into the workflow database. Evidence references cannot contain query or fragment data.

## Outcomes

| Result | Meaning |
|---|---|
| `recorded=true` | Stage is now `interrupted`, checkpoint is now `blocked`, and the audit row was read back in the same transaction |
| `idempotent_replay=true` | The same reconciliation ID and exact immutable request were already recorded; no state changed |
| `recorded=false` | Checkpoint revision, stage status, stage identity or attempt fingerprint was stale or mismatched |
| `ValueError` | Invalid input or an existing reconciliation ID was reused with different immutable evidence |

Only these reason codes are accepted: `uncertain_external_effect`, `evidence_conflict`, and `operator_hold`.

## Append-only audit ledger

Migration `008_workflow_reconciliation_events.sql` adds the PostgreSQL ledger. SQLite adds the same table during its existing idempotent store initialization. The table references the original workflow and stage with `ON DELETE RESTRICT`, records before/after revisions and statuses, and has unique reconciliation IDs plus a unique workflow/stage/revision transition key.

Database triggers reject event updates and deletes. `list_workflow_reconciliation_events()` is read-only. No existing task, workflow, approval, memory or event row is rewritten by the migration.

## Operator and process boundary

- The store API records the supplied operator identifier but does not authenticate it. The method is deliberately not wired to an HTTP route. Any future API exposure must authenticate the operator, enforce role/scope, require explicit human confirmation and write a protected-action audit event before invoking this method.
- The operator must independently establish that the original worker is stopped or isolated before blocking. This transition cannot terminate a process or cancel an external request already accepted by another system.
- After blocking, an operator must inspect authoritative provider/tool receipts. Unknown or conflicting external outcomes remain blocked. No new workflow ID or approval may be used to bypass the original checkpoint.
- This is not a completed-effect reconciliation. A later feature would need separate evidence validation and an explicit, reviewed path for recording a confirmed external result without replay.

## Verification

CI exercises SQLite and PostgreSQL 16/17 with synthetic records only: compare-and-set, stale revision rejection, stage fingerprint mismatch, duplicate-event idempotency, concurrent operators, immutable-event triggers, transaction rollback on audit insertion failure, and read-back after reopening the store.

No hosted database migration or live user-data operation is part of this increment.
