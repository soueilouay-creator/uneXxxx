# uneXpected v7 — Canonical Agent Catalog

**Active canonical roles: 38** (37 preserved legacy roles + 1 new self-improvement governor). The 120 upstream entries are workflow capabilities mapped into these roles, not 120 additional agents.

| ID | Agent | Capability | Upstream workflows mapped | Handoff targets |
|---|---|---|---:|---|
| `orchestrator` | Agent Orchestrator | chat-native adaptation | 19 | project-manager, research-scout, coding-engineer, code-reviewer |
| `research-scout` | Research Scout | tool-gated | 6 | web-scout, deep-research |
| `deep-research` | Deep Research Planner | tool-gated | 20 | research-scout, web-scout, document-rag |
| `web-scout` | Web Scout & Fact Checker | tool-gated | 11 | research-scout, deep-research, security-reviewer |
| `coding-engineer` | Coding Engineer | external-runtime-required | 17 | system-architect, debugger, code-reviewer |
| `system-architect` | System Architect | tool-gated | 27 | coding-engineer, security-reviewer, rag-engineer |
| `debugger` | Debugging Specialist | tool-gated | 1 | coding-engineer, code-reviewer, system-architect |
| `code-reviewer` | Code Review & Test Engineer | measurements-required | 24 | coding-engineer, debugger, security-reviewer |
| `data-analyst` | Data Analyst | measurements-required | 7 | document-rag, deep-research, code-reviewer |
| `document-rag` | Document & RAG Analyst | tool-gated | 38 | knowledge-curator, rag-engineer, deep-research |
| `business-strategist` | Business Strategist | chat-native adaptation | 6 | competitor-intel, sales-intel, startup-due-diligence |
| `competitor-intel` | Competitor Intelligence Analyst | tool-gated | 5 | business-strategist, marketing-seo, sales-intel |
| `marketing-seo` | Marketing & SEO Agent | tool-gated | 1 | creative-director, competitor-intel, sales-intel |
| `sales-intel` | Sales Intelligence Agent | connector/authorization-gated | 0 | business-strategist, competitor-intel, marketing-seo |
| `finance-coach` | Personal Finance & Budget Coach | high-stakes-bounded | 5 | investment-research, business-strategist, legal-scout |
| `investment-research` | Investment Research Analyst | high-stakes-bounded | 5 | finance-coach, deep-research, security-reviewer |
| `legal-scout` | Legal Information Scout | high-stakes-bounded | 1 | deep-research, security-reviewer, business-strategist |
| `career-coach` | Career & Recruitment Coach | chat-native adaptation | 1 | learning-coach, business-strategist, meeting-analyst |
| `learning-coach` | Learning & Tutor Agent | chat-native adaptation | 9 | research-scout, career-coach, coding-engineer |
| `travel-planner` | Travel & Logistics Planner | tool-gated | 4 | web-scout, project-manager, browser-operator |
| `maintenance-engineer` | Industrial Maintenance Troubleshooter | high-stakes-bounded | 0 | debugger, system-architect, data-analyst |
| `creative-director` | Creative & Brand Director | chat-native adaptation | 6 | ux-reviewer, marketing-seo, media-producer |
| `ux-reviewer` | UI/UX & Product Design Critic | measurements-required | 8 | product-manager, creative-director, coding-engineer |
| `product-manager` | Product Manager | chat-native adaptation | 6 | ux-reviewer, system-architect, project-manager |
| `project-manager` | Project & Operations Manager | chat-native adaptation | 10 | orchestrator, product-manager, automation-architect |
| `browser-operator` | Browser & Workflow Planner | connector/authorization-gated | 8 | web-scout, security-reviewer, automation-architect |
| `media-producer` | Image, Video & Audio Producer | external-runtime-required | 7 | creative-director, voice-agent, meeting-analyst |
| `meeting-analyst` | Meeting & Transcript Analyst | tool-gated | 7 | knowledge-curator, career-coach, voice-agent |
| `knowledge-curator` | Memory & Knowledge Curator | chat-native adaptation | 34 | document-rag, rag-engineer, security-reviewer |
| `security-reviewer` | Security & Privacy Reviewer | high-stakes-bounded | 24 | system-architect, code-reviewer, legal-scout |
| `rag-engineer` | RAG & Knowledge Base Engineer | external-runtime-required | 29 | document-rag, knowledge-curator, system-architect |
| `automation-architect` | Automation & Agent Integration Architect | background-runtime-required | 0 | orchestrator, browser-operator, project-manager |
| `startup-due-diligence` | Startup & Project Due Diligence Team | high-stakes-bounded | 0 | business-strategist, competitor-intel, deep-research, investment-research, legal-scout |
| `health-info` | Health Information Explainer | high-stakes-bounded | 3 | deep-research, document-rag, learning-coach |
| `always-on-planner` | Scheduled Monitoring Agent Planner | background-runtime-required | 0 | automation-architect, orchestrator, security-reviewer |
| `voice-agent` | Voice Agent & Conversation Designer | external-runtime-required | 8 | media-producer, meeting-analyst, automation-architect |
| `game-agent` | Game Strategy & Simulation Agent | tool-gated | 3 | coding-engineer, data-analyst, learning-coach |
| `self-improvement-governor` | Self-Improvement Governor | measurements-required | 2 | orchestrator, code-reviewer, learning-coach, security-reviewer |
