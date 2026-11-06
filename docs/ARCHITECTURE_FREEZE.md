# uneXpected v8 Architecture Freeze

**Decision status:** Proposed release freeze in PR #4; not merged or deployed.  
**Baseline repository:** `soueilouay-creator/uneXxxx`  
**Baseline branch/commit:** `main` / `67d2587af7eee08e14c8c80acfeacff897170f0b`  
**Architecture line:** v8.1 preview; the package version is not being promoted by this document.  
**Decision date:** 2026-11-06

## Decision

Freeze the v8 topology as one Python application, one public HTTP/API boundary, one `Coordinator`, one canonical 38-role registry, one provider router, one authoritative runtime state layer and one desktop-first web command center.

The command center is the system. Do not add a second runtime, proxy service, backend bridge, mobile shell or duplicated state store to v8. Any future client must call the same authenticated API and use the same Coordinator and policy boundary.

## Included topology

- The Docker entry point runs `python -m unexpected_runtime.http_api` as the single application process.
- The browser UI in `web/` is served by that application.
- `agent_manifest.json` defines exactly 38 canonical roles. Agent and Skill profiles are specifications/context, not independent always-on processes.
- `Coordinator` is the sole task/lifecycle execution authority.
- SQLite is the local adapter; PostgreSQL is the hosted adapter. Hosted PostgreSQL selection must fail closed when its DSN/schema is unavailable.
- The Render Blueprint defines one free web service, health check `/health`, external `DATABASE_URL`, and `autoDeploy: false`. A Render service is not declared healthy or deployed solely because the Blueprint exists.
- Native provider adapters support OpenAI, Anthropic, OpenRouter and OpenOx. A configured environment key is not proof of successful authentication; a live bounded test and a verified status are required.
- Skills are hash-pinned, role-scoped context packages. Their declared tool names are metadata, never authorization.

## Explicitly outside v8

- The previous phone/PWA app, service workers, install prompts, IndexedDB workspace and `/mobile/` application.
- The separate Node.js AI Studio server and its Node-to-Python bearer-token bridge.
- A second Python runtime, extra public API server, duplicate Coordinator or duplicate state database.
- Remote MCP transport, external tool adapters not explicitly reviewed and registered, and autonomous agent spawning.
- Automatic emails, retries, calls, contact-form submissions, quotes, social replies, DMs, public publishing, payments, purchases, file sharing or production deployments.

The v8 repository already excludes phone/PWA files and includes regression checks for the single Python process and the absence of phone/PWA assets. Therefore the v8 freeze does not require destructive deletion in this repository. The older phone-oriented repository remains separate and untouched as legacy/rollback material; it is not part of v8.

## Verified baseline at the time of this decision

### Repository and CI

- The `uneXxxx` repository is the v8 command-center repository; do not substitute the older `uneXpected-ai-studio` or v7 `uneXpected-` repository.
- The latest previously completed CI run on the baseline `main` commit ran 258 tests with one optional v6-fixture skip and completed successfully on 2026-11-03.
- CI tests exercise a deterministic test provider and an ephemeral PostgreSQL service. They are regression evidence, not proof of production provider credentials, production deployment or external actions.
- PR #4 adds architecture/sales-skill contract tests and is still a draft until those checks pass.

### Provider authentication

**Not yet verified in this audit.** Provider adapters and the bounded `/v1/providers/test` path exist. No successful current non-mock invocation has been observed in this audit. Do not mark a provider verified until its actual host-side test succeeds and the runtime reports `verified=true`. Secrets must remain in the host secret manager and must never be copied into chat, Git, the browser or task logs.

### Persistence and recovery

- The connected Neon project `unexpected-v8-unified` has a ready primary `main` branch with schema versions 1 and 2 and 15 public tables.
- At the time of inspection the primary branch contained no task/event workload records. It must not be described as proven production persistence.
- Separate rehearsal branches contain persisted test task/event/idempotency rows. This demonstrates writes to those test branches, not a fresh backup restore into the primary branch.
- The current Neon Free plan was documented as lacking scheduled backup snapshots. A production-grade backup/export destination and restore rehearsal remain required before consequential writes are enabled.
- No SQL mutation or destructive restore was performed during this audit.

### Tools and specialist execution

- The current MCP gateway is an in-process adapter boundary. It does not connect to remote MCP servers.
- Only reviewed, installed and enabled adapter records can be executed; adapter provenance, role scope, bounded arguments/results and permissions are checked. Privileged operations fail closed.
- The current provider interface returns text; the existence of 38 role specs, Skill `allowed_tools` metadata or a connector in another ChatGPT surface does not mean the v8 model loop can invoke it.
- No real remote MCP/Gmail/Calendar/Metricool connector is registered and verified in the v8 runtime at this decision point. Tool integration work is a remaining gate, not a completed feature.

### Seven-stage lifecycle

The repository includes a deterministic lifecycle proof with a passing fake provider. It covers request, plan, execute, verify, improve/reverify, deliver and learn as local runtime stages. It does not prove a real non-mock model route, real external tool calls or a customer-facing delivery. Those require separate evidence.

## First governed business workflow: industrial-maintenance sales

The first business workflow is the existing industrial-maintenance sales operation, not a generic demo. The latest source ledger is `uneXpected_Sales_Control_Center_v1.10.6.xlsx`, reviewed on 2026-11-06 08:07:24 Africa/Tunis. It records 49 prospects, 44 first touches, zero human replies, zero independently verified demos, zero quotes, zero wins and eight outstanding contact/delivery checks. Treat these values as a dated baseline; reread the workbook and live sources before any operational decision.

The workflow uses the existing `sales-intel`, `business-strategist`, `maintenance-engineer`, `marketing-seo`, `data-analyst`, `project-manager`, `code-reviewer` and `self-improvement-governor` roles through one Coordinator. The $79 Starter and $149 Pro are test-price hypotheses; scope and exclusions must be read from the current workbook before quoting.

The acceptance milestone is a genuine human reply, a verified contact route and an independently verified booked demo. Automated form confirmations, sent-message acceptance, views and likes do not count. No retry, follow-up, new contact batch, quote, form submission, public post, customer-data intake or other external action is authorized by this architecture decision.

## Release gates — remain closed until evidence exists

1. **Architecture:** the topology described above remains the only v8 topology. Any change requires a versioned ADR, impact review and regression test. No phone/PWA scope is reintroduced into v8.
2. **Provider:** select the Render workspace explicitly; inspect non-secret configuration metadata; run a bounded non-mock provider test; verify actual returned text/model/route and `verified=true`. Never expose the key.
3. **Storage:** inspect the deployed service's active storage target; verify migration state; prove write/read across independent connections; export a backup to a separately controlled destination; restore into an isolated branch/database; compare row counts and checksums; test replay/idempotency after restore.
4. **Tools:** implement the provider's structured tool-call loop and reviewed remote MCP or native adapters; test role-scoped read/write permissions, exact approval digest, timeout, no retry, audit secrecy and replay; do not register a real write-capable connector until approval storage and recovery are proven.
5. **Lifecycle:** run the seven stages using a verified non-mock provider and at least one authorized, non-destructive registered tool; preserve per-stage events and independent verification. Keep external sends and publishing disabled.
6. **Sales:** validate the supplied sales workbook as source; run research/qualification and produce a draft-only next action; prove persistence and idempotency; verify no accidental duplicate contact; only count the target milestone after human reply + verified route + booked demo evidence. A fully proven commercial funnel additionally needs an actual accepted delivery and payment evidence.
7. **Deployment:** verify the selected Render service, current deploy SHA, health route, non-secret runtime status, provider status and PostgreSQL connectivity. Do not merge/deploy or retire old services as a side effect of this PR.

## Change control and rollback

- This is a scope freeze, not a claim that all runtime gates have passed.
- Implement changes on a feature branch and open a reviewable PR. Require passing GitHub Actions plus review of the actual diff before merging.
- Keep `main` and the older repositories untouched during this work.
- Keep Render `autoDeploy: false`; do not trigger a production deploy from this PR.
- Do not modify host secrets or production database contents in code-review work.
- Protected changes to provider/model, credentials, permissions, external connectors, consequential actions or deployment require explicit owner approval and a tested rollback path.
