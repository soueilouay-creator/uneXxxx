# Capability matrix — uneXpected Unified

This matrix describes the public `main` source tree, not a live hosted service. It distinguishes definitions, code, runtime registration and external authorization. A successful test/build does not prove live provider access or deployment.

## Registry and command center

| Capability | Repository status | Verified scope / boundary |
|---|---|---|
| Unified command center | Implemented | One Python HTTP application, one Coordinator, one API boundary and one desktop web UI. No second gateway process or phone/PWA application. |
| Specialist agents | 38 canonical role profiles | Imported v7 registry; roles are runtime-selected specifications, not 38 independent model servers. |
| Skills | 3 active Skills | Hash-pinned manifest, role scope, invocation modes and content digests. Skill instructions do not grant permissions or install tools. |
| Workflow Studio | Implemented | Seven-stage command-center lifecycle, searchable/filterable workflow catalogue and recent task records with links to persisted traces. |
| Workflow catalogue | 120 mapped workflow candidates | Imported from the v6→v7 crosswalk with source provenance, role mappings, inputs, procedures, deliverables and acceptance checks. All are explicitly **mapped, not runnable** until separately implemented and tested. |
| Live task traces | Implemented | Authenticated event-cursor reads and UI trace access read persisted events; reconnecting never re-executes a task. |
| Subagent delegation | Implemented, bounded | Up to 3 sequential child tasks, bounded depth/steps/deadlines and isolated supplied inputs. No parallel child queue or inherited privileged approval. |

## Runtime and integration boundaries

| Capability | Repository status | What remains unverified or unavailable |
|---|---|---|
| Provider adapters | Code implemented | Mock, OpenAI, Anthropic, OpenRouter and OpenOx adapters are present. The Blueprint defaults to mock. No live provider credentials or live model invocation have been verified for a new service. |
| PostgreSQL state | Adapter and migrations implemented | Migration 001 defines the baseline; migration 002 adds transactional idempotency claims. The connected Neon Free project's default branch currently reports schema versions 1 and 2, but no Render service is connected to it. |
| SQLite state | Local development only | Render Free web services have ephemeral filesystems; do not use SQLite as hosted durable state. |
| Approval verifier | Code implemented, inactive | GitHub PR-review verifier and PostgreSQL one-use ledger exist. Its token, repository allowlist and trusted reviewer configuration are not present in a deployed service. |
| Replay protection | PostgreSQL adapter and tests implemented | Durable idempotency claims are schema-backed; a hosted end-to-end deployment/restart/replay test remains outstanding. |
| Consequential actions | Denied by default | Publishing, payments, external messages, account changes, destructive writes and protected deployments remain disabled until the trusted approval and recovery controls are verified. |
| MCP adapter boundary | Implemented in-process | `GET /v1/mcp/tools` lists only registered adapters. The current registration count is zero; no remote MCP transport, server discovery or third-party MCP server is connected. |
| Research and browsing | Not wired into runtime | The resource catalogue is a provenance-aware discovery index. Web/current-source search is not wired into this runtime; ChatGPT web/search tools do not automatically become uneXpected runtime tools. |
| Browser, CRM, email and external connectors | Not configured | No connector is registered or authorized in the new runtime. |
| Scheduler and background workers | Not configured | No always-on scheduler, queue worker or autonomous recurring action is deployed. |
| Image, video, voice and music generation | Planning only inside this runtime | External generation services are not connected or authorized by the new deployment. |
| Quality evaluation | Offline contract and regression foundation | CI tests deterministic fixtures. They are not live-model quality measurements. |
| Self-improvement | Governed proposal foundation | Outcomes and proposals are recorded; protected changes require benchmarks, human review and rollback. No silent self-modification. |

## Hosting and recovery status

- The Render Blueprint defines one Free Docker web service with `autoDeploy: false`, `/health` and mock provider mode.
- As inspected on 2026-11-03, **no Render service is currently linked to this repository**. The existing Render services still point to older repositories and were left unchanged.
- The connected Neon project is on its Free plan. Its default branch has schema versions 1 and 2, and a manual pre-migration snapshot exists.
- The Neon project's current history-retention setting is 6 hours. The snapshot schedule is empty; no automatic snapshot schedule or independent export destination was verified.
- A live Render deploy, live provider call, external MCP registration, full restore rehearsal from the stored snapshot, and end-to-end trusted-approval verification are not claimed.

## CI evidence

The verified `main` commit `67d2587af7eee08e14c8c80acfeacff897170f0b` passed GitHub Actions run [41640135070](https://github.com/soueilouay-creator/uneXxxx/actions/runs/41640135070): 258 tests ran, then the Docker image built, the actual container booted and passed API smoke checks, and CLI smoke tests passed. One optional historical archive fixture was skipped because that archive was not present. This evidence applies to that exact source commit, not to Render deployment or live integrations.

## Operating rules

1. A role, Skill, workflow record or capability descriptor is not proof of a running worker or installed integration.
2. A tool can execute only after provenance, role scope, capability status and permissions have been verified.
3. Approval must be bound to the exact action digest and consumed once in durable storage.
4. A timeout is not a retry signal; retries and delegation remain bounded.
5. Mock mode is not live AI-provider evidence.
6. No hosted service, external connector or consequential execution is considered active until its live state is independently verified.
