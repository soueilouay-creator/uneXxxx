# uneXpected Local-Only AI Creator Studio — Design Specification

**Status:** Owner-directed design; local-only requirement confirmed  
**Date:** 2026-11-09  
**Repository:** `soueilouay-creator/uneXxxx`  
**Implementation branch:** `feat/local-only-ai-creator-studio`  
**Baseline:** Creator Studio PR #13 head `5872714a391f0008c6c58ccb20989b2ddc6efc45`

## 1. Mission and non-negotiable requirement

Turn uneXpected V8 into a self-hosted, local-only AI video production studio. The owner's requirement is that all AI inference, creative asset generation, voice, music, editing, rendering, project storage and agent coordination run on the owner's own computer. No external AI API, hosted inference provider, cloud video generation service, remote model fallback, cloud asset store or cloud-based agent execution is permitted.

The target production path is:

**Idea → local research/materials → script → storyboard → original images/scenes → narration → soundtrack/foley → motion/video generation → edit/render → encoded-video QA → local MP4.**

The local Creator Studio must continue to use uneXpected's existing Coordinator, policy boundary, state store and canonical role registry. It must not create a second uneXpected control plane.

Internet may be used only in a separate, explicit bootstrap/update operation to obtain source code, Python/package dependencies and model weights from approved upstream repositories. After bootstrap, the production profile must run with outbound network access blocked. The normal project/generation command must never download a model, phone home, call a remote service or silently switch provider.

## 2. Baseline facts and known blockers

The current Creator Studio implementation is on PR #13, branch `design/creator-studio-lemo-opuscar`, head `5872714a391f0008c6c58ccb20989b2ddc6efc45`.

Existing foundations visible in the branch include:
- the existing uneXpected Coordinator, registry, bounded SubagentRunner, permissions and shared state store;
- Creator Studio project/version records and a render-job contract;
- the pinned Lemo Opuscar code-rendering adapter and a one-shot isolated worker;
- a story-film compositor and encoded MP4 QA helpers;
- YouTube/TikTok project packaging, with publishing disabled.

The inspected CI run #145 (`42425988803`) has a passing `runtime-tests` job but failing `renderer-e2e`. The renderer image builds, but the real end-to-end tests fail because the outer QA process cannot find `ffprobe`; the Opuscar smoke render also exits unsuccessfully. This is a release blocker. The renderer must be repaired and tested before video generation can be called operational.

The current creator renderers assemble assets. They do not yet provide the complete local model pipeline needed to create the story, images, narration, soundtrack and generated motion from an idea.

## 3. Architecture

### 3.1 One uneXpected control plane

Retain one local uneXpected application:
- one authenticated local web command center and API;
- one Coordinator and the current canonical 38-role registry;
- one local-only provider router and permissions/approval policy;
- one SQLite development/local state authority initially;
- one project/artifact index with checksums, provenance and model references.

No Render deployment is required for local production. The local command center binds to loopback by default. Remote access is off by default.

### 3.2 Local inference services

All model runtimes are local processes or local containers. Internal calls may use loopback/private IPC, but must never leave the machine.

- **Text/agent inference:** `llama.cpp` (`llama-server`) is the first implementation candidate for GGUF local models. It supports CPU and several GPU backends and hybrid CPU/GPU inference. The final instruct model and quantization must be selected by a local hardware benchmark, not assumed from a repository name.
- **Image/video workflow runner:** ComfyUI is the local graph execution service. Production launch must use its offline mode and disable optional partner/API nodes. Only pinned, reviewed custom nodes and locally present model weights are allowed.
- **Video generation candidates:** Wan2.2 TI2V-5B is the first practical high-quality candidate to benchmark; its upstream project describes 720p/24fps text-to-video and image-to-video and indicates consumer GPU usage. LTX-2.5 is a second candidate, but its published full model bundle is approximately 66 GiB, so it is not the default. Quantized/offload workflows must be evaluated on the actual machine.
- **Image generation:** use a model available to ComfyUI with a verified model-weight licence. FLUX.1 schnell may be evaluated; do not assume that a repository licence automatically applies to the model weights or related assets. Model choice is benchmark- and licence-gated.
- **Narration:** Qwen3-TTS is a local candidate for English/French narration and expressive voice design. It documents ten languages, including English and French; Arabic is not in its published list. Voice cloning is disabled unless the owner supplies audio and confirms rights/consent.
- **Music/sound:** ACE-Step 1.5 is a local music generation candidate. Use locally generated or original sound effects; no network sound libraries in production.
- **Speech/transcription:** whisper.cpp provides local transcription for subtitle alignment and narration review.
- **Editing/rendering:** retain pinned Lemo Opuscar for programmatic motion/film styles, plus FFmpeg for muxing, subtitles, audio mixing and output encoding. These are deterministic production engines, not substitutes for the generative models.

Model repositories to evaluate/pin:
- llama.cpp — https://github.com/ggml-org/llama.cpp — MIT — reviewed head `0c6dca2faeb5650c74464bd5938f856058953ef9`
- ComfyUI — https://github.com/Comfy-Org/ComfyUI — GPL-3.0 — reviewed head `fca60fe70e5b84c5c6b058263653d15cb3401e44`
- Wan2.2 — https://github.com/Wan-Video/Wan2.2 — Apache-2.0 repository — reviewed head `1ea34ff48f87168174e12956e200b1d908b1c5ff`
- LTX-2 — https://github.com/Lightricks/LTX-2 — Apache-2.0 repository — reviewed head `4f521619ae0029e8fbb64d555030c2b121a33b4f`
- Qwen3-TTS — https://github.com/QwenLM/Qwen3-TTS — Apache-2.0 repository — reviewed head `022e286b98fbec7e1e916cb940cdf532cd9f488e`
- ACE-Step 1.5 — https://github.com/ace-step/ACE-Step-1.5 — MIT repository — reviewed head `ca1e85fe9430179831e6bc6be790c332190a3866`
- whisper.cpp — https://github.com/ggml-org/whisper.cpp — MIT — reviewed head `f92e1e4d1056700c39d4e86c1140f0a088fe1ab6`
- Lemo Opuscar — https://github.com/lemomo-ai/lemo-opuscar — MIT — existing pinned commit `5c05490cc55dfb54f8f4c333f0f0e79cb6500564`

These are repository-level starting points, not automatic permission to redistribute or commercially use every model. Before weights are downloaded or enabled, record the exact model repository, revision, weight-file SHA-256, model-card licence/terms, attribution, commercial-use restrictions, required attribution, model size and hardware requirement. A model with no verifiable weight licence is disabled by default.

### 3.3 Strict local-only provider boundary

Add an explicit runtime mode, for example `UNEXPECTED_AI_MODE=local_only`.

In this mode:
- only the local provider adapter may be selected;
- its base URL must resolve to loopback or a private local container endpoint on an allowlisted port;
- reject HTTPS/public hostnames, remote IPs, proxy environment variables, redirects, DNS-based external endpoints and any cloud provider configuration;
- do not instantiate OpenAI, Anthropic, OpenRouter, OpenOx or generic HTTPS adapters;
- no failover to mock or cloud on runtime failure;
- if the local model is stopped, out of memory, unverified or missing, fail closed with an actionable local diagnostic;
- log only safe model/runtime metadata; never prompt contents or secrets by default.

The existing deterministic mock is permitted for tests only. It must not be presented as real AI output or as a production fallback.

ComfyUI must start with the documented offline options (including `--offline` and disabled partner nodes). Its workflow JSON may contain only locally available nodes and assets. Block unapproved custom nodes and remote URL/image/video/audio inputs.

### 3.4 Local model supervisor and hardware profile

Add a local supervisor that:
1. detects OS, CPU architecture/cores, RAM, disk space, GPU vendor/device and available VRAM using safe, read-only probes;
2. checks pinned runtime versions and local model files/checksums;
3. selects a compatible model profile from a declared capability matrix;
4. starts/stops local inference services with bounded resource limits;
5. exposes readiness, liveness, loaded model identity, memory footprint and process status;
6. stops or degrades safely when a model crashes or exhausts memory;
7. does not download missing assets during normal generation.

The installer must not assume NVIDIA CUDA. Support discovery for NVIDIA, AMD, Intel and Apple Silicon where upstream runtimes permit it. Unknown hardware gets a conservative profile and a clear diagnostic.

Profile policy:
- **CPU-only / low-memory:** use the smallest quantized text model that fits; script/storyboard generation and code-based motion are allowed. Image/video diffusion may be disabled when the machine cannot run it practically. Use original vector/procedural visuals rather than pretending generated video was created.
- **Entry GPU:** enable image, narration and music models only after measured free-memory checks. Video generation remains optional and may use low-resolution/low-frame-count settings.
- **High-memory GPU:** evaluate Wan2.2 TI2V-5B and/or LTX-2.5 using pinned local workflows, quantization/offload and fixed benchmark clips.
- **Very high-memory GPU / multi-GPU:** permit larger video models only after measured performance, thermal and memory tests.

The exact model list, resolution, duration and concurrent workload are decided by a local capability probe and a reproducible benchmark. Do not promise 720p, full-motion video or real-time performance before this test passes.

## 4. uneXpected AI production team

Reuse the existing canonical roles; do not duplicate the registry or invent independent agents that cannot run in the current Coordinator. Add a versioned Creator Team workflow/role overlays that map:
- `orchestrator`: owns the task graph, dispatch, status and final synthesis;
- `creative-director`: creative brief, audience promise, hook, tone and story direction;
- `research-scout` / `deep-research`: local-only source pack research and claim grounding. In offline mode they may use only imported/local references; no web browsing;
- `media-producer`: treatment, storyboard, shot list, scene plan and edit specification;
- `voice-agent`: narration design, pronunciation, pacing and local TTS request;
- `marketing-seo`: locally drafted platform packaging and metadata;
- `qa-engineer` / `code-reviewer`: asset, source, media and technical acceptance checks;
- `security-reviewer`: licence, provenance, prompt-injection and sandbox review;
- `project-manager`: version, dependency, render and recovery tracking;
- `self-improvement-governor`: measured benchmark comparisons and change proposals.

Where the 38-role registry does not contain a sufficiently specialized role (for example, storyboard/continuity or sound design), define a bounded workflow role overlay inside the Creator Team Skill and map it to the existing `media-producer` or `voice-agent` ID. Only add a new canonical role if a demonstrated capability gap cannot be represented without breaking the existing role contract.

Every role uses the same local model service initially, with role-specific instructions and output schemas. The team is a real coordinator-managed workflow, not a claim of 10 separate models running in parallel. Existing SubagentRunner limits (bounded child count/depth/steps) must be respected or deliberately changed with dedicated regression tests. Pipeline stages are persisted so jobs can resume without rerunning successful work.

## 5. End-to-end pipeline

1. Intake: project idea, audience, channel, language, length and style.
2. Local grounding: optionally import user-supplied research/source documents; factual claims without local evidence are labelled unverified.
3. Creative development: logline, hook, outline, script and continuity bible.
4. Storyboard: scene prompts, reference sheets, motion directions, timings and captions.
5. Asset creation: local image model creates originals; local video model creates motion shots where supported; procedural animation covers unsupported scenes.
6. Audio: local TTS narration, local/generated music and sound; apply rights and voice-consent checks.
7. Assembly: timeline, transitions, subtitles, audio mix, thumbnail and platform-specific derivatives.
8. Render: isolated worker receives a validated project bundle only; no model/API credentials or unrestricted host paths.
9. QA: inspect actual MP4 with ffprobe/FFmpeg; frame sampling for black/freeze/continuity checks; check audio presence, loudness/clipping, caption timing, resolution, duration, codecs and checksum.
10. Human review: present master and QA evidence. Local generation and QA do not authorize publication.
11. Export: store a verified master and project manifest locally. Uploads, scheduling, comments, DMs and public sharing remain disabled unless separately approved.

## 6. Model and asset management

Create a machine-readable model lock/registry with at least:
- model_id, task (llm/image/video/tts/music/asr), upstream repository and exact revision;
- exact weight files and SHA-256 values;
- model card and weight licence URLs plus rights status;
- required runtime/version, GPU backend, VRAM/RAM/disk estimates;
- supported languages, maximum tested dimensions/frames/duration;
- benchmark suite, tested machine profile and measured throughput;
- status (`discovered`, `reviewed`, `download-approved`, `cached`, `verified`, `disabled`).

Do not commit model weights to Git. Store them in a configurable local model directory, separate from the source checkout and excluded from Git. Download only in a dedicated bootstrap command with a clear dry-run, size, licence and disk-space preflight. Verify hashes after download. Missing/corrupt models block that capability rather than invoking an external service.

## 7. Local installation and offline operation

Add a guided local installer for Windows, Linux and macOS, with platform-specific checks and clear diagnostics. It should:
- create isolated environments/containers;
- install pinned OSS runtimes and dependencies;
- detect hardware before model selection;
- show model/weight sizes, terms and required disk space;
- ask for explicit user confirmation for model terms where required;
- download selected model files only during bootstrap;
- generate local configuration without secrets;
- run smoke tests and write a checksum-protected local capability report;
- provide a single local start/stop/status command.

Production services bind to loopback or a private internal network. The renderer remains a non-root, no-network, resource-limited sandbox. Local outputs and databases are stored in the configured local workspace. Backups remain local unless the owner separately configures a destination.

## 8. Security, rights and safety

- No external AI API, web endpoint, partner node or hosted inference in `local_only` mode.
- Outbound network is blocked for normal generation and render services. Bootstrap/update is a separate command with explicit network use and a source allowlist.
- Model-generated code is untrusted and executes only inside the render sandbox.
- No provider keys, runtime tokens, database URLs or host secrets in model prompts, generated files or logs.
- No automatic publishing, messaging or account actions.
- Every image, audio, model, font, texture, LoRA and sample asset has its own provenance/licence record.
- Do not imitate real voices or use cloned voices without documented rights and consent.
- Retain previous accepted versions; fail closed; bounded retries; no uncontrolled self-modification.
- Self-improvement uses fixed benchmarks and regression tests; changes to model choice, permissions, network policy or publishing require human approval.

## 9. Acceptance criteria

The local-only Creator Studio is not complete until all of the following are demonstrated on the target machine:
1. The user can create a project in the uneXpected command center.
2. The Coordinator dispatches the Creator Team through existing canonical role IDs and persists every stage.
3. Text generation, image generation, video generation (where hardware supports it), narration, music and transcription are all performed by locally cached models.
4. No external provider is configured or invoked; outbound network is blocked during generation, with a test proving that no external socket/HTTP request is attempted.
5. The project resumes safely after interruption without duplicating completed stages.
6. The renderer produces an actual MP4; ffprobe validates video/audio streams and dimensions.
7. Automated QA runs and the human review checklist is completed.
8. The output and required project assets remain available locally after shutdown/restart.
9. A clean offline rerun succeeds after models have been cached.
10. CI includes unit/contract tests and a small synthetic renderer E2E fixture; hardware/model integration tests run only on a compatible self-hosted runner and publish the measured machine profile.

Passing repository CI alone is not evidence that local AI models are installed or that the owner's machine can run them. A target-machine acceptance report is required.

## 10. Staged delivery

**Stage A — repair and secure the foundation**
- Fix the current renderer E2E failures (outer QA ffprobe discovery and Opuscar smoke render).
- Add reproducible renderer and sandbox contract tests.
- Verify the real MP4 artifact and inspect its media streams.

**Stage B — local-only runtime**
- Add a strict LocalOnlyProvider and provider-router selection.
- Add local service supervision/health checks and a network-deny integration test.
- Prove cloud adapters cannot be selected in local-only mode.

**Stage C — Creator Team**
- Add the Creator Team Skill and a resumable persisted stage graph using current roles.
- Add role-specific JSON contracts, artifact handoffs, idempotency and failure recovery.

**Stage D — local model stack**
- Add ComfyUI offline runtime and pinned workflow contracts.
- Add local model manifest/cache manager; implement local LLM, image, TTS, music, ASR and video adapters.
- Select weights only after hardware and licence preflight.

**Stage E — end-to-end acceptance**
- Generate one original short from an idea entirely offline.
- Generate a longer sample only if the target hardware and measured performance support it.
- Run creative and technical QA, restart recovery, and offline regression tests.

## 11. Explicit non-goals for this build

- No public deployment or cloud production runtime.
- No internet research during offline generation.
- No hosted AI/video services or APIs.
- No automatic YouTube/TikTok uploads or schedules.
- No purchase, paid model access, paid storage or subscriptions.
- No deleting existing system state, project history, archived business files or rollback targets.
- No claim that a feature is working until the target-machine acceptance criteria and evidence exist.

## 12. Design review checklist

- [x] Local-only runtime and no-cloud-fallback requirement is explicit.
- [x] One uneXpected Coordinator/registry remains authoritative.
- [x] Existing renderer CI blocker is carried into Stage A.
- [x] Model source, code licence and model-weight licence are treated separately.
- [x] Hardware-adaptive profiles avoid assuming access to a particular GPU.
- [x] Network-deny, offline restart and end-to-end MP4 tests are required.
- [x] Publishing and destructive actions remain disabled.
- [ ] Target-machine hardware profile and exact model/weight lock remain pending local detection.
