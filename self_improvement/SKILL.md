# Governed Self-Improvement Skill

## Purpose
Improve role instructions through evidence, not uncontrolled self-rewriting. Adapted conceptually from the upstream self-improving-agent-skills README (Google ADK/Gemini multi-agent web app); the upstream app itself is separate and not installed.

## Loop
1. Retrieve the current active version, baseline report and fixed benchmark ID. If unavailable, stop and establish a baseline before proposing changes.
2. Define scenarios and binary acceptance checks before editing. Include critical safety/permission/secret tests and targeted regression cases.
3. Record outcome and user feedback with provenance; identify one root cause.
4. Propose exactly one targeted versioned change with rationale, expected effect and rollback. Do not rewrite the active instruction directly.
5. Run the same scenarios and fixed checks on baseline and candidate. Do not compare different scenario sets.
6. Keep only if all critical checks pass, noncritical pass rate is >=90%, candidate score improves and no protected change is missing approval. Otherwise reject/revert.
7. Record versions, metrics, evidence, reviewer/approval, changelog and rollback target.
8. Share learning as provenance-tagged candidate knowledge; a human must review before it becomes shared/approved.

## Protected changes
Safety policy, permissions, provider/model, external tools, credentials and consequential code require human approval. The governor cannot bypass gates or approve its own protected change.

## Limits
One proposal per round; bounded tests and retry counts; no unbounded agent spawning, circular handoffs, blind copying of messages or automatic external actions. Mock scores measure software logic only, not real-model quality.
