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

