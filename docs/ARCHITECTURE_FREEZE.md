# uneXpected v8 Architecture Freeze

**Decision status:** Accepted and merged to canonical `main` on 2026-11-06; production deployment pending.  
**Baseline repository:** `soueilouay-creator/uneXxxx`  
**Canonical `main` commit:** `58c604cf55c437248284ed6d499f32715ff65f70`  
**Architecture line:** v8.1 preview; the package version is not being promoted by this document.  
**Decision date:** 2026-11-06

## Scope statements

Phone/PWA is out of scope for v8. Remote MCP is not connected in the current runtime. Live provider verification is historically evidenced for OpenRouter on 2026-11-02, but a fresh provider check on 2026-11-06 has not been completed.

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
- The pre-PR baseline `main` CI run passed 258 tests with one optional v6-fixture skip on 2026-11-03.
- PR #4 was merged into canonical `main` on 2026-11-06 as `58c604cf55c437248284ed6d499f32715ff65f70`.
- GitHub Actions run #47 (`42303544578`) passed on the PR integration ref immediately before the squash merge: 260 tests passed, one optional v6-fixture skipped; PostgreSQL migrations, SHA-256 integrity, Docker build, actual-container health/auth/38-role/task smoke, and CLI smoke all passed.
- CI uses deterministic test providers and ephemeral PostgreSQL. This is regression evidence, not proof of production provider credentials, deployment or external actions.

### Provider authentication

**Historical success, current re-test pending.** The Neon `v8-migration-test` branch contains three `provider_verified` events for OpenRouter (`openrouter/free`) between 2026-11-02 16:47:18 and 19:01:23 UTC, plus 11 `provider_used` events with `mock=false` between 17:23:09 and 19:04:57 UTC. This is direct persisted evidence that the hosted v8 runtime made successful real OpenRouter calls at that time. The same branch contains 13 deterministic-mock calls. It also contains 13 failed OpenOx test events; the recorded diagnostic is HTTP 402 `insufficient_balance`. The latest OpenRouter invocation preceded the final 2026-11-02 19:20 UTC Render deployment, and no fresh authenticated provider test was completed on 2026-11-06. The checked-in Render Blueprint sets `UNEXPECTED_DEFAULT_PROVIDER=mock`, but the service's private environment was not readable through the available Render connector, so its effective current default is unverified. Treat OpenRouter as historically verified, OpenOx as blocked by balance, and all current provider readiness as pending a fresh host-side test. Do not expose credentials or mark a current provider verified without a successful fresh invocation.

### Persistence and recovery

- Neon project `unexpected-v8-unified` primary `main` branch is ready, has schema migration version 2 and 15 public tables, but the inspected `tasks`, `events`, `idempotency_claims`, `consumed_approvals` and `workspace_records` tables all contain zero rows. This branch is not evidence of persisted live workload.
- The `v8-migration-test` branch has migration version 2, 24 completed task rows and 139 events. Its records show 11 real OpenRouter calls, 13 deterministic mock calls and two workflow attempts that both ended `blocked_verification`, with `delivered=false`.
- The primary `main` branch has one manual snapshot, `uneXpected-pre-v8-migration-2026-11-03`, created 2026-11-03 12:56:26 UTC. The branch's automatic snapshot schedule is empty. This snapshot is of the empty primary branch, not of the populated `v8-migration-test` branch.
- Existing rehearsal branches contain one idempotency claim and one consumed approval in `v8-recovery-check`; the child `v8-replay-restore-rehearsal` branch contains the same matching records plus additional test records. This proves branch-copy persistence for those test records, not an independent snapshot restore or off-site backup of the data branch.
- Render reports no Render-managed Postgres instance; the v8 service uses an external Neon connection. The Render service's active `DATABASE_URL` branch cannot be confirmed from service metadata because secret values are not exposed, and were not read.
- A verified backup/export destination and a real restore rehearsal for the populated runtime branch remain release gates. No SQL mutation, snapshot creation or destructive restore was performed in this audit.

### Render workspace inspection — 2026-11-06

The owner confirmed use of the Render workspace `My Workspace` (workspace selection is passed explicitly to each request). Read-only inspection found:

- The existing service is `unexpected-v8-command-center` (`srv-dbk8217b9u1s73ftauig`), Free plan, Frankfurt, one configured instance, health path `/health`, auto-deploy disabled.
- The service is currently configured from repository `soueilouay-creator/uneXpected-`, branch `feat/unified-v8-foundation`, not from this repository `soueilouay-creator/uneXxxx` and not from PR #4.
- Its latest recorded live deployment is `dep-dbke4je7bikc73feu3rg`, commit `d1b54ae0e520ff0e701e2584f46d523c2348f6f0`, finished 2026-11-02 19:20:03 UTC. The deployment commit changed the source-inventory file only.
- Render's service metadata says `not_suspended`, but Render returned no service metrics for 2026-11-06 and no service events after 2026-11-02 19:20 UTC in the inspected range. This is insufficient to assert the app is currently responding.
- The existing PR #11 in `uneXpected-` remains a draft. PR #4 in canonical `uneXxxx` was merged on 2026-11-06. The Render service source has not changed, and no deployment, environment update, service retirement or Render service mutation was performed.
- Render lists no managed Postgres database. The app's intended Neon connection remains external; the service's private environment and bearer token were not read.

**Release implication:** The v8.1 code and sales workflow are merged into canonical `uneXxxx/main` and passed PR CI, but are not deployed to Render. The existing service remains bound to `soueilouay-creator/uneXpected-`. Source rebinding, active database/provider verification, backup/restore proof and a controlled manual deployment remain outstanding. Keep `autoDeploy=false` and retain the existing service and rollback target.

## Tools and specialist execution

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
- Keep Render `autoDeploy: false`; the repository merge did not trigger a production deployment.
- Do not modify host secrets or production database contents as part of the source-repository cutover.
- Protected changes to provider/model, credentials, permissions, external connectors, consequential actions or deployment require explicit owner approval and a tested rollback path.
