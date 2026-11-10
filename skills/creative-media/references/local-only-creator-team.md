# Local-only Creator Team

The Creator Team is a bounded workflow executed by the existing uneXpected V8 Coordinator. It does not create a second coordinator or registry.

## Canonical stage map

1. `research-scout` — inventory project-provided local sources; mark unsupported facts unverified.
2. `creative-director` — original concept, audience promise, hook, arc and style.
3. `media-producer` — script, storyboard, scene prompts, motion direction, timeline and asset manifest.
4. `voice-agent` — final narration text, pronunciation, pacing, voice notes, captions and local sound brief.
5. `marketing-seo` — YouTube/TikTok metadata and platform-specific derivatives.
6. `code-reviewer` — consistency, rights/provenance, offline policy and production-package review.

## Execution contract

- The runner must resolve the `local` route and verify the selected provider is marked local before invoking any stage. No cloud model or remote service fallback is permitted.
- Every task includes a local-only network policy and uses an idempotency key scoped to project and stage.
- Every completed output is saved as a new immutable Creator Studio version with stage ID, canonical role ID, provider route and originating task ID.
- On resume, completed stages are reused; missing stages run in order. Failure records a blocked event and stops downstream work.
- Model-generated instructions and source code are untrusted. Generated executable code is only executed in the isolated renderer, never in the API process.
- The runner prepares a creative package only. Actual image, video, voice and music generation must be done by their verified local runtimes. Rendering and encoded-media QA remain separate gates.
- Upload, scheduling, comments, DMs and replies are disabled.

## Stage acceptance

Each stage output must be non-empty and saved. The final review must clearly separate verified local evidence from creative assumptions and missing assets. A `production_package_ready` result is not a rendered video.
