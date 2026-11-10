# uneXpected Cinematic Studio — Seedance 2.5 integration

**Status:** Implementation candidate on branch `feat/cinematic-seedance-local-studio`; not merged or installed on the Android device.
**Date:** 2026-11-10

## Objective

Add genuine AI-generated moving footage to the existing local Creator Studio without replacing the current Android Lite fallback, deleting projects, enabling publishing, or silently changing the existing local-only Creator Team.

## First connected production profile

- Provider: fal.ai queue API.
- Model: `bytedance/seedance-2.5/text-to-video`.
- Output: vertical 9:16, 480p or 720p source clips, 4–30 seconds per scene.
- Project cap: 12 scenes and 180 generated seconds per approved job.
- Native model audio: enabled for generated scene dialogue, ambience and effects.
- Shared character bible: appended to every scene prompt.
- Local assembly: download provider clips, verify media type and checksum, normalize dimensions/frame rate/audio, crossfade scenes, burn short captions, mux to a local MP4 and retain an SRT sidecar.
- QA: existing `CreatorVideoQA` validates the encoded MP4 and caption sidecar. Visual quality, character continuity, voice naturalness and lip synchronization remain human-review requirements.

The first release provides text-guided character consistency only. It does not guarantee identical faces across shots and does not yet accept generated character model-sheet image references. The next continuity milestone is a consented/reference-image upload and Seedance reference-to-video adapter.

## Cost and approval boundary

The read-only quote uses the provider's published frame-area token formula at $0.0214 per 1,000 tokens. The quote is an estimate, not a guaranteed final invoice. Current model schemas and pricing:

- https://fal.ai/models/bytedance/seedance-2.5/text-to-video
- https://fal.ai/models/bytedance/seedance-2.5/reference-to-video/api

A signed, 15-minute, single-use quote binds title, character bible, scenes, durations and resolution. The job submission route checks that the approved maximum equals the quote. Status, quote, UI refresh and preflight do not submit paid requests. A lost/uncertain submission is not automatically retried.

## Secret handling

- API credential is read on the local server from `FAL_KEY` or `~/.config/uneXpected-v8/cinematic.env`.
- The private file must not be a symlink and must have no group/other permission bits (mode 0600).
- The browser receives only provider configured/ready status. It never receives the key.
- Provider API requests use HTTPS and no redirect following. Media downloads accept only HTTPS fal media hosts or the falserverless Google Storage path; redirects must remain on those allowlisted destinations.
- Job manifests contain request metadata and local file hashes, not the provider secret. Provider queue IDs are removed from public job detail.

## API surface

- `GET /v1/creator/cinematic/status`: local preflight and credential-presence status; no provider network call.
- `POST /v1/creator/cinematic/quote`: validate scenes and return signed cost estimate; no provider network call.
- `POST /v1/creator/cinematic/jobs`: consume a signed quote and explicit approval; first point that may submit paid provider generation.
- `GET /v1/creator/cinematic/jobs/{id}`: poll already-submitted scene jobs, download completed results, assemble and QA locally.
- `GET /v1/creator/cinematic/jobs/{id}/file`: stream locally stored, checksum-verified master when assembled.

Publishing/scheduling and social-account access remain disabled.

## UI

Creator Studio has a separate AI Cinematic Studio panel. It accepts a title, common character/world bible, one paragraph per scene, one short caption per scene, duration and resolution. It first produces a quote. Only after the provider is configured and the owner checks the approval box can the generation button submit the signed quote. It polls job progress, shows the local assembled preview, and exposes a download.

Android Lite remains labelled as motion graphics and remains an offline fallback; it is not advertised as AI-generated footage.

## Agent ownership and improvement

The existing roles remain canonical:
- `creative-director`: original dramatic premise, story arc, visual style and scene direction.
- `media-producer`: scene prompts, shot planning, sequencing and production constraints.
- `voice-agent`: dialogue/voice direction and caption review.
- `self-improvement-governor`: fixed-benchmark review, evidence-backed improvement proposals and rollback.
- `system-architect` / `coding-engineer`: changes to the engine and adapters.
- `code-reviewer`: independent code and regression review.

This first code slice adds the footage-generation and assembly route. It does not yet add autonomous LLM storyboard authoring inside Termux; scene prompts are supplied in the panel until an approved, verified planning-model route is connected. The connected video-generation model is not treated as the planning agent.

## Acceptance gates

1. Unit tests cover quote formula, payload validation, tamper/expiry, single-use approval and key secrecy.
2. API tests cover authentication, quote-only behavior, explicit job approval and local media retrieval.
3. CI runs the full regression suite and renderer tests.
4. On Android, verify local FFmpeg reports `drawtext`, `xfade`, and `acrossfade` plus a font before enabling the service.
5. Configure provider key only in the private local file. Do not run a paid job until the owner reviews the quote.
6. First real output must be watched and heard. Technical QA alone cannot approve cinematic quality.
