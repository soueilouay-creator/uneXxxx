# Capability Matrix — uneXpected v8.1 preview

This matrix describes the repository implementation on the v8.1 feature branches. A CI pass is not proof of production configuration, live credentials, external service access or deployment.

| Capability | Runtime status | What is actually available | Boundary / not yet proven |
|---|---|---|---|
| Single command center | Implemented in v8 | One Python HTTP application, Coordinator, desktop web UI and one API boundary | No separate mobile app or second coordinator; hosted cutover is not implied |
| Specialist registry | Implemented | 38 canonical role specifications | Roles are specifications, not 38 independent running models |
| Provider routing | Adapter code present | Deterministic mock plus OpenAI-compatible, Anthropic, OpenRouter and OpenOx routes | A real route requires host secrets and a successful live smoke test; mock is not live-model evidence |
| Skill bundles | Implemented in v8.1 Skills branch | Hash-pinned v1/v2 manifests, role mapping, automatic/manual/always modes, inert references/scripts/assets | No Skill can grant a tool or permission; draft PR #12 is not merged |
| SQLite state | Implemented | Local tasks, event log, capabilities, memory, idempotency and task lineage | Local filesystem persistence is not equivalent to durable hosted backups |
| PostgreSQL state | Adapter and integration tests implemented | Hosted shared state adapter, migrations and task-lineage persistence | Production backup, restore, failover and live environment configuration require separate verification |
| Task event cursors | Implemented in v8.1 branch | Authenticated event cursor API for SQLite/PostgreSQL plus a basic command-center task trace panel | No live streaming or detailed provider token/cost view; no task is re-executed on reconnect |
| MCP adapter boundary | Implemented in v8.1 branch | In-process descriptor/adapter contract, capability provenance matching, role scope, permission checks, bounded inputs/results and timeout handling | No remote MCP transport, server discovery, third-party server connection or external tool is configured; privileged MCP tools are blocked pending durable approval/replay proof; timeout cancellation is cooperative; CI uses fake adapters |
| Subagent delegation | Implemented in v8.1 branch | Up to 3 sequential child runs, depth limit, 4 steps per child, isolated supplied inputs, parent lineage and bounded summaries | No parallel child execution, automatic retry, background child queue or inherited privileged approval |
| Shared knowledge | Implemented foundation | Reviewed, provenance-tagged knowledge records | Document upload, chunking, vector indexing and full RAG retrieval are not implemented |
| Web/current-source research inside runtime | Not configured | External ChatGPT tools may be available outside this runtime | Web/current-source search is not wired into this runtime; external ChatGPT tools are not implicitly available to uneXpected |
| Browser actions / third-party connectors | Not configured | MCP adapter boundary can host reviewed adapters | No live browser, CRM, mail, GitHub write or other external connector is authorized by this branch |
| Code execution | Not granted to agents | Runtime tests and Python package code run in CI/host environment | No agent-facing arbitrary code interpreter or separate sandbox service |
| Scheduler / notifications | Not configured | No always-on scheduler shipped | Recurring tasks remain disabled until durable leases, approval/replay and recovery are proven |
| Image/video/audio generation | Not configured inside runtime | Workflow planning and reviewed Skills can describe production | No external rendering provider is connected by this runtime |
| Consequential actions | Denied by default | Permission policy and action-bound approval verifier interfaces exist | No publish, payment, external message, account change, destructive write or deployment is activated by these changes |
| Quality evaluation | Implemented foundation | Fixed offline regression and quality scenario contracts | Offline mock tests do not establish live-model quality |
| Self-improvement | Governed proposal foundation | Versioned proposals, fingerprints, evaluation and rollback concepts | Protected changes require human review; no silent self-modification |

## v8.1 CI evidence

The v8.1 feature branch is tested through GitHub Actions, including Python compilation, resource/quality contract validation, PostgreSQL migrations, the regression/security suite, single-process Docker image build, container smoke tests and CLI smoke tests. Only completed successful workflow runs count as CI evidence. They do not prove Render deployment or live external integration readiness.

## Operating rules

1. A catalog record is not an installed or authorized adapter.
2. An adapter can execute only when its capability is reviewed, installed, enabled and verified against its pinned provenance.
3. Tool calls are role-scoped, permission-checked, bounded and audited; timeout is not a retry signal.
4. Subagents receive only explicitly supplied data and have independent task IDs and role memory namespaces.
5. Event cursors read persisted history and never replay the original action.
6. No consequential execution is enabled by this capability matrix.
