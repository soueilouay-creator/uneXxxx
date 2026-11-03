# StarNet pattern adaptation for uneXpected

This document records the architecture patterns studied from the public StarNet project and how they are adapted to uneXpected. It is an implementation note, not a claim that StarNet itself is installed or running inside uneXpected.

## Patterns adopted

| Pattern | uneXpected implementation |
| --- | --- |
| Truthful runtime telemetry | The command center reflects persisted task/event state; a role is not shown as running merely because its profile exists. |
| Capability-scoped tools | The capability registry, role scope, source provenance and permission policy gate each adapter call. |
| Informed consent | Consequential actions require a host-verified approval bound to the exact action digest; absent or invalid approval fails closed. |
| Bounded specialist runs | Child runs use explicit inputs, independent task IDs, role checks, deadlines and parent lineage. Parent approval does not elevate child permissions. |
| Reconnectable event history | Task event cursors read durable history after a cursor; reconnecting does not enqueue or repeat execution. |
| Skill lifecycle | Skills are hash-pinned and loaded progressively. Skill metadata never grants tools; script and asset files remain inert. |
| Work accounting | Execution limits, idempotency, task history and provider status are kept distinct from estimates or unverified claims. |
| Deliverable handoff | Completed artifacts are surfaced as task outputs rather than buried only in conversation history. |

## Deliberately not copied

- StarNet's product name, logo, sprites, pixel-art station, UI artwork or trademarks.
- Its local-first desktop packaging, Tauri/Rust shell, local Node sidecar or a second execution runtime.
- Any provider credential, account state, private workspace, or third-party connector configuration.
- Automatic execution permissions, scheduled away-work or remote MCP connectivity.

uneXpected remains one Python application with one Coordinator, one role registry, one permission boundary, one provider router and one authoritative storage interface. SQLite is for local development; hosted shared state requires a configured PostgreSQL service and tested migrations/recovery.

## Source references

- StarNet public README: https://github.com/androoAGI/starnet/blob/feat/harness-backend/README.md
- StarNet code map: https://github.com/androoAGI/starnet/blob/feat/harness-backend/CODE_MAP.md
- StarNet harness architecture: https://github.com/androoAGI/starnet/blob/feat/harness-backend/docs/HARNESS_ARCHITECTURE.md
- StarNet skill ecosystem: https://github.com/androoAGI/starnet/blob/feat/harness-backend/docs/SKILL_ECOSYSTEM_9.md

The upstream StarNet repository declares MIT for code, while its README separately excludes brand identity and artwork from that license. This adaptation uses independently written design notes and does not copy those assets.
