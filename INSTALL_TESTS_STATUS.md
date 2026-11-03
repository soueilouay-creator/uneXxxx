# Install / Tests / Status — uneXpected v7.3.1

## Inventory and deduplication
- Upstream repository: `https://github.com/Shubhamsaboo/awesome-llm-apps`, default branch `main`, branch commit `6c16b23f1bacd0fdf240bb5141ef45e59e82c306`, tree object SHA `dfa79289f46826b4b63946e3a13540c9a4c3ea12`, license `Apache-2.0`.
- Fresh README inventory: 120 unique candidate workflow/app directories after excluding the `agent_skills/` category index; 2,541 recursive tree entries, 1,984 blobs, 557 tree objects, 224 README files; no missing linked paths. The recursive-tree endpoint's top-level SHA was inconsistent with the explicit branch `commit.tree.sha`; a direct fetch by the tree-object SHA confirmed the same 2,541 entries.
- Canonical active agents: **38** = 37 legacy specialist roles preserved + one new self-improvement governor. This is the unique-responsibility count backed by `agent_manifest.json`, not a fixed target.
- Legacy disposition: 37/37 original profiles `kept`; no original Library files modified. Five roles without a direct upstream README entry remain active for distinct sales-intelligence, industrial-maintenance, automation-architecture, startup-due-diligence and monitoring-planning responsibilities.
- Migration: all 120 v6 workflow cards mapped to primary and supporting canonical roles. Crosswalk entries retain description, inputs, procedure, expected output, acceptance checks, safety boundary, external dependencies and source URL. Underlying upstream applications are not claimed installed.

## Local runtime and verification
- Executable local Python scaffold: 38-role registry, coordinator/router, SQLite task queue and audit log, typed handoffs, task DAG, bounded worker/provider pools, deadlines, cancellation, retries and idempotency; per-agent memory and reviewed shared knowledge; hash-pinned workflow skills; provenance-aware metadata-only capability registry; host-verifier/action-bound privileged permissions; and evidence-fingerprinted self-improvement with stale-baseline rejection. Deterministic mock remains the default provider.
- v7.0 baseline: 44 passed, 0 failed, 0 errors, 1 skipped. The historical v7.3.0 verification result is retained below for provenance; it is not a test result for the current v7.3.1 PR head.
- Runtime smoke: all 38 agents invoked via mock; CLI single-agent invocation, 3-agent handoff chain, 3-node DAG and four-scenario contract benchmark passed. Benchmark: 6/6 critical and 10/10 noncritical checks; mock runtime contracts only, not semantic model quality.
- Real provider API responses, live TAAFT operations, semantic model evaluation, production deployment, authenticated approval invocation and background scheduling remain unverified. The Render test host reports gateway and runtime API authentication configured, but configuration presence is not a successful provider call.

## Persistence and activation are separate states
- **Historical local files/package:** v7.3.0 archive built and verified locally; original `uneXpected_v7_unified_runtime.zip` preserved as the v7.0 rollback source. See the v7.3 release section below for the current archive hash.
- **Library upload/read-back:** not completed; no v7.3.0 files are claimed saved to the persistent Library.
- **Global Custom Instructions:** draft at `GLOBAL_CUSTOM_INSTRUCTION_V7.md`; not changed by file tools.
- **ChatGPT Project:** draft at `PROJECT_INSTRUCTIONS_V7.md`; installation not confirmed.
- **External connectors/provider:** GitHub read connector used to refresh the upstream source; runtime provider is mock. Real provider and other runtime connectors are unconfigured.
- **Hosted service:** a separate Render Free test service is deployed for v7.3.1 health checks only; it is not a production or always-on agent service. Its filesystem is ephemeral and auto-deploy is disabled.

Install: `INSTALL.md`. Deploy: `DEPLOY.md`. Migration: `UPGRADE_MIGRATION.md`. Rollback: `ROLLBACK_UNINSTALL.md`. Capability and safety limits: `CAPABILITY_MATRIX.md` and `THREAT_MODEL.md`.


## Historical 7.3.0 — Governed workflow and capability upgrade

- Added a local hash-pinned workflow-skill registry for creative-media, skill-engineering and self-improvement context. Supplemental profiles remain outside `agents/`; the canonical registry still contains exactly 38 roles. Skill text is injected only for a mapped role and matching trigger, with a fresh SHA-256 check before provider dispatch.
- Added a provenance-aware capability registry backed by an additive SQLite table and audited lifecycle events. Records are metadata only; no external capability is executed by registry transitions. The `enabled` state requires an explicitly registered adapter verifier.
- Replaced caller-asserted approval flags with an `ApprovalVerifier` host interface and canonical action-digest binding. Privileged actions default to deny. Durable queued privileged actions remain denied until a host can persist and revalidate an approval reference.
- Bound improvement baselines and candidate evaluations to active-version, instruction and report fingerprints. Promotion now rejects stale baselines and records benchmark/scenario IDs, candidate hashes and approval state in the persisted evaluation report.
- Runtime package version is `7.3.0`. The default provider remains deterministic mock; no real provider, TAAFT adapter, external service, hosted scheduler, account integration or production approval authority is activated by this release.
- The historical v6 archive remains an optional test fixture; its integrity test is retained and skips only when that fixture is not supplied.


## v7.3.0 release verification

- **Automated tests:** 76 run; 75 passed, 1 skipped, 0 failures, 0 errors. The single skipped test is the unchanged optional v6 source ZIP fixture check; the exact v6 ZIP was not supplied.
- **Compilation:** `python -m compileall -q unexpected_runtime tests` passed.
- **CLI status:** reports version `7.3.0`, 38 registered roles, `deterministic-mock`, `local-runtime-scaffold`, background service not running unless separately hosted, and external connectors not configured.
- **CLI list/run/eval:** list reported 38 roles; orchestrator mock invocation returned `completed`; fixed benchmark score 1.0 with 6/6 critical checks and 10/10 noncritical checks. This is runtime/control-plane testing, not semantic model-quality measurement.
- **Package integrity:** release ZIP contains 93 entries; `unzip -t` reported no errors. Embedded file inventory verifies 92 package files (excluding itself). SHA-256 sidecar verified successfully.
- **Release ZIP:** `uneXpected_v7.3_governed_runtime.zip`; its adjacent `.sha256` sidecar is verified by `sha256sum -c`.
- **Rollback source:** original v7.0 ZIP checksum was reverified against its original sidecar; source archive was not modified.
- **Approval boundary:** production identity verification is not configured; `ApprovalVerifier` is an injected host contract only. Privileged actions fail closed when no trusted verifier is supplied.
- **TAAFT/MCP:** no Python runtime adapter is included or live-tested; metadata registry records do not execute external tools.
- **Activation state:** local artifact only. No Library upload/read-back, ChatGPT Project installation, Custom Instructions activation, GitHub push or Render deployment was performed.


## Current v7.3.1 stabilization verification — 2026-11-01

- **Merged release source:** PR #2, `Integrate uneXpected v7.3.1 governed runtime`, merged to `main` at `cdef6c263cbf44f0739a2b90070ec58059aca9a2`. The tested PR head was `6b3ea2568b50e9e179f2a21f8f2aa7cc6d26d474`; the merge commit preserves the same source tree.
- **Pre-merge CI:** GitHub Actions run #32 (`41290438435`) completed successfully on the tested PR head.
- **Post-merge CI:** GitHub Actions run #33 (`41290628188`) completed successfully on the actual `main` merge commit. Compilation, package ZIP integrity, regression suite and CLI smoke steps all passed.
- **Regression suite:** 125 tests run; 124 passed and one optional historical v6 archive fixture was skipped because that external archive was not supplied. No failures or errors.
- **Fixed benchmark:** score 1.0; all 8 declared critical checks true and all 11/11 noncritical checks passed. Provider mode was deterministic mock. This measures runtime/control-plane contracts, not semantic LLM response quality.
- **CLI smoke:** status, list and eval commands passed. The registry reported 38 canonical roles.
- **Inventory:** the exact SHA-256 file inventory passed as part of the regression suite, including the final stabilization changes.
- **Render test host:** service `unexpected-v731-runtime-test` (`srv-dbj237m7bikc73e71pf0`) successfully deployed the tested source tree. Public `/health` returned HTTP 200, version 7.3.1, `provider_configured=true`, `authentication_configured=true` and `privileged_actions=fail-closed`. Unauthenticated `/v1/status` and `/v1/invoke` probes both returned HTTP 401.
- **Render limitations:** the test service is Free, has ephemeral storage, has auto-deploy disabled and remains on the integration branch at the tested source commit. It is not production persistence and must not be used for privileged actions.
- **Security governance:** the repository ruleset named `CODEOWNERS review` exists but its enforcement is disabled. The owner must enable and verify required code-owner review and protected-branch checks separately.
- **Still unverified:** no authenticated runtime invocation, live OpenAI/Claude/OpenRouter response, live TAAFT-backed model request, positive/revoked/replay approval cycle, durable-storage restart test, production backup/restore, or production deployment was performed. Provider/API token presence in the health response is not proof of live connectivity.
- **Activation:** persistent Library upload/read-back, Global Custom Instructions activation and ChatGPT Project installation remain separate and unconfirmed.
