# Resource Intelligence and AI Quality Evaluation Implementation Plan

> **For agentic workers:** Use the host's available task-by-task implementation workflow. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add a governed Awesome resource catalog and a bounded AI-output evaluation runner to uneXpected v8 without creating new roles, services, dependencies, permissions or consequential execution paths.

**Architecture:** Resource Intelligence is a read-only, schema-validated catalog shipped with the Python runtime. AI Quality Evaluation is a separate runner over the existing Coordinator/provider router, task store and event audit stream. Authenticated API/CLI surfaces and the existing desktop command center expose catalog and evaluation evidence; the Improvement Governor remains the only promotion authority.

**Tech Stack:** Python 3.12, standard-library JSON/HTTP/unittest, existing SQLite/PostgreSQL adapters, HTML/CSS/JavaScript command-center client, GitHub Actions and Docker.

## Global Constraints

- Work only on `feat/unified-v8-foundation` / PR #11; do not modify main or merge the PR.
- Keep the existing single Python v8 application and 38-role registry; add no role, service, phone/PWA application or database vendor.
- No external package installation, paid service, background crawler, scheduler, LLM-as-judge, provider default change or credential change.
- Awesome and all retrieved linked resources are untrusted discovery data. A parent Awesome-list license never transfers to a linked project.
- Resource discovery, verification, approval and integration remain distinct states. Catalog access is read-only.
- Live quality runs require an explicitly selected configured and verified non-mock provider before creating any task. CI fixtures must be labelled fixture/offline and never presented as semantic live evaluation.
- Evaluation scenarios are read-only and request no privileged permissions. No external tools, publish, message, payment, deploy, delete or account-change action can be performed by a quality run.
- Evaluation reports must not contain secrets, authorization headers or unnecessary raw outputs. Missing/skipped cases are not passes.
- Existing approval, replay, backup/restore, recovery and consequential-action release gates remain unchanged. Do not deploy Render, retire services or activate privileged execution.
- Do not add a database migration unless implementation proves existing event/task storage cannot retain the required evidence and a separate PostgreSQL migration test is provided.

---

### Task 1: Resource Intelligence registry and catalog

**Files:**
- Create: `unexpected_runtime/resource_intelligence.py`
- Create: `unexpected_runtime/data/resource_catalog.json`
- Create: `tests/test_resource_intelligence.py`
- Modify: `unexpected_runtime/cli.py`
- Modify: `tests/test_structure.py`
- Modify: `README.md`

**Interfaces:**
- `ResourceRegistry(path: str | Path | None = None)`
- `ResourceRegistry.list_resources(category: str | None = None, status: str | None = None) -> list[dict]`
- `ResourceRegistry.summary() -> dict`
- `ResourceRegistry.validate() -> dict`
- CLI: `python -m unexpected_runtime.cli resources [--category CATEGORY] [--status STATUS] [--validate]`

- [x] **Step 1: Add failing registry tests**

Assert default catalog loads the permanent Awesome root source, all resource IDs and canonical URLs are unique, all candidate entries retain their source-list provenance, and child licenses are not inherited from Awesome. Add invalid fixture tests for duplicate IDs, duplicate canonical URLs, unsupported statuses, `verified` without a resource-specific license/maintenance/security evidence, and `integrated` without an integration test reference.

- [x] **Step 2: Verify the expected failure**

Run: `python -m unittest discover -s tests -p 'test_resource_intelligence.py' -v`  
Expected: import or missing-registry behavior fails because the module/catalog do not exist; tests must not fail from syntax or fixture setup.

- [x] **Step 3: Implement the read-only registry**

Load JSON from the package data path by default. Validate schema version, source IDs, resource IDs, absolute HTTPS/HTTP canonical URLs, source references, controlled states and adoption prerequisites. Keep unreviewed child-project license/maintenance/security fields explicitly unverified. Provide deterministic filtering and summary output. Do not implement network refresh, catalog mutations, code downloads or package installs.

- [x] **Step 4: Verify the focused pass**

Run the same focused unittest command. Expected: valid catalog passes; each malformed or premature-adoption fixture raises a precise validation error.

- [x] **Step 5: Verify CLI and structure integration**

Run: `python -m unexpected_runtime.cli resources --validate`  
Expected: JSON validation summary is valid and reports candidate counts without claiming installation. Run `python -m unittest discover -s tests -p 'test_structure.py' -v` after updating the source inventory at the end of the change set.

- [x] **Step 6: Commit the passing deliverable**

Commit the catalog, registry, focused tests, CLI surface and required documentation together after their focused checks pass.

### Task 2: Bounded AI Quality Evaluation runner

**Files:**
- Create: `unexpected_runtime/quality_evaluation.py`
- Create: `unexpected_runtime/data/quality_scenarios.json`
- Create: `tests/test_quality_evaluation.py`
- Modify: `unexpected_runtime/cli.py`
- Modify: `EVALS.md`

**Interfaces:**
- `QualityEvaluationRunner(coordinator, scenario_path: str | Path | None = None, fixture_mode: bool = False)`
- `QualityEvaluationRunner.run(provider_route: str | None = None, scenario_ids: list[str] | None = None) -> dict`
- CLI: `python -m unexpected_runtime.cli quality-eval [--provider-route ROUTE] [--scenario ID ...]`

- [x] **Step 1: Add failing runner tests**

Use an actual Coordinator and test-only provider fixture. Cover one passing scenario per category, a failing case and failure classification, blocked task results, report/event persistence, secret-free reports, invalid scenario contracts, and route preflight. For mock and unverified routes assert zero tasks and zero provider calls; this is the critical fail-closed contract. Fixture mode must be explicit and report `execution_mode=fixture/offline`.

- [x] **Step 2: Verify the expected failure**

Run: `python -m unittest discover -s tests -p 'test_quality_evaluation.py' -v`  
Expected: runner import/missing-behavior assertion fails for the specific unimplemented contract, not from malformed fixture or test command.

- [x] **Step 3: Implement the minimum evaluator**

Validate a fixed versioned scenario set and unique scenario IDs. Bound cases to 8, each case deadline to at most 30 seconds, and response evidence to a digest/length rather than duplicating raw model output. Preflight a configured, verified, non-mock provider before task enqueue in live mode. Allow an explicitly enabled test fixture provider only in test construction; never expose fixture mode in the public API/CLI. Invoke each scenario via `Coordinator.invoke` with empty required permissions and a pinned route. Apply deterministic checks for `contains_all`, `contains_any`, `forbidden_any` and shallow JSON required-key validity. Classify failures as provider_unavailable_or_unverified, timeout, execution_failure, output_format_failure, instruction_following_failure, prompt_injection_failure, grounding_provenance_failure, safety_boundary_failure or regression. Mark incomplete/blocked runs distinctly; only pass if all critical checks pass and the noncritical pass rate is at least 90%. Persist summary and case evidence with non-secret event payloads.

- [x] **Step 4: Verify the focused pass**

Run the same focused unittest command. Expected: fixture report is explicitly offline, passing/failing cases are accurately classified, and a rejected route leaves task count and provider calls at zero.

- [x] **Step 5: Verify CLI integration**

Run: `python -m unexpected_runtime.cli quality-eval --provider-route mock`  
Expected: bounded refusal/blocked result with no task creation; no output may label mock as live quality. Run focused suite again.

- [x] **Step 6: Commit the passing deliverable**

Commit evaluator, scenario data, tests, CLI and evaluation-contract documentation together.

### Task 3: Authenticated API and existing command-center surface

**Files:**
- Modify: `unexpected_runtime/http_api.py`
- Modify: `tests/test_command_center_api.py`
- Modify: `web/index.html`
- Modify: `web/assets/app.js`
- Modify: `web/assets/styles.css`

**Interfaces:**
- Authenticated `GET /v1/resources?category=&status=&limit=` returns `{count, summary, items}`.
- Authenticated `GET /v1/quality-evaluations?limit=` returns persisted report summaries from the audit event stream.
- Authenticated `POST /v1/quality-evaluations` accepts only `provider_route` and optional bounded `scenario_ids`; it returns a report or a blocked result. No task is created on preflight refusal.
- The single existing `intelligence` view renders Resource Intelligence and Quality Evaluation, and refreshes from these APIs.

- [x] **Step 1: Add failing API/UI tests**

Assert every new route requires bearer auth; resource reads return the validated catalog; evaluation history returns reports without secret or full-output leakage; mock/unverified POST receives a blocked response with zero task rows; unknown fields and excessive scenario IDs are rejected; the existing UI includes an Intelligence view and uses both new routes.

- [x] **Step 2: Verify expected failure**

Run: `python -m unittest discover -s tests -p 'test_command_center_api.py' -v`  
Expected: the new routes/UI assertions fail because those endpoints and view do not exist yet.

- [x] **Step 3: Implement authenticated bounded API and UI**

Keep all route handling within the existing bearer-token handler and request limiter. Cap API limits and scenario IDs. Read evaluation report events from the existing store, parse only known event payloads, and return summary evidence. Add an Intelligence tab to the existing app; list resource name/category/status/source and show a manual evaluation action with provider selection, last run and case failures. Do not store the access token or provider credentials beyond existing tab-memory behavior.

- [x] **Step 4: Verify focused API/UI pass**

Run the same API test command. Expected: auth, schema, route rejection, no-task preflight and UI wiring assertions pass.

- [x] **Step 5: Verify affected suites**

Run: `python -m unittest discover -s tests -p 'test_resource_intelligence.py' -v` and `python -m unittest discover -s tests -p 'test_quality_evaluation.py' -v`. Expected: both remain green after API/UI integration.

- [x] **Step 6: Commit the passing deliverable**

Commit API, tests and existing command-center UI together.

### Task 4: Documentation, integrity and end-to-end regression

**Files:**
- Modify: `README.md`
- Modify: `EVALS.md`
- Modify: `tests/test_structure.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `FILE_INVENTORY_SHA256.txt`
- Modify: `docs/plans/2026-11-02-resource-intelligence-ai-quality-evaluation.md`

**Interfaces:**
- CI validates both JSON contracts and runs all Python tests against ephemeral PostgreSQL 16, then builds and smoke-tests the one Docker image.
- Source inventory SHA-256 covers every tracked file except itself.
- Documentation distinguishes fixture/harness checks from live-provider semantic evaluation and says Awesome is a permanent reference, not an installation list.

- [x] **Step 1: Add failing structure/CI contract assertions**

Assert catalog/scenario files are included in Docker image/package, source index and status gates are documented, no new third-party dependency is introduced, and the inventory exactly matches all tracked files with correct SHA-256.

- [x] **Step 2: Verify expected failure**

Run: `python -m unittest discover -s tests -p 'test_structure.py' -v`  
Expected: failures identify missing required catalog/scenario assets or stale inventory until the implementation is complete.

- [x] **Step 3: Update package/CI/documentation contracts**

Add JSON validation to CI, make sure the existing Docker `COPY unexpected_runtime` includes package data, update release evaluation documentation and regenerate the source inventory over every tracked file other than the inventory itself.

- [x] **Step 4: Verify full regression**

Run: `python -m compileall -q unexpected_runtime && python -m unittest discover -s tests -v`  
Expected: all tests pass except the pre-existing optional v6 fixture skip. CI must also pass PostgreSQL migration/integration, inventory check, Docker build/container smoke and CLI smoke.

- [x] **Step 5: Read back commit and CI evidence**

Verify PR #11 is still open/draft/unmerged, verify exact branch head, read back all changed files, and confirm a successful GitHub Actions run for that exact head. No Render deploy is part of this plan.

- [x] **Step 6: Commit the final verified inventory and plan evidence**

Update the plan checkboxes and progress record only after evidence is captured; commit the completed plan/inventory record.

## Unresolved external decisions

- Live model quality is only meaningful against a selected configured and verified provider/model. The first release does not select a provider automatically; the owner chooses one for a live run.
- No automatic source refresh cadence is selected. The catalog remains a reviewed version-controlled snapshot until a host-backed scheduler is separately designed and authorized.
- No child project is approved for installation by this implementation; future adoption requires individual license, maintenance, dependency, security, cost and integration review.


## Completed implementation evidence — 2026-11-02

- Resource Intelligence registry/catalog, CLI, authenticated read API and existing command-center view are implemented. All six initial linked candidates remain discovery-only; their licenses, maintenance and security reviews remain unverified. No linked project was installed.
- AI Quality Evaluation runner/scenarios, CLI, authenticated API and command-center view are implemented. Live evaluation requires explicit provider route selection and a configured/verified non-mock provider before task creation. CI fixture mode is test-only and labelled fixture/offline.
- Deterministic quality checks cover instruction format, prompt injection, grounding/source honesty, consequential-action refusal, structured JSON and false background-work claims. Reports include case/check evidence and output digests; raw output and secrets are not copied into the quality report.
- Regression comparisons only use a prior passing report with the same scenario-set ID/revision, exact scenario IDs, provider route/identity/model, execution mode and evaluation method. Regressed cases retain the underlying failure class.
- GitHub Actions run #467 (ID `41503472451`) completed successfully for code/inventory head `46750b3fe0498e2c08159946d110231046465b50`: **218 tests passed, 1 optional skip**. Compile, catalog/scenario JSON validation, PostgreSQL 16 migrations, SHA-256 inventory, single-process Docker build, actual-container health/auth/38-role/task smoke and CLI smoke all passed.
- CI fixture results prove evaluator and safety contracts; they are not live semantic model-quality evidence. No live quality evaluation was initiated.
- No database migration, new third-party dependency, additional role, paid service, external tool installation, Render deployment, service retirement or PR merge was performed. Consequential actions remain fail-closed.
