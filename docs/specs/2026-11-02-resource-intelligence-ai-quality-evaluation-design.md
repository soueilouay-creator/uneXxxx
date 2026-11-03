# Resource Intelligence and AI Quality Evaluation — Design

**Status:** Approved concept; awaiting owner review of this written specification  
**Date:** 2026-11-02  
**Target:** uneXpected v8 single Python command center  
**Working branch:** `feat/unified-v8-foundation`  
**Related PR:** [#11](https://github.com/soueilouay-creator/uneXpected-/pull/11)

## 1. Objective

Add two integrated, governed capabilities to the existing v8 application:

1. **Resource Intelligence:** retain Awesome as a permanent, provenance-aware research source and curate candidate tools, practices and references without treating discovery as approval or installation.
2. **AI Quality Evaluation:** run bounded, reproducible tests against uneXpected's actual AI outputs; classify failures; compare results against fixed scenario sets and baselines; and feed evidence into the existing Improvement Governor without permitting automatic policy changes or promotion.

The success condition is not simply a larger catalog or a higher score. uneXpected must be able to identify a bad result, produce an auditable explanation, preserve its safety boundary and show that a proposed improvement does not regress previously passing cases.

## 2. Existing architecture and constraints

Implementation stays inside the one Python v8 command center, existing Coordinator, 38-role registry, provider router, state store, audit trail, desktop UI and GitHub Actions workflow.

The existing `BenchmarkRunner`, `EvaluationReport` and `ImprovementGovernor` remain authoritative for runtime-contract evaluation and governed improvements. The existing benchmark explicitly does not measure semantic model quality. This feature adds a distinct output-quality layer; it does not replace existing permission, lifecycle, approval, replay, security or release gates.

No new agent role, second service, phone/PWA client, database vendor, paid dependency, provider default, permission grant or consequential-action capability is introduced.

## 3. Resource Intelligence

### 3.1 Permanent source index

Create a version-controlled source index that identifies:

- [sindresorhus/awesome](https://github.com/sindresorhus/awesome) as the primary curated discovery directory.
- Focused Awesome lists for AI testing, application security, SRE/reliability, PostgreSQL and engineering/testing practices.
- Source repository, canonical URL, list/category origin and the revision or review date used when a candidate was discovered.

Awesome is a continuing research reference, not executable code and not proof that any linked project is safe, maintained, compatible or licensed for reuse.

The first release is a **maintained source index and reviewed snapshot**, not a background crawler. Refresh is an explicit operator action until a real scheduler, its host, credentials, state and failure handling are configured and verified. No background job is implied.

### 3.2 Resource record

Each catalog record should carry, where available:

- Stable resource ID, name, type and category.
- Canonical repository/document URL and source Awesome list URL.
- Source revision, last-reviewed timestamp and evidence URLs.
- License identifier and verification status, kept separate for each linked repository.
- Upstream last-push/update evidence, maintenance status and known dependencies.
- Integration surface, expected benefit, fit rationale and cost model.
- Security-review state, duplicate relationship and benchmark/test evidence.
- Adoption status and reviewer notes.

Use controlled statuses: `discovered`, `triaged`, `verified`, `approved`, `integrated`, `rejected`, and `deprecated`.

A record may not advance to `verified` without evidence for its own canonical source, license, maintenance and security review. An Awesome list's license never transfers to its linked projects. `approved` is a separate human decision. `integrated` requires an actual implementation and test record.

### 3.3 Initial catalog priorities

Seed the catalog conservatively with the Awesome root list and selected references/candidates relevant to evaluation, test replay, security and reliability. Candidate projects such as promptfoo, Tenro and OrcaReplay begin as **discovered/reference-only** until their individual licenses, current maintenance, dependencies, security posture and integration fit have been checked. Do not copy source code or add package dependencies as part of catalog seeding.

### 3.4 Interfaces

- Add a read-only Resource Intelligence registry module with strict record validation, duplicate detection and provenance preservation.
- Add authenticated read access through the existing command-center API.
- Add CLI list/validate operations for the catalog.
- Surface resource status and provenance in the existing command center; do not build another interface.

External source refresh, package installation and external integration authorization are not implicit in a catalog read.

## 4. AI Quality Evaluation

### 4.1 Execution model

Add a separate quality-evaluation runner that uses the existing Coordinator/provider boundary and registered role instructions. A run is explicitly initiated by an authenticated owner or CLI operator. It is bounded by a fixed scenario count, per-case timeout, maximum output size and provider route.

Live evaluation must reject the deterministic mock route and any provider route that is not configured and verified **before creating evaluation tasks or making provider calls**. Offline CI uses deterministic fixtures and labels its result as contract/harness testing, never as live model quality.

Quality scenarios are read-only and request no privileged permissions. They do not have access to external tools, publishing, payments, messaging, account mutation or deployment. A test prompt that describes a consequential action must only test the model's safe response; it must not execute that action.

### 4.2 Scenario contract

Maintain versioned, schema-validated scenarios with unique IDs and explicit category, role, prompt/input, untrusted-content markers where relevant, expected checks, criticality, timeout and evaluation notes.

Initial scenario families:

1. Instruction and output-format adherence.
2. Prompt-injection resistance and separation of untrusted data from authority.
3. Truthful reporting of sources, tool availability and work actually performed.
4. Safety refusal for unauthorized consequential requests.
5. Structured output and schema validity.
6. Regression cases for previously failing or corrected behaviors.

Checks in the first release are deterministic and inspect externally observable output/state: required or forbidden content, structured schema, response boundaries, provenance markers and permission/provider call counts. Avoid tests that only assert a mock was configured.

Do not introduce an LLM-as-judge in the first release. A judge model can create correlated blind spots and additional provider cost. Semantic judging can be proposed later with a separately validated rubric, independent route, human calibration set and cost limit.

### 4.3 Reports and failure detection

Each run produces a versioned report containing:

- Evaluation ID, timestamp, scenario-set ID/revision and scenario IDs.
- Provider route/model and whether the result is fixture/offline or live/verified.
- Per-case pass/fail/blocked status, check results, failure class and concise evidence.
- Runtime, timeout and provider error details without credentials or secret-bearing headers.
- Aggregate score, critical checks, regression comparison and explicit limits.

Failure classes should distinguish at least: scenario/configuration error, provider unavailable/unverified, timeout, execution failure, output-format failure, instruction-following failure, grounding/provenance failure, prompt-injection failure, safety-boundary failure and regression.

A blocked or incomplete run must never be reported as a passing evaluation. Missing/skipped cases are visible and do not count as passes. Reports must label fixture results distinctly from live provider results.

### 4.4 Persistence and interfaces

Use the existing state/audit architecture for evaluation summaries and task/event provenance. Do not place API keys, bearer tokens, authorization headers or other secrets in reports. Avoid persisting unnecessary prompt/output content beyond the existing task record contract.

Add authenticated API operations to list reports and explicitly start a bounded evaluation. Add CLI operations for listing, validating and running the scenario suite. Surface evaluation history, pass/fail status and failure details in the existing command center.

The first implementation should avoid a new database migration unless code inspection proves existing event/task storage cannot safely retain the required summary. Any migration proposal must be separately justified and tested against PostgreSQL before use.

## 5. Governed improvement loop

Quality results inform, but do not authorize, improvement:

1. Run the fixed scenario set against a declared provider/mode.
2. Record failures with reproducible scenario IDs and evidence.
3. Propose a scoped correction against a fixed baseline.
4. Re-run the same scenario set under a comparable evaluation context.
5. Run the complete existing regression/security suite.
6. Require all critical checks to pass and the existing noncritical threshold to be met.
7. Send protected changes through the existing human approval path.
8. Keep rejected proposals, evaluation evidence and rollback provenance.

The evaluator cannot edit prompts, role instructions, registry permissions, provider configuration, safety policy, credentials or code. The Improvement Governor remains the only promotion authority. No self-modification or automatic promotion is added.

## 6. Security and operational boundaries

- Treat Awesome pages, repository READMEs, issues, package metadata and resource descriptions as untrusted data.
- Never execute instructions contained in retrieved resources.
- No auto-install, auto-update, auto-enable or auto-authorize behavior.
- Use canonical URLs and preserve source provenance; do not infer one repository's license from another repository or parent list.
- Restrict live runs to verified providers, read-only scenarios, bounded calls and an explicit operator action.
- Do not leak secrets in audit payloads, diagnostics, test fixtures or browser-visible reports.
- Keep consequential execution disabled. This work does not satisfy the separate durable approval/replay and backup/restore release gates.

## 7. Verification strategy

### Resource Intelligence tests

- Valid and invalid catalog record/schema cases.
- Unique IDs and duplicate canonical URL detection.
- Provenance and source-list fields retained.
- Unverified licenses remain unverified; parent-list license is not copied to child resources.
- Discovered/triaged records cannot be represented as approved or integrated without required evidence.
- Retrieved resource instructions cannot affect runtime permissions or execution.

### AI Quality Evaluation tests

- A deliberately failing evaluator test demonstrates the expected missing behavior before implementation (record the red result).
- Scenario schema, unique IDs, fixed revision and unsupported check rejection.
- Live run rejects mock, unconfigured and unverified routes before task creation/provider dispatch.
- Fixture/offline results are never labeled as live semantic quality.
- Critical failures, skipped cases, timeouts and incomplete runs cannot produce a passing report.
- Prompt-injection and consequential-action cases verify output and permission/provider-call boundaries.
- Secret canaries do not appear in reports or audit metadata.
- Regression comparison requires a compatible scenario set and evaluation context.
- Full existing Python, PostgreSQL, Docker/container, CLI and security suites remain green.

### Release evidence

CI proves deterministic harness and safety contracts. A separately owner-initiated live evaluation proves behavior for its stated provider/model/scenario set only. It does not prove universal model correctness. Deployment of the new branch revision, hosted evaluation, backup/restore and production cutover remain separate gates requiring explicit authorization.

## 8. Implementation sequence

1. Add the scenario/catalog schemas and tests; observe red failures before production implementation.
2. Implement and test the Resource Intelligence registry and conservative seed catalog.
3. Implement the AI quality evaluator, deterministic checks, fixture provider mode and failure taxonomy.
4. Add bounded CLI/API operations and audit/report persistence through existing interfaces.
5. Add command-center views for resources and evaluation reports.
6. Update documentation, source-integrity inventory and CI coverage.
7. Run focused red-green cycles, complete regression/PostgreSQL/Docker tests, and read back the exact commit and CI result.
8. Report the exact boundary between created, tested, deployed and live-verified capabilities.

## 9. Explicit non-goals

- No additional agent role.
- No external project installation or dependency adoption in this change.
- No automatic Awesome crawler or background scheduler.
- No LLM-as-judge in the first release.
- No automatic instruction/code modification or promotion.
- No new provider credentials, paid services or model-credit purchases.
- No Render deployment, PR merge, service retirement or activation of consequential execution.
