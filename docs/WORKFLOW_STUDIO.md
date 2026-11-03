# Workflow Studio

## Runtime lifecycle

1. Request — parse the objective, context, expected deliverable and constraints.
2. Plan — define success criteria, dependencies, failure cases and bounded execution.
3. Route — choose canonical v7 roles, hash-pinned Skills and allowed capabilities.
4. Authorize — reject missing permissions; protected actions require exact, durable, one-use approval.
5. Execute — run bounded provider/tool calls and persist task/event state.
6. Verify — check the actual output and acceptance criteria; use bounded corrections.
7. Deliver & learn — store verified artifacts and record proposals without self-promoting protected changes.

## Catalogue semantics

The workflow catalogue asset contains 120 records from the v6→v7 crosswalk. Each record carries source, role mapping, inputs, procedure, expected deliverable, acceptance checks and safety notes. All are mapped candidates, not runnable, until connected to the Coordinator and passed through workflow integration/acceptance tests.

The two packaged workflow-profile documents (creative media and skill engineering) are procedural instructions, not independently deployable services.

## Skills and tools

The authenticated /v1/skills endpoint returns runtime-loaded and hash-verified Skill metadata. Automatic Skills are selected by the registry. The current manifest contains three active Skills and no manually invocable entries by default.

The authenticated /v1/mcp/tools endpoint returns registered, provenance-verified in-process MCP tools. A tool count of zero is a truthful state. The current MCP gateway does not open remote network connections by itself.
