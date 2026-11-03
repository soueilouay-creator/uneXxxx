# Creative Media Studio — Workflow Reference v1.0.0

This folder stores the workflow reference for `/uneXpected/workflow_profiles/creative-media-studio.md`. It does not install an external renderer or authorize provider actions.

## Route selection
- Image creation or edits: native image generation/editing capability where suitable.
- Video generation/animation: use the currently callable video/media provider only after checking supported action, cost/credits, and required inputs.
- Voice/music/SFX: use the actual speech/audio generation tool available for the task; verify the result rather than claiming it played or was human-reviewed.
- Integrated campaign: combine only the assets necessary for the chosen platform and deliver captions/metadata only when useful.

## Required QA labels
`draft` → `technical checks passed` → `human review complete` → `uploaded`. From `uploaded`, a planned release may move through `scheduled` → `published`, while an immediate release may move directly to `published`. Each transition requires provider evidence; a scheduled state is not required for immediate publication.
