# uneXpected v8 — Single-Application Command Center Design

> Historical design record. The current scope freeze and live evidence ledger are maintained in [`docs/ARCHITECTURE_FREEZE.md`](../ARCHITECTURE_FREEZE.md); where implementation facts or release state differ, that dated freeze record governs.

**Status:** Revised for owner review  
**Revision:** 2 — phone app removed from v8 scope; architecture consolidated further  
**Date:** 2026-11-02  
**Canonical repository:** `soueilouay-creator/uneXxxx`, baseline `main` (v8 command-center repo)  
**Current implementation branch:** `feat/v8-architecture-freeze-sales-workflow` (PR #4); historical implementation branch: `feat/unified-v8-foundation`

## 1. Owner direction and goal

Build **one uneXpected command center that is the system**, not a new interface that forwards work to two separately running applications.

The v8 target is one canonical repository, one application, one public web service, one authenticated API boundary, one governed coordinator, one provider/capability registry, and one shared state model. The command center must inspect and operate the real system state through that same application.

The phone/PWA app is out of scope. Do not merge, package, deploy, or maintain the current phone companion as part of v8. A separate phone app may be designed later as a distinct project. Do not migrate phone-local IndexedDB records as part of this work.

This is a migration, not a rewrite. Preserve the existing 38-role governed runtime and only bring across the useful desktop web-command-center assets and provider capabilities.

## 2. Verified repository findings

- The canonical Python repository's `main` branch contains the 38-role registry, skill and capability manifests, governed coordinator, permissions, provider abstraction, task lifecycle, SQLite state store, self-improvement controls, and regression tests.
- The currently deployed Python test service uses `integration/v7.3.1-governed-runtime`, which is behind `main`. The v8 work must use `main` as its runtime baseline.
- The separate Node.js AI Studio repository contains a browser interface and provider gateway, plus a distinct phone/PWA implementation. Its Node server currently exposes provider orchestration endpoints and serves the phone app under `/mobile/`.
- The phone/PWA implementation is identifiable in `mobile-release/`, `mobile/`, `mobile-assets.mjs`, `mobile-assets.parts/`, `docs/MOBILE_COMPANION.md`, the phone-specific design document, and mobile/phone UI tests and workflow.
- The Python runtime currently uses a deterministic mock provider by default. Its production state store is SQLite; the current hosted test service has no verified persistent disk and its live SQLite contents have not yet been recovered or inspected.
- The Node gateway and Python runtime currently use separate HTTP services and an authenticated network bridge. This architecture will not be retained in v8.
- No code from the phone/PWA project has been imported into the v8 implementation branch. The current v8 branch is based on the Python runtime repository.

## 3. Target architecture: one application, one runtime

### 3.1 Canonical application

Use the governed Python runtime repository as the single canonical application and execution core.

- Keep one Python application process and one public HTTP server.
- Extend the existing Python HTTP application to serve the command-center web assets and expose the system APIs.
- The existing `Coordinator` is the sole execution authority for every agent task and lifecycle run.
- The 38-role registry, permission policy, skill registry, task execution, provider routing, capability checks, state persistence, audit events, and verification remain inside this application.
- Reuse the useful desktop/browser UI and interaction patterns from AI Studio, but adapt the frontend to the unified Python API.
- Port required provider functionality into native Python provider adapters and a single provider router. Provider calls must be made by the governed application, not by a separate Node gateway.
- Retain TAAFT discovery only as an optional read-only adapter if it passes explicit allowlist, provenance, timeout, privacy, and integration tests. It is not a dependency for core task execution.
- Node.js may be used as a local build tool only if the chosen UI assets require it; it must not run as a production application server or runtime sidecar.

**The v8 production topology must not contain:**
- a separate AI Studio Render service that receives UI requests;
- a separate Python runtime Render service that AI Studio forwards tasks to;
- a Node-to-Python bearer-token bridge;
- a second HTTP server or child runtime process inside the container;
- mobile/PWA routes or an installable phone app.

The result is one integrated program, not two backend services hidden inside one container.

### 3.2 Command-center responsibilities

The command center must be operationally connected to the real governed application. It should expose:

1. **System overview:** application health, runtime readiness, storage health, provider readiness, enabled capabilities, and clear degraded/blocked states.
2. **Agent registry:** all 38 canonical roles, IDs, versions, permissions, skills, routing metadata, and health/availability.
3. **Task control:** submit tasks, inspect task IDs, lifecycle stages, inputs/source provenance, results, verification evidence, failures, retries, and idempotency status.
4. **Workflow control:** Request → Plan → Execute → Verify → Improve → Deliver → Learn, with the stage history and stop conditions visible.
5. **Provider control:** select allowed provider routes, test a provider with a bounded low-cost request, and distinguish configured, reachable, and successfully verified.
6. **Integration/capability control:** show source, adapter, scopes, authorization state, health, and approval policy. A catalog entry is never presented as an installed or authorized integration.
7. **Approvals and safety:** show blocked/awaiting-review operations and their action digests. The interface cannot manufacture approval or bypass the runtime's permission checks.
8. **Audit and learning:** review events, outcomes, improvement proposals, fixed benchmark results, protected-change approvals, version history, and rollback status.
9. **Storage and recovery:** show active storage mode, migration status, backups, restore evidence, and data-reconciliation status.
10. **System configuration:** inspect non-secret settings, service/version metadata, limits, and diagnostics. Secret values must never be rendered to the browser.

The interface is an administrative control surface; it must not duplicate coordinator logic in browser JavaScript or write privileged records directly.

### 3.3 Unified request path

```text
User
  -> uneXpected Command Center (web)
  -> One authenticated Python application/API
  -> Coordinator
       -> 38-role Agent Registry + Skill Registry
       -> Permission Policy + Approval Verifier
       -> Bounded Worker Pool + Lifecycle
       -> Provider Router + approved Capability Adapters
       -> Shared State Store + Idempotency + Audit
  -> Verify -> Improve -> Deliver -> Learn
  -> Command Center displays the recorded outcome
```

All task execution must pass through the same coordinator and policy boundary regardless of whether a task starts in the browser, an API client, or a future connector.

### 3.4 API and authentication

Consolidate the current runtime API and the required AI Studio provider functions into one same-origin API. Exact route names are an implementation detail, but the contract must cover health, authenticated system status, agents, tasks, lifecycle execution, provider status/tests, capabilities, approvals, audit events, and improvement proposals.

- Keep one public authentication boundary and one server-side token/session validation path.
- Do not expose provider secrets or internal approval-verifier credentials to the browser.
- Protect state-changing endpoints with authentication, bounded input validation, rate limits, request size limits, and replay/idempotency controls.
- Keep public health responses minimal and free of environment-variable names that disclose deployment details.
- Do not keep a second internal runtime token once there is no separate internal service to authenticate.
- The frontend may request actions, but all permissions and approvals must be revalidated by the coordinator at execution time.

## 4. Data, persistence, and $0 constraint

The command center and runtime must share one authoritative state model for tasks, events, idempotency, agent memory, reviewed knowledge, outcomes, proposals, versions, capabilities, and approval consumption.

- Add a storage interface and migration tests before changing the storage engine.
- SQLite may remain the local development/test adapter. It must not be described as durable production storage unless the hosting storage is proven persistent and backup/restore tests pass.
- A transactional PostgreSQL adapter is the preferred production target for concurrent state and approval consumption, but no database may be provisioned until its current no-cost plan, limits, suspension behavior, and backup/restore path have been verified.
- Maintain the user's $0 budget. Do not create paid storage, paid compute, or a paid hosting resource. If a dependable zero-cost durable store cannot be verified, report the blocker and keep privileged actions disabled.
- Never silently fall back from durable production state to ephemeral local SQLite for approvals, idempotency, or audit.
- Keep data migrations additive and reversible. Preserve old source data until counts, hashes, record samples, and restore tests reconcile.

There is no phone-local data migration in this release. Do not attempt to access, import, overwrite, or delete any phone device's IndexedDB data.

## 5. Providers and integrations

- Replace the AI Studio gateway dependency with direct server-side provider adapters inside the unified Python application.
- Preserve the distinction between configured, reachable, and verified. Secret presence alone is not a successful provider test.
- Keep deterministic mock mode as an explicit test mode; never label mock output as a real provider result.
- Support provider routing through one registry and consistent provenance fields (provider, requested model, actual model, latency, status, task ID).
- OpenAI, Anthropic, and OpenRouter are candidate adapters. Enable each only after its own bounded test passes and the user-approved configuration is present.
- Retain TAAFT only as read-only discovery, subject to allowlisting and tests. Do not allow discovery content to execute tools or override uneXpected policy.
- Other external integrations must be registered as capabilities with explicit provenance, scopes, health and approval rules. No write-capable integration is automatically enabled.

## 6. Safety and approvals

Consequential execution remains disabled until all of the following are true:

- approval records are stored in a durable transactional store;
- approvals are authenticated, bound to the exact action digest, scoped, expiring, and consumed atomically once;
- idempotency and replay protection are transactionally enforced;
- backup and restore preserve approval-consumption state safely;
- concurrency, duplicate-request, replay, expiry, altered-payload, and restore tests pass;
- the owner explicitly approves activation of the relevant capability.

The current local SQLite one-use approval ledger is not enough to enable production privileged execution. Failure to verify approval state must fail closed. This includes publishing, spending, payments, account changes, deployments, messages sent to external users, and any other consequential write action.

## 7. Phone app removal and source preservation

The phone/PWA is removed from the v8 product scope:

- Do not import `mobile-release/`, `mobile/`, `mobile-assets.mjs`, `mobile-assets.parts/`, or the phone companion's PWA manifest/service worker.
- Do not add `/mobile/` routes, install prompts, offline PWA caching, phone-specific voice/chat features, or phone-only workspace storage.
- Do not carry over phone-specific tests, mobile CI workflows, or phone companion documentation as part of the v8 app.
- Reuse only desktop/browser command-center components and backend/provider behavior that genuinely supports the unified system.
- Do not migrate phone-local projects, conversations, memories, or improvements.
- Keep the original AI Studio repository and current service unchanged during migration as a rollback/reference source. This is not keeping the phone app in v8; it avoids destroying the old release before the replacement is proven. The PWA will not be part of the new application and will disappear from the active product when the old service is retired after cutover.

A future phone app, if requested, will be a separate project and will consume the unified API rather than contain its own system state or duplicate workflow engine.

## 8. Preservation requirements

1. Preserve exactly 38 canonical roles and their existing IDs, permissions, routing metadata, instructions, skill mappings, and provenance.
2. Preserve the seven-stage workflow and its current regression tests.
3. Preserve the governed coordinator, policy checks, bounded execution, audit, idempotency, self-improvement governance, benchmark baselines, and rollback controls.
4. Preserve useful desktop AI Studio UI features and provider selection/testing only after adapting them to the unified API.
5. Preserve provider secrets only in host secret storage; never move secret values into Git, browser assets, backups, or logs.
6. Inventory and attempt recovery of the old runtime SQLite data before any service retirement. Its contents have not yet been recovered or inspected.
7. Keep both existing repositories and Render services intact until the new system passes acceptance and the rollback window has passed.
8. Do not claim connector installation, provider verification, migration completion, or data recovery without evidence.

## 9. Failure behavior and rollback

- If the unified application or coordinator is unavailable, health is unhealthy and task execution is rejected.
- If durable storage is unavailable, reject state changes that require it. Do not run approvals, idempotency, or audit in a volatile fallback.
- If a provider fails, show a provider-specific failure and do not fabricate a result.
- If an integration is absent, disabled, unauthorized, or unverified, mark it unavailable and block its actions.
- If a migration batch fails, roll back the target transaction, preserve source data, log the failure, and allow only bounded retries after inspection.
- Deploy the unified application as a preview while the old services remain intact. Verify the entire workflow and data reconciliation before cutover.
- Cutover and retirement are separate operations. Retire the two old Render services only after the unified application is proven and rollback is rehearsed; obtain explicit final confirmation before destructive service removal.

## 10. Acceptance criteria

The v8 release is accepted only when:

- One canonical repository contains the application, governed runtime, web command center, provider adapters, and tests.
- Production runs one public web service and one Python application process; no separate Node app server, Python runtime service, gateway hop, child runtime process, or mobile/PWA route is required.
- The command center reports and manages the real registry, task lifecycle, provider state, capabilities, approvals, audit, improvement proposals, and storage status through the unified API.
- All 38 canonical agents are present and manifest hashes match the reviewed baseline.
- Every agent/task path uses the single coordinator and permission policy.
- Existing Python regression tests pass; new command-center API, authentication, UI, provider-adapter, process, migration, concurrency, idempotency, approval, and recovery tests pass.
- One deterministic full-lifecycle test succeeds, followed by one user-approved low-risk real-provider invocation with independently checked provenance and result.
- Durable storage, backup, restore, replay, and approval-consumption tests pass before any privileged capability can be enabled.
- No phone/PWA files, routes, tests, or service-worker artifacts are included in the v8 runtime image.
- The $0 constraint is maintained; no paid resource is created.
- Old services remain available until cutover and rollback verification are complete; retirement is separately confirmed.

## 11. Migration stages

1. Freeze and inventory the canonical Python baseline, desktop AI Studio assets, provider behavior, old runtime data access, Render settings, and secret names (never secret values).
2. Extract only the useful desktop/browser command-center assets; explicitly exclude the entire phone/PWA implementation.
3. Define the unified API contract and add failing tests for single authentication, task routing, provider selection, status, and lifecycle behavior.
4. Port provider adapters/router and any required read-only discovery capability into Python; remove the AI Studio gateway bridge from the target design.
5. Extend the Python application to serve the web assets and all command-center APIs in one process.
6. Add the shared storage abstraction and evaluate a verified $0 durable provider. Migrate/import only after source backups and reconciliation tests exist.
7. Run regression, security, provider, lifecycle, concurrency, idempotency, approval, backup/restore, and UI tests in an isolated preview deployment.
8. Verify one deterministic task and one approved low-risk real provider task end-to-end; inspect logs and confirm no phone/PWA routes or second-service dependencies.
9. Cut over only after acceptance criteria pass. Keep both old services through the rollback window.
10. Retire the old services only after rollback readiness and explicit final confirmation.
