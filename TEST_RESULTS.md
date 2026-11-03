# Test Results — uneXpected v7.3.1

**Historical v7.0 baseline: 44 passed, 0 failed, 0 errors, 1 skipped.** Command: `UNEXPECTED_PACKAGE_ZIP=/mnt/data/uneXpected-v7-audit/uneXpected_v7_unified_runtime.zip python -m unittest discover -s tests -v` from the package root. The skipped test is an optional v6 source ZIP integrity check; no v6 archive was supplied. All v7 crosswalk tests passed. Python bytecode compilation passed via `python -m compileall -q unexpected_runtime tests`.

## Historical v7.0 release gates

- **Agent manifest/schema and unique IDs:** 38/38 active role specs present and valid for required fields; unique IDs and unique spec paths passed.
- **Legacy crosswalk:** 37/37 original profile paths mapped with explicit `kept` disposition. Original Library files were not modified.
- **Upstream workflow mapping:** 120/120 unique v6 workflow IDs and paths mapped to primary/supporting canonical roles. Each migration entry includes the source URL, responsibility summary, required inputs, procedure steps, expected output, acceptance checks, safety boundary and external dependencies. Markdown/CSV/JSON catalog/crosswalk IDs agree.
- **Critical safety/permission/secret/protected-change checks:** 15/15 passed.
- **Other acceptance/regression checks:** 30/30 passed (100%, exceeding the 90% release threshold).
- **ZIP/package integrity:** archive test passed; per-file SHA-256 inventory matched; required files and package paths verified.

## Historical v7.0 runtime behavior actually exercised

- Invoked all 38 registered roles individually through the deterministic mock provider: 38/38 returned `completed`.
- CLI `status` and `list`: reported 38 registered roles and `deterministic-mock` provider.
- CLI single-agent invocation: `orchestrator` completed.
- CLI typed handoff chain: `research-scout → web-scout → deep-research`, 3/3 completed.
- CLI task graph: 3 dependent nodes completed in topological order.
- CLI fixed benchmark `UNEXPECTED-V7-CORE-2026-10`: score 1.0 on runtime/control-plane checks; 6/6 critical checks true and 10/10 noncritical checks passed.
- Exercised bounded concurrency, cooperative cancellation, timeout, bounded retry, idempotency replay and collision rejection, permission denial, unauthorized handoff rejection, memory isolation, pending/approved knowledge, outcome capture, version promotion, rejection and rollback.

## Historical benchmark scope

The default mock benchmark checks routing, provenance handling, tool-availability truthfulness, background-service truthfulness and high-stakes permission gates. It explicitly **does not measure semantic LLM answer quality**. Promotion tests exercise the evaluation gate using controlled `EvaluationReport` fixtures; no real-model candidate improvement was measured.

## Historical v7.0 failures encountered and recovery

- Initial 36-test run: 2 failures due to a case-sensitive capability assertion and missing thousands separators in inventory text; corrected.
- A subsequent package test used an incorrect ZIP-entry minimum; corrected to match the actual package inventory. The v6 source ZIP check was then decoupled from v7 package validity: it validates the v6 archive if explicitly supplied (`UNEXPECTED_V6_FIXTURE`) and otherwise skips with an explicit reason.
- The checksum test initially attempted to parse its comment header as a hash row; corrected.
- The enriched crosswalk run exposed two additional defects: the Markdown crosswalk did not format stable IDs as code, and concurrent first invocations could race while seeding the baseline agent version in SQLite. The crosswalk IDs were corrected and baseline seeding now starts an immediate SQLite transaction.
- Final post-change run: **44 passed, 0 failures, 0 errors, 1 explicit skip**. The concurrency regression test passed. The v7 package integrity test passed against the canonical archive.

## Historical v7.0 not run / not verified (not counted as passes)

- No live provider API call; the real adapter was tested only for missing-config fail-closed behavior and secret-safe error reporting.
- No live semantic benchmark against a real model, external connector/action test, or production load test.
- No hosted deployment, always-on process, scheduler or notification delivery.
- No production approval-identity connector; v7.0 did not authenticate the caller-supplied approval context. v7.3.0 introduces the host verifier interface, but the production identity authority remains unconfigured.
- Library upload/read-back remains separate from local package verification; no claim is made that the canonical archive is installed in Library or Project settings.
- Account-wide Custom Instructions were not changed and ChatGPT Project installation was not confirmed.

## Historical v7.0 release classification

**Locally release-ready as a mock-tested runtime scaffold with one optional v6-fixture check skipped. Not production-deployed, not live-provider-verified, and not installed persistently in the ChatGPT Library/Project.**


## Historical v7.3.0 release verification

- **Automated tests:** 76 run; 75 passed, 1 skipped, 0 failures, 0 errors. Command: `UNEXPECTED_PACKAGE_ZIP=/mnt/data/uneXpected-v7.3-release/uneXpected_v7.3_governed_runtime.zip python -m unittest discover -s tests -v` from the package root. The one skip is the optional v6 source ZIP test; the exact fixture was not supplied and the test was not weakened or removed.
- **Compilation:** `python -m compileall -q unexpected_runtime tests` passed.
- **CLI status:** `7.3.0`, 38 roles, deterministic mock, local runtime scaffold; external connectors are not configured and background service is not running unless separately hosted.
- **CLI list:** reported 38 roles. **CLI run:** orchestrator returned `completed` with a deterministic mock result. **CLI eval:** fixed benchmark score `1.0`, 6/6 critical checks true, 10/10 noncritical checks passed.
- **Package integrity:** `unzip -t` reported no errors; structural package-integrity test passed against the v7.3.0 release ZIP; sidecar `sha256sum -c` passed. ZIP contains 93 entries and its internal SHA-256 file inventory covers 92 other package files.
- **Release artifact:** `uneXpected_v7.3_governed_runtime.zip`; its adjacent `.sha256` sidecar was verified with `sha256sum -c`.
- **Rollback artifact:** original v7.0 source ZIP passed its original SHA-256 sidecar check; it remains unchanged.
- **Limitations:** the mock benchmark verifies runtime/control-plane contracts only, not semantic model quality. No production `ApprovalVerifier`, live model provider call, TAAFT/MCP adapter, external integration, hosted service, deployment, Library save/read-back or ChatGPT Project activation was exercised.


## Current v7.3.1 stabilization CI — 2026-11-01

- **Merged main commit:** `cdef6c263cbf44f0739a2b90070ec58059aca9a2`.
- **Pre-merge PR CI:** run #32 (`41290438435`) passed on `6b3ea2568b50e9e179f2a21f8f2aa7cc6d26d474`.
- **Post-merge main CI:** run #33 (`41290628188`) passed on `cdef6c263cbf44f0739a2b90070ec58059aca9a2`; all workflow steps passed.
- **Regression suite:** 125 tests run; 124 passed; 1 optional v6 source-archive fixture test skipped; 0 failures and 0 errors.
- **Compilation, package integrity, SHA-256 inventory and CLI smoke tests:** passed.
- **Runtime contract benchmark:** score 1.0, 8/8 critical checks and 11/11 noncritical checks passed. Provider mode: deterministic mock; semantic model quality is not measured.
- **Separate Render test host:** deployed the same source tree and returned HTTP 200 at `/health`. API routes tested without credentials returned 401 as expected. No authenticated or paid model request was made.
- **Production gates still open:** live provider/TAAFT verification, persistent runtime and approval-ledger storage, trusted reviewer/approval replay tests, enforced CODEOWNERS ruleset, production deployment and backup/restore drill.
