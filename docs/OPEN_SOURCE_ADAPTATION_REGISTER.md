# Open-source adaptation register

This public repository studies external architecture and workflow projects, but intentionally integrates only patterns and independently written adapters. It does not copy a dependency wholesale, execute discovered repositories, or treat a public project as an authorised integration.

| Source project | Inspected public information | Pattern adapted for uneXpected | Not copied |
| --- | --- | --- | --- |
| [StarNet](https://github.com/androoAGI/starnet) | README, code map, harness architecture, skill ecosystem; upstream notes MIT for code and excludes brand/artwork. | Operations visibility, capability permissions, task traces, skill lifecycle. | Desktop packaging, artwork, brand, second runtime. |
| [LibreChat](https://github.com/LibreChat-AI/LibreChat) | Public metadata reports MIT; README documents multi-provider routing, Agents, MCP, SKILL.md, trace/cost viewer and approvals. | Provider-agnostic routing, Skills/tools inventory, trace visibility. | LibreChat application code and UI. |
| [LangGraph](https://github.com/langchain-ai/langgraph) | Public metadata and README report MIT; README describes durable execution, human-in-loop, memory and trace/debug. | Persistent checkpoints, approval interrupts, bounded recovery, audit events. | No LangGraph runtime dependency. |
| [n8n](https://github.com/n8n-io/n8n) | README describes visual workflow canvas, approvals, observability and integrations; fair-code/Sustainable Use/Enterprise license. | Workflow catalogue UX and provenance-first design. | No n8n source, nodes, assets or templates. |
| [MCP reference servers](https://github.com/modelcontextprotocol/servers) | README says reference implementations are educational and not production-ready. | Protocol boundary with scoped tools, provenance, limits and least privilege. | No reference server enabled by default. |
| [awesome-llm-apps](https://github.com/Shubhamsaboo/awesome-llm-apps) | Upstream commit and license/provenance recorded in the v6→v7 crosswalk. | 120 candidates mapped to canonical v7 roles. | Not 120 extra agents or runnable deployments. |

## uneXpected integration contract

- One application: one Coordinator, one registry, one policy boundary and one authoritative storage abstraction.
- Agents: 38 canonical v7 role profiles are defined in the agent manifest and agents directory. A profile is not a live worker until a task run is created and recorded.
- Skills: active hash-pinned Skills in the manifest are loaded by the runtime. Role scope and invocation mode are enforced by SkillRegistry; Skills never grant permissions by themselves.
- Workflows: the lifecycle is executed through WorkflowRunner with injected stage adapters. The 120 crosswalk records are discovery/adaptation specifications, not deployed workflows.
- Tools: MCP adapters must be registered, provenance-matched, capability-reviewed and enabled. The command centre reports actual registered adapters.
- Approvals: protected actions remain fail-closed until durable transactional one-use approval and replay boundaries are verified in the target host.
- Improvements: changes are proposals until fixed benchmarks and regression tests pass and a human approves protected promotion; rollback remains available.

## Public-source and license policy

The repository itself is public to support inspection and adaptation. Public visibility is not an open-source license grant. Reuse of third-party code, workflow text, designs, trademarks or media requires source-specific license and attribution review. The project-level license should only be declared after that audit is complete. External adapters stay disabled until credentials, user authorization, network access, pricing and tests are configured.
