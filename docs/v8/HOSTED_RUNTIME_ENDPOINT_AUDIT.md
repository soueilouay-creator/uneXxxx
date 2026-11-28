# Hosted V8 runtime endpoint and authentication audit

**Date:** 2026-11-28  
**Status:** Render configuration and deployed source inspected; live HTTPS/authentication probe not independently completed. No Studio-to-runtime connection or new endpoint is authorized by this audit.

## 1. Render service inventory

Read-only inspection of the confirmed Render workspace returned these relevant services:

| Service | Repository / branch | Runtime | Auto-deploy | URL | Finding |
|---|---|---|---|---|---|
| `unexpected-v8-command-center` | `soueilouay-creator/uneXxxx` / `main` | Docker, Free, Frankfurt, one instance | Off | [Service](https://unexpected-v8-command-center.onrender.com) | Candidate hosted V8 command center |
| `unexpected-v731-runtime-test` | `soueilouay-creator/uneXpected-` / `integration/v7.3.1-governed-runtime` | Python, Free | Off | [Service](https://unexpected-v731-runtime-test.onrender.com) | Older V7.3.1 test runtime, not V8 |
| `unexpected-ai-studio` | `soueilouay-creator/uneXpected-ai-studio` / `main` | Docker, Free, Frankfurt, one instance | **On** | [Studio](https://unexpected-ai-studio.onrender.com) | Existing Studio; no changes made |

The command-center service reports `healthCheckPath=/health`, public IP allowlist `0.0.0.0/0`, and a configured HTTPS Render hostname. Render returned no managed PostgreSQL instances. The service detail payload did not establish a persistent disk or reveal environment-variable values.

The latest live command-center deployment is `dep-dbnjm095efls73bhjikg`, built from commit `8a67c823292901305cad670a60c2f24f0a047267` (2026-11-07). The current core `main` HEAD is `2828fe281b60ea0a343b24973b411bbad650e93e`; open draft PR #19 is at `d2568c181c81e5538c12a344b399c94783bd2f9a`. Auto-deploy is off, so neither newer source state is deployed. No deploy was triggered.

## 2. Deployed source contract (code evidence, not a live handshake)

At the deployed commit:

- `unexpected_runtime/http_api.py` defines a single bearer-token authorizer. It rejects a missing/short/non-ASCII configured token with HTTP 503, and mismatched credentials with HTTP 401 using `hmac.compare_digest`. The token must be at least 32 ASCII characters.
- `/health` is public and intentionally returns a small health/configuration projection. All `/v1/*` GET and POST routes pass through the same bearer-token check.
- `POST /mcp` also passes through that authorizer.
- `unexpected_runtime/mcp_server.py` mounts `/mcp` as stateless Streamable HTTP, uses JSON responses, caps request bodies at 64 KiB, enables DNS-rebinding protection and allowlists the exact Render hostname.
- `unexpected_runtime/coordinator.py` defaults to SQLite. PostgreSQL is selected only when `UNEXPECTED_STORAGE_BACKEND=postgres` and `DATABASE_URL` are configured. The Render connector did not expose the service's environment-variable values, so the actual configured storage backend and token presence are **not verified**.
- Existing local API tests prove that protected read routes reject missing bearer credentials and return structured responses with a test token. They do not prove the deployed service's current response.

Source references: [deployed HTTP API](https://github.com/soueilouay-creator/uneXxxx/blob/8a67c823292901305cad670a60c2f24f0a047267/unexpected_runtime/http_api.py), [deployed MCP transport](https://github.com/soueilouay-creator/uneXxxx/blob/8a67c823292901305cad670a60c2f24f0a047267/unexpected_runtime/mcp_server.py), [storage selection](https://github.com/soueilouay-creator/uneXxxx/blob/8a67c823292901305cad670a60c2f24f0a047267/unexpected_runtime/coordinator.py), and [local API auth tests](https://github.com/soueilouay-creator/uneXxxx/blob/8a67c823292901305cad670a60c2f24f0a047267/tests/test_command_center_api.py).

## 3. Live probe outcome

A read-only GET probe was attempted against `/health`, `/v1/status` and `/mcp` without credentials. The execution container could not resolve the Render hostname (DNS resolution failed before an HTTP response); the web fetcher also reported the URL inaccessible. Render request/application logs for 2026-11-21 through 2026-11-28 were empty, and no service events were returned for that interval.

This is an **environmental verification blocker**, not evidence that the service is down. No authenticated request was attempted, and no token or secret was read.

## 4. Security decision: do not expose reconciliation events yet

The current API uses one shared bearer token for both read and write-capable `/v1` operations and the MCP transport. There is no independently verified read-only operator identity/scope. Reusing that token in Studio would grant more authority than a read-only reconciliation panel requires.

Therefore this run does **not** add an HTTP route, Studio client, credential, environment variable, deployment, or state-changing control. The existing reconciliation storage method remains unexposed.

Before a read-only operator view can be enabled, independently verify:

1. The live `/health` TLS/HTTP response and certificate/hostname.
2. The live unauthenticated `/v1/status` response (401 when configured, or 503 when locked), then a safe authenticated status projection through an approved secret-bearing runtime—not by copying a token into chat.
3. The live `/mcp` unauthorized response and a separately approved, non-mutating MCP transport handshake.
4. The actual storage backend and persistence/backup path without exposing environment values.
5. A distinct read-only identity/scope that cannot invoke write-capable routes or MCP task submission.

Keep the Studio service and its auto-deploy setting unchanged. Do not merge or deploy while its current production auto-deploy guard has not been separately reviewed.

## 5. Preservation and cost

No repository source, migration, database, task, approval, memory, user record, Studio UI/PWA, provider configuration, secret, Render setting, deployment, DNS record or external integration was changed. No package, infrastructure or provider credit was added or used. GitHub Actions account-level billing and Render account-level usage telemetry are not exposed by these read-only checks.
