# Runtime connectivity implementation plan

**Goal:** Connect uneXpected v7.3.1 to the existing real AI gateway and expose a bounded authenticated API, then verify the execution path.

**Architecture:** Reuse the existing Node AI Studio gateway as the provider credential boundary. Python uses a separate gateway bearer token. A small HTTP API exposes unprivileged agent invocation only. Existing TAAFT catalog access remains read-only; GitHub/Render app connectors are not implicitly forwarded to the remote runtime.

**Stack:** Python standard library, Coordinator, urllib, http.server, SQLite, unittest, GitHub Actions and Render.

## Constraints
- Keep mock as the default; enable real provider mode deliberately.
- Never put provider, gateway, GitHub or Render credentials in Git or chat.
- Reject non-live/mock gateway responses; bound request sizes and timeouts.
- Protect private API routes with a distinct bearer token and fail closed if missing.
- Reject permission and approval fields from public invocation requests.
- Keep PR #2 unmerged and production service unchanged pending independent review and live validation.

## Implementation tasks

- [x] Add AIStudioGatewayProvider, retaining OpenAI/Anthropic/OpenRouter secrets only in the existing gateway.
- [x] Add authenticated runtime HTTP API with /health, /v1/status and /v1/invoke.
- [x] Add tests for provider selection, secret-safe failures, bearer enforcement, request limits and the Coordinator-to-gateway path.
- [x] Document secret handoff, cost-aware model modes and the authorized-tool boundary.
- [ ] Deploy a separate locked Free Render test service with auto-deploy disabled.
- [ ] Add gateway bearer token and separate runtime API token in Render secret settings; never send them through chat.
- [ ] Run a real, low-cost model invocation and verify a LIVE provider label and completed Coordinator result.
- [ ] Implement GitHub/Render adapters only after separate read-only scopes, allowlists and tool-call schemas are agreed and tested.

## Outstanding safeguards

- The GitHub approval verifier remains a separate gate. It needs an independent reviewer and persistent state before privileged actions can be enabled.
- Render Free instances have no persistent filesystem; do not treat SQLite memory or the approval replay ledger as durable there.
- The ChatGPT GitHub/Render connectors are not available to the separate Python process merely because they are connected to this assistant.
