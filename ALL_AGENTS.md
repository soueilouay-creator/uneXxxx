# All Canonical Agent Specs

**38 active roles.** Each role has a separate spec in `agents/`; this file is an index, not a substitute for individual specs.

## Agent Orchestrator (`orchestrator`)
Route a goal into the smallest safe task graph, coordinate handoffs and synthesize one result.
Capability: `chat-native adaptation` · Version `1.0.0` · Memory `agent:orchestrator`
Spec: `agents/orchestrator.md`
Mapped upstream workflows: 19

## Research Scout (`research-scout`)
Run a fast, scoped evidence scan and return the best primary sources and known unknowns.
Capability: `tool-gated` · Version `1.0.0` · Memory `agent:research-scout`
Spec: `agents/research-scout.md`
Mapped upstream workflows: 6

## Deep Research Planner (`deep-research`)
Investigate multi-part questions with explicit subquestions, competing hypotheses and evidence grading.
Capability: `tool-gated` · Version `1.0.0` · Memory `agent:deep-research`
Spec: `agents/deep-research.md`
Mapped upstream workflows: 20

## Web Scout & Fact Checker (`web-scout`)
Verify specific claims, dates, quotes, source credibility and link validity.
Capability: `tool-gated` · Version `1.0.0` · Memory `agent:web-scout`
Spec: `agents/web-scout.md`
Mapped upstream workflows: 11

## Coding Engineer (`coding-engineer`)
Implement and refactor software with runnable code, error handling and tests.
Capability: `external-runtime-required` · Version `1.0.0` · Memory `agent:coding-engineer`
Spec: `agents/coding-engineer.md`
Mapped upstream workflows: 17

## System Architect (`system-architect`)
Design components, interfaces, data flows, deployment boundaries and failure modes.
Capability: `tool-gated` · Version `1.0.0` · Memory `agent:system-architect`
Spec: `agents/system-architect.md`
Mapped upstream workflows: 27

## Debugging Specialist (`debugger`)
Isolate root cause using reproducible symptoms, logs and discriminating tests.
Capability: `tool-gated` · Version `1.0.0` · Memory `agent:debugger`
Spec: `agents/debugger.md`
Mapped upstream workflows: 1

## Code Review & Test Engineer (`code-reviewer`)
Assess correctness, security, maintainability and regression risk independently of implementation.
Capability: `measurements-required` · Version `1.0.0` · Memory `agent:code-reviewer`
Spec: `agents/code-reviewer.md`
Mapped upstream workflows: 24

## Data Analyst (`data-analyst`)
Inspect datasets, validate quality and produce reproducible calculations and decision-useful summaries.
Capability: `measurements-required` · Version `1.0.0` · Memory `agent:data-analyst`
Spec: `agents/data-analyst.md`
Mapped upstream workflows: 7

## Document & RAG Analyst (`document-rag`)
Answer questions grounded in user files with precise citations and contradiction tracking.
Capability: `tool-gated` · Version `1.0.0` · Memory `agent:document-rag`
Spec: `agents/document-rag.md`
Mapped upstream workflows: 38

## Business Strategist (`business-strategist`)
Evaluate business models, customer value, operating model, economics and validation experiments.
Capability: `chat-native adaptation` · Version `1.0.0` · Memory `agent:business-strategist`
Spec: `agents/business-strategist.md`
Mapped upstream workflows: 6

## Competitor Intelligence Analyst (`competitor-intel`)
Compare competitors using current public evidence and identify defensible gaps.
Capability: `tool-gated` · Version `1.0.0` · Memory `agent:competitor-intel`
Spec: `agents/competitor-intel.md`
Mapped upstream workflows: 5

## Marketing & SEO Agent (`marketing-seo`)
Plan search-led content, positioning, editorial calendars and measurable campaigns.
Capability: `tool-gated` · Version `1.0.0` · Memory `agent:marketing-seo`
Spec: `agents/marketing-seo.md`
Mapped upstream workflows: 1

## Sales Intelligence Agent (`sales-intel`)
Structure prospect qualification, account research, pipeline insights and outreach experiments.
Capability: `connector/authorization-gated` · Version `1.0.0` · Memory `agent:sales-intel`
Spec: `agents/sales-intel.md`
Mapped upstream workflows: 0

## Personal Finance & Budget Coach (`finance-coach`)
Build budgets, cash-flow scenarios and savings plans with transparent assumptions.
Capability: `high-stakes-bounded` · Version `1.0.0` · Memory `agent:finance-coach`
Spec: `agents/finance-coach.md`
Mapped upstream workflows: 5

## Investment Research Analyst (`investment-research`)
Analyze investments, risk factors and scenarios without executing trades.
Capability: `high-stakes-bounded` · Version `1.0.0` · Memory `agent:investment-research`
Spec: `agents/investment-research.md`
Mapped upstream workflows: 5

## Legal Information Scout (`legal-scout`)
Research legal/regulatory questions by jurisdiction and date with primary-source grounding.
Capability: `high-stakes-bounded` · Version `1.0.0` · Memory `agent:legal-scout`
Spec: `agents/legal-scout.md`
Mapped upstream workflows: 1

## Career & Recruitment Coach (`career-coach`)
Tailor career materials and interview practice while preserving the user's actual history.
Capability: `chat-native adaptation` · Version `1.0.0` · Memory `agent:career-coach`
Spec: `agents/career-coach.md`
Mapped upstream workflows: 1

## Learning & Tutor Agent (`learning-coach`)
Teach a topic with scaffolded explanations, practice and feedback loops.
Capability: `chat-native adaptation` · Version `1.0.0` · Memory `agent:learning-coach`
Spec: `agents/learning-coach.md`
Mapped upstream workflows: 9

## Travel & Logistics Planner (`travel-planner`)
Build feasible itineraries using current opening hours, geography, budget and transit constraints.
Capability: `tool-gated` · Version `1.0.0` · Memory `agent:travel-planner`
Spec: `agents/travel-planner.md`
Mapped upstream workflows: 4

## Industrial Maintenance Troubleshooter (`maintenance-engineer`)
Diagnose industrial equipment faults through safe isolation, structured measurements and OEM guidance.
Capability: `high-stakes-bounded` · Version `1.0.0` · Memory `agent:maintenance-engineer`
Spec: `agents/maintenance-engineer.md`
Mapped upstream workflows: 0

## Creative & Brand Director (`creative-director`)
Create coherent brand direction, naming, messaging and creative briefs.
Capability: `chat-native adaptation` · Version `1.0.0` · Memory `agent:creative-director`
Spec: `agents/creative-director.md`
Mapped upstream workflows: 6

## UI/UX & Product Design Critic (`ux-reviewer`)
Review usability, information architecture, accessibility and interaction clarity.
Capability: `measurements-required` · Version `1.0.0` · Memory `agent:ux-reviewer`
Spec: `agents/ux-reviewer.md`
Mapped upstream workflows: 8

## Product Manager (`product-manager`)
Turn user problems into requirements, prioritization, roadmap and measurable acceptance criteria.
Capability: `chat-native adaptation` · Version `1.0.0` · Memory `agent:product-manager`
Spec: `agents/product-manager.md`
Mapped upstream workflows: 6

## Project & Operations Manager (`project-manager`)
Plan work, manage scope, dependencies, risks, milestones and closeout.
Capability: `chat-native adaptation` · Version `1.0.0` · Memory `agent:project-manager`
Spec: `agents/project-manager.md`
Mapped upstream workflows: 10

## Browser & Workflow Planner (`browser-operator`)
Plan or execute supported multi-step browser actions with page-content distrust and confirmation gates.
Capability: `connector/authorization-gated` · Version `1.0.0` · Memory `agent:browser-operator`
Spec: `agents/browser-operator.md`
Mapped upstream workflows: 8

## Image, Video & Audio Producer (`media-producer`)
Produce scripts, storyboards, narration text, shot lists, edit plans and publishing metadata.
Capability: `external-runtime-required` · Version `1.0.0` · Memory `agent:media-producer`
Spec: `agents/media-producer.md`
Mapped upstream workflows: 7

## Meeting & Transcript Analyst (`meeting-analyst`)
Convert meeting notes/transcripts into decisions, action items, owners and unresolved issues.
Capability: `tool-gated` · Version `1.0.0` · Memory `agent:meeting-analyst`
Spec: `agents/meeting-analyst.md`
Mapped upstream workflows: 7

## Memory & Knowledge Curator (`knowledge-curator`)
Organize durable project knowledge, provenance, deduplication, retention and retrieval boundaries.
Capability: `chat-native adaptation` · Version `1.0.0` · Memory `agent:knowledge-curator`
Spec: `agents/knowledge-curator.md`
Mapped upstream workflows: 34

## Security & Privacy Reviewer (`security-reviewer`)
Threat-model systems and workflows; review least privilege, secrets, data flow and supply-chain risk.
Capability: `high-stakes-bounded` · Version `1.0.0` · Memory `agent:security-reviewer`
Spec: `agents/security-reviewer.md`
Mapped upstream workflows: 24

## RAG & Knowledge Base Engineer (`rag-engineer`)
Design and implement retrieval, chunking, indexing, ranking, citations, evaluation and refresh pipelines.
Capability: `external-runtime-required` · Version `1.0.0` · Memory `agent:rag-engineer`
Spec: `agents/rag-engineer.md`
Mapped upstream workflows: 29

## Automation & Agent Integration Architect (`automation-architect`)
Design event-triggered workflows with typed contracts, idempotency, approvals, observability and rollback.
Capability: `background-runtime-required` · Version `1.0.0` · Memory `agent:automation-architect`
Spec: `agents/automation-architect.md`
Mapped upstream workflows: 0

## Startup & Project Due Diligence Team (`startup-due-diligence`)
Assess a company/project across market, product, team, financial, legal, operational and technical risks.
Capability: `high-stakes-bounded` · Version `1.0.0` · Memory `agent:startup-due-diligence`
Spec: `agents/startup-due-diligence.md`
Mapped upstream workflows: 0

## Health Information Explainer (`health-info`)
Explain health information, prepare questions and distinguish general guidance from urgent red flags.
Capability: `high-stakes-bounded` · Version `1.0.0` · Memory `agent:health-info`
Spec: `agents/health-info.md`
Mapped upstream workflows: 3

## Scheduled Monitoring Agent Planner (`always-on-planner`)
Specify a real monitoring plan with source, schedule, thresholds, deduplication, alert channel and failure behavior.
Capability: `background-runtime-required` · Version `1.0.0` · Memory `agent:always-on-planner`
Spec: `agents/always-on-planner.md`
Mapped upstream workflows: 0

## Voice Agent & Conversation Designer (`voice-agent`)
Design voice dialogue, turn-taking, recovery, accessibility, escalation and voice evaluation.
Capability: `external-runtime-required` · Version `1.0.0` · Memory `agent:voice-agent`
Spec: `agents/voice-agent.md`
Mapped upstream workflows: 8

## Game Strategy & Simulation Agent (`game-agent`)
Design game strategies, rules, search methods, simulations and evaluation metrics.
Capability: `tool-gated` · Version `1.0.0` · Memory `agent:game-agent`
Spec: `agents/game-agent.md`
Mapped upstream workflows: 3

## Self-Improvement Governor (`self-improvement-governor`)
Coordinate feedback capture, versioned proposals, fixed benchmarks, regression checks, promotion, changelog and rollback.
Capability: `measurements-required` · Version `1.0.0` · Memory `agent:self-improvement-governor`
Spec: `agents/self-improvement-governor.md`
Mapped upstream workflows: 2

