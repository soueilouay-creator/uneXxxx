# uneXpected v8 — Single Command Center

uneXpected v8 is one governed Python application with one desktop web command center, one coordinator, one canonical 38-role registry, one provider router, and one authoritative state layer.

**The command center is the system.** It does not forward work to a separate AI Studio gateway or a second Python service.

## What is included

- One Python HTTP application and one public API boundary.
- A desktop-first command center for system health, agents, tasks, the visual Workflow Studio, Skills & tools, providers, capabilities, approvals, audit, and improvement proposals.
- A searchable catalogue of 120 v6→v7 workflow candidates, with role mappings, source provenance, procedure steps, deliverables and acceptance checks. Candidate records are not treated as runnable deployments.
- The canonical 38 specialist roles and a hash-pinned Skill bundle registry with backward-compatible v1/v2 manifests.
- The governed coordinator and seven-stage workflow: Request → Plan → Route → Authorize → Execute → Verify → Deliver & learn.
- Resource Intelligence: permanent Awesome research index with provenance, independent license/security status and discovery-only adoption states.
- AI Quality Evaluation: bounded deterministic output checks for instruction following, prompt injection, grounding, safety, structured output and regressions.
- Native server-side provider adapters for OpenAI, Anthropic, OpenRouter and the OpenOx Responses API, plus explicit deterministic mock mode. Provider credentials remain server-side and live routes require a successful connection check.
- SQLite for local development and PostgreSQL for hosted shared state.
- Single-flight idempotency claims, replay detection, and a PostgreSQL one-use approval ledger.
- Additive database migrations and an explicit no-fallback rule for hosted PostgreSQL.
- A single Docker image and one Render web service definition.

## Explicitly excluded

- The previous phone/PWA app, mobile routes, service workers, install prompts, mobile workspace and phone-specific tests.
- The separate Node.js AI Studio server and its gateway bridge.
- Any second Python runtime service.
- Automatic publishing, spending, payments, external messaging, account changes, deployment or other consequential writes.

A future phone app, if requested, will be a separate client of the unified API. It will not contain a second coordinator or independent system state.

## Local development

Requires Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export UNEXPECTED_STORAGE_BACKEND=sqlite
export UNEXPECTED_DEFAULT_PROVIDER=mock
export UNEXPECTED_RUNTIME_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export UNEXPECTED_RUNTIME_BIND_HOST=127.0.0.1
export PORT=10000
python -m unexpected_runtime.http_api
```

Open `http://127.0.0.1:10000`. The command center asks for the API token; the browser keeps it in tab memory only. SQLite state is local development state, not durable hosted state.

Inspect the curated research catalog with `python -m unexpected_runtime.cli resources --validate`. A live quality evaluation is an explicit operator action and requires a configured, already verified non-mock route, for example `python -m unexpected_runtime.cli quality-eval --provider-route openrouter`. A mock or unverified route is rejected before evaluation tasks are created. The deterministic CI fixture suite tests evaluator contracts only; it is not live semantic model evidence.

## Provider configuration

Provider credentials must be stored in the host's secret manager, never in Git or browser storage.

- `OPENAI_API_KEY` and optional `OPENAI_MODEL`
- `ANTHROPIC_API_KEY` and optional `ANTHROPIC_MODEL`
- `OPENROUTER_API_KEY` and optional `OPENROUTER_MODEL`
- `OPENOX_API_KEY`, optional `OPENOX_BASE_URL` (default `https://api.openoxai.com/v1`) and `OPENOX_MODEL` (default `gpt-6-astra`); OpenOx uses the native `/responses` endpoint, not `/chat/completions`.
- `UNEXPECTED_DEFAULT_PROVIDER=mock|openai|anthropic|openrouter|openox`

A configured key is not a verified provider. Use the bounded **Test connection** action to verify a live route. Mock mode is never presented as a live provider.

## Hosted storage

Set `UNEXPECTED_STORAGE_BACKEND=postgres` and supply `DATABASE_URL` in the host secret manager. The app refuses to start in PostgreSQL mode if the URL or required v8 schema is unavailable; it never silently falls back to ephemeral SQLite.

Apply migrations in order from an isolated database branch before configuring the service:

1. Existing schema version 1.
2. `migrations/002_idempotency_claims.sql`.

For a fresh PostgreSQL database, apply `migrations/001_initial.sql` followed by `migrations/002_idempotency_claims.sql`. For an existing schema-v1 database, first compare it against migration 001, then apply only migration 002. The v8 adapter refuses to start before schema version 2. The included Render Blueprint creates one free web service only; it does not create a database.

The current Neon Free plan has no scheduled backup snapshots. Verify the current limits, backup/export destination, and restore process before relying on it for durable production records.

## Verified Skill bundles

The authenticated command center exposes `GET /v1/skills` for metadata-only Skill discovery. `POST /v1/invoke` accepts an optional `skill_ids` array (up to four unique IDs) for explicit user-invoked Skills. Task records persist the selected IDs, and the idempotency/approval action digests bind the selection.

- Manifest schema v1 remains compatible; schema v2 adds `invocation_mode`, `description`, `allowed_tools`, and hash-pinned `resources`.
- Invocation modes are `automatic` (trigger-matched), `user_invocable` (explicitly selected), and `always_apply` (attached only to mapped roles).
- Every Skill and bundled resource is pinned by SHA-256 and checked at load and again before context use. Paths must remain inside the package root.
- Only the main `SKILL.md` and explicitly typed `reference` files enter model context. `script` and `asset` resources are inert, are never executed, and are not injected.
- `allowed_tools` is descriptive metadata only. It never installs or authorizes an MCP tool; adapter verification, role permissions and host approvals remain authoritative.
- Selection limits: 4 requested Skills, 8 applied Skills, 32 resources per Skill, 256 KiB per resource, and 64 KiB of context per Skill.

Example authenticated request:

```json
{
  "agent_id": "maintenance-engineer",
  "objective": "Review the preventive-maintenance checklist",
  "skill_ids": ["maintenance-checklist"]
}
```

## Governed MCP adapter boundary

The v8.1 branch adds an in-process MCP adapter contract and an authenticated metadata catalog at GET /v1/mcp/tools. Adapters must match a reviewed capability record by source URL, publisher, version, content digest, permission scopes and data-access scopes. A capability must be installed, explicitly enabled and revalidated before each call.

Tool calls are role-scoped, permission-checked and bounded by JSON input/result sizes and a deadline. Audit events store hashes and safe metadata rather than raw arguments or results. A timeout is not retried automatically and only signals cooperative cancellation; Python cannot forcibly stop an already-running in-process adapter. Privileged MCP tools are rejected until durable approval/replay storage is verified, so this branch must not register write-capable adapters.

**Important:** this is an adapter boundary, not a remote MCP client. It does not discover or connect to external MCP servers, and no third-party tool is enabled by default. CI uses deterministic fake adapters.

## Bounded specialist delegation

The Coordinator exposes a bounded subagent workflow through POST /v1/subagents/run and its internal run_subagents method. A parent may delegate up to three sequential child tasks. Each child has:

- Its own task ID and role-specific memory namespace.
- Only the explicitly supplied JSON inputs; parent conversation and private context are not copied automatically.
- A maximum of four steps, a bounded deadline and a role handoff check.
- A deterministic parent-scoped idempotency key prevents duplicate child invocations when the same delegation is retried.
- A persisted parent_task_id and a concise result summary returned to the parent.

The maximum configured delegation depth is three. Cycles, unauthorized handoffs, oversized inputs and budget overflow fail closed. Parent approval never grants a child broader permissions. This release does not run child tasks in parallel or retry failed child runs automatically.

## Resumable task event reads

Authenticated GET /v1/tasks/{task_id}/events?after={event_id} returns ordered, bounded event pages from SQLite or PostgreSQL. The response includes next_cursor and has_more. A client reconnects by supplying the last received event ID; this only reads persisted history and never re-executes the task.

The command center includes a basic visual trace panel. Live streaming and detailed provider token/cost views remain future work. Cost is recorded only when an actual provider reports it or the runtime measures it; unknown values are not fabricated.

## Security and approval boundary

- One bearer-token boundary protects all `/v1/*` APIs.
- Provider keys and database credentials remain server-side.
- The browser cannot read or write database tables directly.
- All task execution passes through the Coordinator and permission policy.
- The approval ledger binds a one-use approval ID to an action digest and consumes it atomically.
- Consequential execution remains disabled until authenticated approval, transaction/replay, backup and restore tests all pass and the owner separately approves activation.
- A capability catalogue record is not proof that an integration is installed or authorized.

## Verification

Run the full suite:

```bash
python -m compileall -q unexpected_runtime
python -m unittest discover -s tests -v
```

The deployment contract tests assert one Python process, one Render web service, a `/health` check, PostgreSQL fail-closed behavior, and no phone/PWA assets in the v8 web tree.

## Migration and rollback

The original AI Studio repository and both old Render services remain untouched during migration. The v8 service must pass preview, provider, database, lifecycle, backup/restore and rollback checks before cutover. Retiring either old service is a separate operation requiring explicit final confirmation.

## Workflow Studio and open-source adaptation

The command center exposes the runtime lifecycle and a searchable v6→v7 workflow crosswalk. The 120 crosswalk records are clearly labelled mapped candidates until an executable implementation passes workflow tests. Skills are loaded from the hash-pinned manifest and filtered by canonical role. MCP tools appear only when an adapter is registered and provenance-verified. Architecture references and source-specific license notes are in `docs/OPEN_SOURCE_ADAPTATION_REGISTER.md` and `THIRD_PARTY_NOTICES.md`.

## Resource Intelligence and AI quality

The versioned catalog in `unexpected_runtime/data/resource_catalog.json` indexes [sindresorhus/awesome](https://github.com/sindresorhus/awesome) as a permanent discovery source. Linked repositories are separate candidates: their license, maintenance, dependencies and security posture are not inherited from the list. Catalog states distinguish discovered, triaged, verified, approved and integrated. No catalog read installs or authorizes a tool.

The authenticated command center exposes `GET /v1/resources`, `GET /v1/quality-evaluations` and the owner-initiated `POST /v1/quality-evaluations`. The CLI exposes `resources` and `quality-eval`. Quality runs are bounded to the versioned scenario set, use only a configured and verified non-mock provider, and request no privileged permissions. Reports retain case outcomes and output digests rather than duplicating raw output. Fixture/offline CI tests are labelled separately from live provider runs. There is no background catalog crawler, package installer, LLM-as-judge or automatic improvement promotion.

## License and public adaptation

Project-owned uneXpected source code and documentation are licensed under the [MIT License](LICENSE) to support reuse and adaptation. Third-party material is not relicensed by that grant: see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the preserved license files under `third_party/licenses/`. Upstream names, trademarks, logos and artwork remain with their respective owners.
