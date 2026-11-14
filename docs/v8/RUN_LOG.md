# uneXpected V8 engineering run log

This file is append-only. Each entry records one bounded engineering increment and its verification evidence.

## Run 3 — 2026-11-12 — Lifecycle checkpoint integration

- **Phase:** Phase 3, durable execution.
- **Baseline:** resumed the existing upgrade/v8-workflow-checkpoint-ledger-20261111 branch at e395158de06bd733aff8db2a13495bffc5d62d52; draft PR #16 remained open. Main was verified at d04b651774b7699f3430dc36972c2de74c587839.
- **Changes:** wired the existing checkpoint ledger into WorkflowRunner and Coordinator.run_lifecycle; exposed the existing workflow ID as an optional bounded /v1/lifecycle request field; added deterministic replay/ambiguous-stage tests; updated the checkpoint contract.
- **Preservation:** no production database, Render service, deployment, secret, source archive, existing task, memory, approval, or Creator Studio record was changed. All changes are additive source/test/documentation changes on the existing feature branch.
- **Safety behavior:** completed stage outputs are replayed; started stages fail closed; terminal results replay without provider calls. No claim of exactly-once external execution.
- **Verification:** pending CI for the new commit; parent commit e395158de06bd733aff8db2a13495bffc5d62d52 had both runtime and renderer CI jobs complete successfully (372 passed, 3 skipped; renderer smoke passed).
- **Costs:** no new dependency, service, provider call, deployment, paid test, or infrastructure created. GitHub Actions account-level billing is not visible.
- **Next:** add safe task/idempotency/approval reconciliation for ambiguous stages; prove restart after process termination; verify production backup/export and restore before any Neon migration.

## Run 4 — 2026-11-12 — Lifecycle HTTP workflow-ID allowlist fix

- **Phase:** Phase 3, durable execution integration.
- **Baseline:** inspected core main at d04b651774b7699f3430dc36972c2de74c587839 and resumed draft PR #16 at 76de85ef55762a71d632ecefd429300b7e21bbd9. CI run 43144257850 exposed one failing regression: the authenticated /v1/lifecycle test received HTTP 400 because workflow_id was parsed but omitted from the lifecycle request allowlist.
- **Change:** added workflow_id to the /v1/lifecycle allowlist only. The ordinary /v1/invoke allowlist remains unchanged. The existing authenticated HTTP replay test covers acceptance, persisted terminal status and replay without repeating reviewer calls.
- **Rollback:** parent commit 76de85ef55762a71d632ecefd429300b7e21bbd9 remains intact; no history was rewritten.
- **Verification:** the previous CI run reported 377 tests, one error and three skipped. New CI verification is pending; no pass is claimed yet.
- **Preservation:** no source archive, user data, SQLite/Neon production data, PWA, provider configuration or deployment was modified. No database migration was run.
- **Costs:** no new dependencies, services, provider calls or paid tests. GitHub Actions account-level billing is not visible.
- **Next:** verify the full CI rerun, then add a process-termination/restart test that reconciles checkpoint stages with task and idempotency records before any ambiguous-stage release.

## Run 5 — 2026-11-13 — Restart persistence regression coverage

- **Phase:** Phase 3, durable execution.
- **Baseline:** rechecked core `main` at `d04b651774b7699f3430dc36972c2de74c587839`; resumed draft PR #16 on `upgrade/v8-workflow-checkpoint-ledger-20261111` at `25695fd0d40075b2b8f0c8a6749b5461e9b4c189` (9 commits ahead, 0 behind; no deleted paths in the PR diff). Prior CI run [43145486051](https://github.com/soueilouay-creator/uneXxxx/actions/runs/43145486051) completed successfully: runtime job and renderer E2E job both passed; runtime suite ran 377 tests.
- **Change:** added two deterministic regression tests to `tests/test_workflow_lifecycle.py`. They reopen the same SQLite state file through a fresh `StateStore` instance and prove (1) completed stages replay without rerunning their callbacks while later stages finish once, and (2) an ambiguous `started` stage remains blocked with no callback execution after reopening. Updated the checkpoint contract and this append-only log.
- **Safety boundary:** these tests validate a new storage instance, not an OS process-kill test or PostgreSQL multi-process race. Ambiguous stages still fail closed; no automatic external side-effect replay or exactly-once claim is introduced.
- **Preservation:** no existing task, memory, approval, creator record, production database, Neon branch, Render service, PWA, source archive, deployment, or secret was changed. No migration was run.
- **Verification:** new CI is triggered by this commit; results are pending and will be recorded separately. The prior run is historical evidence only.
- **Costs:** no new package, service, provider call, API-generation credit or infrastructure. GitHub Actions account-level billing is not visible.
- **Next:** verify this CI run, then design a task/idempotency/approval reconciliation contract for ambiguous stages before enabling any resume behavior.


## Run 6 — 2026-11-14 — Completed-stage recovery reconciliation guard

- **Phase:** Phase 3, durable execution.
- **Baseline:** verified core \`main\` at \`d04b651774b7699f3430dc36972c2de74c587839\`; resumed PR #16 on \`upgrade/v8-workflow-checkpoint-ledger-20261111\` at \`b8f939ebc300b37cbeae014b930a2625e856d072\` (10 commits ahead, 0 behind; compare reported no deleted paths). Verified prior CI run [43353454636](https://github.com/soueilouay-creator/uneXxxx/actions/runs/43353454636): runtime suite 379 tests, 3 skipped; renderer E2E passed.
- **Change:** before reusing a completed stage with a task reference, WorkflowRunner now verifies the linked task row is completed and its stored result matches the task. When an idempotency key exists, the claim must be completed for the same task and match the reconstructed request hash and result. Tasks with privileged permission scopes block for human review because the current approval ledger is not durably linked to task/stage identity. Added read-only claim lookup parity to SQLite and PostgreSQL.
- **Regression coverage:** added deterministic tests for missing/nonterminal tasks, running/mismatched idempotency claims, request-hash/result mismatches, privileged approval gaps and a valid replay path; added a PostgreSQL ephemeral-CI lookup test. Updated existing restart fixtures to seed their linked task records.
- **Safety boundary:** all reconciliation is read-only. Started stages still fail closed. No automatic stale-stage takeover, approval release, provider retry, external write or exactly-once claim is introduced.
- **Preservation:** existing task, memory, event, approval, Creator Studio and user records remain untouched; no migration, production database access, deployment, PWA/source archive change or secret access.
- **Verification:** new CI is triggered by this commit; test count and result will be appended after the run completes.
- **Costs:** no new package, service, provider call, generation credit, paid infrastructure or database migration. GitHub Actions account-level billing is not visible.
- **Next:** add an OS-process termination test and design a durable, action-digest-bound approval reference that can be reconciled without weakening the one-use approval ledger.


### Run 6 verification update — 2026-11-14

- **Implementation commit:** \`ea19bcb7b5830c4e62d95cd84d1ba0dde74b0f8d\`; verified CI head \`5e3eaa91bd3aeaa56075b18b32cd92bda995f3fb\`.
- **CI run:** [43547031183](https://github.com/soueilouay-creator/uneXxxx/actions/runs/43547031183). Runtime job completed successfully: \`Ran 388 tests in 94.196s\`; \`OK (skipped=3)\`. The new SQLite reconciliation cases and PostgreSQL idempotency-lookup test all passed.
- **Additional checks:** ephemeral PostgreSQL migrations passed; source integrity fixture and SHA-256 inventory passed; single-process Docker image build, actual container smoke test and CLI smoke tests passed.
- **Outstanding CI:** renderer E2E remained in progress at the immutable Opuscar worker build step when this entry was written. The MP4 render and image-identity steps were not yet verified.
- **Correction recorded:** the first CI attempt \`43546874318\` stopped at the inventory parser because a temporary comment row was not a digest/path record. The row was removed; the second run passed the inventory check. No source test failure was hidden.
- **Interpretation:** the workflow/task/idempotency recovery guard is runtime-test verified. This does not complete PostgreSQL process-crash recovery, durable approval linkage or the overall V8 release gate.


### Run 6 final CI completion — 2026-11-14

- **CI run:** [43547031183](https://github.com/soueilouay-creator/uneXxxx/actions/runs/43547031183) completed successfully on tested head \`5e3eaa91bd3aeaa56075b18b32cd92bda995f3fb\`.
- **Runtime job:** \`Ran 388 tests in 94.196s\`; \`OK (skipped=3)\`. All eight new recovery/lookup regression tests passed, including the PostgreSQL ephemeral-database lookup.
- **Renderer E2E:** \`Ran 2 tests in 27.731s\`; \`OK\`. Immutable renderer worker built, real vertical MP4 render passed with worker network disabled, and renderer image identity was confirmed.
- **Other gates:** ephemeral PostgreSQL migrations, changed-file SHA-256 inventory, runtime compile, JavaScript/YAML/Bash checks, Docker image build, actual container smoke test and CLI smoke tests all passed.
- **Commit lineage:** implementation commit \`ea19bcb7b5830c4e62d95cd84d1ba0dde74b0f8d\`; CI-tested source/manifest head \`5e3eaa91bd3aeaa56075b18b32cd92bda995f3fb\`. Subsequent commits only append verification evidence and refresh the SHA-256 inventory; runtime source and tests were unchanged.
- **PR #16 remains draft and unmerged.** No production deployment, production database migration, user-data migration or external provider call was performed.


## Run 7 — 2026-11-14 — Abrupt process-termination recovery regression

- **Phase:** Phase 3, durable execution.
- **Baseline:** rechecked runtime repository default branch `main` at `d04b651774b7699f3430dc36972c2de74c587839`; resumed open draft PR #16 on `upgrade/v8-workflow-checkpoint-ledger-20261111` at `90df1e5930c5d388d64e094b9ee1080992c299bf` (24 commits ahead, 0 behind; the existing compare contained no removed paths).
- **Change:** added `tests/test_workflow_process_recovery.py`. The test starts an isolated child Python process, commits a stage claim, terminates the child abruptly from inside the stage callback, reopens the same temporary SQLite database in the parent, and verifies that retry remains blocked without invoking any callback or changing the stage attempt token/checkpoint revision.
- **Scope:** regression-test and documentation increment only. No production runtime implementation, schema, dependency, coordinator or approval behavior was changed. Privileged workflow recovery continues to fail closed pending durable approval-to-task/stage linkage.
- **Verification:** CI has not yet run for this commit. Existing parent CI evidence is historical only: runtime suite 388 tests with 3 skipped, renderer E2E 2/2, ephemeral PostgreSQL migrations, inventory, Docker and CLI smoke passed on the prior tested source.
- **Preservation:** test uses only a newly created temporary SQLite database. No existing task, event, memory, approval, Creator Studio record, user data, Neon branch, Render service, deployment, PWA, source archive, setting or secret was read or changed.
- **Costs:** no new package, infrastructure, provider call, generation credit, paid service or database migration. GitHub Actions account-level billing is not visible.
- **Next:** add a durable, action-digest-bound approval reference through the workflow-stage and task creation path without changing the current one-use verifier semantics; then test concurrent PostgreSQL recovery with separate connections and processes. Do not release automatic replay of ambiguous stages until these checks pass.


## Run 8 — 2026-11-14 — Approval execution-binding design

- **Phase:** Phase 3, durable execution and privileged-action recovery design.
- **Baseline:** verified core `main` at `d04b651774b7699f3430dc36972c2de74c587839` and draft PR #16 at `0ce8b5f198e1028c8c863ef87b05c30029db3abd` on `upgrade/v8-workflow-checkpoint-ledger-20261111` (25 commits ahead, 0 behind; no removed paths).
- **Verification closed:** CI run [43578227455](https://github.com/soueilouay-creator/uneXxxx/actions/runs/43578227455) completed successfully. Runtime/security suite: **389 tests, 3 skipped, 0 failures**. The new `test_abrupt_process_exit_leaves_started_stage_blocked_after_reopen` passed. Renderer E2E: **2 tests, 0 failures**. Ephemeral PostgreSQL migrations, changed-file SHA-256 inventory, Docker build/container smoke, CLI smoke and isolated renderer image/render checks passed.
- **Finding:** current `Coordinator.invoke` authorizes before creating `TaskRequest`, so the approval verifier cannot bind consumption to the future task. The existing one-use ledger persists only approval ID/action digest/consumption time. The HTTP invocation API rejects approval fields. `WorkflowRunner` marks a stage `started` before invoking its callback, so a new human-approval pause cannot reuse that status without risking ambiguous-execution replay.
- **Design:** added `docs/plans/2026-11-14-approval-execution-binding.md` with a repository-grounded, five-task implementation plan: durable execution intents; a separate additive approval-binding table and atomic one-use consumption; prepared-task authorization/enqueue API; explicit non-ambiguous workflow approval pause/resume; and separate-connection/process PostgreSQL verification.
- **Safety boundary:** this run is documentation-only. No runtime source, database schema, approval record, task, provider, Render/Neon resource, deployment, PWA or user data changed. Existing unbound approvals remain untouched and are not authorized for replay.
- **Costs:** no new dependencies, provider calls, paid infrastructure, migrations or deployment. CI account-level billing is not exposed.
- **Next:** implement Task 1 of the saved plan with TDD on the existing feature branch; do not wire bound approval consumption until durable execution intents exist.


## Run 9 — 2026-11-14 — Execution-intent storage contract (TDD red)

- **Phase:** Phase 3, durable execution; approval-binding Task 1.
- **Baseline:** rechecked core `main` at `d04b651774b7699f3430dc36972c2de74c587839` and draft PR #16 at `39455b3cef468e9cd812b2b7cb8d2ce0f39bdbc6` (26 commits ahead, 0 behind; no removed paths).
- **Test change:** added `tests/test_approval_execution_intents.py` first. It specifies SQLite and ephemeral-PostgreSQL parity for stable intent creation/read-back, idempotent duplicate create, conflicting identity rejection, unique task ownership, workflow/stage pair validation, SHA-256/permission validation, revision-checked legal transitions and concurrent single-winner transitions.
- **TDD status:** red stage only. No production implementation or schema change has been made in this commit. The focused suite is expected to fail because the new storage methods/table do not exist yet; the CI result will record the actual failure.
- **Preservation:** tests use a temporary SQLite database or the ephemeral PostgreSQL CI database. No existing task, approval, user data, production database, Neon branch, Render service, deployment, PWA, secret or provider was touched.
- **Costs:** no new dependency, provider call, paid infrastructure, production migration or deployment. GitHub Actions account-level billing is not exposed.
- **Next:** observe the focused CI failure for the missing methods, then implement the minimum additive SQLite/PostgreSQL intent contract and migration 005.
