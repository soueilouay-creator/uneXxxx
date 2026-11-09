# Local-Only Creator Studio Implementation Plan

**Branch:** `feat/local-only-ai-creator-studio`  
**Plan date:** 2026-11-09  
**Design:** `docs/specs/2026-11-09-local-only-ai-creator-studio-design.md`

## Delivery goal

Implement a strictly local model route and a resumable Creator Team production workflow in the existing uneXpected V8 application. All normal generation calls must stay on loopback/private local processes. Bootstrap/download is a separate explicit operation. Cloud provider adapters must be unreachable when local-only mode is active.

## Task 1 — Local-only model route

**Files:** modify `unexpected_runtime/providers.py`, `tests/test_provider_router.py`, `.env.example`, README local runtime section.

**Interface:** `LocalOnlyProvider(base_url, model, default_timeout)`; `UNEXPECTED_AI_MODE=local_only`, `UNEXPECTED_LOCAL_BASE_URL`, and `UNEXPECTED_LOCAL_MODEL`.

**Behavior:** the provider accepts only HTTP loopback endpoints (localhost, 127.0.0.1, ::1), rejects public hosts, redirects and proxy use, uses the local OpenAI-compatible chat-completions schema without requiring an API key, bounds time and response size, and never falls back to mock/cloud. The router returns only the `local` route in local-only mode even if cloud keys happen to be present in the host environment.

**Tests:** local mode ignores cloud keys and exposes only the local route; remote URL and conflicting provider selections fail closed; local responses parse correctly; auth secrets are never attached; redirect/proxy behavior is blocked.

## Task 2 — Local model registry and bootstrap preflight

**Files:** create `local_ai/model_registry.json`, `local_ai/README.md`, `unexpected_runtime/local_ai.py`, `tests/test_local_ai.py`.

**Interface:** model registry records task, upstream repository, revision, runtime, model-weight licence status, expected local paths, checksum, hardware constraints and availability state. `inspect_local_ai(root, registry)` reports detected platform, CPU/RAM/disk, installed local executables and cached model files. `validate_model_lock` rejects malformed hashes, path traversal, unreviewed model-weight terms and missing local files.

**Behavior:** inspection is read-only. It must not download files, contact external URLs, start arbitrary processes or silently grant a capability. Unknown/uncached weights remain disabled. A missing video model does not block code-rendered/illustrated outputs if local assets and the required local text model exist.

**Tests:** deterministic fake filesystem/hardware probes; bad checksum, path traversal, missing weight and unreviewed licence stay unavailable; inspection makes no network request.

## Task 3 — Local runtime supervisor and offline launch

**Files:** create `local_ai/config.example.json`, `local_ai/start-local.sh`, `local_ai/start-local.ps1`, `local_ai/stop-local.sh`, `local_ai/stop-local.ps1`; modify `unexpected_runtime/cli.py` and CLI tests.

**Interface:** CLI `local-ai status|preflight|start|stop`. Runtime commands use explicit local binary/model paths and loopback binds. ComfyUI starts with offline and partner-node-disable flags. The renderer remains a separate networkless sandbox.

**Behavior:** preflight prints actionable missing dependency/model details. Start refuses to run when the selected runtime/model is not present or model licence is unreviewed. It does not install software or download models implicitly. Stop only terminates processes started by the supervisor and recorded with an owned PID record.

**Tests:** command contracts, safe PID ownership, non-loopback binding rejection, missing executable/model reporting, offline ComfyUI arguments.

## Task 4 — Persisted Creator Team orchestration

**Files:** create `unexpected_runtime/creator_team.py`, `skills/creative-media/references/local-only-creator-team.md`, `tests/test_creator_team.py`; integrate through `Coordinator` and the existing Creator Studio API only where tests prove the contract.

**Interface:** a bounded stage graph maps existing role IDs to research, creative direction, production, narration, packaging and QA. It uses the configured local provider route, persists each stage output/version and stage state, supports restart/resume, and returns a local project manifest.

**Behavior:** reuse existing role IDs and permission checks. No duplicate agent registry or independent coordinator. Each stage is idempotent by project/version/stage key; an interrupted stage is resumable; outputs are stored as local project artifacts; all factual claims without imported local sources are marked unverified. Public publishing remains disabled.

**Tests:** stage order and role assignments; provider route pinned to local; interrupted stage resume; replay without duplicate artifacts; provider failure leaves a recoverable blocked stage; no external publisher calls.

## Task 5 — Renderer integration and end-to-end offline acceptance

**Files:** modify renderer worker/QA tests and CI workflow; add a small synthetic offline Creator Team fixture.

**Behavior:** repair the missing `ffprobe` QA path and the failing Opuscar render smoke job. Test one complete short pipeline with a small local test model/mock only for deterministic CI plumbing; hardware model generation is separately gated and must never be mislabeled as an actual AI-model test. A target-machine acceptance run must generate a real original short with cached local models and outbound network blocked.

**Tests:** runtime suite, renderer E2E, no-network checks, encoded MP4 stream inspection, restart/recovery test and model-lock checksum verification.

## Boundaries

- Do not merge into `main`, deploy, change cloud secrets, or enable publishing.
- Do not commit model weights or credentials.
- Do not enable a model until its weight licence, revision and checksum are reviewed.
- No cloud or mock fallback in local-only production mode.
- Do not call the system a complete local AI video creator until target-machine offline end-to-end acceptance passes.

## Unresolved environmental fact

The current session has repository access but no direct shell/filesystem access to the owner's computer. Exact GPU/RAM detection, native runtime installation, model downloads and full hardware video-generation benchmarks must run through the local installer on that computer. The repository can provide the installer and acceptance checks; remote GitHub CI cannot prove the owner's local hardware capability.
