# Changelog

## v8.1.1-preview — Governed tools, isolated subagents and resumable trace reads (2026-11-03)

- Adds an in-process MCP adapter gateway with provenance-matched capability descriptors, explicit enabled-state checks, role scopes, permission checks, bounded JSON inputs/results, cooperative deadlines and redacted audit metadata; privileged tool scopes remain blocked pending durable approval/replay verification. No remote MCP transport or external MCP server is configured.
- Adds bounded specialist child runs through the Coordinator and authenticated API. Each child has a separate task ID, explicitly supplied input, persisted parent-task lineage, deterministic idempotency key and bounded summary; parent approvals do not grant child privileges.
- Adds ordered, task-scoped event cursor reads for SQLite and PostgreSQL through authenticated GET /v1/tasks/{task_id}/events. Reconnect reads persisted events and never repeats the original task.
- Adds a basic command-center trace panel with cursor-based older-event loading; raw event payloads are not displayed in the UI.
- Adds regression tests for tool gating, provenance mismatch, role scope, input/output limits, child isolation, handoff scope, depth/child-count limits and cursor continuation.
- Draft feature PR #15 only. No merge, Render deployment, live MCP server connection, scheduler activation, or consequential execution is included.

## v8.1.0-preview — Verified Skill bundles (2026-11-02)

- Extends the existing local SHA-256-pinned Skill registry with backward-compatible manifest v2 bundle metadata.
- Adds mapped-role `automatic`, `user_invocable`, and `always_apply` selection with bounded context/resource limits.
- Verifies main Skill and bundled resources; only main Skill and reference text are injected, while scripts/assets remain inert.
- Adds authenticated `/v1/skills` discovery and optional `skill_ids` on `/v1/invoke`; requested Skill IDs are persisted and bound into idempotency and approval action digests.
- Declared tool IDs remain metadata only; no MCP server, external tool, or new capability is installed or authorized by this change.
- Draft feature branch only; no merge, deployment, privileged execution or production activation is included.

## v8.0.0-preview — Single Command Center (2026-11-02)

- Consolidates the governed Python runtime and desktop command center into one Python application and one public API.
- Excludes the previous phone/PWA app and separate Node.js AI Studio gateway from the v8 target.
- Adds authenticated command-center views and APIs for the 38-role registry, tasks, lifecycle events, providers, capabilities, governance, audit and improvement proposals.
- Adds native Anthropic, OpenAI and OpenRouter provider routes with immutable per-task selection and bounded provider connectivity tests.
- Adds atomic single-flight idempotency claims and a PostgreSQL state-store adapter.
- Adds a PostgreSQL one-use approval ledger and additive migration 002; consequential execution remains disabled pending full backup/restore and activation verification.
- Adds one Python Docker image and a free Render preview Blueprint; existing services remain untouched.

**Preview only:** no production cutover, old-service retirement, paid resource, provider secret migration or consequential execution activation is included.

# uneXpected v7.3.1 Changelog

## 7.0.0 — Unified local runtime scaffold

- Preserved all 37 legacy specialist profile files as read-only source material; mapped each to one canonical v7 spec.
- Added one distinct `self-improvement-governor` role, for 38 canonical active roles total. The existing orchestrator remains responsible for task routing; the governor is responsible for benchmark-gated version changes.
- Mapped 120 current README-linked upstream candidate directories to canonical roles as workflow capabilities rather than cloning them into additional agents. Five legacy roles have no direct README-entry mapping but remain active because their responsibilities are distinct.
- Added per-agent specs and manifest, Markdown/CSV/JSON catalogs, consolidated index, v6 migration crosswalk, source manifest, capability matrix, threat model, architecture, install/deploy/migration/rollback guidance, and global/Project instruction drafts.
- Added standard-library Python runtime with SQLite task queue, event/audit log, per-agent memory namespaces, provenance-tagged reviewed shared knowledge, typed handoffs, DAG execution, bounded worker/provider pools, deadlines, cooperative cancellation, retry limits, idempotency payload checks, cycle/budget guards, provider abstraction, deterministic mock and optional environment-configured OpenAI-compatible adapter.
- Added four-scenario runtime-contract benchmark runner and governed outcome/proposal/evaluation/promotion/rollback loop. Protected-change text is conservatively detected and still requires a human-approval flag; this CLI does not authenticate the approver.
- Historical v7.0 test record: 44 tests passed, 0 failed, 0 errors, and 1 optional v6 fixture test skipped. The final post-change run retained that single explicit skip; it was not removed or counted as a pass.
- During crosswalk enrichment, a regression run found a Markdown stable-ID formatting mismatch and a SQLite baseline-seeding race under concurrent first invocations; both were corrected and the concurrency test passed.
- Not deployed or connected: real provider, web/browser tools inside this runtime, third-party connectors, hosted background service, scheduler, notifications, ChatGPT Project installation, global Custom Instructions activation, and Library persistence.

## Build recovery notes

Early test rounds exposed a case-sensitive capability assertion, number-format mismatch, incorrect ZIP-entry threshold and checksum-header parsing. Each was diagnosed and corrected. The historical v7.0 post-change suite completed with zero failures/errors and one optional v6 fixture skip; see `TEST_RESULTS.md`.


## 7.3.0 — Governed workflow and capability upgrade

- Added a local hash-pinned workflow-skill registry for creative-media, skill-engineering and self-improvement context. Supplemental profiles remain outside `agents/`; the canonical registry still contains exactly 38 roles. Skill text is injected only for a mapped role and matching trigger, with a fresh SHA-256 check before provider dispatch.
- Added a provenance-aware capability registry backed by an additive SQLite table and audited lifecycle events. Records are metadata only; no external capability is executed by registry transitions. The `enabled` state requires an explicitly registered adapter verifier.
- Replaced caller-asserted approval flags with an `ApprovalVerifier` host interface and canonical action-digest binding. Privileged actions default to deny. Durable queued privileged actions remain denied until a host can persist and revalidate an approval reference.
- Bound improvement baselines and candidate evaluations to active-version, instruction and report fingerprints. Promotion now rejects stale baselines and records benchmark/scenario IDs, candidate hashes and approval state in the persisted evaluation report.
- Runtime package version is `7.3.0`. The default provider remains deterministic mock; no real provider, TAAFT adapter, external service, hosted scheduler, account integration or production approval authority is activated by this release.
- The historical v6 archive remains an optional test fixture; its integrity test is retained and skips only when that fixture is not supplied.


## 7.3.1 — GitHub-backed approval verifier

- Added read-only GitHub PR review verification against a request JSON file in the exact reviewed head commit.
- Enforced trusted reviewer allowlisting, current repository admin permission, no self-approval, same-repository head, open non-draft PR, fixed base branch, exact permission and action digest, freshness and stale-review rejection.
- Added atomic SQLite one-use consumption so verified approval references cannot be replayed.
- Coordinator auto-wires the verifier only when the required host environment variables exist; otherwise privileged actions remain fail-closed.
- Added a repository Actions workflow to create bot-authored, reviewable approval-request PRs without exposing a write token to the runtime.
- No production token or hosting secret is included in the package.


## 7.3.1 — GitHub trusted approvals and canonical integration readiness

- Added a concrete read-only GitHub REST approval verifier. Approval is tied to an immutable request document at the exact PR head commit and a current approval from a configured trusted repository administrator.
- Restricted approval PRs to the `approval-requests/<proposal_id>` head branch and `github-actions[bot]` author; fork PRs, self-approval, stale commits, later trusted reviews that invalidate the approval, wrong action digests, missing scopes and replay are denied.
- Added read-only token environment configuration. No token or host secret is bundled; a configured-looking environment variable is not live connection evidence.
- Added a manual, owner-gated Actions workflow to generate approval request PRs and a CI workflow to run the full suite and CLI smoke checks.
- The single-use SQLite ledger is supported only on one active runtime instance with persistent storage; horizontal scaling requires a shared transactional ledger.
- No deployment, production token configuration, branch-protection ruleset or live approval workflow run is claimed by this package build.
