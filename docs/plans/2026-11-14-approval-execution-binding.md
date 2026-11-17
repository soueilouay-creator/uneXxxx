# Approval Execution Binding Implementation Plan

> **For agentic workers:** Use the host's available task-by-task implementation workflow. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every newly authorized privileged operation provably belong to one immutable task or workflow-stage execution, and make recovery verify that exact relationship before reusing any completed result.

**Architecture:** Introduce a durable execution intent before requesting approval, so the task identity and canonical action digest exist before the approval is consumed. Extend the existing one-use approval ledger with a separate, additive binding record written in the same ledger transaction as consumption; persist the same reference in task and workflow-stage records. Keep old unbound approvals retained, but never treat them as valid evidence for new privileged execution or recovery.

**Tech Stack:** Existing Python runtime, SQLite `StateStore`, PostgreSQL `PostgresStateStore`, GitHub pull-request approval workflow, existing unittest suite and ephemeral PostgreSQL CI service. No new dependencies.

## Global Constraints

- Preserve all existing task, event, memory, approval, Creator Studio, PWA, user and deployment data. Add tables and optional fields only; do not rewrite, drop, truncate or backfill existing approval rows.
- Keep the `consumed_approvals` one-use invariant. A single approval ID can be consumed only once, and the action digest must match exactly.
- No privileged action may run from caller-asserted identity alone. The GitHub verifier remains the trust authority; ledger writes are fail-closed.
- No automatic replay of an ambiguous external side effect. Missing, malformed, stale, mismatched or unavailable evidence blocks execution/recovery and requires a new approval or human review.
- Existing unbound consumed approvals remain unchanged. They cannot be retroactively attached to a task or stage.
- SQLite approval-ledger persistence and application StateStore are currently separate files; the design must not assume a cross-file atomic transaction. A consumed approval that is not followed by its matching task is safely lost and must not be rebound to another task.
- PostgreSQL approval consumption and binding rows must be written in one transaction. Rollback must leave neither row if either insert fails.
- Do not run a production migration, deploy, restart a service, call a live provider, send messages, publish content or incur a charge. Use deterministic mocks and ephemeral CI databases.
- Keep the current branch and draft PR workflow. No force push, merge, or production change.

---

## Repository findings and design decisions

The following are observed in the current branch:

- `unexpected_runtime/coordinator.py`: `Coordinator.invoke` calls `PermissionPolicy.authorize` before it creates the `TaskRequest`; therefore the current verifier has no stable task identifier to bind.
- `unexpected_runtime/permissions.py`: privileged authorization requires a host verifier and canonical action digest, but the verifier interface has no execution-binding argument.
- `unexpected_runtime/approvals.py`: the GitHub verifier checks the immutable request document, review on the exact PR head, trusted admin, freshness and action digest. Its SQLite one-use ledger stores only approval ID, digest and consumed time.
- `unexpected_runtime/postgres_approval_ledger.py` and `migrations/001_initial.sql`: PostgreSQL has the matching one-use `consumed_approvals` table and atomic insert, but no task/workflow binding.
- `unexpected_runtime/workflow.py`: a stage is marked `started` before its callback; callback failure leaves an ambiguous started stage. Completed-stage reconciliation currently blocks tasks with privileged scopes because approval linkage is absent.
- `.github/workflows/request-approval.yml`: approval requests accept canonical action-details JSON and a digest, but do not require a stable execution identity.
- `unexpected_runtime/http_api.py`: the public invocation endpoints currently reject privileged approval fields; they do not expose a prepare-then-authorize flow.

Design choices:

1. Add a stable `execution_id` and preallocated `task_id` before approval is requested. The approval digest covers the exact task identity and optional workflow-stage identity, not just the operation description.
2. Represent the immutable binding as `ApprovalExecutionBinding(execution_id, task_id, workflow_id=None, stage_key=None)`. Workflow ID and stage key must either both be present or both be absent.
3. Add an `approval_execution_bindings` table rather than changing the existing `consumed_approvals` table. The new row is keyed by approval ID and has unique execution and task identities.
4. Add a persisted approval-intent record in the application StateStore. It owns the preallocated task ID, request hash, action digest, permission, optional workflow-stage identity and state transitions. The intent is never silently reused for a different request.
5. For SQLite, consume and bind within the existing approval-ledger SQLite file. Because the application task database is a separate file, a crash after approval consumption but before task enqueue leaves a consumed approval attached to its intent; that intent is blocked and a fresh approval is required. Never transfer the approval to a new task.
6. For PostgreSQL, insert the consumed approval and its execution binding in one database transaction. Application task persistence remains a separate transaction; recovery must reconcile both records by exact identity.
7. Keep direct task authorization and workflow-stage pause/resume as separate deliverables. A lifecycle stage must be explicitly waiting for approval before it can resume; it must never be mistaken for a started external operation.

## Task 1: Durable execution intent and immutable task identity

**Files:**
- Modify: `unexpected_runtime/models.py`
- Modify: `unexpected_runtime/storage.py`
- Modify: `unexpected_runtime/postgres_storage.py`
- Create: `migrations/005_approval_execution_intents.sql`
- Test: `tests/test_approval_execution_intents.py`
- Test: `tests/test_postgres_approval_execution_intents.py`

**Interfaces:**
- Add `ApprovalExecutionBinding(execution_id: str, task_id: str, workflow_id: str | None = None, stage_key: str | None = None)`.
- Add StateStore and PostgresStateStore parity methods:
  - `create_approval_execution_intent(intent_id, task_id, request_hash, action_digest, permission, workflow_id=None, stage_key=None)`
  - `get_approval_execution_intent(intent_id)`
  - `transition_approval_execution_intent(intent_id, expected_state, new_state, expected_revision)`
- Persist intent states `prepared`, `awaiting_approval`, `approved`, `enqueued`, `completed` and `blocked`, with revision-checked transitions. Allowed transitions are `prepared -> awaiting_approval -> approved -> enqueued -> completed`; any nonterminal state may transition to `blocked`, and no terminal state may be reopened.
- Store the canonical request hash and action digest. Reusing an intent ID with a different task ID, request hash, action digest, permission or workflow-stage identity must reject without modifying the original row.

- [ ] **Step 1: Add the focused failing tests**

Test SQLite create/read/reopen, revision conflict, illegal transition, duplicate intent with identical data, and duplicate intent with one changed field. Test that a blocked or completed intent cannot be reopened. Test invalid workflow binding where only one of workflow ID and stage key is present.

- [ ] **Step 2: Verify the relevant failure**

Run: `python -m unittest tests.test_approval_execution_intents -v`

Expected: import or missing-method failures that identify the absent intent contract; no setup error.

- [ ] **Step 3: Implement the minimum behavior**

Create migration 005 with a new `approval_execution_intents` table and indexes. Use `CREATE TABLE IF NOT EXISTS` for SQLite. Use compare-and-set updates with the expected revision and state. Do not modify existing task, approval or checkpoint rows. Enforce the same value and transition contract in both adapters.

- [ ] **Step 4: Verify the focused pass**

Run: `python -m unittest tests.test_approval_execution_intents -v`

Expected: all focused SQLite intent tests pass, including reopen and conflict cases.

- [ ] **Step 5: Run the PostgreSQL integration check**

Run: `python -m unittest tests.test_postgres_approval_execution_intents -v` with `TEST_POSTGRES_DSN` pointed only at an ephemeral PostgreSQL 16 database after migrations 001–005.

Expected: create/read/reopen and separate-connection revision races pass; no production DSN is used.

- [ ] **Step 6: Commit the passing deliverable**

Commit message: `feat(v8): add durable approval execution intents`.

## Task 2: Bind one-use approval consumption to the intent

**Files:**
- Modify: `unexpected_runtime/approvals.py`
- Modify: `unexpected_runtime/postgres_approval_ledger.py`
- Create: `migrations/006_approval_execution_bindings.sql`
- Modify: `tests/test_github_approval.py`
- Modify: `tests/test_postgres_approval_ledger.py`
- Create: `tests/test_approval_execution_binding.py`

**Interfaces:**
- Extend the ledger contract with:
  - `consume_once_bound(approval_id, action_digest, permission, binding) -> bool`
  - `get_consumed_binding(approval_id) -> dict | None`
- Add a bound verifier entry point:
  - `verify_bound(approval, permission, action_digest, binding) -> bool`
- Keep legacy `verify` and `consume_once` methods for compatibility with existing stored approval behavior, but do not use them to authorize a new execution intent.
- Persist approval ID, action digest, permission, execution ID, task ID, optional workflow ID, optional stage key and consumed time in the binding record.

- [ ] **Step 1: Add the focused failing tests**

Test that two concurrent consumers of one approval ID produce exactly one winner; that a second execution ID or task ID cannot reuse it; that a valid approval bound to execution A cannot authorize execution B, another workflow ID, another stage key or a changed action digest; that a ledger/database failure denies authorization; and that legacy unbound rows are retained but return no bound reference.

- [ ] **Step 2: Verify the relevant failure**

Run: `python -m unittest tests.test_approval_execution_binding tests.test_postgres_approval_ledger -v`

Expected: bound methods are absent and the focused assertions fail for that reason.

- [ ] **Step 3: Implement the minimum behavior**

Add migration 006 with a separate `approval_execution_bindings` table. Keep `consumed_approvals` unchanged. The PostgreSQL adapter must insert the consumed row and binding row using one connection/transaction; conflict or either insert failure rolls back both. The SQLite verifier must use one transaction in its existing approval-ledger file for the same two inserts. Never catch a failed database insert and return success. Implement read-only binding lookup for recovery.

- [ ] **Step 4: Verify the focused pass**

Run: `python -m unittest tests.test_approval_execution_binding tests.test_postgres_approval_ledger -v`

Expected: single-use, exact-binding, rollback and concurrency tests pass. At most one process wins consumption for a given approval ID.

- [ ] **Step 5: Verify existing approval behavior**

Run: `python -m unittest tests.test_github_approval tests.test_approvals -v`

Expected: all existing trust, freshness, reviewer, exact-head and one-use tests remain green. Existing legacy records remain untouched.

- [ ] **Step 6: Commit the passing deliverable**

Commit message: `feat(v8): bind consumed approvals to execution intents`.

## Task 3: Authorize and enqueue only the prepared task

**Files:**
- Modify: `unexpected_runtime/permissions.py`
- Modify: `unexpected_runtime/coordinator.py`
- Modify: `unexpected_runtime/models.py`
- Modify: `unexpected_runtime/http_api.py`
- Modify: `.github/workflows/request-approval.yml`
- Modify: `tests/test_approvals.py`
- Modify: `tests/test_command_center_api.py`
- Modify: `tests/test_github_approval.py`

**Interfaces:**
- Add `Coordinator.prepare_invoke(..., workflow_id=None, stage_key=None) -> dict`; it validates the same request fields as `invoke`, allocates and persists a stable task/intent ID, then returns only the execution ID, task ID, permission, canonical action details and digest. It must not call a provider or enqueue a task.
- Extend `Coordinator.invoke(..., execution_id=None, approval=None)`. For a privileged scope, require a matching prepared intent and `ApprovalExecutionBinding`; load the intent, recompute request hash/action digest, verify the host approval, consume it with the exact binding, and enqueue only the task ID from the intent.
- Add an authenticated `POST /v1/approval-intents` route for preparing an intent. Extend `POST /v1/invoke` with only `execution_id` and the documented structured approval fields; all other unknown fields remain rejected.
- The request-approval GitHub workflow must require the immutable execution binding in `action_details_json`; the verifier compares it with the binding supplied by the caller before consuming. The PR file continues to be immutable and the review must target its exact head commit.
- Non-privileged `/v1/invoke` requests retain the current request contract and do not need an approval intent.

- [ ] **Step 1: Add the focused failing tests**

Test prepare-only behavior (no task row, provider call or external side effect), task ID stability between prepare and invoke, exact request/digest matching, missing approval, forged approver, wrong intent, wrong task ID, changed workflow/stage binding, replay of an already consumed approval, and unknown API fields. Test that a consumed approval with no matching task remains blocked and cannot be rebound.

- [ ] **Step 2: Verify the relevant failure**

Run: `python -m unittest tests.test_approvals tests.test_command_center_api tests.test_github_approval -v`

Expected: missing prepare route/interface or missing exact-binding assertion failures; no unrelated setup failures.

- [ ] **Step 3: Implement the minimum behavior**

Generate the task ID before authorization. Include execution ID, task ID and optional workflow/stage identity in canonical action details before computing the digest. Store a non-secret approval reference on the exact task payload. Do not expose approval tokens or GitHub credentials. After successful bound consumption, compare-and-set the intent to `approved`, persist the task with that task ID, then move the intent to `enqueued`. If the process stops between approval consumption and task enqueue, leave the intent blocked and require a new intent and approval; do not reclaim the consumed approval.

- [ ] **Step 4: Verify the focused pass**

Run: `python -m unittest tests.test_approvals tests.test_command_center_api tests.test_github_approval -v`

Expected: the prepared task can be enqueued only once with the exact approved action and identity; all negative cases fail closed.

- [ ] **Step 5: Run the task and MCP regression suites**

Run: `python -m unittest tests.test_runtime tests.test_gateway_integration tests.test_mcp_gateway -v`

Expected: ordinary task execution and existing permission boundaries remain green; privileged invocations without a bound host approval remain denied.

- [ ] **Step 6: Commit the passing deliverable**

Commit message: `feat(v8): require bound approval for privileged invocation`.

## Task 4: Make workflow-stage approval a resumable, non-ambiguous state

**Files:**
- Modify: `unexpected_runtime/workflow.py`
- Modify: `unexpected_runtime/coordinator.py`
- Modify: `unexpected_runtime/storage.py`
- Modify: `unexpected_runtime/postgres_storage.py`
- Create: `migrations/007_workflow_stage_approval_intents.sql`
- Modify: `unexpected_runtime/http_api.py`
- Modify: `tests/test_workflow_recovery.py`
- Create: `tests/test_workflow_approval_recovery.py`
- Modify: `docs/v8/WORKFLOW_CHECKPOINT_LEDGER.md`

**Interfaces:**
- Add a separate stage-approval intent keyed by workflow ID and stable stage key, with stage request hash, execution ID, task ID, action digest, approval ID and state. Do not overload the current `started` status to mean “waiting for a human”.
- Add an explicit `waiting_approval` workflow result. A missing approval must return this result before a task/provider/tool callback starts.
- On resume, accept only the same workflow ID, stage key, stage request hash and execution ID, and only after the ledger returns the exact consumed binding and task/claim records agree.
- If a stage is already `started` without the dedicated waiting-approval intent, it remains ambiguous and blocked. Never infer that it is merely waiting for approval.
- For task execution that already began, apply the existing task/idempotency reconciliation rules. Missing or inconclusive evidence remains blocked.

- [ ] **Step 1: Add the focused failing tests**

Test that an unapproved stage returns `waiting_approval` without invoking the callback; that a valid approval resumes only the same workflow/stage/task identity; that a changed stage request, workflow ID, task ID, stage key or digest is rejected; that a pre-existing ambiguous `started` stage remains blocked; and that process termination at each boundary (before consumption, after consumption, after task enqueue and after task completion) never triggers duplicate provider/tool execution.

- [ ] **Step 2: Verify the relevant failure**

Run: `python -m unittest tests.test_workflow_approval_recovery tests.test_workflow_recovery -v`

Expected: missing waiting-approval state/interface or exact-binding assertions fail; existing ambiguous-stage tests remain green.

- [ ] **Step 3: Implement the minimum behavior**

Introduce a separate additive workflow-stage approval-intent table and compare-and-set transitions. Refactor `WorkflowRunner` so explicit approval preflight is resolved before an actual stage callback is considered executable. Keep existing stage checkpoint `started` semantics for operations that may have begun. Persist stage/task references before dispatch and never replay a stage that may already have caused an external side effect.

- [ ] **Step 4: Verify the focused pass**

Run: `python -m unittest tests.test_workflow_approval_recovery tests.test_workflow_recovery tests.test_workflow_process_recovery -v`

Expected: waiting/resume cases pass and every ambiguous process-exit case stays blocked without duplicate callbacks.

- [ ] **Step 5: Run lifecycle and API regression suites**

Run: `python -m unittest tests.test_workflow_lifecycle tests.test_command_center_api tests.test_postgres_storage -v`

Expected: existing completed-stage replay, terminal-result and authenticated API behavior remain green; old clients still work without approval fields.

- [ ] **Step 6: Commit the passing deliverable**

Commit message: `feat(v8): add explicit workflow approval pause and resume`.

## Task 5: Verify PostgreSQL concurrency and end-to-end recovery

**Files:**
- Modify: `tests/test_postgres_approval_ledger.py`
- Modify: `tests/test_postgres_storage.py`
- Modify: `tests/test_postgres_integration.py`
- Modify: `tests/test_workflow_approval_recovery.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/v8/WORKFLOW_CHECKPOINT_LEDGER.md`
- Modify: `docs/v8/RUN_LOG.md`
- Modify: `FILE_INVENTORY_SHA256.txt`

**Interfaces:**
- Use the existing ephemeral PostgreSQL 16 CI service and current migration runner. No production DSN or live provider is permitted.
- Exercise independent PostgreSQL connections and subprocesses, not only an in-process shared fake.
- Verify that approval consumption plus binding has one winner, that a task cannot be attached to a second intent, and that a completed stage is replayed only when workflow, stage, task, action digest, permission and approval reference all match.

- [ ] **Step 1: Add the focused failing tests**

Run concurrent separate-connection approval consumers and separate-process workflow recovery. Include a simulated failure between consumed-approval commit and task enqueue, a failure between task completion and stage checkpoint completion, and a read-back of all related rows after each run.

- [ ] **Step 2: Verify the relevant failure**

Run: `python -m unittest tests.test_postgres_approval_ledger tests.test_postgres_storage tests.test_workflow_approval_recovery -v` against the ephemeral PostgreSQL 16 service.

Expected: tests expose any missing unique constraint, transaction boundary, stale revision handling or mismatched binding.

- [ ] **Step 3: Implement the minimum behavior**

Use unique constraints and transaction-scoped inserts, not process-local locks, as the cross-process source of truth. Keep all recovery lookups read-only. Any partial or contradictory evidence blocks; no automatic repair or reassignment is allowed.

- [ ] **Step 4: Verify the focused pass**

Run the same focused PostgreSQL test command.

Expected: one winner per approval ID and execution ID; all mismatch and interruption cases block without duplicate provider/tool callbacks.

- [ ] **Step 5: Run the full CI acceptance suite**

Run: `python -m compileall -q unexpected_runtime`, `node --check web/assets/app.js`, then `python -m unittest discover -s tests -v`; let the existing GitHub Actions workflow apply migrations 001–007, verify the changed-file SHA-256 inventory, build the runtime container, perform authenticated container smoke tests and render the existing isolated renderer E2E fixture.

Expected: every job succeeds; runtime tests have zero failures; renderer E2E passes; no production database or provider is accessed.

- [ ] **Step 6: Commit the passing deliverable**

Commit message: `test(v8): verify bound approval recovery across processes`.

---

## Release gates

Do not enable privileged workflow recovery or mark the approval-binding phase complete until all of these are verified:

- A new approval is bound to one immutable execution ID and task ID; workflow operations also bind to the exact workflow ID and stage key.
- The canonical digest covers the operation, permission, task ID, execution ID and workflow-stage identity.
- The GitHub review is trusted, fresh, on the exact immutable request commit, and references the same digest and execution binding.
- One-use consumption and binding are atomic within each approval-ledger database; conflicting or reused approvals have one winner only.
- Task and workflow-stage records point back to the same approval ID, digest and binding; recovery performs read-only exact-match checks.
- Every crash boundary has a deterministic regression test, including separate-process SQLite and separate-connection/process PostgreSQL tests.
- Missing task, claim, approval, stage or binding evidence fails closed. No old unbound approval is backfilled or reassigned.
- Existing non-privileged invocation, lifecycle replay, all 38 registered roles, Studio/PWA, task/event/memory/approval data and old HTTP clients remain compatible.
- No critical/high security regression, unapproved cost, production migration, deployment or external action occurs.

## Unresolved implementation boundary

The design does not authorize a legacy privileged execution to be resumed. Existing approval records have no stable task/stage identity and remain unbound. The workflow pause state is new; a stage already marked `started` by the current runner remains ambiguous and cannot be converted to `waiting_approval`. The first implementation should deliver task-bound invocation before workflow-stage pause/resume, then integrate the latter only with its own crash tests.
