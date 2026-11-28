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


## Run 10 — 2026-11-15 — Approval-intent red-test harness correction

- **Phase:** Phase 3, durable execution; approval-binding Task 1 (test-first).
- **Baseline:** rechecked core `main` at `d04b651774b7699f3430dc36972c2de74c587839`; resumed draft PR #16 on `upgrade/v8-workflow-checkpoint-ledger-20261111` at `74685047134bd1c289055241b3f3123e0a72a60b` (27 commits ahead, 0 behind). The compare reports no removed paths.
- **Observed CI:** run [43579323788](https://github.com/soueilouay-creator/uneXxxx/actions/runs/43579323788) failed in the runtime job (405 tests, 16 errors, 3 skipped); renderer E2E passed. The new contract tests exposed the expected missing SQLite/PostgreSQL intent methods, but also revealed a test-helper TypeError because `intent_values()` did not accept the request-hash and permission overrides used by its validation test.
- **Change:** corrected only the test helper signature and value forwarding in `tests/test_approval_execution_intents.py`. No runtime code, schema, migration, dependency, coordinator, permission verifier or approval ledger was changed. The previous test file remains recoverable from parent commit `74685047134bd1c289055241b3f3123e0a72a60b`.
- **Verification:** SHA-256 inventory updated for the test and run log; a new CI run is required to prove the red stage contains only expected missing-method failures before implementation.
- **Preservation:** no tracked path was removed; no existing task, event, memory, approval, user record, production database, Neon branch, Render service, deployment, PWA, source archive, setting or secret was accessed or changed.
- **Costs:** no new package, provider/API call, generation credit, paid infrastructure, migration or deployment. GitHub Actions account-level billing is not visible.
- **Next:** verify the corrected red suite, then implement the smallest additive SQLite/PostgreSQL execution-intent storage contract and migration 005.


### Run 10 CI verification — 2026-11-15

- **Tested commit:** `95a01c407c859ad9b3977dd9c7951d13f6e54e44`.
- **CI:** [run 43669717326](https://github.com/soueilouay-creator/uneXxxx/actions/runs/43669717326) completed with an expected red runtime job and a green renderer E2E job.
- **Runtime result:** `Ran 405 tests`; `FAILED (errors=16, skipped=3)`. All 16 errors are now the expected `AttributeError: ... has no attribute 'create_approval_execution_intent'` in the not-yet-implemented SQLite/PostgreSQL storage contract. The earlier helper `TypeError` is gone. This establishes a clean test-first failure signal; it is not a passing release suite.
- **Renderer result:** `Ran 2 tests in 26.730s`; `OK`. The immutable rendering worker built and both renderer end-to-end tests passed.
- **Interpretation:** the next implementation step is now safe to begin: add the execution-intent persistence contract to SQLite and PostgreSQL with migration 005, preserving the existing tables and rows. No approval consumption or coordinator wiring is included in that first storage increment.
- **Preservation and cost:** compare remains 27 commits ahead / 0 behind with no removed paths. No production migration, database write, deployment, provider call, package addition or paid infrastructure was performed; GitHub Actions billing impact is not visible.


## Run 11 — 2026-11-15 — Approval execution intent storage and migration 005

- **Phase:** Phase 3, durable execution; approval-binding Task 1.
- **Baseline and rollback:** rechecked default branch `main` at `d04b651774b7699f3430dc36972c2de74c587839`; resumed open draft PR #16 on `upgrade/v8-workflow-checkpoint-ledger-20261111` at `64ec5023ed63b599d88d8b5587da2fe346fb829a`. This parent commit remains the rollback point; no history rewrite or main-branch write.
- **Implementation:** added additive PostgreSQL migration `migrations/005_approval_execution_intents.sql`; added additive SQLite table/index initialization; implemented create/read/idempotent identity checks and state/revision compare-and-swap transitions in both `unexpected_runtime/storage.py` and `unexpected_runtime/postgres_storage.py`.
- **State safety:** one intent per task; request/action SHA-256 validation; workflow/stage pairing; immutable identity on repeated create; explicit legal transition graph; terminal states cannot be reopened; stale revisions and duplicate concurrent transitions return false; PostgreSQL methods require schema version 5 and never create/repair production tables.
- **Preservation tests:** expanded `tests/test_approval_execution_intents.py` to verify old task/event/memory records remain readable after intent operations and after opening a pre-existing SQLite database. CI now seeds pre-005 PostgreSQL task/event/memory rows, applies migration 005, and reads them back before running the runtime suite.
- **Verification status:** implementation commit CI pending. The TDD red signal is recorded in CI run [43669717326](https://github.com/soueilouay-creator/uneXxxx/actions/runs/43669717326): 405 tests, 16 expected missing-method errors, 3 skipped; renderer E2E 2/2 passed. The focused failure was the absent storage methods, after the earlier test-helper TypeError had been fixed.
- **Preservation:** source branch and all pre-existing repository paths remain intact; no production database, Neon branch, Render service, deployment, provider, credential, existing user record, PWA or source archive was changed. CI uses an ephemeral PostgreSQL service only.
- **Costs:** no dependency, external service, provider call, paid API, infrastructure or production migration added. GitHub Actions account-level billing remains unobservable.
- **Next:** observe the full CI run; repair only evidence-backed failures; then append exact tested SHA, command, counts and job outcomes to this log.


### Run 11 CI verification — 2026-11-15 — initial implementation result

- **CI run:** [43696572852](https://github.com/soueilouay-creator/uneXxxx/actions/runs/43696572852), tested commit `f3e312dd0436409179ad4ee771a3919f737d1c5d`.
- **Migration and preservation rehearsal:** passed. Migrations 001–004 were applied to ephemeral PostgreSQL, synthetic pre-005 task/event/memory records were seeded, migration 005 applied, and all three rows read back unchanged.
- **Static checks:** runtime compile, JavaScript syntax, YAML/Bash validation, resource contracts and SHA-256 inventory passed.
- **Runtime suite:** `Ran 408 tests in 74.118s`; `FAILED (failures=1, errors=2, skipped=3)`. Two new adapter contract errors showed that a stale expected state/revision must return false before illegal-transition validation. One existing PostgreSQL queue test claimed the task created by the new preservation fixture; the fixture had left a queued synthetic task in the shared ephemeral CI database.
- **Renderer job:** still running at the time of this update; no renderer result is claimed here.
- **Correction plan:** make stale compare-and-set requests return false when persisted state/revision has moved; keep an exception for an illegal transition at the current revision; finish the preservation fixture task to avoid polluting subsequent PG tests; constrain the new state set to the six states specified by the saved approval-binding design.
- **No production effects:** ephemeral CI database only; no Neon/Render production access, deployment, provider call or user-data migration.

## Run 12 — 2026-11-15 — Stale revision handling and CI fixture isolation

- **Phase:** Phase 3, durable execution; approval-intent storage refinement.
- **Baseline and rollback:** resumed the same draft PR #16 at `f3e312dd0436409179ad4ee771a3919f737d1c5d`; that commit remains the rollback point. Default branch `main` remains `d04b651774b7699f3430dc36972c2de74c587839`.
- **Changes:** in both SQLite and PostgreSQL adapters, stale expected state/revision requests now return false before illegal-transition validation; illegal transitions at the current expected state/revision still raise ValueError. Intent states now match the six-state design (`prepared`, `awaiting_approval`, `approved`, `enqueued`, `completed`, `blocked`). Added an explicit blocked-terminal regression. The preservation contract test now marks its synthetic queued task complete so it cannot interfere with subsequent queue tests sharing the ephemeral PostgreSQL database.
- **Migration compatibility:** PostgreSQL migration 005 remains additive and idempotent; only the state CHECK constraint was narrowed before merge/use. SQLite initialization adds the same six-state check for newly created intent tables. No production database has received migration 005.
- **Verification:** new CI pending. Prior failed CI evidence and the exact errors remain recorded above; no green claim until the full suite passes on the new head.
- **Next:** review the rerun's focused intent contract and full regression suite; run process/connection concurrency evidence, then move to Task 2 approval binding only after Task 1 is green.
- **Costs/preservation:** no dependencies, paid tests, API credits, paid infrastructure, deployment or production writes. Existing tasks/events/memories and all non-target files remain preserved; GitHub Actions account-level billing is not visible.


### Run 12 final CI verification — 2026-11-15

- **Tested commit:** `5941a06845088ac246aa7801f8a88f01e89fe3eb`.
- **CI run:** [43696872369](https://github.com/soueilouay-creator/uneXxxx/actions/runs/43696872369) completed successfully; both `runtime-tests` and `renderer-e2e` are green.
- **Runtime/security:** `Ran 410 tests in 75.725s`; `OK (skipped=3)`.
- **Renderer E2E:** `Ran 2 tests in 28.457s`; `OK`. The immutable renderer worker built, a real vertical MP4 rendered with worker network disabled, and image identity was confirmed.
- **PostgreSQL migration preservation:** migrations 001–005 applied to the ephemeral PostgreSQL 16 service. Synthetic task, event and memory records inserted before migration 005 were read back unchanged after it.
- **Additional gates:** runtime compile, JavaScript syntax, YAML/Bash validation, resource catalog validation, changed-file SHA-256 inventory, runtime Docker image build, live container smoke test and CLI smoke tests all passed.
- **Task 1 status:** completed and verified on this commit. The approval execution intent remains a storage-only object; no approval consumption or privileged task invocation is wired to it yet.
- **Preservation:** PR #16 remains open and draft, 31 commits ahead and 0 behind main; compare shows no removed paths. No production migration, Neon/Render change, deployment, provider call, or user-data mutation occurred.

## Run 13 — 2026-11-15 — Bound approval ledger contract (TDD red)

- **Phase:** Phase 3, durable execution; approval-binding Task 2.
- **Baseline and rollback:** Task 1 verified at `5941a06845088ac246aa7801f8a88f01e89fe3eb`; default branch `main` remains `d04b651774b7699f3430dc36972c2de74c587839`. Work remains on the existing `upgrade/v8-workflow-checkpoint-ledger-20261111` branch and draft PR #16.
- **Test-first changes:** added immutable `ApprovalExecutionBinding` model and focused failing tests for SQLite verifier binding, exact execution/task/workflow/stage/digest identity, concurrent one-use consumption, ledger outage fail-closed behavior, retained legacy unbound rows, PostgreSQL transactional rollback on binding failure, uniqueness and multi-connection concurrency.
- **TDD red expectation:** ledger `consume_once_bound`, read-back, and verifier `verify_bound` do not yet exist. No approval binding table or implementation is included in this test-first increment.
- **Safety boundary:** legacy `verify` and `consume_once` behavior remains unchanged. No current task is newly authorized by an execution intent. Approval PRs, production data and user records are not touched.
- **Verification:** focused tests and resulting red CI are pending; the previous full CI green on Task 1 is historical evidence, not a pass for the new tests.
- **Next:** confirm the new contract fails only for absent bound methods, then add migration 006 and same-transaction SQLite/PostgreSQL bound consumption plus lookup; no coordinator/HTTP wiring until Task 3.
- **Costs/preservation:** no new dependencies, provider/API calls, paid infrastructure, deployment or production migration. GitHub Actions account-level billing is not visible.


## Run 14 — 2026-11-15 — Atomic bound approval consumption and lookup

- **Phase:** Phase 3, durable execution; approval-binding Task 2.
- **Baseline and rollback:** Task 2 red contract is on `1ce74b0214ea1711fe61bee9a9889ec8c5c356c1`; this commit is the rollback point. Work remains on the existing draft PR #16 branch. No force push, merge or main-branch change.
- **Implementation:** added additive PostgreSQL migration `migrations/006_approval_execution_bindings.sql`; SQLite now creates the matching binding table additively in the existing approval-ledger database. Added `consume_once_bound` and `get_consumed_binding` to the PostgreSQL ledger and corresponding SQLite verifier paths; added `verify_bound` while retaining legacy `verify` and `consume_once`.
- **Binding checks:** immutable execution ID, task ID and optional workflow/stage tuple must exactly match the execution-binding object embedded in the immutable approval request's `action_details`; the entire action digest must still match. Unique execution/task ownership and single-use approval ID are enforced by database uniqueness constraints.
- **Atomicity:** PostgreSQL inserts `consumed_approvals` and its binding on one connection/transaction. If the binding insert conflicts or fails, the preceding consumed-approval insert is rolled back. SQLite uses `BEGIN IMMEDIATE` and the same all-or-nothing semantics in the existing approval-ledger file. Legacy unbound approval rows are neither updated nor backfilled.
- **CI preservation:** updated the ephemeral PostgreSQL migration rehearsal to seed a legacy consumed approval after migration 005 and before migration 006, then verify the row remains and no binding row is synthesized.
- **Safety boundary:** this remains Task 2 only. Coordinator invocation, HTTP prepare/authorize flow and workflow pause/resume are not wired yet. No production approval, production database, deployment, provider or customer-facing action was touched.
- **Verification:** CI for the implementation commit is pending. The Task 2 test-first run [43699560139](https://github.com/soueilouay-creator/uneXxxx/actions/runs/43699560139) is still in progress at the time of this commit; its eventual red/green outcome will be recorded separately, not inferred.
- **Next:** inspect the test-first run's failure reasons, then run focused verifier/ledger tests and the complete CI suite on this implementation head. Fix only concrete failures. Do not begin Task 3 until Task 2 is green.
- **Costs/preservation:** no new dependency, paid service, provider call, API credit, production migration or deployment. The PostgreSQL migration rehearsal remains ephemeral CI only; GitHub Actions billing impact is not visible.


## Run 15 — 2026-11-17 — PostgreSQL approval resume and backup/restore acceptance

- **Scope:** add a positive PostgreSQL workflow pause → approve → resume test using a new PostgresStateStore instance, plus a disposable PostgreSQL logical backup/restore drill. No production DSN, Neon branch, Render service, provider secret or user data is used.
- **Approval recovery test:** the test prepares a workflow-stage execution intent, confirms the first run pauses before stage start/callback, consumes a one-use approval with an immutable execution/task/workflow/stage binding, applies revision-checked state transitions, resumes through a newly opened PostgreSQL store, and checks the execution, stage and workflow finish as completed. Existing independent-connection concurrency and abrupt-process-exit tests remain enabled.
- **Backup/restore drill:** the test applies migrations 001–007 to a temporary source database, seeds task/event/memory/approval records, creates and lists a custom-format archive, restores it transactionally into a separate temporary database, then compares all public base-table row counts and exact representative read-backs. Cleanup drops only the uniquely named temporary CI databases.
- **Runbook:** added docs/v8/POSTGRES_BACKUP_RESTORE.md. It requires a separate empty restore target, checksum validation and post-restore read-back; it forbids a destructive in-place --clean restore.
- **Verification:** implementation commit CI is pending. Do not infer a pass until the runtime, renderer, backup/restore and Studio integration workflows report completed success on the new SHA.
- **Production boundary:** no production backup, snapshot, retention schedule, off-site archive, Neon restore, Render change, merge-to-production or deployment is performed by the CI drill. Production backup scheduling, secure off-site retention and an approved recovery exercise remain operational release blockers.

## Run 16 — 2026-11-26 — read-only workflow recovery inspection

**Phase:** Phase 3, durable execution and recovery operator visibility.

**Baseline and rollback**
- Core main HEAD before this run: 2828fe281b60ea0a343b24973b411bbad650e93e.
- Created backup branch backup/v8-core-pre-recovery-inspection-20261126 at that exact main commit.
- Feature branch: upgrade/v8-recovery-inspection-20261126.
- Draft PR: https://github.com/soueilouay-creator/uneXxxx/pull/19.
- Implementation/test/docs head verified by CI: adf2520580358f4be3fd0be358d600e2f7ba88a6.

**Completed**
- Added unexpected_runtime/recovery_inspection.py, a read-only and sanitized workflow recovery inspector.
- Added five SQLite tests and two PostgreSQL tests for missing checkpoints, ambiguous started stages, non-mutating inspection, missing linked-task evidence, pending approval bindings and input validation.
- Added docs/v8/WORKFLOW_RECOVERY_INSPECTION.md with operator handling boundaries and requirements for a future write-capable reconciliation operation.
- Updated FILE_INVENTORY_SHA256.txt; the final implementation head passed the repository inventory check.
- No package, service, migration, API route or UI change was added.

**Verification**
- CI run 45745387633 on implementation head adf2520580358f4be3fd0be358d600e2f7ba88a6.
- Runtime-tests job passed: python -m unittest discover -s tests -v; 450 tests passed, including all seven new recovery-inspection tests. Compileall, JavaScript syntax, workflow YAML/Bash validation, additive migration preservation, source inventory verification, Docker build and authenticated container smoke test also passed.
- PostgreSQL 17 release-proof job passed: six tests covering independent-connection approval concurrency, abrupt-process recovery, pause/resume, consumed-approval replay protection and logical backup/restore.
- Renderer end-to-end job was still running at the time of this log entry; it is not counted as passed.

**Live infrastructure inspection (read-only)**
- Render workspace My Workspace: unexpected-v8-command-center is on main with auto-deploy off and the Free plan; unexpected-ai-studio is on main with auto-deploy on and the Free plan. No Render PostgreSQL instances were listed.
- Neon organization plan is Free. Project unexpected-v8-unified (tiny-glade-03545028) has ten branches; all ten, including the default main branch, are archived. The default branch logical size is 31,432,704 bytes.
- One manual snapshot exists: uneXpected-pre-cutover-main-2026-11-07, created 2026-11-07T08:50:13Z. The default branch snapshot schedule is empty. Project history retention is 21,600 seconds. The Neon consumption endpoint is restricted to paid plans, so account-level usage/cost metrics were not available.
- No Neon data tables were queried. No branch was unarchived/restored/created, no snapshot was restored, no database or service setting was changed, and no credentials were accessed.

**Preservation and cost**
- The feature branch is seven commits ahead and zero behind core main; four changed paths, three added files plus the source inventory update, zero deleted paths.
- The backup branch still points to the pre-run main SHA. No existing application source, task, memory, approval, workflow, project or database record was modified.
- No new dependency, paid infrastructure, provider API call or generation credit was used. GitHub Actions ran the repository CI; account-level billing is not visible through the available connector.
- The remote GitHub branch diff was verified. A local working-tree status was not exposed by the connected GitHub interface.

**Blocked / next**
- The hosted Neon default branch is archived and no automatic snapshot schedule exists. Production database connectivity and production backup/restore remain unverified; do not unarchive or restore without a separately approved, backed-up recovery plan.
- This helper is diagnostic only. There is still no supported, revision-checked operator transition to reconcile an ambiguous started stage.
- Next: finish the renderer CI result, then design an append-only reconciliation audit record and compare-and-set transition with SQLite/PostgreSQL parity tests. Do not apply a production migration until an active authorized database and independent backup/read-back are verified.



## Run 17 — 2026-11-27 — revision-checked manual-review block

**Phase:** Phase 3, durable execution and operator recovery.

**Baseline and rollback**
- Re-verified core default branch `main` at `2828fe281b60ea0a343b24973b411bbad650e93e`.
- Reused open draft PR #19 and branch `upgrade/v8-recovery-inspection-20261126`, whose starting head was `5711458b2450aa7478972eea532b9733ef0b0147`.
- Created rollback branch `backup/v8-core-pre-reconciliation-20261127` at that exact pre-change feature head.
- Studio repository was rechecked separately; no Studio files were changed in this run.

**Completed**
- Added `unexpected_runtime/workflow_reconciliation.py` for bounded request validation, attempt-token fingerprints and immutable event matching.
- Added `record_workflow_reconciliation_block()` and read-only event listing to both SQLite `StateStore` and PostgreSQL `PostgresStateStore`.
- Added `migrations/008_workflow_reconciliation_events.sql`; SQLite initialization adds the equivalent table and append-only triggers without a schema-version bump.
- Extended recovery inspection with the stage request hash and a SHA-256 attempt fingerprint; the raw token remains hidden.
- Added `tests/test_workflow_reconciliation.py` for both backends.
- Added the PostgreSQL reconciliation suite to the PostgreSQL 17 release-proof CI command.
- Added `docs/v8/WORKFLOW_RECONCILIATION.md`.
- Updated the changed-file SHA-256 inventory.

**Safety semantics**
- Only a still-`started` stage with matching checkpoint revision, stage index, stage request hash and attempt-token fingerprint can be blocked.
- The stage changes to `interrupted`; the checkpoint changes to `blocked` with a revision increment. The original attempt token, stage result, task records and approval records are not rewritten.
- The event is appended atomically and database triggers reject updates/deletes.
- This is a manual-review block, not an external-effect success/failure decision and not an automatic recovery/replay path.
- The method is not exposed through HTTP, CLI, scheduler or UI. The operator identifier is recorded but not authenticated by this storage layer; future API exposure requires authentication and explicit human confirmation.

**Verification**
- CI result pending for the new implementation commit. No pass is claimed until the SQLite suite, PostgreSQL 16/17 suites, migration-preservation step and renderer E2E all complete on the new commit.
- No hosted PostgreSQL migration, production database access, provider API request, user-data operation or deployment was performed.

**Costs and blockers**
- No dependency, package, infrastructure or provider credit was added or used. GitHub Actions account-level billing remains unverified.
- Hosted production database remains unavailable for a verified migration/restore rehearsal: the previous read-only Neon audit found all branches archived and no scheduled snapshot. This must be rechecked before any production migration.
- Next: verify exact-head CI, then add authenticated operator visibility only after the runtime transport and identity boundary are independently verified.


**CI correction note**
- First implementation run: https://github.com/soueilouay-creator/uneXxxx/actions/runs/45927399721
- PostgreSQL 17 applied migrations 001–008 successfully. All four initial PostgreSQL reconciliation tests and all seven SQLite reconciliation tests passed.
- The existing PostgreSQL backup/restore proof failed because it hard-coded schema version 7 and a fixture payload with migration count 7. This was a stale test expectation caused by the additive migration, not a migration or restore failure.
- Corrected tests/test_postgres_backup_restore.py to derive the expected version from the checked-in migration filenames, added PostgreSQL audit-insert failure rollback coverage, and made the documentation explicit about both-backend rollback testing.
- The corrected exact-head CI run was pending at the time of this note; final verification closure is recorded below.


**Second CI correction note**
- Second implementation run: https://github.com/soueilouay-creator/uneXxxx/actions/runs/45927751000
- PostgreSQL 17 migration application and the existing custom-archive backup/restore read-back passed. The five existing PostgreSQL approval/recovery tests passed, as did four of the five PostgreSQL reconciliation tests and all seven SQLite reconciliation tests.
- The additional PostgreSQL rollback-injection test failed before exercising application code: the test fixture's dollar-quoted PL/pgSQL body was altered by the psycopg query parser, producing invalid SQL.
- Replaced that fixture body with a single-quoted SQL function body. The implementation transaction code was unchanged. The corrected exact-head CI run is pending.


## Run 17 verification closure — implementation commit 9f013b43e096423c69d0ea6879032417ce668d06

**GitHub Actions:** Run #45927932067 — exact implementation head 9f013b43e096423c69d0ea6879032417ce668d06; all three jobs completed with conclusion success (exit code 0).

- **Runtime regression/security:** command: python -m unittest discover -s tests -v; 462 tests, 3 skipped, result OK; exit code 0. The same job passed runtime compilation, JavaScript syntax checks, workflow YAML/Bash checks, migration-preservation checks, source integrity, changed-file SHA-256 inventory verification and docker build --pull -t unexpected-v8-command-center:ci .
- **PostgreSQL 17 release proof:** command: python -m unittest tests.test_postgres_workflow_stage_approval tests.test_postgres_backup_restore tests.test_workflow_reconciliation -v; 18 tests, result OK; exit code 0. Migrations 001–008 applied; independent-connection concurrency, approval/recovery, append-only audit, injected audit-insert rollback and custom-archive backup/restore read-back passed.
- **Renderer E2E:** docker build --pull -f renderer/Dockerfile -t unexpected-creator-renderer:locked . succeeded. Command: python -m unittest tests.test_creator_end_to_end -v; 2 tests, result OK; exit code 0. Both real MP4 packaging/QA tests passed with worker networking disabled. Renderer image digest: sha256:54629777e6f6f972c9fa8a8d6ad43ca2f33927e36a2f152b5ee77cddd77e5b10.

**Run 17 outcome:** the audited manual-review block, SQLite/PostgreSQL parity, stale-revision rejection, one-winner concurrency, idempotency, append-only triggers, transaction rollback and read-back are verified in CI. The implementation is still a draft PR and is not deployed.

**Outstanding V8 release blockers remain:** no active hosted PostgreSQL branch/Render Postgres or verified production backup/restore path; no live OpenAI/Anthropic/third-provider compatibility proof; authenticated operator API/UI not wired; full MCP threat/security gate, model/tool observability and evaluation, engineering sandbox, and end-to-end product-data preservation audit remain incomplete.

**Next increment:** add an authenticated, read-only operator view for workflow reconciliation events only after verifying the actual hosted runtime transport and identity boundary. Keep state-changing reconciliation controls unavailable until explicit human approval and worker-isolation evidence are enforceable.


## Run 18 — 2026-11-28 — Hosted runtime endpoint and authentication boundary audit

**Phase:** Phase 3, durable execution and hosted-runtime integration boundary.

**Baseline and rollback**
- Re-verified core `main` at `2828fe281b60ea0a343b24973b411bbad650e93e`.
- Resumed draft PR #19 on `upgrade/v8-recovery-inspection-20261126` at `d2568c181c81e5538c12a344b399c94783bd2f9a`; it remains open, unmerged and not deployed.
- Created rollback branch `backup/v8-core-pre-hosted-runtime-audit-20261128` at the exact pre-change feature head `d2568c181c81e5538c12a344b399c94783bd2f9a`.
- Re-verified Studio `main` at `6f5bc823e1ffd9284abae7dbbb6c1dae97ebf90b`; no Studio file was changed.

**Completed**
- Added `docs/v8/HOSTED_RUNTIME_ENDPOINT_AUDIT.md` with the live Render service inventory, deployed commit, source-level HTTP/MCP transport contract, shared bearer-token boundary, storage-selection uncertainty, live-probe limitation and explicit no-integration decision.
- Confirmed the Render command-center service is configured on the public HTTPS Render hostname with `/health`, auto-deploy off, Free plan and a single Frankfurt instance. Its latest live deployment is commit `8a67c823292901305cad670a60c2f24f0a047267`, older than current core `main` and PR #19.
- Confirmed the separate V7.3.1 test service is not the V8 command center; the Studio service still has auto-deploy enabled; no Render PostgreSQL instances are listed.
- Inspected the deployed source at its exact deployed SHA: `/v1/*` and `/mcp` use one shared bearer token; `/health` is public; the token check requires at least 32 ASCII characters and uses constant-time comparison. The MCP app is stateless Streamable HTTP with DNS-rebinding protection and an exact-host allowlist.
- Confirmed the source defaults to SQLite unless PostgreSQL is explicitly selected by environment. Render did not expose environment-variable values, so the actual token presence and storage backend remain unverified.
- Attempted only read-only live GET probes. DNS resolution failed in the execution container before HTTP; the web fetcher could not access the URL; Render request/application logs and service events were empty for 2026-11-21 through 2026-11-28. This does not establish that the host is down.

**Decision**
- No HTTP route or Studio client was added. A single shared bearer token currently authorizes both read and write-capable routes, so it is not a least-privilege credential for a read-only operator panel.
- Keep hosted runtime separate until live TLS/HTTP, unauthenticated rejection, approved authenticated status, MCP transport, actual storage persistence and a distinct read-only scope are verified.
- No environment variable, credential, service setting, deployment, DNS record or database was changed.

**Preservation and cost**
- Documentation-only changes plus checksum inventory. No tracked source, migration, user data, PWA, provider, approval, memory, deployment or integration was changed.
- No new dependency, infrastructure, paid trial, subscription, provider call or API credit. GitHub Actions billing and Render account-level usage are not visible.

**Verification**
- This audit records repository, Render control-plane and deployed-source evidence. The live endpoint probe is explicitly blocked by DNS/network access; no live HTTP status or TLS handshake is claimed.
- Exact-head CI for this documentation/checksum commit is pending and will be recorded after completion.

**Next**
- Obtain a non-secret live TLS/HTTP probe from an approved network path, verify the configured storage backend and backup posture, then design a separate read-only operator identity. Do not deploy or merge as part of this audit.


### Run 18 exact-head CI closure — implementation/documentation commit 8a44ea388b932b6cd65d56c2d5d47adf27d14d7d

GitHub Actions [run #46098339623](https://github.com/soueilouay-creator/uneXxxx/actions/runs/46098339623) completed successfully on the exact branch head `8a44ea388b932b6cd65d56c2d5d47adf27d14d7d`. All three jobs concluded success:

- **runtime-tests:** `python -m unittest discover -s tests -v` — 462 tests, 3 skipped, 0 failures (82.293 seconds). Runtime compilation, command-center JavaScript syntax, workflow YAML/Bash validation, resource/scenario contracts, additive migration preservation, source-integrity fixture, changed-file SHA-256 inventory, Docker build, actual-container smoke test and CLI smoke tests all passed.
- **postgres17-release-proof:** `python -m unittest tests.test_postgres_workflow_stage_approval tests.test_postgres_backup_restore tests.test_workflow_reconciliation -v` — 18 tests, 0 failures (3.325 seconds). Migrations 001–008, independent-connection approval/reconciliation concurrency, abrupt-process recovery, pause/resume, append-only audit protections, transaction rollback and custom-archive backup/restore read-back passed.
- **renderer-e2e:** `docker build --pull -f renderer/Dockerfile -t unexpected-creator-renderer:locked .` followed by `python -m unittest tests.test_creator_end_to_end -v` — 2 tests, 0 failures (27.587 seconds). A real vertical MP4 was rendered with worker networking disabled. Renderer image ID: `sha256:91e11bbe3563f936f6c8694f12141c4695a2530bb554240af25f1dc29e3505f4`.

The run also verified the changed-file SHA-256 inventory for 13 changed paths. The only follow-up after this tested commit is this documentation-only CI closure and its inventory digest; no executable source or tests changed after the successful run. PR #19 remains draft, open and unmerged; no production deployment or migration occurred.
