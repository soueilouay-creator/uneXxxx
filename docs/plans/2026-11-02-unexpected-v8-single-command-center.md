# uneXpected v8 Single Command Center Implementation Plan

> **For agentic workers:** Use the host's available task-by-task implementation workflow. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver one Python-hosted uneXpected command center that operates the governed 38-role runtime directly, without a separate Node gateway/service or phone app.

**Architecture:** Extend the existing Python HTTP application to serve a desktop web command center and same-origin APIs. The existing Coordinator remains the only execution authority; provider routing, persistent state, permissions, approvals, audit, and workflow lifecycle are integrated into the same process. Neon PostgreSQL is the intended shared store only if the existing project remains within its verified $0 Free limits; privileged actions remain disabled until durable approval/replay and recovery tests pass.

**Tech Stack:** Python 3.10+ standard library runtime, unittest, HTML/CSS/vanilla JavaScript, PostgreSQL via psycopg 3 (production adapter), existing GitHub Actions CI, existing Render host.

## Global Constraints

- Use only the canonical repository `soueilouay-creator/uneXpected-` and the isolated branch `feat/unified-v8-foundation`; do not implement on `main`.
- Preserve exactly 38 canonical roles, IDs, permission scopes, handoff metadata, instructions, skill mappings, provenance, and the seven-stage workflow.
- One production application process and one public service. No separate Node server, no second Python service, no Node-to-Python bridge, and no phone/PWA files, routes, assets, service workers, or tests in v8.
- Reuse desktop command-center concepts only; do not copy the AI Studio phone/PWA implementation.
- All task and lifecycle execution must pass through the existing `Coordinator` and permission policy.
- Keep provider credentials server-side. Never return secret values, include them in logs, or commit them.
- Preserve deterministic mock mode as test-only behavior and distinguish configured, reachable, and verified provider states.
- Maintain the $0 budget. The existing Neon project `tiny-glade-03545028` has a Free-plan-compatible compute configuration, but no scheduled snapshots are configured; its current data tables are empty except for one schema migration row. Do not provision another database or enable paid resources. Re-check quotas and cost before any production configuration.
- Do not activate consequential execution until approvals are authenticated, action-digest-bound, expiring, transactionally one-use, replay-protected, and backed by a tested recovery process.
- Keep the two old Render services and the AI Studio repository unchanged until a preview deployment passes acceptance and rollback is rehearsed. Service retirement is a separate, explicitly confirmed action.
- Do not migrate phone-local IndexedDB data.

---

### Task 1: Unified web shell and authenticated command-center API

**Files:**
- Create: `web/index.html` — desktop command-center shell.
- Create: `web/styles.css` — responsive desktop layout, status states, accessible controls.
- Create: `web/app.js` — browser controller; no provider secrets or policy logic.
- Create: `unexpected_runtime/web_ui.py` — safe static asset resolution and MIME handling.
- Modify: `unexpected_runtime/http_api.py` — serve `/`, static assets, and authenticated command-center read APIs.
- Modify: `unexpected_runtime/coordinator.py` only if a read-only registry/status accessor is needed.
- Modify: `tests/test_gateway_integration.py` or create `tests/test_command_center_api.py`.

**Interfaces:**
- Existing: `create_server(*, coordinator=None, api_token=None, host="127.0.0.1", port=0)`.
- Existing: `Coordinator.status()`, `Coordinator.list_agents()`, `Coordinator.store.events(limit)`.
- Produce: `GET /`, `GET /assets/styles.css`, `GET /assets/app.js`, `GET /v1/agents`, `GET /v1/tasks`, `GET /v1/events`, `GET /v1/capabilities`, `GET /v1/improvements`; all `/v1/*` routes except health require the same bearer auth as current API.
- Produce a JSON status shape containing application/runtime version, registry count, provider status (no secret), storage mode/health, approval state, and explicit degraded/blocked states.

- [ ] **Step 1: Add failing HTTP tests**
  - Assert `GET /` serves the command-center HTML and does not redirect to `/mobile/`.
  - Assert CSS/JS routes serve only known files and unknown asset paths return 404.
  - Assert `/v1/agents`, `/v1/tasks`, `/v1/events`, `/v1/capabilities`, and `/v1/improvements` return 401 without auth and structured data with auth.
  - Assert health is minimal and contains no token, environment variable names, state filesystem path, or provider key.
  - Assert no response includes mobile/PWA/install/service-worker references.
- [ ] **Step 2: Verify red**
  - Run: `python -m unittest tests.test_command_center_api -v`
  - Expected: failures because command-center routes and web assets are absent.
- [ ] **Step 3: Implement the web shell and read APIs**
  - Serve files only from the fixed `web/` directory; reject traversal, encoded traversal, missing files, and directories.
  - Reuse coordinator/store read-only methods; do not let the browser access SQLite/Postgres directly.
  - Build a desktop-first responsive layout with system status, agent registry, workflow/task feed, provider status, integrations/capabilities, approvals, audit, and improvement sections.
  - The UI must show unavailable/unverified/blocked values explicitly and must never imply that a catalog item is connected.
- [ ] **Step 4: Verify focused pass**
  - Run: `python -m unittest tests.test_command_center_api -v`
  - Expected: all new HTTP/static/security tests pass.
- [ ] **Step 5: Run affected regression**
  - Run: `python -m unittest tests.test_gateway_integration tests.test_runtime -v`
  - Expected: existing authentication, request-boundary, lifecycle, and invocation behavior remains green.
- [ ] **Step 6: Commit**
  - `git add web unexpected_runtime/web_ui.py unexpected_runtime/http_api.py unexpected_runtime/coordinator.py tests`
  - `git commit -m "feat: add unified command center web and API"`

### Task 2: Native provider adapters and per-task provider routing

**Files:**
- Modify: `unexpected_runtime/providers.py` — native Anthropic and OpenRouter adapters, provider registry/router, safe status.
- Modify: `unexpected_runtime/models.py` — optional provider route on task/lifecycle requests if required by existing dataclass contract.
- Modify: `unexpected_runtime/coordinator.py` — resolve a provider for each request without mutating shared provider state.
- Modify: `unexpected_runtime/http_api.py` — authenticated provider status and bounded provider-test route; accept a declared provider route for invocation/lifecycle.
- Modify: `.env.example` — document variable names only, with no secrets.
- Create or modify: `tests/test_provider_router.py`, `tests/test_gateway_integration.py`.

**Interfaces:**
- Existing: `Provider.generate(*, system_prompt, user_prompt, agent_id, task_id, timeout) -> str`.
- Produce: `ProviderRouter.status() -> dict`, `ProviderRouter.resolve(route: str) -> Provider`, `GET /v1/providers`, `POST /v1/providers/test`.
- Supported candidate route names: `mock`, `openai`, `anthropic`, `openrouter`. Route aliases and a compare mode are not required unless the UI needs them.
- Provider result provenance must identify provider, requested model, actual model when available, latency, route, and verified status. A provider key being present is only configured, never verified.

- [ ] **Step 1: Add failing adapter/router tests**
  - Anthropic request uses HTTPS, required API version header, bounded response read, no redirects, and server-side key.
  - OpenRouter uses HTTPS OpenAI-compatible chat completions endpoint with configured model and key.
  - Missing keys, invalid URL, redirects, malformed responses, oversized response, timeout, and HTTP errors fail closed without leaking credential text.
  - Per-task route selects the correct provider; concurrent tasks on different routes do not mutate or leak the shared provider selection.
  - Mock output is marked mock and cannot be recorded as a real provider verification.
- [ ] **Step 2: Verify red**
  - Run: `python -m unittest tests.test_provider_router -v`
  - Expected: missing provider/router interfaces or assertions fail for the intended behavior.
- [ ] **Step 3: Implement adapters and routing**
  - Keep the existing OpenAI-compatible adapter and reuse it for OpenAI/OpenRouter with distinct configuration and identity.
  - Implement the native Anthropic Messages API adapter.
  - Route each task using immutable request context; do not assign to `Coordinator.provider` during requests.
  - Keep `AIStudioGatewayProvider` only as a deprecated compatibility adapter for old tests/configuration; remove it from the v8 production path and docs.
  - Add one bounded provider test operation with no task persistence and no side effects beyond the provider request.
- [ ] **Step 4: Verify focused pass**
  - Run: `python -m unittest tests.test_provider_router -v`
  - Expected: all adapter, security, concurrency, and provenance tests pass.
- [ ] **Step 5: Run provider/runtime regression**
  - Run: `python -m unittest tests.test_gateway_integration tests.test_runtime tests.test_workflow_lifecycle -v`
  - Expected: existing runtime and lifecycle behavior remains green.
- [ ] **Step 6: Commit**
  - `git add unexpected_runtime/providers.py unexpected_runtime/models.py unexpected_runtime/coordinator.py unexpected_runtime/http_api.py .env.example tests`
  - `git commit -m "feat: route tasks through native provider adapters"`

### Task 3: PostgreSQL state adapter and durable approval ledger

**Files:**
- Create: `unexpected_runtime/postgres_storage.py` — PostgreSQL implementation of the StateStore contract.
- Create: `unexpected_runtime/postgres_idempotency.py` — atomic single-flight claims, replay and result storage.
- Create: `unexpected_runtime/postgres_approval_ledger.py` — atomic one-use approval ledger.
- Modify: `unexpected_runtime/storage.py` — explicit storage factory or protocol boundary.
- Modify: `unexpected_runtime/coordinator.py` — select backend using `UNEXPECTED_STORAGE_BACKEND` and `DATABASE_URL`; fail closed if production config is incomplete.
- Modify: `unexpected_runtime/approvals.py` — inject a ledger interface rather than hard-coding SQLite for hosted verification.
- Create: `migrations/002_idempotency_claims.sql` — additive claim table/index only after comparing the existing Neon schema.
- Create: `requirements.txt` — pin a supported psycopg 3 binary extra only if deployment build requires it.
- Create: `tests/test_postgres_storage.py`, `tests/test_postgres_approval_ledger.py`, `tests/test_storage_contract.py`.

**Interfaces:**
- Existing: `StateStore(path)` methods used by `Coordinator`: `enqueue`, `get_task`, `mark_task`, `claim_next`, `events`, `log_event`, memory methods, idempotency methods, knowledge methods, outcome methods, proposal/version/baseline/capability methods.
- Produce: `PostgresStateStore(dsn)` with the same public method contract and explicit `close()`; `ApprovalLedger.consume_once(approval_id, action_digest) -> bool`.
- SQLite remains the default local/test adapter. Hosted Postgres is selected explicitly. There is no silent fallback from configured Postgres to SQLite.
- Database tables already observed in Neon: `tasks`, `events`, `agent_memory`, `shared_knowledge`, `idempotency`, `outcomes`, `proposals`, `agent_versions`, `baselines`, `capabilities`, `consumed_approvals`, `workspace_records`, `workspace_devices`, `schema_migrations`. Current table row counts were zero except one migration ledger row; do not truncate or recreate them.
- Neon Free official limits checked 2026-11-02: $0/month, 100 CU-hours/project/month, 1 GB storage/project, 5 GB network transfer/month, 6-hour instant restore, one manual snapshot; automated backup schedules are not available on Free. Therefore approval activation still requires a separately tested export/restore process and explicit policy decision.

- [ ] **Step 1: Add failing contract and ledger tests**
  - Run the same StateStore contract tests against SQLite and a disposable Postgres test database when available.
  - Verify idempotency key insertion and result storage are atomic under concurrent requests; same key/same payload replays result; same key/different payload rejects.
  - Verify approval consumption uses a single atomic insert/transaction; exactly one of concurrent duplicate attempts succeeds; altered digest and replay fail.
  - Verify provider/database outages fail closed and never fall back to local SQLite.
  - Verify migration is additive and leaves existing tables/rows intact.
- [ ] **Step 2: Verify red**
  - Run: `python -m unittest tests.test_storage_contract tests.test_postgres_storage tests.test_postgres_approval_ledger -v`
  - Expected: Postgres adapter and approval-ledger tests fail because the implementation does not yet exist.
- [ ] **Step 3: Implement storage/ledger**
  - Use parameterized SQL and explicit transactions; do not interpolate user values into SQL.
  - Keep transaction scope narrow and enforce unique constraints for task IDs, idempotency keys, approval IDs, and migration versions.
  - Use a shared connection factory/pool with bounded connections and statement timeouts; close resources cleanly.
  - Compare migration 002 with actual Neon schema before applying. No destructive DDL.
  - Use Neon project `tiny-glade-03545028` only if Free plan remains active and no paid upgrade is required; never retrieve or print connection-string secrets in tool output.
  - Do not enable the GitHub approval verifier until Postgres-backed consumption plus backup/restore and replay tests pass.
- [ ] **Step 4: Verify focused pass**
  - Run: `python -m unittest tests.test_storage_contract tests.test_postgres_storage tests.test_postgres_approval_ledger -v`
  - Expected: SQLite contract passes; Postgres tests pass against a disposable branch/test database; duplicate approval consumption has one winner.
- [ ] **Step 5: Run full runtime regression**
  - Run: `python -m unittest discover -s tests -v`
  - Expected: existing suite and new storage tests pass; no local state files or secrets are added to Git.
- [ ] **Step 6: Commit**
  - `git add unexpected_runtime migrations requirements.txt tests`
  - `git commit -m "feat: add durable postgres state and approval ledger"`

### Task 4: Integrate command-center controls and lifecycle observability

**Files:**
- Modify: `unexpected_runtime/http_api.py` — task/lifecycle invocation, task lookup, provider route, status and safe diagnostics.
- Modify: `unexpected_runtime/coordinator.py` — read-only task/result accessors and immutable provider override context.
- Modify: `unexpected_runtime/storage.py` and `unexpected_runtime/postgres_storage.py` — list/read methods required by the UI.
- Modify: `web/app.js` — task submission, agent detail, provider testing, audit feed, approval visibility, improvement proposals.
- Modify: `web/index.html` and `web/styles.css` — operational panels and accessible status indicators.
- Create: `tests/test_command_center_workflows.py`.

**Interfaces:**
- Produce: `POST /v1/invoke` and `POST /v1/lifecycle` with optional explicit provider route, retaining strict allowlisted request fields.
- Produce: `GET /v1/tasks/{task_id}`, `GET /v1/events?limit=...`, `GET /v1/approvals` (read-only), `GET /v1/improvements`, `POST /v1/improvements/propose` (proposal-only; no promotion).
- All mutating actions pass through coordinator and permissions; browser cannot approve, promote, rollback, or execute privileged actions merely by calling a route.
- Lifecycle timeline must display Request → Plan → Execute → Verify → Improve → Deliver → Learn and actual event/outcome evidence.

- [ ] **Step 1: Add failing workflow/API tests**
  - Authenticated lifecycle request reaches Coordinator and persists events/results.
  - Task detail and event feed return only records from the selected task/limit.
  - Unknown task returns 404; invalid provider route and unsupported fields return 400; rate limit returns 429.
  - An unverified provider route is unavailable and never yields a simulated success labelled as live.
  - Privileged permissions and approval payloads remain rejected at HTTP boundary.
  - Improvement proposal endpoint records a proposal only; it cannot promote a role version.
- [ ] **Step 2: Verify red**
  - Run: `python -m unittest tests.test_command_center_workflows -v`
  - Expected: route and UI behaviors fail before implementation.
- [ ] **Step 3: Implement connected controls**
  - Wire forms and panels to same-origin APIs; render API errors, task status, and provider provenance.
  - Keep client state as a view cache only; server store is authoritative.
  - Do not implement autonomous external writes, scheduled publishing, spending, messaging, or deployment controls.
- [ ] **Step 4: Verify focused pass**
  - Run: `python -m unittest tests.test_command_center_workflows tests.test_command_center_api -v`
  - Expected: all task, lifecycle, permissions, and UI API contract tests pass.
- [ ] **Step 5: Run full regression**
  - Run: `python -m unittest discover -s tests -v`
  - Expected: all tests pass; registry count remains 38.
- [ ] **Step 6: Commit**
  - `git add unexpected_runtime web tests`
  - `git commit -m "feat: connect command center to governed lifecycle"`

### Task 5: Single-service packaging, preview, and release verification

**Files:**
- Create: `Dockerfile` — one Python app image, no Node production server.
- Create: `render.yaml` — one Render web service and `/health` check, no paid database creation.
- Modify: `.github/workflows/ci.yml` — Python build, compile, unit/regression, package artifact and phone/PWA exclusion check.
- Modify: `README.md`, `DEPLOY.md`, `.env.example` — v8 single-app deployment and safe configuration.
- Create: `tests/test_deployment_contract.py` — static deployment contract checks.
- Create: `progress.md` — verified task ledger for implementation.

**Interfaces:**
- Production entry point: `python -m unexpected_runtime.http_api` or a dedicated `unexpected_runtime.__main__` wrapper; exactly one HTTP server and one Coordinator.
- Render health path: `/health`.
- Required host config: `UNEXPECTED_API_TOKEN` (or retained canonical token name), `UNEXPECTED_STORAGE_BACKEND=postgres`, `DATABASE_URL`, provider keys/model settings; no secret values in repository.
- `/health` reports overall app, coordinator, and database readiness without disclosing credentials or internal paths.

- [ ] **Step 1: Add failing packaging/deployment tests**
  - Assert Dockerfile launches the Python app only; no `node server.js`, Node runtime, phone/PWA assets, or gateway URL/token.
  - Assert Render config defines one service, `/health`, and no paid Postgres/Redis resource.
  - Assert built image includes web assets and the 38-role manifests and excludes `mobile/`, `mobile-release/`, `sw.js`, `manifest.webmanifest`, and `mobile-assets.parts/`.
  - Assert missing DB config causes an explicit unhealthy/locked status when Postgres mode is selected.
- [ ] **Step 2: Verify red**
  - Run: `python -m unittest tests.test_deployment_contract -v`
  - Expected: deployment tests fail until the single-process packaging files exist.
- [ ] **Step 3: Implement single-service packaging**
  - Build the Python application image with only runtime dependencies.
  - Use one Render service and one health check; do not change or delete old services.
  - Keep provider/DB credentials as Render environment secrets.
  - Preserve a safe mock-only local mode and explicit production Postgres mode.
- [ ] **Step 4: Verify focused and full pass**
  - Run: `python -m unittest tests.test_deployment_contract -v`
  - Run: `python -m compileall -q unexpected_runtime`
  - Run: `python -m unittest discover -s tests -v`
  - Expected: deployment contract, compilation, and all tests pass.
- [ ] **Step 5: Preview and live verification**
  - Open a draft PR from `feat/unified-v8-foundation` to `main` to run repository CI.
  - Deploy only to a new preview service after CI passes; old services remain running.
  - Verify `/health`, authenticated status, 38-role registry, one deterministic lifecycle, and one owner-approved low-cost real-provider invocation with actual provider/model provenance.
  - Verify Postgres migration, concurrent idempotency, approval single-use, backup export, restore into a disposable branch, and replay rejection after restore.
  - Keep consequential execution disabled until the entire approval/recovery gate passes and owner separately approves activation.
- [ ] **Step 6: Release handoff**
  - Commit all passing deliverables in small commits.
  - Report commit IDs, CI run evidence, preview URL, health and lifecycle evidence, provider route/model, storage/recovery status, remaining blockers, and rollback instructions.
  - Do not merge, cut over, or retire the old services without explicit final confirmation.

---

## Unresolved externally observable decisions

1. **Provider defaults:** recommend OpenAI as the default live route only if its key and bounded test are verified; otherwise show provider unavailable and keep mock clearly labelled. The final default route is a release setting, not inferred from secret presence.
2. **Command-center authentication UX:** recommend one owner-only bearer token entry held only in browser session memory. If a proper owner login/managed auth flow is preferred, it requires a separate design and tests.
3. **Neon backup policy under $0:** Free plan has only six-hour instant restore and one manual snapshot, with no scheduled backups. The command center can verify export/restore, but an independent backup destination is needed for longer retention. No consequential writes until the owner accepts the recovery limitation or a $0 backup destination is verified.
4. **Old service retirement:** remains a separate approval after preview acceptance and rollback rehearsal.
