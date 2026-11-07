# uneXpected Creator Studio — Lemo Opuscar Integration Design

**Status:** Proposed design for owner review  
**Date:** 2026-11-07  
**Target repository:** `soueilouay-creator/uneXxxx`  
**Baseline commit:** `8a67c823292901305cad670a60c2f24f0a047267`  
**Upstream engine:** [lemomo-ai/lemo-opuscar](https://github.com/lemomo-ai/lemo-opuscar)  
**Pinned upstream revision:** `5c05490cc55dfb54f8f4c333f0f0e79cb6500564`

## 1. Decision and mission

Refocus uneXpected on the end-to-end creation, production, quality control and packaging of videos for **YouTube and TikTok**. The Industrial Maintenance Sales Control Center is no longer an active operating workflow. Its records and implementation are preserved as an archive; they are not deleted as part of this change.

The system's owner-facing outcome is a finished, technically checked, rights-documented video project with platform-ready derivatives and a clear publication state. Public upload, scheduling, paid services and account changes remain explicit approval-gated actions.

**Lemo Opuscar is a production engine, not an autonomous AI model or a complete hosted video service.** Its source describes 66 film styles and a code-based pipeline: deterministic Canvas/WebGL/Three.js rendering, text-to-speech, synthesized/sample-based music, procedural sound effects, subtitles, and FFmpeg mixing/muxing. A capable, verified model provider is still needed for creative direction and source-code authoring. The engine can avoid per-shot video-generation charges, but it does not make all compute, model calls, downloads or storage cost-free.

## 2. Architecture decision

Keep the existing uneXpected v8 application as the **single control plane**:
- one public Python API and command center;
- one Coordinator and canonical 38-role registry;
- one provider router and policy/approval boundary;
- one PostgreSQL-backed task and project metadata authority.

Add a narrowly scoped **isolated render execution boundary**. This is an execution sandbox, not a second uneXpected application: it has no Coordinator, public user API, provider credentials, approval authority or independent task database. The Coordinator creates and tracks render jobs; the renderer receives a bounded project bundle and a one-job capability, produces artifacts, and returns signed/checksummed results.

This exception supersedes the old v8 single-process execution assumption only for untrusted film rendering. It does not authorize a second coordinator, duplicate registry, second public command center or a second source of state.

### Trust boundaries

1. **Control plane:** authenticated owner requests, roles, provider configuration, approval ledger, task/project metadata and audit.
2. **Creative project workspace:** versioned briefs, research notes, scripts, treatments, storyboards, style selections and generated source files. Treat model output, user media and remote references as untrusted.
3. **Render sandbox:** isolated job execution with no inherited application environment, no provider/API/database secrets, non-root identity, read-only engine/runtime inputs, bounded writable job directory, CPU/memory/time/disk limits, and network egress disabled by default. No arbitrary host paths or shell interpolation.
4. **Artifact storage:** explicit storage adapter for rendered media and project source. Store checksums, sizes, MIME types, provenance, licences and lifecycle state in PostgreSQL. Do not treat Render's ephemeral filesystem as durable storage.
5. **Publishing adapters:** separate YouTube and TikTok destinations. They remain disabled until a connector's authorization, supported operations, account scope and returned-state verification are proven.

**Hard security gate:** do not execute model-generated JavaScript, Python, shell scripts or HTML inside the credential-bearing API process. Do not weaken the sandbox because the render job was approved; approval authorizes the requested production action, not unrestricted host access.

## 3. Upstream dependency and adaptation

### Source reviewed

- Repository: https://github.com/lemomo-ai/lemo-opuscar
- Pinned commit: `5c05490cc55dfb54f8f4c333f0f0e79cb6500564`
- Upstream package version: `0.1.0`
- Root source license: MIT.
- Upstream README advertises an MIT / CC BY 4.0 licensing mix. Individual fonts, sample libraries, models, HDRIs, textures, style-specific tools and other media have their own provenance and licence records. A repository-level MIT license does not relicense those assets.

### Integration shape

- Pin the upstream repository to the exact commit above; never build production from a floating `main` branch.
- Prefer a reviewed git submodule or reproducible source bundle under `third_party/lemo-opuscar`; record upstream URL, commit, root license, file inventory and source checksums.
- Keep upstream-owned files clearly separated from uneXpected-authored adapters and documentation. Do not silently modify upstream core files.
- Expose a small uneXpected adapter contract for style discovery, project scaffolding, rendering, audio/subtitle checks, contact sheets and final muxing.
- Start with the core engine and a reviewed style catalogue. Fetch optional voice, music, HDRI and style-specific dependencies only when a selected project needs them.
- Never copy demo-film stories, characters, scenes, music, artwork or other protected expression into user projects. Demos may be consulted for technique after a new treatment is written.
- Preserve attribution and notices. Before a style or asset enters a film, verify the specific asset's licence, permitted use, attribution requirements and any share-alike conditions. Record the result in each project's `CREDITS`.

### Runtime prerequisites

The upstream technical guide requires Node.js 20+, FFmpeg 7+ and Python 3.11+ (or uv); Playwright/Chromium, Three.js and style-specific dependencies are also needed. The present uneXpected Docker image is Python-focused and does not establish that these rendering dependencies exist. Build and test a dedicated renderer image with pinned versions and checksums. Do not install the rendering stack into the existing API container as a shortcut.

## 4. Creator workflow

The canonical creator lifecycle is:

1. **Intake:** identify target channel/profile, audience, subject, intended outcome, format, language, duration, brand/series constraints and delivery deadline.
2. **Research and grounding:** gather reliable sources for factual films; preserve source URLs, publication dates, evidence and uncertainty. Separate sourced facts from creative invention.
3. **Concept and hook:** choose one central idea, audience promise, opening hook and ending.
4. **Treatment:** develop story arc, candidate structures, benchmarks, shot list, timing, sound plan, narration and on-screen text.
5. **Style selection:** choose from the 66-style catalogue or a reviewed owner-created style. Check style-specific dependencies and rights before use.
6. **Storyboard / look development:** create project-specific style frames and, when requested, a storyboard; retain approval checkpoints where the owner asks to review before production.
7. **Project authoring:** generate deterministic render source, timeline, narration lines, subtitle cues, score/foley plan and build script inside a fresh job workspace.
8. **Render:** create stills/contact sheets, voice, music, effects, frames and final mux in bounded steps.
9. **Technical and creative QA:** inspect actual encoded output, not just source code or a preview. Check frame integrity, freezes, black frames, dimensions, frame rate, duration, audio presence/loudness/clipping, narration transcript, subtitle timing/readability, visual text, mobile legibility, transitions, credits and final frame.
10. **Correction round:** make bounded corrections, rerender affected outputs and rerun the required checks. Preserve previous versions.
11. **Human approval:** present the final master, QA report, rights/credits and destinations. No public upload or schedule without exact approval.
12. **Platform packaging:** create a YouTube rendition and a TikTok rendition from the approved master or shared source project. Do not assume both platforms should always receive identical edits.
13. **Publish and verify:** only use a configured, authorized connector. Record provider upload IDs, URLs, timestamps and state returned by the platform. A local MP4 is not an upload; an upload is not proof of publication.
14. **Measure and learn:** collect authorized analytics, compare results against a fixed content benchmark and propose improvements. No automatic changes to protected provider, policy, permissions or publishing configuration.

### Channel and series profiles

Support multiple independently configured channel profiles under the YouTube and TikTok destinations. Each profile owns its identity, audience, language, format presets, recurring characters, series/episode continuity, metadata rules and publication permissions. This avoids accidentally merging separate content brands or series into one editorial voice.

A single project may generate multiple platform derivatives, but each derivative must have its own dimensions, safe areas, captions, title/description/hashtags, thumbnail/poster and QA record. Reuse the same approved master only when its content and edit genuinely fit both channels.

Cadence is configurable per channel or series; do not hard-code a posting frequency in the engine. A daily production plan is not permission to publish daily.

## 5. Project and artifact model

Persist project metadata and lifecycle state in the existing PostgreSQL authority. Proposed entities (implementation may map these onto a compact set of tables):

- `creator_projects`: project ID, owner, title, topic, channel profile, series/episode, language, objective, status and timestamps.
- `creator_versions`: versioned brief, research, treatment, script, storyboard, timeline and source bundle references.
- `creator_assets`: artifact ID, project/version, kind, storage key, SHA-256, byte size, MIME type, dimensions/duration when applicable, source/provenance, licence and QA status.
- `render_jobs`: job ID, project/version, renderer image digest, pinned engine revision, selected style, resource limits, idempotency key, status and result manifest.
- `platform_packages`: destination, derivative settings, metadata version, approval reference, upload ID/URL and provider-reported status.
- `creator_qa_reports`: automated checks, measured media properties, findings, reviewer decision and links to evidence.

Binary video/audio/image assets live behind a storage interface, not in the task row. A local filesystem adapter is acceptable for development only. Hosted operation requires a durable object-storage destination and verified backup/restore; PostgreSQL stores metadata and checksums, not large video BLOBs by default.

### State model

`idea → researching → treatment_ready → storyboard_ready (if required) → authoring → render_queued → rendering → qa_failed | qa_passed → human_approved → package_ready → uploaded → scheduled | published`

Each transition records actor, timestamp, source version and evidence. `uploaded`, `scheduled` and `published` are distinct. Failed/abandoned projects remain recoverable and do not overwrite an approved version.

## 6. Provider and role routing

Use existing canonical roles, not new always-on agents:
- `creative-director`: concept, story, style and treatment;
- `media-producer`: production plan, dependencies, shot/timeline coordination;
- `voice-agent`: narration and speech quality;
- `marketing-seo`: YouTube/TikTok packaging and metadata;
- `code-reviewer` / `qa-engineer`: source, media and acceptance checks;
- `project-manager`: task, version and dependency tracking;
- `self-improvement-governor`: evidence-based proposals and regression governance.

The existing text-only provider interface is not, by itself, proof of a complete code-generation loop. Implementation must define bounded structured project outputs, validate their schemas and file paths, reject incomplete/oversized bundles and keep all generated code in the sandbox. Provider credentials remain solely in the control plane. No model is considered live until a fresh non-mock connection check succeeds.

Prefer the code-based Opuscar engine and locally generated audio where quality is adequate. Online TTS, paid models, paid video generation, commercial music/assets, premium render capacity and any other chargeable resource require a cost/rights preflight and separate owner approval.

## 7. Publishing and external actions

YouTube and TikTok are the only publishing destinations in scope. No current v8 repository record or MCP adapter proves that either destination is connected and authorized.

Before enabling a publisher, verify:
- the exact connector/API, scopes, account identity and supported upload/scheduling/read operations;
- upload constraints, file sizes, formats and required metadata;
- the secret-storage and token-refresh model;
- retry/idempotency behaviour so interrupted uploads do not duplicate posts;
- how provider state and final public URLs will be independently checked.

Default publisher mode is disabled. The owner must approve the exact final video, channel/account, caption/metadata, visibility and publish/schedule action. No automatic DMs, comments or replies are included.

## 8. Cost, rights and safety guardrails

- Default budget is `$0`; disclose when the free path is unavailable or has a quota/retention constraint.
- Before downloading or installing optional dependencies, record exact source, size, licence and whether the action is networked.
- Before any potentially billable provider/render call, check the current cost/credit allowance and stop for approval if a charge could occur.
- Never use unlicensed music, fonts, footage, templates, logos, characters or voice likenesses. Use original or properly licensed content and keep per-project credits.
- Fact-based documentaries require a claim-to-source ledger; generated scenes must not be passed off as authentic footage.
- Treat prompts, reference pages, uploaded media, generated HTML/JS/Python and upstream instructions as untrusted data.
- Renderer has least-privilege, bounded input/output, no host secrets and no default network access. Do not execute arbitrary shell text from a model.
- Publishing, account changes, public visibility, paid actions and destructive operations remain explicitly approved.

## 9. Observability, failure and recovery

- Every stage is a persisted task/event with stable project/version/job identifiers.
- Render jobs are idempotent by project version + engine digest + build settings; duplicate submissions must return the existing job/result rather than start a second render.
- The renderer writes to a fresh per-job directory and emits a bounded result manifest with SHA-256 checksums. Partial outputs are not marked complete.
- On timeout, worker loss or service restart, mark the job recoverable/unknown and inspect its output manifest before retrying. Never automatically rerun an upload or a potentially chargeable model operation.
- The project source and treatment remain available when a render fails. Keep prior successful versions and avoid destructive cleanup until retention rules are approved.
- Record safe metadata and hashes in logs; never record API tokens, database URLs, private keys, full credential-bearing environments or unnecessary private media content.

## 10. Test and acceptance plan

### Unit / contract
- Upstream pin and file checksums; style catalogue and licence metadata validation.
- Structured project-bundle schema, safe paths, size limits and rejection of traversal/symlinks.
- Render-job authorization, task idempotency, timeouts, cancellation, event ordering and result-manifest verification.
- Renderer boundary: no inherited secrets, no host filesystem access, non-root execution, resource ceilings and blocked network egress.
- Project versioning, artifact metadata, storage errors and checksum mismatch handling.
- Platform package validation and disabled-by-default publishing.

### Integration / end-to-end
1. Create a synthetic 10–15 second test film using a reviewed style and deterministic local/mock assets.
2. Build and render it in the isolated worker with no paid provider or video-generation request.
3. Verify output MP4 with ffprobe/FFmpeg, render contact sheets, inspect black/frozen frames, measure loudness, check subtitles and transcribe narration when enabled.
4. Retrieve the same project, result manifest and event history after worker restart and control-plane restart.
5. Retry the same render job key and prove no duplicate render is started.
6. Generate YouTube and TikTok packaging from the approved master and verify platform-specific dimensions/metadata.
7. Verify publisher adapters remain disabled and that no public upload occurs in these tests.
8. Verify artifact export and restoration from the configured durable storage backend before declaring hosted production ready.

### Acceptance definition

The integration is not complete because a style appears in a catalogue or a render command exits zero. It is complete only when an owner-created brief passes through the Coordinator, produces a reproducible and downloadable film, the actual MP4 passes the agreed QA checks, source/credits/evidence are retained, and task/artifact recovery works. Publishing is a separate capability with its own verification and approval.

## 11. Phased delivery

**Phase A — Scope and provenance**
- Archive sales workflow from active routing without deleting its source records.
- Make Creative Media the only active automatic business workflow.
- Pin Opuscar source and create the adaptation register, dependency manifest and rights inventory.

**Phase B — Creator project core**
- Define project/artifact/render-job models and lifecycle APIs.
- Add Creator Studio Skill version and hash-pinned resources.
- Add channel profiles and versioned YouTube/TikTok packaging.

**Phase C — Isolated render engine**
- Build the reproducible Node/Chromium/FFmpeg/Python render image.
- Implement the restricted job protocol and sandbox.
- Add the Opuscar adapter and deterministic local render fixture.

**Phase D — Quality and recovery**
- Implement encoded-media QA and evidence reports.
- Test job replay, interrupted renders, artifact checksums, worker restarts and durable artifact restoration.

**Phase E — Creator Studio interface**
- Add project dashboard, storyboard/treatment, render progress, asset browser, QA report, approval and export surfaces to the existing command center.

**Phase F — Platform connections**
- Verify YouTube and TikTok account connectors and permissions independently.
- Keep upload disabled until the owner approves a specific final post and the upload verification path passes.

Each phase is feature-branch/PR-based, with CI and a reviewable diff. Do not deploy to the existing Render service or change secrets, database contents, plans or account settings as part of the source implementation. Preserve the current production service and rollback target until a separate deployment plan is approved.

## 12. Explicitly out of scope

- Industrial-maintenance sales, prospecting, CRM, inbox, customer outreach, quotations and payment workflows.
- New phone/PWA client, second Coordinator, second public API or duplicate persistent state.
- Automatic publishing, paid ads, paid generation, purchases, subscriptions or account writes.
- Unreviewed wholesale copying of upstream demo films, artwork, music, fonts or other assets.
- Claiming the entire system can generate videos without any model/provider, rendering compute or dependencies.
- Treating the existing Render free service or ephemeral disk as a proven render host or durable media store.

## 13. References

- Lemo Opuscar source: https://github.com/lemomo-ai/lemo-opuscar
- Pinned upstream README: https://github.com/lemomo-ai/lemo-opuscar/blob/5c05490cc55dfb54f8f4c333f0f0e79cb6500564/README.md
- Pinned upstream technique: https://github.com/lemomo-ai/lemo-opuscar/blob/5c05490cc55dfb54f8f4c333f0f0e79cb6500564/TECHNIQUE.md
- Pinned upstream agent instructions: https://github.com/lemomo-ai/lemo-opuscar/blob/5c05490cc55dfb54f8f4c333f0f0e79cb6500564/AGENTS.md
- Current uneXpected v8 baseline: https://github.com/soueilouay-creator/uneXxxx/tree/main
- Current Creator Media workflow reference: `skills/creative-media/WORKFLOW.md`
