# Verified workflow lifecycle

## Canonical sequence

**Request → Plan → Execute → Verify → (Improve → Verify) ↻ → Deliver → Learn**

The runtime applies a quality gate at each stage. The initial review must pass before refinement starts. The specialist then improves the same candidate and the independent reviewer checks each revised version. Failed post-improvement feedback is fed into the next bounded improvement round; only a passing refined candidate can be delivered.

## Native runtime path

`Coordinator.run_lifecycle(agent_id, objective, inputs, max_corrections=1, max_improvements=3, deadline_seconds=60)` is the default specialist-backed path.

1. **Request:** stores the target role, objective and supplied inputs for this cycle.
2. **Plan:** calls the registered `project-manager` role for ordered steps, dependencies, risks and acceptance criteria.
3. **Execute:** calls the selected registered specialist role with the request and plan.
4. **Verify:** calls the independent `code-reviewer` role. Its first non-empty line must be exactly `VERDICT: PASS` or `VERDICT: FAIL`. Missing, malformed or failed verdicts fail closed.
5. **Iterative Improve & Verify:** after the initial PASS, calls the selected specialist to improve the same candidate, then calls `code-reviewer` again. If a revised candidate fails, the reviewer feedback is passed to the next improvement round, up to `max_improvements` (default 3, allowed 1–5). Each round is independently reviewed. A PASS ends refinement; exhaustion uses the remaining bounded correction/replanning budget or blocks delivery. The result records the number of improvements and each reviewer verdict.
6. **Learn:** records the terminal result, verification history and task provenance through `ImprovementGovernor.record_outcome`, including blocked cycles.

Each stage uses the regular coordinator invocation path and therefore inherits the configured provider, role instructions, timeouts, audit records and permission policy. This is an independent role-based model review—not a deterministic test suite, formal proof, or automatic verification of external facts. Tasks needing executable tests, source checks or domain-specific measurements must supply and run those checks as part of the specialist's work. The lifecycle itself does not grant privileged permissions or configure external tools.

## Retry and result contract

- Native coordinator correction budget is 0–2. The generic `WorkflowRunner` primitive supports 0–5 for host-specific use.
- A failed initial review returns to planning with reviewer feedback while correction budget remains.
- A failed post-improvement review returns the same candidate to the specialist for another improvement round. If the improvement budget is exhausted, the runner uses the remaining correction budget to replan/re-execute or blocks.
- Exhausting both the improvement and correction budgets produces `blocked_verification`; stage exceptions produce `blocked_execution`.
- No improve call occurs after a failed initial review. No delivery call occurs unless the initial review passes and an improved candidate subsequently passes independent review.
- Learning is attempted for delivered and blocked cycles. If learning fails, `learning_error` is surfaced separately; it does not turn a blocked cycle into success.
- `deadline_seconds` is a per-stage coordinator invocation deadline, not a total wall-clock budget for the entire cycle.

## Interfaces

- Python: `Coordinator.run_lifecycle(...)` for native role orchestration; `Coordinator.run_workflow(...)` for explicitly injected host adapters.
- CLI: `python -m unexpected_runtime.cli lifecycle <agent_id> --objective '...' --inputs '{}' --max-improvements 3`.
- Authenticated HTTP: `POST /v1/lifecycle` with `agent_id`, `objective`, optional `inputs`, `deadline_seconds`, `max_corrections` and `max_improvements`.

The lifecycle HTTP endpoint returns 200 only for `status=delivered`; blocked cycles return 502. It accepts 0–2 corrections and 1–5 improvement rounds (default 3). The generic `WorkflowRunner` and `Coordinator.run_workflow` expose the same bounded improvement option. The normal `POST /v1/invoke` endpoint remains available and unchanged.

## Delivery and self-improvement boundaries

`deliver` currently packages a local result for the caller. It does not publish content, send mail, write repositories, deploy, pay, delete or alter accounts. Those actions continue to require their own separately authorized integration and approval.

`Learn` stores outcomes; it does not rewrite role instructions or automatically promote code. The existing self-improvement governor's fixed benchmarks, regression checks, evidence fingerprints, human approval for protected changes and rollback rules remain authoritative.

The 38-role registry and existing provider/permission boundaries are preserved. Runtime activation in a hosted service still requires a separately verified deployment and live provider smoke test; a passing mock CI run does not prove live model access or deployment.
