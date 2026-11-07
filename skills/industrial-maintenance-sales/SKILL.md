# ARCHIVED — NOT ACTIVE (2026-11-07)

> This Skill is preserved as historical source only. It is removed from active Skill routing and must not be loaded for new work. Existing files, prospect records, workbooks, database tables and backups are intentionally retained.

---

# Industrial Maintenance Sales Workflow

**ID:** `industrial-maintenance-sales`  
**Version:** 1.0.0  
**Mode:** Automatic, trigger-matched Skill context for approved roles; not a separate agent or service.  
**Purpose:** Turn evidence-backed industrial-maintenance prospects into genuine enquiries, qualified demonstrations, scoped offers, accepted delivery and measurable learning.

## Role routing

Use the smallest useful set of existing roles:
- `sales-intel`: prospect research, deduplication, contact verification evidence, reply triage and pipeline analysis.
- `business-strategist`: offer fit, discovery, commercial scope and quote preparation.
- `maintenance-engineer`: maintenance terminology, equipment/PM scope, parts and operational suitability. Never invent a prospect's equipment or maintenance problem.
- `marketing-seo`: content hooks, channel metadata and source-coded calls to action.
- `data-analyst`: Sales Control Center reconciliation, workbook QA and funnel measurement.
- `project-manager`: bounded plan, owners, dependencies and stage gates.
- `code-reviewer`: independent verification of facts, calculations, deliverables and claims.
- `self-improvement-governor`: evidence-backed improvement proposal only; protected policy, tool, provider, permission and release changes require human approval.

These are specifications within the canonical 38-role registry. Do not describe them as separate models, always-on services or concurrent agents unless the runtime proves that behavior.

## Source of truth and provenance

Use the latest supplied or connected `uneXpected_Sales_Control_Center` workbook as the authoritative sales ledger. Preserve its existing prospect IDs, status, evidence references, next actions and approval gates. Do not replace it with a second unconnected CRM or infer that the runtime database is synchronized with the workbook.

A reviewed baseline snapshot was read from `uneXpected_Sales_Control_Center_v1.10.6.xlsx` on 2026-11-06 at 08:07:24 Africa/Tunis:
- 49 prospects; 44 first touches (43 email sends and one official form submission).
- 0 human prospect replies, 0 independently verified demos, 0 quotes and 0 wins.
- 8 address/delivery checks blocked or awaiting resolution.
- 5 researched prospects remained uncontacted.
This is a dated baseline, not a live inbox result. Re-read the current source before using any status as current. A website auto-confirmation is not a human reply. A send accepted by Gmail is not proof of delivery or reading. Absence of a bounce is not proof of delivery.

## Offers and commercial boundaries

Treat all listed prices as test hypotheses, not market benchmarks, tax advice, income guarantees or an approved customer-specific quote.

**Starter Preventive Maintenance Tracker — $79 starting hypothesis**
Includes an asset register, PM planner, next-due / days-left / status visibility, work-order log, basic dashboard, one revision and quick usage notes.
Does not include bulk data cleaning, custom formulas, VBA/macros, multi-site consolidation, integrations or multiple revisions.

**Pro Spare-Parts & Reporting Tracker — $149 starting hypothesis**
Includes Starter plus spare-parts stock, reorder threshold, suggested order quantity, linked parts usage, stock value and parts/labor/downtime summary.
Does not include ERP integration, barcode scanning, automatic purchasing, advanced financial/accounting reports, VBA or large custom imports.

Custom work is quote-after-discovery only. Confirm machine count, Excel version, users, SKU volume, stock locations, reorder policy, required fields, integrations, data sensitivity, support, terms and payment route before proposing custom scope. Never promise savings, uptime improvements, compatibility, payment methods, dates or custom features without evidence.

## Execution sequence and exit criteria

1. **Research:** identify the company from official/public sources, record source URL and date, deduplicate, and label fit as a hypothesis. Never invent a person, address or maintenance problem.
2. **Qualify:** determine likely segment and the relevant maintenance/production buyer only from evidence. Ask about the real process only after a human response. Do not assume the company lacks a CMMS or uses paper.
3. **Draft:** prepare one personalized message with a truthful product description, one clear question and an optional fictional-data demo. Validate the exact recipient and channel.
4. **Approve and first-touch:** before sending or submitting, confirm exact copy, recipient, channel and action-specific approval. Log the provider's returned message/form state and timestamp. Never infer delivery or reading.
5. **Triage:** read the full relevant thread, identify human replies versus automated responses and DSNs, classify intent, record the evidence and draft the next response. Honor opt-outs immediately. Never retry a bounced/uncertain address or change recipients by guess.
6. **Discovery/demo:** use synthetic data until the prospect explicitly agrees to share safe, minimum-necessary information. Confirm machine count, existing process, Excel environment, users and any spare-parts/reporting need. A demo is booked only when a real human agrees to a specific meeting and the meeting is independently verified in the authorized calendar or equivalent evidence.
7. **Quote:** prepare the $79 or $149 starting offer only when its scope fits the confirmed need. Custom scope requires written requirements, acceptance criteria and a separately verified commercial/payment route. Do not send a quote without explicit approval.
8. **Delivery:** use a separate copy for each customer, keep the master template untouched, apply the written scope, test formulas, date logic, dropdowns, edge cases and version history, and verify the handover package. Do not import customer data before terms and authorization are agreed.
9. **Handover and feedback:** provide the agreed guide and walkthrough; record acceptance, actual payment evidence and actionable feedback. Do not claim a sale, payment or testimonial from a verbal expression of interest.
10. **Improve and retain:** record evidence and classify issues by frequency, severity and effort. Change a template or workflow only through a versioned proposal, fixed regression benchmark, tests, human approval for protected changes and an available rollback.
11. **Close or park:** record the actual outcome, reason, last touch and stop preference. One follow-up is a planning limit, not standing permission to send. Park silent leads after the approved follow-up and do not schedule further contact unless invited.

## Tool and authorization rules

- Use only tool IDs actually present in the current runtime's registered, enabled and provenance-verified capability list. A role profile, Skill `allowed_tools` value, catalogue entry, prompt, connector name or ChatGPT-side integration is not proof that the v8 runtime can call that tool.
- The current v8 MCP gateway is an in-process adapter boundary, not a remote MCP client. No third-party adapter is enabled by this Skill. If the required tool is absent, stop at a draft or verified local artifact and report the blocker; do not simulate a tool result.
- A configured provider key is not authentication proof. Live model work requires a successful bounded non-mock provider test and `verified=true`. The lifecycle reviewer gate must not run on mock or unverified routes.
- Never expose API keys, bearer tokens, database URLs, customer data or private inbox contents in prompts, task logs, browser output, repository files or reports.
- No automatic email sends, retries, calls, contact-form submissions, follow-ups, quotes, public posts, publishing, file sharing, payment actions, purchases or deployment. Each consequential external action requires the applicable connector authorization and explicit approval for the exact action.
- `allowed_tools` metadata is descriptive. It never installs, authorizes or enables a connector. Privileged operations stay disabled until durable approval, replay protection, transactional persistence, backup and restore have been verified.

## Acceptance checklist

A workflow result is accepted only when it contains:
- A named source-of-truth snapshot/version and evidence URLs or record references.
- A deduplicated prospect record with uncertainty clearly marked.
- Accurate product scope, exclusions and test-price caveat.
- Exact stage, owner/role, next action and evidence-based exit criterion.
- Separate status for draft, approved, sent, delivered, read, human-replied, demo-booked, quoted, accepted, paid and handed over.
- A record of every blocked connector, missing authorization and unresolved unknown.
- Independent verification of the requested artifact and no unsupported completion claims.

**Business success milestone:** a genuine human reply, a verified contact route and a booked demonstration. Views, likes, opens, automated form confirmations and email acceptance are not qualified enquiries or revenue.
