# uneXpected Unified — zero-spend deployment readiness

## Current verified state (2026-11-03)

- Public source: [soueilouay-creator/uneXxxx](https://github.com/soueilouay-creator/uneXxxx), default branch `main`.
- Runtime: one Python command center, 38 role profiles, 3 active Skills and 120 mapped workflow candidates.
- The checked-in `render.yaml` defines one Free Docker web service in Frankfurt, with `autoDeploy: false` and `/health`.
- **No Render service is currently linked to this repository.** The four existing services in the connected workspace still point to older repositories; they were not changed.
- The existing Neon project `unexpected-v8-unified` is on the Free plan. Its default `main` branch has migration versions 1 and 2. A manual snapshot named `uneXpected-pre-v8-migration-2026-11-03` was created before the migration. The snapshot schedule is empty.
- No live provider key, live model call, remote MCP server, external connector, or trusted GitHub approval verifier is configured for a new Render service.

## $0 deployment contract

**Do not create or deploy a service until the Render workspace billing guard has been checked and it is confirmed that usage cannot create a charge.** This is a deliberate safeguard for the no-spend requirement, not a code limitation.

The current Render Free/Hobby documentation describes:

- 750 Free instance-hours per workspace per calendar month, shared across its Free services.
- 5 GB of included outbound bandwidth and 500 build-pipeline minutes for a Hobby workspace.
- A Free web service spins down after 15 minutes without inbound traffic and its filesystem is ephemeral; local changes are lost on restart, redeploy or spin-down.
- Outbound bandwidth beyond the included amount is currently listed at **$0.15/GB**. With a payment method, overages can be billed; without one, Render suspends Free services instead. The connected Render tools cannot inspect or set the account's billing payment method or spend limit, so a $0 total charge cannot yet be guaranteed.

Official sources:
- [Render Free instances and limits](https://render.com/docs/free)
- [Render outbound bandwidth pricing and billing](https://render.com/docs/outbound-bandwidth)
- [Render Blueprint environment variables](https://render.com/docs/blueprint-spec)
- [Render environment variables and secrets](https://render.com/docs/configure-environment-variables)

The existing Neon Free project currently reports a 1 GB logical-storage limit and 100 CU-hours per project per month; its configured instant-restore history is 6 hours. Scheduled Neon snapshots are available only on paid plans according to Neon's published snapshot guidance. The manual snapshot listed above is not a recurring backup.

Official sources:
- [Neon Free plan update (1 GB per project)](https://neon.com/blog/neon-free-plan-1-gb-per-project)
- [Neon snapshot scheduling and paid-plan availability](https://neon.com/blog/three-ways-to-use-your-snapshots)
- [Neon branching and restore-window guidance](https://neon.com/blog/practical-guide-to-database-branching)

## Blueprint configuration

The initial Blueprint intentionally includes only non-provider settings:

| Variable | Initial value / purpose |
|---|---|
| `UNEXPECTED_STORAGE_BACKEND` | `postgres`; no hosted SQLite fallback |
| `UNEXPECTED_APPROVAL_LEDGER_BACKEND` | `postgres` |
| `DATABASE_URL` | `sync: false`; set privately to the existing Neon `main` connection string |
| `UNEXPECTED_RUNTIME_API_TOKEN` | `generateValue: true`; Render generates the bearer token |
| `UNEXPECTED_DEFAULT_PROVIDER` | `mock`; no paid model calls are made |
| `UNEXPECTED_MAX_WORKERS` | `4` |
| `UNEXPECTED_MAX_RETRIES` | `1` |
| `UNEXPECTED_STATE_DIR` | `/tmp/uneXpected-state`; hosted durable state is PostgreSQL |

Optional provider keys are deliberately absent from the initial Blueprint. Do not configure OpenAI, Anthropic, OpenRouter or OpenOx until a separately confirmed no-cost/free-credit path exists. An adapter in source code is not permission to incur usage charges.

The GitHub approval verifier also remains unconfigured: its read-only token, exact repository allowlist and trusted reviewer identities are not set. The application must continue to report privileged execution as fail-closed.

## Apply only after the billing guard is confirmed

1. In the Render Dashboard, confirm the workspace's current billing state, payment-method status, included usage and spend-limit behavior. Keep the workspace on its Free/Hobby tier.
2. If the dashboard cannot guarantee no charges beyond included usage, do not apply the Blueprint.
3. Open the [Render Blueprint creation page](https://dashboard.render.com/blueprint/new?repo=https://github.com/soueilouay-creator/uneXxxx) and review the single Free web service.
4. During initial creation, enter the Neon `main` connection string into the private `DATABASE_URL` prompt; keep the generated runtime API token private.
5. Verify the selected commit is on `main`, keep automatic deployment disabled, and apply only the Free web service. The Blueprint does not create another database.
6. Wait for the deploy to reach `live`; then verify `GET /health` reports storage readiness and `GET /` serves the command center.
7. In the UI, use the generated bearer token from Render's private environment settings. Verify authenticated status, 38 roles, 3 Skills, 120 mapped workflow candidates, registered tool count (currently 0), a mock invocation, persisted task events and task trace access.
8. Recheck service metrics and workspace included usage. Stop if a threshold could trigger a charge.

## Rollback and safety

- Keep all four existing Render services unchanged until the new service has passed the full hosted checks.
- The Free Render filesystem is ephemeral. Hosted task, event, approval and idempotency state must use PostgreSQL; never switch the new hosted service to SQLite.
- No automatic snapshot schedule is configured on the current Neon Free plan. Keep the manual pre-migration snapshot and do not claim continuous backup coverage.
- A complete backup and restore test to a disposable branch is still required before treating the deployment as production-ready.
- Consequential actions remain disabled until the trusted verifier, durable one-use approval ledger, idempotency/replay checks, backup and restore tests all pass. Do not enable publishing, payments, messages, account changes, destructive writes or autonomous deployment.
- Retire the older services only after the new one is verified and a separate rollback/cutover review is complete.
