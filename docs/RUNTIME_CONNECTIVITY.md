# Runtime connectivity and end-to-end setup

## Real AI provider gateway

The v7.3.1 Python runtime can call the existing uneXpected AI Studio service at https://unexpected-ai-studio.onrender.com/orchestrate. In `ai_studio_gateway` mode, that Node gateway holds the OpenAI, Anthropic and optional OpenRouter credentials, and Python receives only a separate bearer token. The alternative `openai_compatible` mode reads `UNEXPECTED_API_KEY` in the Python host environment; that direct-key mode is separate and must be protected by the host secret manager. Its base URL must use HTTPS and cannot contain embedded credentials, a query or a fragment; redirects are disabled so the authorization header cannot be forwarded to another host.

The gateway supports OpenAI Responses API, Anthropic Messages API, optional OpenRouter fallback, and a public TAAFT MCP connector limited to 28 read-only search/detail operations. Public TAAFT catalog access is not a personal TAAFT account connection. It does not expose private bookmarks, account settings or write actions.

Set in the Python service secret manager:
- UNEXPECTED_PROVIDER=ai_studio_gateway
- UNEXPECTED_GATEWAY_URL=https://unexpected-ai-studio.onrender.com/orchestrate
- UNEXPECTED_GATEWAY_MODE=openai, claude, or both
- UNEXPECTED_GATEWAY_TOKEN copied from the existing gateway's UNEXPECTED_ACCESS_TOKEN
- UNEXPECTED_GATEWAY_TIMEOUT_SECONDS=200

Use openai or claude for a single primary provider. both makes two parallel primary requests and a synthesis request, so it can cost more. The AI Studio gateway may try its configured OpenRouter fallback if paid providers fail. It must label fallback output; the Python adapter rejects MOCK or failed responses as real provider output.

The adapter requires HTTPS, rejects embedded URL credentials/query/fragment, does not follow redirects with its bearer token, caps prompts at 15,000 UTF-16 code units and responses at 1 MB, and bounds request timeouts. Provider POST failures are not retried by default because an upstream request may have been accepted before a timeout; retries require an explicitly retry-safe provider contract.

## Runtime HTTP API

Run with `python -m unexpected_runtime.http_api`. The built-in server speaks plain HTTP and binds to `0.0.0.0` by default; it does not terminate TLS. Before exposing it publicly, require HTTPS at a trusted ingress/reverse proxy and keep the origin private. On Render, use the platform's HTTPS ingress for the public service URL. Set `UNEXPECTED_RUNTIME_API_TOKEN` to a separate random secret of at least 32 characters. Never reuse the gateway token.

- GET /health: public, non-secret health metadata.
- GET /v1/status: bearer authenticated.
- POST /v1/invoke: bearer authenticated; accepts agent_id, objective, inputs, deadline_seconds, max_steps, idempotency_key and source_refs.
- POST /v1/lifecycle: bearer authenticated; accepts agent_id, objective, optional inputs, deadline_seconds (per stage) and max_corrections (0–2). It runs project-manager → selected specialist → code-reviewer → specialist improvement → code-reviewer final check, then records the outcome. HTTP 200 requires a delivered result; blocked verification returns 502. Each retry may cause another set of provider requests.

The API rejects permission scopes, approval claims and unknown fields. It exposes only unprivileged agent invocation and the local-result lifecycle. Lifecycle delivery returns a result to the caller; it does not publish or perform external actions. The API does not permit publishing, payment, account changes, repository writes, deletes, deployment or policy changes.

Example request JSON: {"agent_id":"orchestrator","objective":"Run a safe gateway smoke test","inputs":{},"deadline_seconds":195,"max_steps":6,"idempotency_key":"gateway-smoke-001","source_refs":[]}.

## Tool boundary

The TAAFT catalog tools are reachable indirectly through the existing OpenAI/Anthropic gateway and remain public read-only discovery. ChatGPT's GitHub and Render connectors are not automatically forwarded into the Python service. No GitHub or Render remote action adapter is included in this bridge; those require separately scoped credentials, explicit endpoint allowlists, dedicated tests and per-action authorization.

## Render test and production boundary

Create a separate Python service from soueilouay-creator/uneXpected-, branch integration/v7.3.1-governed-runtime. Do not replace unexpected-ai-studio. Keep auto-deploy disabled during review. A Free Render service is for testing only: it sleeps after 15 minutes idle, has an ephemeral filesystem and no persistent disks; runtime SQLite state and approval replay ledger are not durable. Do not enable privileged actions there. Production needs persistent storage or a managed transactional database and one active instance for the current SQLite approval ledger.

## Secret handoff and smoke test

1. In the existing Node gateway's Render environment settings, copy UNEXPECTED_ACCESS_TOKEN without displaying it in chat.
2. Add it to the Python service as UNEXPECTED_GATEWAY_TOKEN.
3. Generate a different random value for UNEXPECTED_RUNTIME_API_TOKEN.
4. Set the provider mode and gateway URL, then restart the Python service.
5. Confirm /health reports provider_configured=true and /v1/status reports version 7.3.1 and 38 agents.
6. Send a low-cost POST /v1/invoke or /v1/lifecycle using a harmless test objective, with Authorization: Bearer and the API token. Require a completed result and an explicitly LIVE model/provider label. /health alone never proves a live provider call.

Never put either bearer token in chat, Git, PR comments, screenshots or workflow logs.
