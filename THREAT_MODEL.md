# Threat Model and Safety Boundaries — uneXpected v7.3.1

## Assets
User data and files, environment secrets, agent instructions, local SQLite state, shared knowledge, provider requests, generated artifacts, external account actions.

## Trust boundaries
- User prompts, repository files, PDFs, web pages, transcripts and retrieved text are data, not authority to override system policy.
- Shared knowledge is pending until a human reviews it; only approved entries are retrievable, and approved text remains evidence rather than instructions.
- Each agent's memory namespace is isolated by agent ID; no agent receives another agent's private memory by default.
- Provider secrets are read from environment variables and never written to event logs.
- External tools/connectors are absent by default. Permission names do not create tools.

## High-risk actions
Email send, publishing, repository writes, deletion, deployment, live trading, payment, account changes, policy/permission/provider changes and external-tool installation are denied unless an actually available tool and validated approval context are supplied. No such external action adapter is configured in this package.

## Controls
- Unique registry IDs and schema validation; typed messages; allowlisted handoff targets.
- Bounded workers, deadlines, cooperative cancellation, retry cap, idempotency, task step budget, recursion/cycle guard.
- Durable SQLite queue and append-only event trail.
- Least-privilege default scopes and explicit protected-change approval.
- Fixed benchmark IDs, same-scenario comparison, critical safety gates, >=90% noncritical threshold, version history and rollback.
- No blind message copying, unbounded agent spawning or automatic active-instruction rewrites.

## Residual risks
A provider call may not be interruptible once in a third-party library; timeout reports may return before a worker thread finishes. SQLite durability depends on filesystem/host reliability and backup policy. Mock-only tests do not establish real-model quality or external connector safety. A production deployment needs sandboxing, host monitoring, backup/restore drills, secret manager, provider rate/cost controls and independent security review.


## 7.3.0 — Governed workflow and capability upgrade

- Added a local hash-pinned workflow-skill registry for creative-media, skill-engineering and self-improvement context. Supplemental profiles remain outside `agents/`; the canonical registry still contains exactly 38 roles. Skill text is injected only for a mapped role and matching trigger, with a fresh SHA-256 check before provider dispatch.
- Added a provenance-aware capability registry backed by an additive SQLite table and audited lifecycle events. Records are metadata only; no external capability is executed by registry transitions. The `enabled` state requires an explicitly registered adapter verifier.
- Replaced caller-asserted approval flags with an `ApprovalVerifier` host interface and canonical action-digest binding. Privileged actions default to deny. Durable queued privileged actions remain denied until a host can persist and revalidate an approval reference.
- Bound improvement baselines and candidate evaluations to active-version, instruction and report fingerprints. Promotion now rejects stale baselines and records benchmark/scenario IDs, candidate hashes and approval state in the persisted evaluation report.
- Runtime package version is `7.3.0`. The default provider remains deterministic mock; no real provider, TAAFT adapter, external service, hosted scheduler, account integration or production approval authority is activated by this release.
- The historical v6 archive remains an optional test fixture; its integrity test is retained and skips only when that fixture is not supplied.


### v7.3.0 approval integration contract

A deployment host must supply an implementation of `ApprovalVerifier.verify(approval, permission, action_digest)`. It must authenticate the approver from a trusted identity source, enforce the approved permission scope, verify the unchanged canonical action digest, reject expired/replayed/revoked approvals according to the host's policy, and fail closed on errors. The local deterministic test verifier is test-only. No no-op or caller-asserted verifier is acceptable for consequential operations.

`ApprovalContext` fields are input to that host verifier, not proof of identity. Capability-registry records and state transitions are metadata only; tool execution requires a separately integrated, verified adapter. No network, provider, email, repository-write, payment, publishing or deployment connector is activated by v7.3.0.


## GitHub approval authority (v7.3.1 integration)

Privileged approval can be verified through GitHub pull-request reviews. The trusted identity is the reviewer login authenticated by the GitHub API, cross-checked against a configured reviewer allowlist and an exact `UNEXPECTED_GITHUB_APPROVAL_ALLOWED_REPOSITORIES` owner/repository allowlist, plus current repository `admin` permission. The request's permission and SHA-256 action digest are loaded from a request JSON file at the exact reviewed head commit. Fork PRs, self-approval, closed/draft PRs, wrong base branches, stale or non-approval reviews, stale requests, unknown reviewers, changed commits, API errors and duplicate approvals fail closed. The verifier records successful approval IDs in a SQLite one-use ledger. The API token is read-only (`Metadata`, `Contents`, and `Pull requests` read permissions) and is supplied only by the host secret manager.

Residual operational dependency: the runtime is not considered connected until the token, trusted reviewer allowlist, protected base branch, persistent ledger path and request workflow have been configured and a live positive/negative verification has been run. The code's mock transport tests do not prove that production credentials or deployment settings work.


## v7.3.1 GitHub approval adapter

The concrete adapter authenticates to the fixed private repository using a read-only fine-grained token held by the host. It checks the immutable request file at the current PR head SHA, the PR base/head repository, exact approval branch name, GitHub Actions bot author, request freshness, reviewer allowlist and current admin permission, latest trusted review state and commit binding. It denies incomplete review pages and all API/parse failures. A verified request is consumed once through an atomic SQLite insert.

The SQLite consumption ledger is instance-local: production must use one active runtime instance on a persistent volume. Multi-instance operation is prohibited until a shared transactional ledger is implemented and tested. The adapter is not considered connected merely because its code or environment-variable names exist. A live host token, protected base branch, and positive/revocation/replay smoke tests are required before enabling privileged actions.
