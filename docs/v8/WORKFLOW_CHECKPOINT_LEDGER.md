# Workflow checkpoint ledger — foundation increment

**Status:** additive persistence contract integrated with Coordinator.run_lifecycle and the authenticated /v1/lifecycle API. Completed stages replay from stored results; ambiguous in-flight stages fail closed. This is conservative restart recovery, not an exactly-once execution guarantee.

## Why this increment exists

The current V8 coordinator persists task and event records, but a multi-stage workflow keeps its in-progress stage state in process memory. This increment adds a separate checkpoint ledger without changing existing task, event, memory, approval or Creator Studio records.

## New PostgreSQL schema

Migration `004_workflow_checkpoints.sql` adds:

- `workflow_checkpoints`: immutable workflow identity/request hash, checkpoint schema version, optimistic revision, lifecycle status, current stage and serialized state.
- `workflow_stage_checkpoints`: one row per workflow/stage key, unique stage ordering, request hash, attempt token, status, task reference and serialized result.

Both tables are additive. Foreign keys use `ON DELETE RESTRICT`; the migration contains no DROP, TRUNCATE, DELETE, UPDATE of existing application rows or column replacement.

The local SQLite `StateStore` creates matching tables with `CREATE TABLE IF NOT EXISTS`. Existing SQLite records are not copied, rewritten or cleared.

## Store contract

- `create_workflow_checkpoint` is idempotent for the same workflow ID, request hash and checkpoint version. Reusing an ID with a different request hash/version is rejected; existing checkpoint state is never overwritten.
- `begin_workflow_stage` returns `can_execute=true` only for the first insert. A repeated start returns the existing row with `can_execute=false`.
- A stage start that has no completion record is ambiguous. The store deliberately does not grant a second execution token or automatically retry it.
- `complete_workflow_stage` is compare-and-set: only the original attempt token can complete a started stage, and a second completion is rejected.
- `save_workflow_checkpoint` uses an expected revision. Stale writers cannot overwrite a newer checkpoint. Terminal checkpoints cannot be changed through this method.
- Stage and workflow request hashes must be 64-character lowercase SHA-256 hex strings.

## Recovery safety boundary

This ledger is groundwork, not a claim of exactly-once provider execution or full crash recovery. If a process stops after a stage is marked `started` but before its result is committed, the operation may have completed outside the database. That row is therefore ambiguous and must not be replayed automatically. A future resume coordinator must reconcile task state, stage result, idempotency claim and any approval before continuing; if evidence is inconclusive, it must stop for human review.

No provider call, approval consumption, external write, Render restart, Neon migration or production deployment is part of this increment.

## Verification plan

The new deterministic SQLite tests verify restart persistence, idempotent stage acquisition, token-bound completion, optimistic revision conflict, request-hash mismatch rejection and preservation of pre-existing task/memory/event records. A PostgreSQL integration test runs against the existing ephemeral PostgreSQL CI service after the migration runner applies all sorted migrations.

The populated Neon project remains read-only until a current backup/export and independent restore/read-back path are verified.


## Lifecycle integration — 2026-11-12

- Coordinator.run_lifecycle now creates a checkpoint by default in the already-configured SQLite or PostgreSQL store.
- The workflow ID is returned in the existing lifecycle result. The authenticated /v1/lifecycle endpoint accepts an optional workflow_id (maximum 128 characters); resubmitting the same ID and identical request/configuration replays completed stages and returns a terminal result without repeating provider calls.
- The checkpoint identity binds the original request, selected provider route, correction/improvement limits and per-stage deadline. Reusing an ID for a different identity is rejected.
- Stage keys are deterministic within a workflow (0001:plan, 0002:execute, and so on). Each stage hash also binds its arguments. Completed stage values are restored and local coordinator context is rehydrated before later stages continue.
- A stage still marked started is never re-executed. The lifecycle returns blocked_execution, does not run later stages or learning, and leaves the checkpoint in running for explicit reconciliation.
- A terminal result is persisted as completed or blocked; repeat submissions return the stored result without running stage callbacks.

### Remaining recovery boundary

The coordinator does not yet automatically reconcile an ambiguous stage with its related task row, provider idempotency record, or external approval/action state. If a process stops after a stage begins but before the stage result is committed, an operator must inspect the task/event evidence before any future reconciliation mechanism can safely release it. No automatic lease expiry, stale-stage takeover or exactly-once external side effect is claimed.

## Storage-instance restart regression coverage — 2026-11-13

Two additional lifecycle regressions now exercise the checkpointed runner through a fresh SQLite `StateStore` instance over the same persisted database file:

- A completed plan stage is restored after reopening; only remaining stages execute, and delivery/learning each occur once.
- A stage left in `started` remains ambiguous after reopening; the runner blocks before invoking any stage callback and leaves the checkpoint unchanged.

This verifies storage persistence across a new runtime storage instance. It is not yet an OS-level process-kill test, a PostgreSQL multi-process race test, or proof of exactly-once external execution. Ambiguous external side effects continue to fail closed pending task/idempotency/approval reconciliation.


## Completed-stage task reconciliation — 2026-11-14

Before a persisted completed stage is reused, the runner now performs read-only checks when the stage carries a task reference:

- The referenced task row must exist, remain in \`completed\` state, and contain a parseable result bound to the same task and agent.
- If the task has an idempotency key, the store must expose a matching claim in \`completed\` state. Its task ID, reconstructed request hash and decoded result must match the persisted task.
- If the task requested a privileged permission, replay stops for human review. The current one-use approval ledger records approval ID and action digest separately; no durable task/stage reference exists to prove which approval authorized this task.
- Missing lookups, malformed records, stale claims and mismatches fail closed. No task, claim, approval or checkpoint row is changed by this preflight.

SQLite and PostgreSQL expose the same read-only \`get_idempotency_claim\` contract. No schema migration or production database access is required for this increment.

This guard reconciles completed stages that have a task reference; it does not release \`started\` stages. Those remain blocked because the task reference may not have been committed before interruption. Stages without a task reference cannot be cross-checked against the task ledger. OS-level process termination, approval-to-stage linkage, PostgreSQL multi-process crash recovery and exactly-once external effects remain open release requirements.
