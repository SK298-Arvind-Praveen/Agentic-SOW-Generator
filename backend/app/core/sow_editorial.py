"""Shared content ownership and relevance rules for SOW authors and editor."""

import re
from app.core.section_formats import SUCCESS_CRITERIA

SECTION_PURPOSES = {
    "business_benefits": "Return only brief one-sentence bullets describing distinct customer, agent or operational outcomes. Merge overlapping benefits. No introductory paragraph, headings, feature catalogue, implementation details, invented ROI or repeated objectives.",
    "raci_matrix": "Exactly one table: Workstream | Shellkode | actual client name. Use combined RA/CI/RAC/I codes. Group delivery-level work, not modules or controls. Shellkode leads implementation and technical testing; client owns business acceptance and policy approval. Do not assign client CI universally. No job-role columns, second table or explanatory paragraphs.",
    "project_overview": "State the solution being delivered, who uses it and its end result. Do not enumerate modules, test evidence, dependencies or controls.",
    "current_state": "Describe only existing systems and workflow facts needed to understand the integration or replacement boundary. Group related systems; omit staffing inventories, future features, survey details and questions.",
    "scope_of_work": "Own the implementation commitments. Group related actions under meaningful modules; preserve distinct business rules, interfaces, exceptions and outputs once. Do not add a bullet for each reasoning dimension or a test record for every action.",
    "architecture_diagram": "Explain the end-to-end solution flow and the roles and interactions of relevant logical layers and chosen services. Add only material deployment, data, integration and security decisions. Do not repeat implementation scope or enumerate an AWS service catalogue.",
    "customer_dependencies": "Own concrete prerequisites such as integration access and test data. Combine access for related systems in one bullet. Do not create dependency IDs, timing/impact columns or a separate row per credential. Decisions belong in Open Clarifications and ongoing customer duties in Customer Responsibilities.",
    "customer_responsibilities": "Return only concise one-sentence bullets covering customer decisions, participation, acceptance and operational ownership. Combine related approvals and UAT participation. Do not enumerate systems, credentials, tests or implementation tasks already in Dependencies or Scope. No introduction, subsection headings, discovery questionnaire, invented approval deadlines, staffing numbers or incident SLAs.",
    "assumptions": "State only material gap-filling delivery premises Shellkode relies on for the agreed work. A premise must identify a project-specific condition whose failure would change delivery effort, design, cost or acceptance, such as usable linked customer data, representative test cases or compatible existing interfaces. Do not turn confirmed features, launch channels, languages, phases or platform choices into assumptions merely to repeat Scope. Use a capacity, format or retention baseline only when evidenced and materially relied upon; never invent quantities or treat model planning guesses as customer agreement. State the condition directly, without saying information was missing or explaining the rationale. Access checklists belong in Dependencies; exclusions belong in Out of Scope. Keep genuinely unresolved material decisions in Open Clarifications. Use short one-sentence bullets with one meaningful bold phrase; no quota or filler.",
    "out_of_scope": "State only relevant work outside the agreed deliverables: explicit exclusions or plausible adjacent work that could reasonably be mistaken as included. Check every exclusion against Scope, phase boundaries and Assumptions; never exclude included work or infer exclusion from silence. Do not mirror each scope feature or assumption with its negative. Remove generic absent technologies, hardware and certifications unless genuinely relevant. Keep distinct boundaries separate and remove duplicate exclusions. Post-acceptance model migration is appropriate only when relevant and not already included in agreed support. Use short one-sentence bullets; no quota or filler.",
    "open_clarifications": "Ask only unresolved decisions that block scope agreement, architecture sizing, price or acceptance. Merge questions about the same decision. API field mappings, survey copy, log schemas, workshop scheduling and implementation tuning belong in discovery, not a contract questionnaire. Do not carry every upstream unknown forward.",
    "timelines_deliverables": "Use the selected table or Gantt format. Group related activities, preserve supplied timing and leave unsupported timing blank. Do not repeat the scope action list.",
    "success_criteria": SUCCESS_CRITERIA,
    "project_team_effort": "Show the compact resource/count/effort table only. Do not narrate each role or invent counts or durations. Leave unavailable numeric cells blank.",
    "technical_specifications": "Keep only specific interface, data and non-functional constraints not already stated in scope or architecture. No generic NFR catalogue or invented requirement IDs.",
    "security_requirements": "State the applicable access, data protection and regulatory controls once. No generic control matrix or invented audit/certification commitments.",
    "data_migration_readiness": "Describe only the agreed datasets and migration/readiness boundary. Do not manufacture migration waves, cleansing or historical migration when they are not required.",
    "testing_and_acceptance_plan": "Describe the test approach and customer acceptance responsibilities briefly. Keep acceptance thresholds in Success Criteria when selected; do not create a test-case or traceability register.",
    "risks_mitigations": "Include only concrete project-specific risks and their actionable mitigations. No generic risk catalogue, invented likelihood scores or repeated dependencies.",
    "day2_operations_support": "State included support work, period, hours and responsibility where agreed. Do not restate the build scope or manufacture incident tiers, response SLAs or ongoing services.",
}

EDITORIAL_CONTRACT = """CONCISE, RELEVANT, SIMPLE — CLIENT DELIVERY AGREEMENT
Generated narrative sections use short bullets, except About Client which retains two brief factual paragraphs. Prefer 8-16 words per sentence; retain essential conditions rather than cutting meaning to meet a count. Keep distinct points separate: never group them into a wordy omnibus bullet. Audit long lists and delete irrelevant or duplicate points, not required commitments. Tables remain tables, and approved static/legal text stays unchanged.
Selecting a section authorises its subject; it does not require a full checklist or a page of content.
Give every detail one primary home. Scope owns the work; other sections add only a different contractual fact.
ASSUMPTIONS / EXCLUSIONS BOUNDARY: review both against the agreed deliverables. Assumptions state material delivery premises filling genuine gaps, not confirmed features or negative scope. Out of Scope states relevant excluded work, not the inverse of every premise. For each assumption ask what delivery consequence changes if it fails; for each exclusion ask which plausible adjacent work it rules out. Remove points without a material answer. Never claim an included unified platform is also excluded. Confirmed launch channels and languages normally belong in Scope, not repeated in both lists. Existing API compatibility can be an assumption while development of replacement APIs can be excluded: shared keywords alone do not make distinct conditions duplicates. Keep both only when each adds a necessary, different boundary. Do not invent customer agreement, quantities or arbitrary restrictions. Leave either section empty if no relevant points survive; never add filler or missing-information commentary.
Before retaining a point, ask: what specific scope boundary, delivery condition, acceptance decision or customer duty would be lost if this were removed?
If the answer is none, remove it. A true fact is not automatically relevant to this section.
Delete duplicate statements of the same action or boundary. Keep distinct obligations and exceptions separate; do not group points merely to lower the bullet count.
Use familiar verbs: build, connect, check, store, test, hand over. Avoid 'enterprise-grade', 'comprehensive', 'robust', 'posture', 'governance baseline' and repeated 'evidenced by'.
Use one short sentence per bullet. Never prefix it with a bold summary label followed by a colon or dash. Write the sentence directly, retaining any subject necessary to its meaning.
In every generated narrative bullet, emphasise its most important action, outcome, condition or boundary using one short inline **bold** span, usually 1-2 words. Choose what a reader needs to scan, not just product names: **historical records**, **approved rules**, **business acceptance**. Keep the sentence intact; no bold lead-in labels, whole sentences or repeated decorative highlights. In About Client retain two factual paragraphs with sparse meaningful emphasis; do not convert them to bullets. Tables need no bold in every cell. Never change protected static/legal wording or its formatting.
Write a delivery agreement, not a specification, test script or operating manual. Keep only details that change what is delivered or accepted.
Keep distinct approvals and customer duties separate. Delete repeated exclusions; describe success as outcomes rather than replaying every feature.
Keep the full volumetric inventory in AWS Pricing. Assumptions may state a source-backed capacity or retention baseline only when it materially bounds delivery; do not duplicate the full inventory. Never state a disputed design choice as settled while asking to confirm it elsewhere.
Use the same delivery boundary throughout Objective, Scope, Timeline, Acceptance and Exclusions. The template mode alone does not authorise excluding production or support explicitly agreed in the deliverable plan. Preserve explicit phase boundaries; unresolved source conflicts belong in Open Clarifications, not invented exclusions or commitments.
Do not strip punctuation between clauses to shorten text. Prefer a short grammatical sentence to a compressed run-on.
Check complete sentences, clause separators, agreement and end punctuation. Do not return sentence fragments or dangling clauses. Do not confuse legitimate AI-generated summaries with commentary about generating this SOW.
Do not shorten prose by dropping qualifiers, negation, units, thresholds, human review or phase boundaries.
Tables are for values people compare (pricing, staffing, schedule, contacts); narrative commitments use bullets.
Solution Architecture text must contain only short one-sentence Markdown bullets explaining the design. No introductory or flowing prose paragraphs. The dedicated diagram pipeline supplies the visual; never draw ASCII boxes, arrows, Mermaid or fenced diagram code in the section text. Describe the request flow and material integration, data, handover and security choices without a service catalogue or repeated scope details.
Scope module actions must remain individual Markdown bullets after editing. Preserve the deliverables summary table and deliverable boundaries; change module headings only through the reviewer's validated module_groups operation when reviewing. Shortening must never collapse a list into a paragraph.
Create scope modules for cohesive capabilities, not one per source row, AWS service, control or minor feature. Combine related actions in their owning module while preserving every distinct requirement. Language support belongs with the conversational engine; analytics feeds belong with reporting; notification triggers and survey feedback often share a workstream. Build-time support readiness and ongoing support are different obligations, not two copies of the same service. No target module count applies.
Never turn a list of processes into a tracking register with invented IDs, owners, status, impact and evidence columns.
Do not add minimum counts, arbitrary page limits or an item for every module in every section.
No comments about missing inputs, source documents, generation, confirmation status or how the SOW was written.
Keep undecided matters undecided; never convert a question into an assumption or exclusion to shorten it.
The agreed deliverable plan controls the delivery boundary, not the template's POC/production label. Objective must not exclude go-live or support when an agreed deliverable includes it. Do not invent a default eight-week schedule or staffing allocation.
Business Benefits describe outcomes, not how each feature works. Keep each distinct outcome in its own short bullet and remove repeated benefits. Avoid absolute promises such as 'without operational cost' or guaranteed resolution improvements.
Customer Dependencies own access, credentials and test material. Customer Responsibilities own decisions, acceptance and ongoing content/agent ownership; do not repeat the dependencies there. Existing team size is not a commitment to dedicate those people to UAT.
In Roles and Responsibilities, both party cells contain only combined R/A/C/I letters, never sentences or parenthetical explanations. A build/integration row can cover many systems. Do not invent activities (such as migration) merely to populate this table. No legend.
RACI is a delivery responsibility summary, not a scope index: combine chatbot, channels, integrations and security under implementation where their ownership is the same; keep business acceptance separate from technical testing and keep client-owned prerequisites distinct. Preserve any genuinely different accountability.
Timeline outcomes name the milestone result, not the services or implementation tasks used to deliver it. Team Effort contains only its table, not a paragraph describing every role.
Success Criteria is not a test script: never invent a number of test runs, channel repetitions or evidence documents. Preserve agreed acceptance targets; do not reclassify them as post-go-live metrics to avoid unresolved acceptance decisions.
Scope owns each implementation obligation once. Do not repeat architecture explanations (service purpose, data path, rejected alternatives) in scope bullets. Refer to the agreed architecture where sufficient; retain project-specific interfaces, rules and deliverable boundaries.
About Client contains two short factual paragraphs about company identity, products, channels and established operations only; no bullets, RFQ, vendor evaluation, renewal motivation, engagement narrative or generic praise. Remove pain points, bottlenecks and criticism of the customer's processes; do not replace these with invented positive claims.
Architecture prose should normally be 4-6 short design bullets, not a walkthrough of every diagram node. Describe the main path and material design decisions; retain implementation actions in Scope and individual services in the diagram. Preserve exceptional project constraints rather than mechanically truncating to a quota.
Roles and Responsibilities should normally have 5-8 delivery-stage rows in one table. Group related work with identical accountability; preserve separate client acceptance, access and policy ownership. No row per feature or AWS service.
Dependencies owns the access/data handover checklist. Assumptions states the material conditions under which delivery works, such as usable linked historical exports or approved classification rules being available for configuration. Keep a premise only when it adds a contractual condition, not another copy of the checklist. Customer Responsibilities owns decisions, participation and acceptance. Do not invent approval turnaround times, a single environment, an eight-week plan or one-time-only migration because the input leaves those choices open.
Preserve product identity exactly: a customer system called Connect CRM is not automatically Amazon Connect. A familiar word is not evidence for an AWS product mapping. Separate existing systems from explicitly chosen new AWS components; reference architectures never authorise replacing a named client product.
Preserve ambiguous source acronyms and category codes; do not silently turn NPA into NPS or ER into ET. Ask a focused clarification when the distinction changes a report or business rule.
Compare every exclusion with the full requirements, not only the generated scope. Do not exclude grammar assistance, sentiment, integrations, testing, training or support merely because an earlier generated section omitted them. Explicit source conflicts need clarification, not an invented phase or future-release label.
Open Clarifications contains questions only, without an introduction describing how the document was written. Do not ask whether an already agreed inclusion/exclusion should be reversed.
Style examples only, never copy their facts into another project:
- Prefer the compact reference-SOW style: direct verbs, familiar words and one independently testable action per bullet. Group related actions under a few cohesive scope headings, not one heading per implementation detail.
- Replace explanatory task narratives with their delivery commitment: 'Write one results record per call for the existing dashboard.' Do not repeat how every upstream stage produced it.
- Keep architecture to the principal flow and material decisions, assumptions to critical delivery baselines, and exclusions to realistic contractual boundaries. Do not enumerate all possible categories.
- Use short business-sizing context and a single monthly infrastructure estimate table for AWS pricing; never repeat the same amount as calculator total, MRR and ARR.
- Benefit: 'Reduce repeat enquiries through self-service and proactive order updates.' Not a catalogue of every journey, integration and notification channel.
- Customer duty: 'Review the design and complete business acceptance testing.' Keep access prerequisites in Dependencies.
- Timeline outcome: 'Channel integrations ready for testing.' Not a second scope specification in a table cell.
- Long: 'Implement comprehensive monitoring covering platform health ... Configure alerting mechanisms ... Establish real-time dashboards ...'
  Concise: 'Configure health monitoring and alerts for the platform and its integrations.'
- Repeated prerequisites: API credentials, API documentation, sandbox credentials for each system.
  Concise: 'Provide API documentation and sandbox access for the agreed integrations.' Keep any unique access constraint.
- Weak assumption: 'The chatbot will include reporting dashboards.' Delete: this is a scope feature.
- Relevant assumption: 'Capacity is based on 500 concurrent sessions.' Retain only if this is an adopted sizing baseline, not an invented value.
- Relevant delivery premise: 'Historical exports retain the identifiers linking customers, tickets and attachments.' Use only for a migration that actually needs those relationships; never import example facts into another project.
- Relevant delivery premise: 'The customer provides approved routing rules for configuration and acceptance.' Use only when rule-based routing is part of the agreed work; do not also repeat the same request in Dependencies.
- Relevant exclusion: 'Migration to another AI model after acceptance is excluded.' Include only if applicable and compatible with the agreed support scope.
"""

OPTIONAL_CONTRACT_SECTIONS = {"assumptions", "out_of_scope", "open_clarifications", "risks_mitigations"}


def section_editorial_contract(category):
    return EDITORIAL_CONTRACT + "\nSECTION'S SOLE PURPOSE\n" + SECTION_PURPOSES.get(
        category, "State only the distinct commitments or facts this selected topic needs; avoid duplicating other sections."
    )


def editorial_category(title, fallback):
    """Editorial purposes are narrower than the UI's grouped section selectors."""
    title = re.sub(r"^\s*\d+[.)]\s*", "", title).casefold()
    for prefix, category in (
        ("current state", "current_state"),
        ("technical specifications", "technical_specifications"),
        ("security,", "security_requirements"),
        ("data migration", "data_migration_readiness"),
        ("testing and acceptance", "testing_and_acceptance_plan"),
        ("risks and mitigations", "risks_mitigations"),
        ("day-2", "day2_operations_support"),
    ):
        if title.startswith(prefix):
            return category
    return fallback


def strip_bullet_leadins(text):
    """Remove generated mini-headlines; leave tables and ordinary emphasis alone."""
    return re.sub(
        r"(?m)^(\s*[-*•]\s+)(?:\*\*[^\n*]+?:\s*\*\*|\*\*[^\n*]+?\*\*\s*[:–—-])\s*(\S[^\n]*)$",
        r"\1\2", text,
    )


def validate_editorial_revision(original, revision, categories):
    """Reject incomplete edits, added sections, expansion and altered numeric facts.

    This guards structure and numbers, not semantic equivalence; the editor's
    instructions are still responsible for retaining non-numeric obligations.
    """
    if not isinstance(revision, dict) or set(revision) != set(original):
        raise ValueError("Editorial response must contain exactly the editable section keys")
    for key, value in revision.items():
        if not isinstance(value, str):
            raise ValueError("Editorial bodies must be strings")
        if not value.strip() and categories[key] not in OPTIONAL_CONTRACT_SECTIONS:
            raise ValueError("Editorial review cannot erase a required section")
        if len(value.split()) > len(original[key].split()):
            raise ValueError("Editorial review cannot expand a section")

    def numbers(text):
        # Ignore list numbering and generated tracking IDs, not actual quantities.
        text = re.sub(r"(?m)^\s*\d+[.)]\s+", "", text)
        text = re.sub(r"\b(?:SC|DEP|NFR|RISK|CL)-\d+\b", "", text)
        return set(re.findall(r"(?<!\w)\d+(?:[,.]\d+)*(?:\s*%)?", text))

    before = numbers("\n".join(original.values()))
    after = numbers("\n".join(revision.values()))
    if before != after:
        raise ValueError("Editorial review must preserve numeric facts")
