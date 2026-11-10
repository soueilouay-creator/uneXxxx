# uneXpected Creator Studio Implementation Plan

> **For agentic workers:** Use the host's available task-by-task implementation workflow. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refocus uneXpected v8 into a governed YouTube/TikTok Creator Studio and integrate a pinned Lemo Opuscar code-based filmmaking engine through an isolated render boundary.

**Architecture:** Keep the existing Python API, Coordinator, 38-role registry, provider router and PostgreSQL state as the single control plane. Add creator project/version/artifact records and a hash-pinned Creator Studio Skill; run Opuscar only in a restricted renderer that receives a per-job bundle and no control-plane secrets. Keep publishing disabled until platform authorization and returned-state verification are proven.

**Tech Stack:** Python 3.12, existing uneXpected runtime, SQLite/PostgreSQL adapters, additive PostgreSQL migrations, HTML/CSS/vanilla JavaScript command center, Node.js 20+, Playwright/Chromium, Three.js, Python 3.11+, FFmpeg 7+, Docker-based render sandbox, GitHub Actions.

## Global Constraints

- Scope is YouTube and TikTok video creation, production, quality review, packaging and evidence-backed performance learning. Industrial-maintenance sales/prospecting/customer outreach is no longer an active workflow.
- Preserve the industrial-maintenance-sales Skill source and historical business records as archive material. Remove it from active Skill routing without deleting source files, prospect records, workbooks, database tables or backups.
- Preserve one uneXpected Coordinator, one canonical 38-role registry, one authenticated public API, one approval/policy boundary and one authoritative project/task metadata store. Do not add a second uneXpected application, public control plane or agent registry.
- The render sandbox is an isolated execution boundary, not another coordinator. It must not receive provider keys, runtime bearer tokens, approval credentials, database URLs, host environment variables or unrestricted host filesystem access.
- Never execute model-generated JavaScript, Python, HTML or shell in the credential-bearing API process. Run shell commands with argument arrays, never interpolated shell strings.
- Pin Lemo Opuscar to upstream commit `5c05490cc55dfb54f8f4c333f0f0e79cb6500564`; do not build from floating `main`. Preserve the MIT notice and independently record licences for fonts, sample libraries, HDRIs, textures, models and other assets.
- Prefer code-based rendering and local/original audio where suitable. Default budget is $0. No paid model calls, generation, subscriptions, media assets, render capacity or other chargeable operation without a specific cost preflight and approval.
- Local filesystem artifact storage is development-only. Hosted readiness requires a durable object-storage destination, tested export/restore and verified cost/retention terms. Do not claim Render's ephemeral filesystem is durable.
- YouTube and TikTok are the only publishing destinations in scope. Publisher adapters remain disabled until exact account identity, OAuth scopes, upload behavior, idempotency, privacy/visibility and publication verification are tested. No automatic upload, scheduling, comments, DMs or replies.
- No production deployment, service rebinding, host secret update, database mutation, paid plan change, branch deletion or service retirement is included. Keep the existing Render service and rollback target unchanged.
- Project state transitions are persisted with evidence. A generated MP4 is not proof of human review, upload, scheduling or publication.
- Implement test-first in a feature branch; commit each independently passing task; run the full suite and inspect the final diff before merge.

---

## Task 1: Make Creator Studio the only active media workflow

**Files:**
- Modify: `skills/creative-media/WORKFLOW.md` (observed)
- Modify: `skill_manifest.json` (observed)
- Modify: `skills/industrial-maintenance-sales/SKILL.md` (observed; archive banner only)
- Modify: `tests/test_skills.py` and `tests/test_structure.py` (observed)
- Modify: `README.md` and `docs/ARCHITECTURE_FREEZE.md` (observed; add dated superseding scope note while preserving historical text)
- Create: `skills/creative-media/references/lemo-opuscar-interface.md` (proposed hash-pinned Skill reference)
- Modify: `FILE_INVENTORY_SHA256.txt` (observed integrity contract)

**Interfaces:**
- Consumes: Skill manifest schema v2; existing IDs `creative-media`, `skill-engineering`, `self-improvement`; canonical roles `creative-director`, `media-producer`, `voice-agent`, `marketing-seo`, `code-reviewer`, `qa-engineer`, `project-manager`, `self-improvement-governor`.
- Produces: updated `creative-media` Skill content and a schema-v2 `resources[]` entry with `kind: "reference"`, exact path and SHA-256. Keep the current Skill ID stable for compatibility. Active Skill IDs become exactly `creative-media`, `skill-engineering` and `self-improvement`; the sales Skill is not loaded.

- [x] **Step 1: Add failing routing and archive tests**

Update the existing Skill/structure tests to assert that video/Shorts/film objectives resolve to `creative-media` for mapped creative roles; the active manifest contains exactly the three IDs above; the sales Skill is absent from active routing but its source file remains and starts with a dated archived/not-active notice; the 38-role count and unique IDs remain unchanged; every active Skill and resource hash matches its bytes; and the Creator Studio reference calls Opuscar a code-based engine, not a hosted video model.

- [x] **Step 2: Verify the relevant failure**

Run: `python -m unittest tests.test_skills tests.test_structure -v`

Expected: new assertions fail against the current four-Skill manifest and the existing general-purpose creative-media instructions.

- [x] **Step 3: Implement the minimum routing change**

Rewrite the existing creative-media workflow as the Creator Studio procedure: brief/research, hook/script, treatment, style selection, storyboard/look, project authoring, render, encoded-media QA, human approval, platform packaging and evidence-backed learning. Add the Opuscar adapter reference and archive notice to the existing sales Skill. Remove only the sales record from the active manifest; update creative-media's version/description/triggers/resources/hash. Update README scope and append a dated superseding note to the architecture-freeze history. Regenerate the SHA-256 inventory from the actual tracked tree.

- [x] **Step 4: Verify the focused pass**

Run: `python -m unittest tests.test_skills tests.test_structure -v`

Expected: all focused tests pass; there remain 38 canonical roles, three active Skills and one preserved archived sales Skill file.

- [x] **Step 5: Run the affected integration check**

Run: `python -m unittest discover -s tests -v`

Expected: the complete suite passes, with only the already-optional v6 fixture skipped when not supplied. No prospect or customer records are read or mutated.

- [x] **Step 6: Commit the passing deliverable**

```bash
git add skills/creative-media/WORKFLOW.md skills/creative-media/references/lemo-opuscar-interface.md skills/industrial-maintenance-sales/SKILL.md skill_manifest.json tests/test_skills.py tests/test_structure.py README.md docs/ARCHITECTURE_FREEZE.md FILE_INVENTORY_SHA256.txt
git commit -m "feat: refocus active workflow on creator studio"
```

**Verification evidence (2026-11-07):** Full repository CI run [#42396950841](https://github.com/soueilouay-creator/uneXxxx/actions/runs/42396950841) passed on commit `60bd102fd09fbc5e008909e23bfa8e15afdaa8b0`: 270 tests passed with one optional v6 fixture skipped; source integrity fixture, Docker image build, actual-container smoke test and CLI smoke test all passed. The expected red phase was observed first on the earlier test-only commit. Sales source remains archived; historical sales data was not read or modified.

## Task 2: Add creator project, version, asset and state persistence

**Files:**
- Create: `unexpected_runtime/creator_studio.py` (proposed domain types, transition policy and service)
- Modify: `unexpected_runtime/storage.py` and `unexpected_runtime/postgres_storage.py` (observed adapters)
- Create: `migrations/003_creator_studio.sql` (proposed additive hosted schema)
- Create: `tests/test_creator_studio.py` and `tests/test_postgres_creator_studio.py` (proposed)

**Interfaces:**
- `CreatorProject`: `project_id, title, topic, channel_profile, language, status, created_at, updated_at`.
- `CreatorVersion`: `version_id, project_id, version_no, kind, content_json, parent_version_id, created_at`.
- `CreatorAsset`: `asset_id, project_id, version_id, kind, storage_key, sha256, byte_size, mime_type, provenance_json, license_json, qa_status, created_at`.
- `RenderJob`: `job_id, project_id, version_id, engine_commit, style_id, status, idempotency_key, resource_limits_json, result_manifest_json, created_at, updated_at`.
- `CreatorStudioService(store, artifact_store, render_dispatcher)` exposes `create_project(payload, actor)`, `get_project(project_id)`, `list_projects(limit)`, `save_version(project_id, kind, content, parent_version_id, actor)`, `register_asset(asset)`, `create_render_job(job)`, `get_render_job(job_id)`, `transition_project(project_id, expected_status, next_status, actor, evidence)`.
- Both state adapters implement the same creator persistence methods. Transitions use compare-and-set semantics and return the stored record or a typed not-found/conflict result.

- [ ] **Step 1: Add failing SQLite and PostgreSQL contract tests**

Test project create/list/read; version numbering and immutable prior versions; project foreign-key enforcement; valid and invalid lifecycle transitions; duplicate render idempotency key returns the prior job; same key with a different request digest is rejected; asset checksum mismatch is rejected before registration; QA/package evidence is append-only; and task/event history remains unchanged. Run equivalent cases against PostgreSQL after migrations 001, 002 and 003.

- [ ] **Step 2: Verify the relevant failure**

Run: `python -m unittest tests.test_creator_studio tests.test_postgres_creator_studio -v`

Expected: missing imports/methods fail because creator types and persistence do not yet exist.

- [ ] **Step 3: Implement the minimum persistence layer**

Create domain dataclasses and the transition map. Add tables `creator_projects`, `creator_versions`, `creator_assets`, `creator_render_jobs`, `creator_qa_reports` and `creator_platform_packages`, with foreign keys, unique project/version numbers, unique render idempotency keys and indexes on project/status/timestamps. Add matching SQLite initialization and PostgreSQL migration 003. Persist transition evidence through the existing event mechanism. Keep media bytes outside PostgreSQL: define `ArtifactStore.put(key, bytes, mime_type) -> StoredArtifact`, `get(key) -> bytes`, `delete(key) -> None`; implement a temporary/local test adapter only. Do not configure hosted object storage in this task.

- [ ] **Step 4: Verify the focused pass**

Run: `python -m unittest tests.test_creator_studio tests.test_postgres_creator_studio -v`

Expected: both adapters pass the same persistence/transition contract; migration 003 applies cleanly after migration 002 and is idempotent.

- [ ] **Step 5: Run the affected integration check**

Run: `python -m unittest tests.test_postgres_storage tests.test_postgres_approval_ledger tests.test_idempotency_claims tests.test_task_event_cursor tests.test_creator_studio tests.test_postgres_creator_studio -v`

Expected: creator records coexist with existing tasks, approvals and replay data; no existing storage semantics regress.

- [ ] **Step 6: Commit the passing deliverable**

```bash
git add unexpected_runtime/creator_studio.py unexpected_runtime/storage.py unexpected_runtime/postgres_storage.py migrations/003_creator_studio.sql tests/test_creator_studio.py tests/test_postgres_creator_studio.py
git commit -m "feat: persist creator projects and render jobs"
```

## Task 3: Pin Opuscar and build the isolated render worker contract

**Files:**
- Create: `.gitmodules` and `third_party/lemo-opuscar` (proposed pinned upstream submodule)
- Create: `third_party/licenses/lemo-opuscar-LICENSE` and `third_party/lemo-opuscar.lock.json` (proposed licence and commit/source inventory)
- Create: `unexpected_runtime/render_jobs.py` (proposed job/result contracts and dispatcher Protocol)
- Create: `unexpected_runtime/lemo_opuscar.py` (proposed style catalogue and build adapter)
- Create: `renderer/Dockerfile`, `renderer/entrypoint.py`, `renderer/job.schema.json`, `renderer/README.md` (proposed isolated image and one-job entry point)
- Create: `tests/test_render_jobs.py` and `tests/test_render_sandbox_contract.py` (proposed)
- Modify: `.github/workflows/ci.yml` (observed; recursive submodule checkout and renderer build)

**Interfaces:**
- `RenderJobSpec`: `job_id, project_id, version_id, engine_commit, style_id, input_manifest, output_profile, limits`.
- `RenderResultManifest`: `job_id, engine_commit, status, artifacts[], checks[], started_at, completed_at`; each artifact has relative path, MIME type, byte size and SHA-256.
- `RenderDispatcher.submit(spec) -> RenderSubmission`; `RenderDispatcher.get(job_id) -> RenderStatus`. The Coordinator accepts this interface by injection; it does not own or launch a Docker daemon.
- `OpuscarAdapter.list_styles() -> list[StyleInfo]`, `preflight(spec) -> PreflightReport`, `build_command(spec) -> list[str]`.
- Renderer input is a bounded JSON manifest and project files mounted read-only. Output is a fresh writable job directory plus a JSON result manifest.

- [ ] **Step 1: Add failing adapter and sandbox contract tests**

Test the exact upstream commit lock; style listing reads only the pinned style directory; unknown styles and missing required resources fail preflight; project paths reject traversal, absolute paths and symlinks; oversized manifests/files are rejected; output paths remain within the job directory; result-manifest size/checksum mismatch is rejected; duplicate keys do not submit duplicate render work. Assert invocation uses an argument array, non-root UID, read-only root, read-only input mount, one writable output mount, no network, no new privileges, dropped capabilities and explicit CPU/memory/PID/time/disk limits. Assert provider/API/database environment variables are absent from the sandbox.

- [ ] **Step 2: Verify the relevant failure**

Run: `python -m unittest tests.test_render_jobs tests.test_render_sandbox_contract -v`

Expected: tests fail because the adapter, job schema and renderer boundary do not exist.

- [ ] **Step 3: Implement the pinned engine and one-job renderer**

Add upstream source as a submodule at the exact approved commit. Preserve the upstream MIT notice and create a source inventory; do not copy demo stories or alter upstream core/style folders. Build a separate image with pinned Node 20, Python 3.11+, Playwright/Chromium, Three.js and FFmpeg 7+; record installed versions and image digest. The renderer entry point accepts one validated job manifest and processes only files beneath its assigned input/output directories. The render host/supervisor invokes Docker using `subprocess.run([...], shell=False)` with `--network=none`, `--read-only`, `--user`, `--cap-drop=ALL`, `--security-opt=no-new-privileges`, explicit resource limits and only the two job mounts. No Docker socket, CLI or render host credentials are added to the uneXpected API image. If the host cannot provide Docker isolation, return typed `renderer_unavailable` and keep the job recoverable/blocked; never fall back to in-process execution.

- [ ] **Step 4: Verify the focused pass**

Run: `python -m unittest tests.test_render_jobs tests.test_render_sandbox_contract -v`

Expected: schema, pin, path, output-integrity and no-secret sandbox contract tests pass.

- [ ] **Step 5: Run the affected integration check**

Run: `docker build -f renderer/Dockerfile -t unexpected-creator-renderer:locked .`

Expected: image builds with the pinned engine and reports Node, Python, Chromium/Playwright and FFmpeg versions. Run the fixture with `--network=none` and temporary input/output directories; it returns a complete result manifest and an MP4 whose checksum matches. If Docker is unavailable in the host, record an environment blocker; do not substitute a weaker sandbox.

- [ ] **Step 6: Commit the passing deliverable**

```bash
git add .gitmodules third_party unexpected_runtime/render_jobs.py unexpected_runtime/lemo_opuscar.py renderer tests/test_render_jobs.py tests/test_render_sandbox_contract.py .github/workflows/ci.yml
git commit -m "feat: add pinned isolated Opuscar renderer"
```

## Task 4: Connect creator workflow to the Coordinator and authenticated API

**Files:**
- Modify: `unexpected_runtime/coordinator.py` and `unexpected_runtime/http_api.py` (observed)
- Modify: `unexpected_runtime/creator_studio.py` (from Task 2)
- Modify: `tests/test_command_center_api.py` (observed)
- Create: `tests/test_creator_api.py` (proposed)

**Interfaces:**
- `GET /v1/creator/projects?limit=N` returns `{count, items}`.
- `POST /v1/creator/projects` accepts only `title, topic, channel_profile, language`; returns `201 {project}`.
- `GET /v1/creator/projects/{project_id}` returns `{project, versions, assets, render_jobs}`.
- `POST /v1/creator/projects/{project_id}/versions` accepts `kind, content, parent_version_id`; returns `201 {version}`.
- `POST /v1/creator/projects/{project_id}/render` accepts `version_id, style_id, output_profile, render_options, idempotency_key`; returns `202 {job}`, `409` for conflicting idempotency, or `503` with a non-secret renderer-unavailable reason.
- `GET /v1/creator/render-jobs/{job_id}` returns persisted state and verified result metadata.
- Routes use the existing bearer-token boundary, body-size cap, rate limiter and JSON helpers. No unauthenticated creator route is added.

- [ ] **Step 1: Add failing API tests**

Assert anonymous calls return 401; unknown routes and IDs return 404; unsupported fields and oversized JSON fail with 400/413; invalid transitions return 409; duplicate idempotency key returns the same job; unavailable renderer returns 503 without in-process execution; project/version records remain available after Coordinator restart. Assert responses/logs never expose tokens, database URLs, local filesystem paths or full private media payloads.

- [ ] **Step 2: Verify the relevant failure**

Run: `python -m unittest tests.test_creator_api -v`

Expected: tests fail because Creator Studio API routes and service injection do not yet exist.

- [ ] **Step 3: Implement authenticated routes**

Inject optional CreatorStudioService and RenderDispatcher through the existing Coordinator construction seam. Add only the routes above. Validate allowlisted fields, JSON types, current project version, idempotency key and output profile before persisting a job. Persist the job before worker dispatch. If dispatch is unavailable or times out, preserve the durable job and return its state; never create a second job on retry. Do not expose arbitrary artifact paths or raw worker logs.

- [ ] **Step 4: Verify the focused pass**

Run: `python -m unittest tests.test_creator_api -v`

Expected: all auth, schema, idempotency, not-found, unavailable-worker and response-redaction cases pass.

- [ ] **Step 5: Run the affected integration check**

Run: `python -m unittest tests.test_command_center_api tests.test_workflow_lifecycle tests.test_workflow_seven_stage_proof tests.test_creator_api -v`

Expected: the original 38-role, authenticated task and seven-stage APIs remain unchanged; creator routes share the existing Coordinator and store.

- [ ] **Step 6: Commit the passing deliverable**

```bash
git add unexpected_runtime/coordinator.py unexpected_runtime/http_api.py unexpected_runtime/creator_studio.py tests/test_command_center_api.py tests/test_creator_api.py
git commit -m "feat: expose governed creator project APIs"
```

## Task 5: Add encoded-media QA and YouTube/TikTok packaging

**Files:**
- Create: `unexpected_runtime/creator_qa.py` (proposed)
- Create: `unexpected_runtime/platform_packages.py` (proposed)
- Create: `tests/test_creator_qa.py` and `tests/test_platform_packages.py` (proposed)
- Modify: `unexpected_runtime/creator_studio.py` and creator API tests (from prior tasks)

**Interfaces:**
- `CreatorQA.inspect(video_path, subtitle_path=None, narration_script=None) -> QAReport`.
- QA report records container/codec, dimensions, FPS, duration, video/audio stream presence, black-frame/freeze checks, loudness/true-peak results where audio exists, subtitle timing/readability, narration transcript result when ASR is available, output checksum and explicit skipped-check reasons.
- `PlatformPackageBuilder.build(project, approved_asset, profile) -> PlatformPackage` returns metadata and a derivative render request; it never uploads.
- Platform profiles are versioned data with destination, target aspect/resolution, safe areas, caption/metadata fields and validation rules. Defaults must be explicit per channel profile.

- [ ] **Step 1: Add failing QA and package tests**

Use a deterministic synthetic clip plus fixtures for no audio, no video, zero duration, black frames, freezes, invalid subtitle cues, too-short on-screen text, bad audio peak, mismatched transcript, wrong aspect ratio and checksum corruption. Missing optional ASR must be reported as skipped, not passed. Verify a master can produce separate YouTube/TikTok metadata profiles and that the package builder has no upload method.

- [ ] **Step 2: Verify the relevant failure**

Run: `python -m unittest tests.test_creator_qa tests.test_platform_packages -v`

Expected: tests fail because QA and package modules do not yet exist.

- [ ] **Step 3: Implement QA and package generation**

Run `ffprobe` and bounded FFmpeg analysis inside the renderer for stream properties, blackdetect, freezedetect and ebur128/loudness. Use Opuscar readcheck and speech-to-text checks when the required optional dependencies are installed. Record skipped checks and never label unchecked human listening as complete. Build separate YouTube/TikTok metadata packages and request platform-specific derivatives through the dispatcher when the master does not satisfy a profile. Do not implement upload, OAuth or scheduling endpoints.

- [ ] **Step 4: Verify the focused pass**

Run: `python -m unittest tests.test_creator_qa tests.test_platform_packages -v`

Expected: synthetic fixtures produce the expected pass/fail/skipped results and profiles remain separate.

- [ ] **Step 5: Run the affected integration check**

Run: `python -m unittest tests.test_creator_studio tests.test_creator_api tests.test_creator_qa tests.test_platform_packages -v`

Expected: a project version can move from rendered to QA-passed, then human-approved by a separate explicit action, then package-ready; failed QA cannot enter approved/package-ready state.

- [ ] **Step 6: Commit the passing deliverable**

```bash
git add unexpected_runtime/creator_qa.py unexpected_runtime/platform_packages.py unexpected_runtime/creator_studio.py tests/test_creator_qa.py tests/test_platform_packages.py tests/test_creator_studio.py tests/test_creator_api.py
git commit -m "feat: verify creator media and build platform packages"
```

## Task 6: Add Creator Studio surfaces to the existing command center

**Files:**
- Modify: `web/index.html`, `web/assets/app.js`, `web/assets/styles.css` (observed)
- Modify: `tests/test_command_center_api.py` and `tests/test_structure.py` (observed)
- Create: `tests/test_creator_ui.py` (proposed)

**Interfaces:**
- Browser uses existing API authentication and calls only authenticated `/v1/creator/*` routes.
- UI panels: project list/create, project detail/version history, style selection, render submission/progress, asset/QA evidence, human review state and YouTube/TikTok package preview.
- No client-side database access, provider credentials, shell execution, arbitrary path or publishing action.

- [ ] **Step 1: Add failing UI contract tests**

Verify navigation includes one Creator Studio view; create/list/detail forms call the specified API routes; state labels distinguish queued/rendering/QA failed/QA passed/human approved/package ready; missing renderer displays blocked/unavailable; YouTube/TikTok package previews are separate; no publish/schedule/send control appears; assets continue to be served by the existing Python process.

- [ ] **Step 2: Verify the relevant failure**

Run: `python -m unittest tests.test_creator_ui -v`

Expected: tests fail because the Creator Studio view does not exist.

- [ ] **Step 3: Implement the view**

Add one Creator Studio navigation item to the existing shell. Reuse auth-token handling, fetch helpers, loading/error panels and responsive styles. Render status only from API responses; do not synthesize ready/published states in the browser. Do not add a second front-end app or mobile/PWA routes.

- [ ] **Step 4: Verify the focused pass**

Run: `python -m unittest tests.test_creator_ui tests.test_command_center_api -v`

Expected: Creator Studio UI contracts pass and existing command-center navigation remains intact.

- [ ] **Step 5: Run the affected integration check**

Run: `python -m unittest discover -s tests -v`

Expected: the full Python/UI contract suite passes with unchanged 38-role registry and authenticated API boundary.

- [ ] **Step 6: Commit the passing deliverable**

```bash
git add web/index.html web/assets/app.js web/assets/styles.css tests/test_creator_ui.py tests/test_command_center_api.py tests/test_structure.py
git commit -m "feat: add creator studio command center"
```

## Task 7: Prove the end-to-end local film and publish-ready handoff

**Files:**
- Create: `tests/fixtures/creator-smoke/` and `tests/test_creator_end_to_end.py` (proposed)
- Modify: `.github/workflows/ci.yml`, `README.md`, `DEPLOY.md`, `THIRD_PARTY_NOTICES.md`, `docs/OPEN_SOURCE_ADAPTATION_REGISTER.md`, `FILE_INVENTORY_SHA256.txt` (observed)
- Create: `docs/CREATOR_STUDIO_OPERATIONS.md` and `docs/CREATOR_STUDIO_RECOVERY.md` (proposed)

**Interfaces:**
- Smoke project runs Coordinator → CreatorStudioService → persisted render job → isolated renderer → result manifest/checksum → media QA → separate platform package previews.
- CI reports distinct unit, renderer image build, sandbox fixture and artifact QA results. Missing Docker produces a blocked status, not an assumed pass.
- Operations docs name exact prerequisites, local command sequence, artifact locations, status semantics, recovery and rollback.

- [ ] **Step 1: Add failing end-to-end tests**

Create one original 10–15 second code-drawn synthetic test film with a deterministic local/no-cost audio fixture, no external footage and no paid model/video call. Assert a playable MP4, correct result-manifest checksums, QA report, YouTube package and TikTok package. Assert project/job/result retrieval works after renderer-worker restart and retrying the same render key does not create a duplicate. Assert no upload provider is called and no public URL is recorded.

- [ ] **Step 2: Verify the relevant failure**

Run: `python -m unittest tests.test_creator_end_to_end -v`

Expected: tests fail until the creator modules and renderer fixture are connected.

- [ ] **Step 3: Implement end-to-end wiring and operations docs**

Wire the local development dispatcher to the isolated renderer only where Docker is available. Keep the hosted API dispatcher unset by default until a supported renderer host/worker and durable object storage are verified. Add CI with recursive submodule checkout and renderer image build; run the deterministic fixture with no network egress. Document that the current Render Free web service is not a verified renderer host or durable video storage target. Update the upstream adaptation register with the pinned commit and MIT/licence boundaries. Preserve archive/rollback assets. Regenerate the source inventory and any release archive only after the tree is stable.

- [ ] **Step 4: Verify the focused pass**

Run: `python -m unittest tests.test_creator_end_to_end -v`

Expected: local smoke generates and verifies the synthetic MP4; worker restart and idempotent replay recover the same project/job; no upload takes place.

- [ ] **Step 5: Run final release checks**

Run:
```bash
python -m compileall -q unexpected_runtime
python -m unittest discover -s tests -v
docker build -f renderer/Dockerfile -t unexpected-creator-renderer:locked .
git diff --check
```

Expected: Python compile and full tests pass, the optional v6 fixture is the only documented skip when absent, the isolated renderer builds at the pinned engine revision, manifest hashes match and the 38-role count remains unchanged. Inspect the full PR diff for secrets, private media, active sales routing or accidental publishing routes.

- [ ] **Step 6: Commit the passing deliverable**

```bash
git add tests/fixtures/creator-smoke tests/test_creator_end_to_end.py .github/workflows/ci.yml README.md DEPLOY.md THIRD_PARTY_NOTICES.md docs/OPEN_SOURCE_ADAPTATION_REGISTER.md docs/CREATOR_STUDIO_OPERATIONS.md docs/CREATOR_STUDIO_RECOVERY.md FILE_INVENTORY_SHA256.txt
git commit -m "test: prove end-to-end Creator Studio render workflow"
```

## Execution gates and unresolved product decisions

These are deliberate decision seams. Preserve disabled/fail-closed behavior until they are resolved:

1. **Hosted render execution:** the existing Render Free web service is not proven to offer Docker, a separate worker host or isolated execution. Code and local container proof can be completed, but hosted rendering remains disabled until a genuinely supported $0 worker target is found and security-tested. Do not add a paid service without approval.
2. **Durable artifact storage:** no object-storage provider or durable destination is currently verified. Local storage is development/test only. Hosted production needs a separately approved provider, price/retention review and restore test.
3. **Upstream packaging:** use the pinned submodule only after CI and the target build host demonstrate recursive submodule checkout. Otherwise use a pinned source archive with recorded SHA-256 and equivalent reproducibility checks; never fall back to a moving branch.
4. **Narration default:** Opuscar documents offline Kokoro for English and online edge-tts for Chinese. Keep voice/language and network requirements explicit per project; do not silently use an online TTS route under a $0 claim.
5. **Channel identity and cadence:** channel profile IDs, language, audience, recurring characters/series rules and cadence are configured per YouTube/TikTok account. Do not infer one universal identity or posting frequency.
6. **Publishing authorization:** exact YouTube/TikTok connectors, account identities and OAuth scopes are not currently proven in the uneXpected runtime. Keep publishing disabled; implementation ends at separately validated upload-ready packages until connector verification and exact owner approval.

## Rollback

- Baseline remains `main` at `8a67c823292901305cad670a60c2f24f0a047267`; implementation stays on a feature branch and is submitted for PR review.
- Sales Skill source and all business records remain preserved. Reverting active Skill routing restores the prior behavior without recovering deleted data.
- Database changes are additive migration 003. Roll back by disabling Creator Studio routes and retaining tables; do not drop creator/project/render tables during normal rollback.
- Keep renderer image/version pinned per job. Disable a failed renderer version for new jobs while retaining project sources and completed artifacts.
- Keep `render.yaml`, Render source, environment variables, database branch and current production deployment unchanged throughout implementation. Deployment/cutover is a separate owner-approved operation.
