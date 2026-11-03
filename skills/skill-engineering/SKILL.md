# Skill Engineering — Reusable Skill v1.0.0

## Trigger
Skill creation/adaptation, OmniSkill or agent-skill integration, specialist profile design, agent registry/command updates, install verification, or skill package QA.

## Steps
1. Inspect available source assets and installed skills.
2. Define capability and non-capability boundaries.
3. Write one versioned profile plus required index, command, test, and rollback updates.
4. Test triggers, overlap routing, unsafe writes, unavailable tools, persistence failures, and idempotent re-install.
5. Save to the exact Library path and read back; separately report UI activation and runtime authorization.
6. Publish release report with evidence and blocked items.

## Invariants
No invented agents/integrations; no secret handling in files/chat; no silent destructive overwrite; no consequential write without authorization and required approval; no completion claim without fresh verification.
