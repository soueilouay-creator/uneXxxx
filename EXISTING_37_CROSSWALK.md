# Existing 37-profile crosswalk

The 37 original `/uneXpected/agents/*.md` files are preserved unchanged and are read-only migration sources. Each has one canonical v7 spec. None is retired as redundant: responsibility review found distinct objective/input/output boundaries; the 120 upstream templates are merged as workflow capabilities rather than cloned into new agents.

| Legacy profile | Canonical v7 ID | Disposition | Reason |
|---|---|---|---|
| `/uneXpected/agents/orchestrator.md` | `orchestrator` | kept | Kept as a distinct responsibility: Route a goal into the smallest safe task graph, coordinate handoffs and synthesize one result. |
| `/uneXpected/agents/research-scout.md` | `research-scout` | kept | Kept as a distinct responsibility: Run a fast, scoped evidence scan and return the best primary sources and known unknowns. |
| `/uneXpected/agents/deep-research.md` | `deep-research` | kept | Kept as a distinct responsibility: Investigate multi-part questions with explicit subquestions, competing hypotheses and evidence grading. |
| `/uneXpected/agents/web-scout.md` | `web-scout` | kept | Kept as a distinct responsibility: Verify specific claims, dates, quotes, source credibility and link validity. |
| `/uneXpected/agents/coding-engineer.md` | `coding-engineer` | kept | Kept as a distinct responsibility: Implement and refactor software with runnable code, error handling and tests. |
| `/uneXpected/agents/system-architect.md` | `system-architect` | kept | Kept as a distinct responsibility: Design components, interfaces, data flows, deployment boundaries and failure modes. |
| `/uneXpected/agents/debugger.md` | `debugger` | kept | Kept as a distinct responsibility: Isolate root cause using reproducible symptoms, logs and discriminating tests. |
| `/uneXpected/agents/code-reviewer.md` | `code-reviewer` | kept | Kept as a distinct responsibility: Assess correctness, security, maintainability and regression risk independently of implementation. |
| `/uneXpected/agents/data-analyst.md` | `data-analyst` | kept | Kept as a distinct responsibility: Inspect datasets, validate quality and produce reproducible calculations and decision-useful summaries. |
| `/uneXpected/agents/document-rag.md` | `document-rag` | kept | Kept as a distinct responsibility: Answer questions grounded in user files with precise citations and contradiction tracking. |
| `/uneXpected/agents/business-strategist.md` | `business-strategist` | kept | Kept as a distinct responsibility: Evaluate business models, customer value, operating model, economics and validation experiments. |
| `/uneXpected/agents/competitor-intel.md` | `competitor-intel` | kept | Kept as a distinct responsibility: Compare competitors using current public evidence and identify defensible gaps. |
| `/uneXpected/agents/marketing-seo.md` | `marketing-seo` | kept | Kept as a distinct responsibility: Plan search-led content, positioning, editorial calendars and measurable campaigns. |
| `/uneXpected/agents/sales-intel.md` | `sales-intel` | kept | Kept as a distinct responsibility: Structure prospect qualification, account research, pipeline insights and outreach experiments. |
| `/uneXpected/agents/finance-coach.md` | `finance-coach` | kept | Kept as a distinct responsibility: Build budgets, cash-flow scenarios and savings plans with transparent assumptions. |
| `/uneXpected/agents/investment-research.md` | `investment-research` | kept | Kept as a distinct responsibility: Analyze investments, risk factors and scenarios without executing trades. |
| `/uneXpected/agents/legal-scout.md` | `legal-scout` | kept | Kept as a distinct responsibility: Research legal/regulatory questions by jurisdiction and date with primary-source grounding. |
| `/uneXpected/agents/career-coach.md` | `career-coach` | kept | Kept as a distinct responsibility: Tailor career materials and interview practice while preserving the user's actual history. |
| `/uneXpected/agents/learning-coach.md` | `learning-coach` | kept | Kept as a distinct responsibility: Teach a topic with scaffolded explanations, practice and feedback loops. |
| `/uneXpected/agents/travel-planner.md` | `travel-planner` | kept | Kept as a distinct responsibility: Build feasible itineraries using current opening hours, geography, budget and transit constraints. |
| `/uneXpected/agents/maintenance-engineer.md` | `maintenance-engineer` | kept | Kept as a distinct responsibility: Diagnose industrial equipment faults through safe isolation, structured measurements and OEM guidance. |
| `/uneXpected/agents/creative-director.md` | `creative-director` | kept | Kept as a distinct responsibility: Create coherent brand direction, naming, messaging and creative briefs. |
| `/uneXpected/agents/ux-reviewer.md` | `ux-reviewer` | kept | Kept as a distinct responsibility: Review usability, information architecture, accessibility and interaction clarity. |
| `/uneXpected/agents/product-manager.md` | `product-manager` | kept | Kept as a distinct responsibility: Turn user problems into requirements, prioritization, roadmap and measurable acceptance criteria. |
| `/uneXpected/agents/project-manager.md` | `project-manager` | kept | Kept as a distinct responsibility: Plan work, manage scope, dependencies, risks, milestones and closeout. |
| `/uneXpected/agents/browser-operator.md` | `browser-operator` | kept | Kept as a distinct responsibility: Plan or execute supported multi-step browser actions with page-content distrust and confirmation gates. |
| `/uneXpected/agents/media-producer.md` | `media-producer` | kept | Kept as a distinct responsibility: Produce scripts, storyboards, narration text, shot lists, edit plans and publishing metadata. |
| `/uneXpected/agents/meeting-analyst.md` | `meeting-analyst` | kept | Kept as a distinct responsibility: Convert meeting notes/transcripts into decisions, action items, owners and unresolved issues. |
| `/uneXpected/agents/knowledge-curator.md` | `knowledge-curator` | kept | Kept as a distinct responsibility: Organize durable project knowledge, provenance, deduplication, retention and retrieval boundaries. |
| `/uneXpected/agents/security-reviewer.md` | `security-reviewer` | kept | Kept as a distinct responsibility: Threat-model systems and workflows; review least privilege, secrets, data flow and supply-chain risk. |
| `/uneXpected/agents/rag-engineer.md` | `rag-engineer` | kept | Kept as a distinct responsibility: Design and implement retrieval, chunking, indexing, ranking, citations, evaluation and refresh pipelines. |
| `/uneXpected/agents/automation-architect.md` | `automation-architect` | kept | Kept as a distinct responsibility: Design event-triggered workflows with typed contracts, idempotency, approvals, observability and rollback. |
| `/uneXpected/agents/startup-due-diligence.md` | `startup-due-diligence` | kept | Kept as a distinct responsibility: Assess a company/project across market, product, team, financial, legal, operational and technical risks. |
| `/uneXpected/agents/health-info.md` | `health-info` | kept | Kept as a distinct responsibility: Explain health information, prepare questions and distinguish general guidance from urgent red flags. |
| `/uneXpected/agents/always-on-planner.md` | `always-on-planner` | kept | Kept as a distinct responsibility: Specify a real monitoring plan with source, schedule, thresholds, deduplication, alert channel and failure behavior. |
| `/uneXpected/agents/voice-agent.md` | `voice-agent` | kept | Kept as a distinct responsibility: Design voice dialogue, turn-taking, recovery, accessibility, escalation and voice evaluation. |
| `/uneXpected/agents/game-agent.md` | `game-agent` | kept | Kept as a distinct responsibility: Design game strategies, rules, search methods, simulations and evaluation metrics. |

## Roles not directly mapped by an upstream README entry
These five legacy roles remain active because their responsibilities are not directly represented by the current README-linked inventory: `sales-intel` (sales qualification/pipeline), `maintenance-engineer` (industrial fault isolation), `automation-architect` (integration contracts/retries/rollback), `startup-due-diligence` (cross-functional diligence synthesis), and `always-on-planner` (monitoring/alert specification). Related workflow cards may still hand off to these roles.

## New v7 core role
`self-improvement-governor` is new. It governs evaluation/promotion/rollback and does not replace the existing `orchestrator`, which routes ordinary task work.
