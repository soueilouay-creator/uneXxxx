# Package Status — uneXpected v7.3.1

- **Canonical active roles:** 38 — 37 preserved legacy roles plus one new self-improvement governor. The count is derived from the manifest and unique responsibilities, not a target quota.
- **Candidate inputs:** 120 current README-linked upstream workflow directories mapped to canonical roles as workflow capabilities, not 120 additional active agents. Five legacy roles have no direct README-entry mapping but remain active because their responsibilities are distinct.
- **Migration detail:** all 120 workflow cards include item-specific source, description, inputs, procedure, output, acceptance checks, safety boundary and dependencies in the v6→v7 crosswalk.
- **Runtime:** standard-library Python scaffold with SQLite task queue/state/audit, typed handoffs and task DAG, bounded worker/provider pools, deadlines, cooperative cancellation, bounded retries, idempotency request-hash checks, cycle/budget guards, isolated per-agent memory, provenance-tagged human-reviewed shared knowledge, deterministic mock provider, optional environment-configured OpenAI-compatible adapter, four-scenario contract benchmark runner, hash-pinned local workflow skill context, provenance-aware metadata capability registry, host-verifier/action-bound privileged authorization, evidence-fingerprinted improvement proposals, stale-baseline rejection, and governed promotion/rollback.
- **v7.3.1 verification:** see the release verification record in `INSTALL_TESTS_STATUS.md` and `TEST_RESULTS.md`; the optional v6 archive fixture is not bundled and its test remains skipped.
- **Canonical release archive:** `uneXpected_v7.3.1_governed_runtime.zip` is the governed 38-role Python runtime for this release; the original `uneXpected_v7_unified_runtime.zip` remains the untouched v7.0 rollback source. The previous 35-role Node.js archive is noncanonical and must not be distributed under the canonical name. The structural suite validates the canonical ZIP when `UNEXPECTED_PACKAGE_ZIP` is set; `FILE_INVENTORY_SHA256.txt` lists hashes for all other package files. The adjacent `.sha256` sidecar is the authoritative release archive checksum.
- **Provider:** deterministic mock remains the default for CLI and CI tests. The Render test service reports its AI Studio gateway token configured, but no authenticated invocation or real OpenAI/Claude/OpenRouter response has been verified; configuration presence is not live verification.
- **External capabilities:** web/browser actions inside this runtime, third-party connectors, live trade/payment/mail/publishing/repository writes/deletion/deployment, hosting, scheduler and notifications are not configured. Permission names do not create tools.
- **Library:** persistent Library upload/read-back is not confirmed; GitHub merge and local/package verification do not imply Library persistence.
- **Global Custom Instructions:** v7 draft only; not changed by file tools. **Project installation:** not confirmed. **Hosted/background service:** not deployed.
- **Approval boundary:** the package includes `GitHubPullRequestApprovalVerifier` and `approval_verifier_from_env()`. It remains disabled until a host configures a read-only GitHub token, an exact repository allowlist, trusted reviewer identities and durable ledger storage. Without those valid settings, privileged actions and protected promotion/rollback remain denied.


## v7.3.0 local release status

The v7.3.1 archive includes GitHub-backed approval-verifier code and a manual approval-request workflow. The verifier is not operationally connected until its read-only token, exact repository allowlist, trusted reviewer identities, protected base branch and persistent ledger are configured and live approval/revocation/replay tests pass. The runtime remains a separate local scaffold; the GitHub/Render test service is not proof that production approval authority is enabled.


## Current v7.3.1 stabilization state — 2026-11-01

- **Repository:** PR #2 merged to `main` at `cdef6c263cbf44f0739a2b90070ec58059aca9a2`. The release remains v7.3.1; no new major architecture or role expansion was introduced.
- **CI:** pre-merge run #32 and post-merge main run #33 both passed. The full suite ran 125 tests: 124 passed and one optional historical v6 fixture test skipped. Compilation, package integrity, SHA-256 inventory, CLI smoke tests and fixed runtime-contract benchmark passed.
- **Benchmark:** deterministic-mock runtime/control-plane score 1.0, 8/8 critical and 11/11 noncritical checks. This is not a real-model quality evaluation.
- **Runtime test deployment:** `unexpected-v731-runtime-test` on Render, source branch `integration/v7.3.1-governed-runtime`, deployed commit `6b3ea2568b50e9e179f2a21f8f2aa7cc6d26d474`. Health returned HTTP 200 for v7.3.1; gateway and runtime authentication were reported configured; privileged actions remained fail-closed. Unauthenticated status and invoke routes returned HTTP 401.
- **Persistence:** Render Free has ephemeral storage. Do not enable production privileged actions or rely on its SQLite approval ledger for replay prevention across restarts.
- **Governance:** the repository `CODEOWNERS review` ruleset is present but disabled. Required code-owner review/branch protection remains to be enabled and verified.
- **Live integrations:** no authenticated API invocation, live provider completion, TAAFT operation, positive/revoked/replay approval test, production backup/restore or production deploy has been verified.
- **Activation:** Library save/read-back, Global Custom Instructions active state and ChatGPT Project installation remain unconfirmed.
