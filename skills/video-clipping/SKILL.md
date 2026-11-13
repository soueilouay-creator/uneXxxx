# Video Clipping & Shorts Extraction — Reusable uneXpected Skill

**ID:** `video-clipping`  
**Version:** `1.0.0`  
**Invocation:** Explicit user-invoked Skill (`user_invocable`)  
**Purpose:** Turn an authorized long-form video, VOD, or uploaded source into a set of reviewed vertical Shorts. This capability is reusable across channels and projects; it is not specific to Vice City Files or GTA.

## Current readiness — important

This Skill is registered as a workflow specification only. **No SupoClip worker, V8 adapter, remote MCP connection, or processing entitlement is currently installed or verified.** Its `allowed_tools` list is intentionally empty. The Skill cannot create, download, render, or retrieve clips until a real worker and reviewed adapter are separately implemented, enabled, authenticated, and tested.

Do not claim a task has started or a clip exists unless the verified adapter returns a real task ID and the finished MP4 is retrieved and checked. When the owner confirms that a computer is available, begin with the workstation and connection preflight in this Skill. Until then, the Android phone is a control surface only; do not try to host the complete SupoClip stack on it.

## Specialist routing

Use only the roles needed for the request:

- `media-producer`: source intake, clip-job plan, deliverable tracking, export and media QA coordination.
- `creative-director`: clip selection criteria, hook, context, pacing and editorial instructions.
- `research-scout`: source provenance, creator identity, usage permission and rights evidence.
- `code-reviewer`: independent review of the worker adapter, security boundaries, output checks and completion claims.
- `project-manager`: workstation setup, bounded milestones, blockers and recovery.

These are role specifications in the existing canonical registry, not independent always-on agents or extra coordinators.

## SupoClip source assessment and provenance

The proposed processing engine is [SupoClip](https://github.com/FujiwaraChoki/supoclip), pinned for this assessment to upstream commit [`bedf6ce43f8fe54d736db596db1f736508b7b6ec`](https://github.com/FujiwaraChoki/supoclip/tree/bedf6ce43f8fe54d736db596db1f736508b7b6ec).

At that revision, its README describes support for:

- YouTube videos.
- Twitch VODs and clips.
- Kick VODs and clips.
- User-uploaded video files.
- AI-assisted selection of roughly 3–7 moments, virality scoring, 9:16 framing, face-aware cropping, word-synced subtitles, hook titles and platform export presets.

**Live streams themselves are not supported.** A livestream request must wait for an accessible VOD/replay or an authorized clip. Verify the supported source path again when installing because upstream behavior can change.

SupoClip is licensed under **AGPL-3.0**. Preserve upstream notices and license terms. Before modifying or offering a modified SupoClip service to users over a network, review AGPL-3.0 source-availability obligations and retain the corresponding source for the deployed version. This Skill references the upstream project; it does not vendor SupoClip code into uneXpected.

Useful pinned references:

- [Upstream README](https://github.com/FujiwaraChoki/supoclip/blob/bedf6ce43f8fe54d736db596db1f736508b7b6ec/README.md)
- [Upstream license](https://github.com/FujiwaraChoki/supoclip/blob/bedf6ce43f8fe54d736db596db1f736508b7b6ec/LICENSE)
- [Architecture](https://github.com/FujiwaraChoki/supoclip/blob/bedf6ce43f8fe54d736db596db1f736508b7b6ec/docs/architecture.md)
- [Configuration](https://github.com/FujiwaraChoki/supoclip/blob/bedf6ce43f8fe54d736db596db1f736508b7b6ec/docs/configuration.md)
- [MCP server documentation](https://github.com/FujiwaraChoki/supoclip/blob/bedf6ce43f8fe54d736db596db1f736508b7b6ec/mcp/README.md)

## Source rights and safety gate

Before any source is submitted to a worker:

1. Identify the actual source URL, platform, channel/creator and whether it is a live stream, VOD, clip or uploaded file.
2. Establish that the user owns the content or has explicit permission/licensing that covers downloading, editing and the intended reuse. A publicly viewable URL alone is not permission. Do not assume that commentary, attribution or a fair-use label automatically makes reuse lawful.
3. Preserve the permission evidence, applicable terms, source URL, retrieval date, original title and requested use in the project record.
4. If rights are uncertain, stop at a research/draft stage and ask for permission or a properly licensed source. Do not contact a creator on the user's behalf; prepare a message only when requested and obtain approval before sending.
5. Do not process leaked or unreleased material, bypass DRM/access controls, use private sources without authorization, or remove watermarks/attributions to disguise ownership.

For GTA/gameplay projects, creator permission to clip a stream is separate from publisher rights in game footage, music and other assets. Check both applicable creator permissions and publisher/platform terms. Do not promise monetization rights.

## $0 budget and local-hosting policy

The user's default budget is **$0**. Use self-hosted processing on the owner's computer only after the owner confirms the machine is available and the setup is reviewed.

- Do not use SupoClip's hosted paid plans or paid clip-creation quota.
- Do not start trials, purchase credits, subscribe, or incur pay-per-use charges.
- Do not configure paid transcription, LLM, proxy, Apify, B-roll, storage or publishing providers. In particular, do not silently use services such as AssemblyAI, hosted LLM APIs or Apify fallbacks.
- Prefer local Whisper transcription and local Ollama inference where compatible with the installed SupoClip version and machine capacity.
- Check every dependency, model download, license, storage requirement, network path and free allowance before setup. A tool being open source does not make compute, storage, downloads or optional services free.
- If the required local path cannot meet the task without a paid service, stop and report the exact blocker. Never switch providers or use a free trial as a fallback.

The upstream application is a multi-service stack (Next.js frontend, FastAPI backend, Redis queue, ARQ worker, PostgreSQL and media storage). It is designed to run with Docker and a capable computer, not as a reliable full server stack on the owner's Android phone.

## uneXpected V8 integration boundary

- Keep uneXpected V8 as the sole user-facing Coordinator, approval authority and authoritative record of the user's request and its outcome.
- Treat SupoClip only as a replaceable, isolated media-processing worker. Its internal job queue/database may manage rendering jobs, but it must not become a second uneXpected coordinator or the source of truth for V8 tasks.
- The V8 adapter must be a reviewed capability with verified source, version, content digest, permission scope, data-access scope, authentication, bounded inputs/results, deadline and audit events.
- The adapter must be installed, explicitly enabled and revalidated before each use. A Skill declaration, source URL or tool name does not grant permission or create a connection.
- The current V8 MCP boundary is in-process and is **not** a remote MCP client. Do not claim the upstream SupoClip MCP server is connected. A future integration may use a narrow authenticated adapter to SupoClip's self-hosted API/MCP boundary, but the secure transport from the selected computer to the actual V8 runtime must first be designed and tested. Do not expose a workstation service directly to the public internet.
- Keep V8 bearer tokens, provider credentials, database URLs and SupoClip secrets out of prompts, source bundles, media metadata, logs and Git. Store any required secret only in the appropriate host secret store.
- Scope any eventual adapter to the minimum needed: create a clip task, read its status, list generated clips, and retrieve/export approved outputs. Do not register billing, subscription, account-management, direct-publishing or social-account tools.
- Do not run untrusted generated scripts or media-processing code in the credential-bearing V8 API process. Keep download/ingest and rendering isolated from the control plane.

## Workstation setup gate

When the owner confirms a computer is available:

1. Ask for the operating system and inspect CPU, RAM, free disk, GPU availability (if relevant), Docker support, Python/Node requirements and FFmpeg availability. Do not assume the computer is compatible.
2. Check the pinned SupoClip revision, setup instructions, required Docker services and local Whisper/Ollama configuration. Recheck upstream changes before changing the pin.
3. Estimate disk use and processing limits using a sample source length. Confirm that all chosen components and model weights are genuinely free to use for the intended purpose.
4. Present the exact components, ports, network exposure, permissions and data retention before installation. Keep the worker private; do not deploy it publicly or change production services.
5. Install only after the owner explicitly approves the specific workstation setup. Do not request credentials in chat.
6. Design the least-privilege authenticated bridge to V8. If the current runtime cannot securely reach the worker, keep it local and report that the remote control path is blocked rather than opening an unsafe port or adding another public API.
7. Run a small authorized test source end-to-end and preserve logs with secrets redacted.

## Clip production workflow

1. **Intake:** capture the source URL or upload, platform, intended project/channel, language, clip count, target duration, aspect ratio, caption style and editorial objective. Ask only for missing information that materially changes the job.
2. **Rights check:** complete the source-rights gate above. Record what reuse is allowed and what is not.
3. **Preflight:** verify the adapter and worker health, model availability, free disk, duration limits, $0 route, source accessibility and output directory. If any required service is unavailable or paid, block before submitting a job.
4. **Create task:** send only the user-approved source and bounded processing instructions. Store the returned worker task ID in the V8 task event. Never invent a task ID or progress state.
5. **Track:** read the real worker status with bounded polling. Do not duplicate jobs on timeout; determine whether the existing task is still running before any retry. A timeout alone is not evidence that processing failed.
6. **Collect:** retrieve actual MP4 outputs and their metadata from the verified worker. Keep the source URL, worker task ID, timestamps, clip rationale, transcript/caption data, rights evidence and output checksums together.
7. **Quality assurance:** inspect every encoded MP4, not just a job-success flag. Verify:
   - File opens and decodes; duration and frame rate are present and within the requested limits.
   - Portrait dimensions and aspect ratio are correct for 9:16 Shorts.
   - Audio and video streams exist as expected; speech is intelligible and not clipped or unintentionally muted.
   - Captions are synchronized, readable on a phone, correctly spelled where verifiable, and inside safe margins.
   - No unintended black frames, freezes, glitches, abrupt cuts, missing audio, watermarks or visual artifacts.
   - The opening hook has enough context, the clip has a coherent beginning and ending, and the edit does not materially misrepresent the source.
   - Rights/attribution requirements are met and the output checksum is recorded.
8. **Deliver:** present each verified MP4 with its title, source and timestamp range, short rationale, duration, QA status and rights notes. Distinguish machine checks from human review.
9. **Human approval:** keep the clips as private drafts for owner review. Do not upload, publish, schedule, contact creators, change accounts or enable SupoClip's direct-publishing path.

## Failure and recovery rules

- **No verified worker/adapter:** stop before task creation; provide a setup plan only and label processing `blocked`.
- **Live source only:** wait for an accessible VOD/replay or an authorized clip; do not claim live clipping is supported.
- **Unclear rights:** block processing until ownership or permission is evidenced.
- **Paid dependency or exhausted quota:** stop before charge; do not activate a trial or switch to a paid fallback.
- **Insufficient computer resources or storage:** report the measured constraint and offer a lower-cost configuration only if it remains genuinely free and meets quality requirements.
- **Worker timeout:** inspect the existing task before retrying; use bounded, idempotent retries only when the worker supports them.
- **Partial outputs:** preserve verified successful outputs, mark missing ones as failed, and do not silently report the whole batch as complete.
- **Bad export:** keep the previous output, record the failure, correct the cause and re-run QA. Never overwrite the last accepted file.

## Acceptance criteria

A batch is technically complete only when all delivered clips have:

- A source URL and documented rights basis.
- A real worker task ID and terminal success state.
- A retrieved MP4 file with a verified checksum.
- Verified duration, dimensions, frame rate and audio/video streams.
- Caption, visual-quality and content-context checks.
- A clear `QA passed`, `QA failed` or `human review pending` status.

Technical completion is separate from owner approval and from platform publication. No views, engagement or virality result is guaranteed.
