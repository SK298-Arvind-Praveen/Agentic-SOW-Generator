<!-- BEGIN_GLOBAL_TEMPLATE_CONTRACT -->
# POC SOW GLOBAL AUTHORING AND BENCHMARK CONTRACT

This contract is part of the runtime prompt for every generated section. It encodes the observable structure and writing standard of the 35-page reference SOW, `Axis Securities __ Agentic AI-powered CRM Platform __ SOW Draft 1.0.0.docx.pdf`. The runtime does not need access to that PDF. Do not merely claim to be "benchmark quality"; follow the concrete rules below.

## A. Reference-derived document model

The finished POC SOW must read like a detailed implementation baseline, not a generic proposal. Its substantive flow is controlled by the user's section selections. The cover, Document Control, and Table of Contents remain structural document elements; every other top-level topic is included only when selected.

1. cover page;
2. Document Control before the Table of Contents;
3. only the user-selected company, client, overview, scope, architecture, dependency,
   assumption, exclusion, timeline, pricing, responsibility, team, clarification,
   success, termination, contact, terms, and acceptance topics, in template order.

Never introduce an unselected top-level topic or re-create an excluded topic as a subsection.

## B. Evidence and inference policy

Classify every material statement mentally as one of the following and write accordingly:

- **Confirmed:** directly stated by the user's product details, an uploaded source, or structured requirements. State it plainly and preserve exact quantities, names, wording, identifiers, and qualifications.
- A statement inside an uploaded source is not automatically Confirmed. Preserve explicit source labels such as **Assumption**, **Derived**, **Proposed**, **To be confirmed**, **Not stated**, **Needs clarification**, **optional**, and **future**. Conflicting sources are **Open** until reconciled.
- **Derived:** a necessary synthesis of confirmed facts, such as grouping requirements into modules or identifying an obvious dependency. State it plainly only when the reasoning is direct and low risk.
- **Proposed:** an architect-authored design choice, implementation approach, validation method, sequence, staffing model, or AWS service not confirmed by the source. Label it "Proposed" or "proposed for baseline confirmation" at the point of use.
- **Open:** a fact that changes scope, cost, architecture, acceptance, compliance, or sequencing and cannot safely be inferred. Carry it to Open Clarifications; never answer it on the customer's behalf.

Sparse input is expected. Expand it into a professional SOW by decomposing stated capabilities, mapping actors/inputs/outputs/dependencies, and proposing sensible implementation detail. Do not compensate for sparse input by fabricating customer facts or contractual commitments.

## C. Cross-section consistency rules

- Use British Indian English throughout, not US spelling. Prefer `organisation`, `organise`, `centralised`, `analyse`, `behaviour`, `colour`, `programme`, `licence` (noun), and `fulfilment`. Preserve official product names, API fields, quoted source text, and identifiers exactly as supplied.
- Use the same project name, customer name, module names, requirement IDs, actors, integrations, AWS services, environments, quantities, and status labels everywhere.
- Establish one deliverable/module work breakdown inside Scope of Work and reuse it in Architecture, Open Clarifications, Out of Scope, Assumptions, Success Criteria, Pricing inputs, and Team Effort.
- Preserve explicitly numbered or named customer-authored deliverables as top-level deliverables when each
  defines a distinct reviewable business outcome. They do not require separate deployments or acceptance
  dates. Treat ordinary feature rows, artefact lists, technical layers, and checklists as modules or outputs.
- Preserve supplied requirement identifiers. When IDs are absent, create stable IDs using short module prefixes such as `EM-01`, `KB-01`, or `WF-01`; never renumber them differently in another section.
- Do not contradict inclusion boundaries. A baseline capability included in Scope of Work must not be excluded in Out of Scope; distinguish a limited included capability from an advanced deferred capability.
- Do not invent a week-by-week schedule or committed duration. Sequence may be proposed as dependency logic, but dates and durations remain open unless supplied.
- Do not invent prices, calculator links, funding status, resource commitments, data volumes, concurrency, SLAs, accuracy thresholds, availability, recovery objectives, or achieved outcomes.

## D. Regulatory, compliance, AI, and human-review fidelity

- Preserve regulator names, statutory references, residency statements, mandatory disclaimer text, forbidden-phrase rules, retention requirements, audit requirements, and source qualifications exactly when supplied.
- Never convert "intended to support", "consistent with expectations", "designed for", "subject to confirmation", or a similar qualified statement into certification or a claim that the solution is compliant.
- If the exact mandatory wording is not supplied, do not invent it. Record the wording/approval as an open clarification and describe only the control mechanism.
- For AI-generated drafts, recommendations, summaries, classifications, scores, or decisions, state the human-in-the-loop boundary: the responsible user reviews the generated output and remains accountable for what is sent, approved, or acted upon.
- Do not imply autonomous regulated decisions unless the source expressly requires and governs them.

## E. Content density and form

- Write only the implementation detail needed to define scope, ownership, dependency, boundary, decision, or validation. Do not expand every category when it adds no decision value.
- Prefer concise bullets for requirements, boundaries, responsibilities, decisions, dependencies, risks, and validation. Use prose only for a short rationale and tables only for genuinely comparable records.
- Start a section with no more than one orienting paragraph of 60 words. Do not place a second prose paragraph immediately after it; move actionable content into bullets.
- Default to no subsections. Outside Scope of Work, use at most two direct subsections and no nested subsections. Within Scope of Work, use one direct heading per deliverable and one nested heading per cohesive module; use prose and bullets beneath the module.
- Put each bullet on its own Markdown line, keep it to one main idea, and use a real nested Markdown bullet only when the hierarchy is necessary.
- Tables should normally contain two to four columns and must never exceed five. If detail will create narrow prose-heavy cells, split the table or put explanatory prose beneath it.
- Each detailed module should normally contain: objective/boundary, workflow, functional requirements, roles and permissions, data, integrations, business rules and exceptions, AI/human review where relevant, security/compliance where relevant, dependencies, and validation notes. Omit a category only when genuinely inapplicable.
- Use a sequential `Workflow` only where sequence materially aids understanding. A data store, reporting capability, integration layer, or governance capability does not automatically need its own numbered workflow.
- A workflow should contain the meaningful end-to-end stages needed to explain the module. Consolidate low-value UI clicks into phases or capability bullets.
- Avoid filler, marketing claims, repeated project summaries, vague bullets, and generic AWS catalogues.
- When Architecture Diagram is selected, provide only the concise decisions, constraints, flow and unresolved boundaries needed to interpret the generated visual. Do not duplicate the diagram as a prose-heavy component catalogue.

## F.1 Heading hierarchy and numbering

- The template's `##` headings are the only top-level categories and are rendered as Heading 1.
- Use `###` for direct subcategories and `####` for a category beneath them. Use `#####` only for a genuinely necessary fourth level.
- Every substantive subheading must participate in the parent hierarchy: `1.1`, `1.2`, `4.1`, `4.1.1`, and so on. The DOCX renderer normalizes these numbers deterministically, so do not use bold Normal paragraphs as substitute headings.
- Do not skip a heading level. Do not create an unnumbered generic label such as `Workflow`, `Requirements`, or `Dependencies` outside the hierarchy.
- Keep categorical headings concise. Put explanatory sentences in the following paragraph, not in the heading itself.

## F. Reference-derived visual contract

The DOCX renderer, not the LLM, enforces the visual design. Author Markdown that supports these deterministic rules:

- US Letter portrait pages;
- DM Sans typography;
- purple `#5D3FD3` for top-level headings and table headers;
- blue `#1A4BD2` for header/subsection accents;
- dark gray `#434343` body text;
- compact, left-aligned tables with purple header rows, light-gray alternating rows, thin gray borders, and repeating headers;
- project/SOW label at left and ShellKode logo at right in the header;
- thin gray footer rule, padded `Confidential Copyright © ShellKode 2026` at left, and live `Page X of Y` centred on the line below;
- no manual spacer pages, no explicit page-break directives in generated Markdown, and no headings consisting solely of formatting punctuation.

## G. Mandatory final self-check for every section

Before responding, confirm internally that the section:

1. follows its local template instructions;
2. uses only confirmed, directly derived, clearly proposed, or explicitly open statements;
3. preserves source wording and numbers;
4. matches the shared module taxonomy and terminology;
5. contains no new top-level section;
6. contains no unsupported commitment or compliance claim; and
7. returns only the Markdown body, without the section title or commentary about the task.
<!-- END_GLOBAL_TEMPLATE_CONTRACT -->

[META_STATIC]
## {PROJECT_TITLE}

Statement of Work - Proof of Concept

Prepared for {COMPANY_NAME}
Prepared by {AUTHOR_NAME}, {AUTHOR_ORG}
{DOCUMENT_DATE} | Version {VERSION}

[META_STATIC_TABLE]
## Table_of_contents

Document Version Control
1. Objective
2. Current State
3. Scope of Work
4. Solution Architecture — AWS
5. Open Clarifications
6. Out of Scope
7. Assumptions and Dependencies
8. Timeline and Deliverables
9. Success Criteria
10. AWS Pricing
11. {AUTHOR_ORG_SHORT} Project Team Effort
Acceptance and Signatories to Statement of Work

[META_GENERATED]
## Document Version Control

PURPOSE
Create the concise provenance and revision baseline that appears immediately after the cover in the reference SOW.

REQUIRED STRUCTURE

1. Start with exactly one five-column table:

| Version | Date | Prepared By | Status | Classification |
|---|---|---|---|---|

2. Populate it using supplied metadata:
   - Version: the supplied document version; do not normalize it to a different format.
   - Date: the supplied document date.
   - Prepared By: the supplied author or author organization. Do not invent a team name.
   - Status: use a supplied status; otherwise use `Draft for Client Review`.
   - Classification: use a supplied classification; otherwise use `Confidential - {COMPANY_NAME}`.

3. Add `### Revision Basis` and identify the exact evidence used for this SOW:
   - the user's product-details text;
   - names/titles of uploaded documents or extracted sources when available;
   - confirmed workshop, clarification, evaluation, phasing, or approval records only when the evidence names them.
   - Never invent a BRD, evaluation sheet, workshop, approval, version history, or previous agreement.

4. If confirmed priorities, phases, deliverables, or module order exist, add `### Phasing Direction Received from {COMPANY_NAME_SHORT}` with a compact table of no more than four columns. Preserve the customer wording and distinguish priority from dependency. If no phasing direction is supplied, omit this subsection entirely.

QUALITY RULES

- Keep the section within 500 words and preferably one page.
- Make the relationship between sources and scope explicit.
- Do not summarize the entire solution here.
- Do not add assumptions, open questions, signatures, or commercial terms here.

[META_STATIC]
## About ShellKode

**ShellKode** is a cloud-native technology company focused on helping organizations modernize their IT environments through Cloud, Data, AI/ML, and Generative AI. The company works with businesses to build scalable, enterprise-grade solutions that improve operational efficiency, generate insights, and solve complex technology challenges.

ShellKode’s key capabilities include Cloud Strategy & Consulting, Cloud Migration & Modernization, Data Engineering & Analytics, Machine Learning, Generative AI, and Agentic AI. Its AI offerings include intelligent document processing, RAG-based knowledge systems, AI agents, conversational assistants, speech analytics, computer vision, and multilingual AI solutions.

The company works across industries including BFSI, Retail & E-commerce, Logistics & Supply Chain, and Healthcare, delivering solutions that combine cloud infrastructure, enterprise data, and AI. ShellKode also has a strong AWS focus, with capabilities around AWS cloud migration, modernization, and Generative AI solutions.

[META_GENERATED]
## About {COMPANY_NAME}

Write exactly two brief, source-grounded prose paragraphs about {COMPANY_NAME}. Cover only its
company profile, industry, products/services and established business operations. Do not describe
this project, its problem, requirements, proposed solution, engagement, or ShellKode's involvement. Do not use subsections,
bullets, numbered lists, or tables. Do not invent industry position, scale, revenue, locations,
products, regulations, or achievements. When source information is limited, keep both paragraphs
to confirmed company facts; omit unsupported details without commenting that information is missing.

[META_GENERATED]
## 1. Objective

PURPOSE
Translate the customer's stated need into the decision and implementation baseline governed by this SOW.

REQUIRED STRUCTURE

Opening narrative - write one concise paragraph covering:

- the business problem or opportunity and why the POC is being undertaken;
- the exact delivery boundary represented by this SOW;
- the relationship between this POC and any broader programme, existing platform, prior phase, or future production rollout when supplied;
- what this SOW enables: solution design, effort estimation, build, validation, or a go/no-go decision;
- any confirmed supersession or precedence rule, without claiming that this SOW supersedes another document unless the source says so.

- After the opening narrative, provide only the outcome-oriented bullets needed to cover the evidenced objective; do not add an `Objectives` subsection or filler to meet a count.
- Each objective must name a capability or business outcome and its intended validation.
- Preserve confirmed outcomes and metrics. If no metric is supplied, state an observable demonstration outcome rather than inventing a number.
- Cover the primary workflow, data/integration outcome, AI outcome where relevant, and operational/governance outcome where relevant.
- Avoid generic objectives such as "improve efficiency" unless followed by the specific mechanism and evidence.

- End the objective bullet list with one brief reader-orientation bullet only when it adds decision value. Do not create a separate How to Read subsection.

BOUNDARIES

- Do not create separate company-profile or executive-summary content.
- Do not describe detailed requirements that belong in Scope of Work.
- Do not state committed dates, costs, or acceptance thresholds unless supplied.

[META_GENERATED]
## 2. Current State

PURPOSE
Explain the evidence-backed current operating context and why the POC is needed.

REQUIRED COVERAGE

1. Opening context:
   - identify the current process/platform only when named;
   - identify the actors and channels involved;
   - state whether the POC replaces, augments, integrates with, or validates an alternative to the current state.

2. Current workflow:
   - describe the current sequence from trigger/input to outcome;
   - name systems, handoffs, manual steps, and data locations only when supplied;
   - preserve known volumes, dates, age of platform, or usage patterns exactly.

3. Pain points and constraints:
   - use concise bullets for each source-supported pain point; do not infer extra shortcomings to make the section look comprehensive;
   - connect each pain point to a workflow consequence such as delay, inconsistency, rework, weak visibility, risk, or cost;
   - distinguish source-confirmed issues from plausible but unconfirmed concerns.

4. Capability gaps:
   - identify missing functionality addressed by the POC, including data, AI, search, quality, governance, integration, or user-experience gaps only when relevant;
   - state when a capability is net-new rather than a migration.

5. Evidence gaps:
   - if current-state facts needed for sizing or design are unavailable, state them briefly and ensure the material item also appears in Open Clarifications.

RULES

- Use concise prose plus bullets; no table unless the source provides structured current-state data that benefits from comparison.
- Do not invent a legacy system name, failure rate, handling time, current architecture, or quantified business impact.
- Do not prescribe the target architecture here.
- Do not add a new top-level heading.

[META_GENERATED]
## 3. Scope of Work

PURPOSE
Produce the implementation-grade heart of the SOW. This section should carry most of the document's functional detail and should be materially more detailed than every other generated section.

ARCHITECT-LED DECOMPOSITION

- If the shared work breakdown contains more than one deliverable, begin with exactly one compact table using `#`, `Deliverable`, `Included Modules`, and `Core Outcome`. Omit this table when there is only one deliverable.
- Follow the shared solution-architecture work breakdown. Group the scope first by outcome-oriented deliverable using `### Deliverable 1 - <Name>`, then by cohesive mini-problem using `#### <Module Name>`.
- Determine the natural number of deliverables and modules from the source and problem. Do not force a standard module count, delivery lifecycle, or benchmark-specific taxonomy.
- Keep Scope of Work, architecture, timeline and acceptance terminology aligned to the same work breakdown.
- Preserve source section/requirement identifiers. Otherwise create stable IDs using a short module prefix.

MANDATORY CONTENT FOR EACH MODULE

### Module reasoning (integrate into prose; do not emit this as a heading)

Reason through the following internally. Use an opening sentence only when it establishes an essential module boundary that cannot be expressed clearly in the implementation bullets:

- objective and business boundary;
- actors/personas;
- trigger/input and expected output;
- relationship to the preceding/following modules;
- explicit inclusion and partial-scope boundaries.

### Workflow and functional behavior

- Describe the normal flow in logical order from initiation to completion.
- Cover user/system actions, states, handoffs, decision points, queues, notifications, and exception paths that are supported by the source.
- Describe sequence with bullets when the module has a meaningful workflow; use capability or processing-rule bullets for non-sequential modules.
- Include every material stage and decision needed to explain the source-backed process without imposing a fixed step count.
- Do not invent screens, states, approval levels, classifications, or business rules absent from the evidence; mark proposed workflow mechanics clearly.

### Concise gold-standard expression

- Write direct implementation-scope bullets beneath each module heading; do not expose the reasoning framework as document structure.
- Do not create standalone or inline pseudo-sections named Proposed Approach, Proposed Implementation, Implementation Approach, Key Outputs, Dependencies, Validation Evidence, Roles, Inputs, Requirements, or Outputs.
- Where closely related actions form one sub-capability, use a single bullet with an inline bold lead-in, for example `- **Monitoring and alert activation:** Configure platform, integration and journey-health monitoring with severity-based notifications to agreed support channels.`
- Each bullet must add a distinct scope action, rule, integration, boundary, qualification, or acceptance-relevant outcome. Remove repetitions and merge bullets that express the same obligation.
- Integrate unique dependencies, proposal status, open points, outputs and validation conditions into the relevant scope bullet instead of appending repeated category lists to every module.
- Avoid generic technology catalogues and inflated qualifiers. Name services only where they define a real Confirmed or explicitly Proposed design decision.

### Functional requirements

Use a compact table only when the source itself contains dense comparable requirements that cannot be expressed more clearly as direct bullets:

| ID | Requirement | Detail |
|---|---|---|

For each requirement:

- use an imperative, testable requirement statement;
- include the actor, trigger/input, processing/rule, output/state, and exception or boundary when applicable;
- preserve supplied values, thresholds, classification hierarchies, routing logic, escalation levels, TAT/SLA rules, and content constraints exactly;
- separate unrelated requirements instead of packing a paragraph into one cell;
- create enough requirements to cover every source-backed feature. Do not cap the count merely to keep the section short.

### Roles and permissions

- Identify relevant personas and permitted actions only when supplied or directly implied by the workflow.
- Put an unconfirmed role/permission model in Open Clarifications rather than inventing access rights.
- State administrative ownership for configurable rules, templates, taxonomies, or evaluation criteria when supported.

### Data and migration

- Cover source data, format, volume, classification, quality, history, attachments, metadata, retention, migration/reconciliation, and system of record when relevant.
- Preserve confirmed numbers exactly and do not convert approximate values into exact commitments.
- If migration is in scope but reconciliation criteria are unknown, state the dependency/open item.

### Integrations

- Name each source-confirmed external system and the supported interaction.
- Cover direction, payload/business event, authentication, status/error handling, and ownership when known.
- For an integration inferred as necessary but not supplied, label it proposed and carry interface/authentication details to Open Clarifications.
- Do not invent an API, vendor, protocol, or latency.

### AI/ML behavior and human review - conditional

When AI/ML is in scope, cover only applicable capabilities such as drafting, summarization, retrieval, classification, extraction, recommendation, sentiment, scoring, or guardrails. For each:

- identify grounding/context inputs;
- state the produced output;
- state confidence/fallback behavior only when supplied or clearly label it proposed;
- state that the responsible human reviews generated output and remains responsible for sending, approving, or acting;
- identify evaluation evidence and unresolved benchmark/threshold questions;
- never claim guaranteed accuracy or fully autonomous regulated decision-making.

### Security, compliance, and audit - conditional

- Carry source-backed access, encryption, residency, retention, logging, disclaimer, audit, and regulator requirements into the relevant module.
- Preserve exact mandatory wording when supplied.
- If exact wording, control owner, evidence, or approval is missing, describe the mechanism and add an open clarification.

### Dependencies and validation

Conclude the module naturally with concise dependency and validation bullets covering:

- confirmed customer inputs/access/approvals;
- upstream/downstream module dependencies;
- the observable demonstration, test record, reconciliation, log, report, or sign-off evidence for the module;
- proposed items clearly labelled for baseline confirmation.

DOCUMENT-WIDE COMPLETENESS CHECK

Before returning the section, verify that every deliverable has one or more meaningful modules and that every key feature, workflow step, use case, integration, data source, technical requirement, compliance requirement, security requirement, success metric, and expressly in-scope deliverable from the requirements baseline appears in at least one module. Do not omit difficult or ambiguous requirements; preserve them and flag the ambiguity.

Do not create numbered or unnumbered headings named Task Statement, Objective, Inputs, Requirements, Outputs, Dependencies, or Validation. Those are architectural reasoning dimensions, not document subsections; weave them into the module introduction and delivery actions.

EXCLUSIONS

- Do not add standalone timeline, test plan, risk register, customer responsibility, support, change-order, termination, marketing, terms, data ownership, or deliverable-acceptance subsections.
- Do not repeat architecture service catalogues, pricing, or staffing here.
- Do not create diagram placeholders or ASCII diagrams.

[META_GENERATED]
## 4. Solution Architecture — AWS

PURPOSE
Provide concise engineering context for the generated logical architecture visual.

ARCHITECTURE EVIDENCE RULE

- Treat `confirmed_aws_services` as confirmed.
- Treat `proposed_aws_services`, architect-selected patterns, topology, scaling, and availability choices as Proposed unless the source confirms them.
- Never state a deployment region, data residency rule, number of Availability Zones, environment count, service tier, or network path as confirmed unless supplied.
- Use the module taxonomy from Section 2 and show how each module maps to components/services.

REQUIRED STRUCTURE

### 5.1 Architecture and Flow

- Start with concise bullets covering only material workload, data, integration, compliance and POC constraints supported by the evidence.
- Add one brief boundary statement for the generated visual; do not repeat every node.
- Use the natural number of steps required for the primary end-to-end data flow and material fallback; do not split actions merely to lengthen the sequence.

### 5.2 Decisions, Controls and Open Boundaries

- Use one compact `Decision/Boundary`, `Rationale`, and `Status` table containing only material decisions. Status must be `Confirmed`, `Proposed`, or `Open`.
- Follow with concise bullets for decision-driving performance, availability, security and observability, audit, residency, retention and recovery requirements.
- When a target is absent, state the confirmation needed instead of inventing one.

COMPLIANCE BOUNDARY

Repeat the exact source qualification for residency/regulatory expectations when necessary. Architecture language must describe controls and intent, not certify compliance.

OUTPUT RULES

- Do not emit diagram syntax, a placeholder image box, or a prose duplicate of the generated diagram.
- Do not list unrelated AWS services.
- Every named service needs a purpose and Confirmed/Proposed status.
- Do not state a multi-AZ, serverless, container, microservices, or managed-service pattern as decided unless the evidence supports it or it is explicitly labelled Proposed.

[META_TABLE]
## 5. Open Clarifications

PURPOSE
Create the authoritative unresolved-item register for facts that materially affect design, scope, acceptance, cost, compliance, or dependency sequencing.

REQUIRED OUTPUT

Start with one short paragraph explaining that items must be closed during discovery/design before the affected baseline is committed.

Use exactly this three-column table:

| Module/Area | Open Item | Status / Note |
|---|---|---|

INCLUSION RULES

- Carry every unresolved item already present in the normalized requirements.
- Add specific gaps discovered while authoring Current State, Detailed Scope, Architecture, Pricing, Success Criteria, or Team Effort.
- Include, where applicable: roles/permissions, sample data, volumes/peaks, data quality, migration reconciliation, interfaces/APIs, authentication, error handling, AI evaluation dataset, quality thresholds, human-review workflow, exact disclaimers/guardrails, regulatory approval owner, retention/deletion, environments, NFRs, RTO/RPO, acceptance evidence, calculator inputs, staffing, duration, and production boundary.
- Phrase each item as one answerable question or confirmation request, not a vague topic.
- Never say that information was not provided, specified, stated, supplied, available or confirmed.
  Ask the question directly and leave `Status / Note` blank when no source-backed status or action exists.
- State a source-backed impact or next action in `Status / Note` and preserve meaningful supplied statuses verbatim.
- Use the same module names as Section 2.

PROHIBITIONS

- Do not silently resolve an unknown.
- Do not label a source-confirmed fact open.
- Do not invent customer responses such as `Will check and update`.
- Do not repeat low-impact editorial questions.
- Do not include generic boilerplate such as `requirements to be confirmed` without naming the requirement and impact.

[META_GENERATED]
## 6. Out of Scope

PURPOSE
Make the POC boundary explicit while preserving the nuanced difference between a limited included baseline and an advanced deferred capability.

REQUIRED STRUCTURE

- Write one opening paragraph explaining the basis of exclusion: expressly deferred, outside the stated POC objective, dependent on a later phase, or not supported by the supplied baseline.
- Group meaningful exclusions as bullets beginning with a bold capability label; do not create exclusion subsections.
- Use the actual deferred capability names from the source. Each bullet must state what is excluded and, where needed, what limited related capability remains included.
- Include only concrete exclusions supported by the evidence or by the expressly selected POC/production boundary; do not target a count or inflate a narrow project.

CONDITIONAL COVERAGE

- Functional: workflows/features beyond the agreed use cases.
- Data: volumes, formats, history, enrichment, migration, or labeling beyond the agreed baseline.
- Integration: external systems/interfaces not expressly included.
- AI/ML: fine-tuning, custom-model development, autonomous decisions, or unsupported modalities unless expressly in scope.
- UI/channel: native mobile, portals, dashboards, voice, social, or other channels only when they are outside the stated baseline.
- Operational: production rollout, support, managed operations, training, or documentation only when the source expressly excludes or defers it. Never exclude a requested support, training, testing, go-live, or documentation deliverable.
- Compliance: certification or legal/regulatory approval unless expressly included.
- Commercial: third-party licenses, cloud consumption, or services not included in the stated commercial boundary, without inventing terms.

RULES

- Do not exclude a capability included in Scope of Work.
- Before writing each exclusion, compare it against key deliverables, functional requirements, the shared work breakdown, and source-labelled requirements. Any overlap stays in scope.
- Put conflicting, optional, `To be confirmed`, or source-assumption boundaries in Open Clarifications unless the source explicitly assigns them to a future phase.
- A POC limitation may state what is not implemented or accepted during the POC, but must not rewrite the customer's broader RFQ as permanently out of scope.
- Architect-proposed commercial boundaries must be labelled `Proposed - subject to baseline confirmation`; never present them as customer-agreed exclusions.
- Do not use broad exclusions that nullify the POC objective.
- Do not add contractual change-control language or legal boilerplate.
- Do not exclude testing needed to demonstrate the POC's Success Criteria.

[META_GENERATED]
## Customer Dependencies

Create a concise dependency register using `ID`, `Customer Dependency`, `Owner Role`, `Needed By`,
`Impact if Delayed`, and `Status`. Include only dependencies that follow from the selected scope,
such as AWS account access, representative data, integration access, subject-matter experts,
security decisions, reviews, test participants, licences, and approvals. Preserve confirmed dates
and owners; otherwise use `To be confirmed`. Do not convert planning assumptions into confirmed
customer commitments.

[META_GENERATED]
## 7. Assumptions

PURPOSE
State the planning conditions used to establish the delivery baseline and the consequences when they do not hold, separated from customer dependencies and unresolved questions.

REQUIRED STRUCTURE

Do not create assumption subsections. Group applicable items as concise bullets with bold inline labels selected from:

- **Platform and Integration:**
- **Data:**
- **Access, Security, and Compliance:**
- **Governance and Business Inputs:**
- **Sequencing and Environments:**

CONTENT RULES

- Generate only the specific planning assumptions needed by the project; do not target a count.
- Every item must derive from the source or be explicitly labelled as a planning assumption.
- Identify the responsible party when useful: `{COMPANY_NAME_SHORT}`, `{AUTHOR_ORG_SHORT}`, a named vendor, or a project role.
- Include the consequence when an unmet assumption affects schedule, scope, cost, quality, architecture, or acceptance.
- Use concrete supplied systems, formats, volumes, services, approval bodies, and review inputs.
- Include integration access only for relevant named/proposed integrations.
- Include data quality, representativeness, rights, and format assumptions when data is used.
- Include AI evaluation/grounding inputs and human reviewers when AI is in scope.
- Include compliance/security approvals only when applicable and preserve qualifications.
- State parallel/sequential relationships using the module names from Section 2.

DISTINCTION RULES

- An assumption is a planning condition used to draft the SOW.
- Do not repeat the Customer Dependencies register in this section.
- An open clarification is a question whose answer is not known. Do not disguise an open question as an assumption.
- Do not invent feedback SLAs, access-provision periods, dates, or durations.

STYLE

- Formal, specific, and readable.
- Prefer bullets; use a compact table only if ownership/consequence comparison materially improves clarity.
- Do not duplicate Out of Scope verbatim.

[META_GENERATED]
## 8. Timeline and Deliverables

PURPOSE
Provide a practical delivery sequence only when the user has selected timeline content.

REQUIRED OUTPUT

- Use a compact table with `Phase`, `Activities and Deliverables`, `Duration`, and `Exit Evidence`.
- Derive phases from the selected scope and preserve any source-confirmed dates, milestones, or durations exactly.
- When dates or duration are not supplied, use `TBC` and identify the planning dependency; never invent a committed schedule.
- Distinguish parallel and sequential work where the requirements support it.
- Do not repeat staffing, pricing, assumptions, or acceptance boilerplate.
- Label architect-derived sequencing as `Proposed - subject to baseline confirmation`.

[META_GENERATED]
## 9. Success Criteria

PURPOSE
Define observable, reviewable evidence that the POC has demonstrated the in-scope capabilities without manufacturing unagreed numeric commitments.

REQUIRED OUTPUT

- Begin directly with one concise criterion per material, testable outcome. Do not invent or subdivide criteria to meet a count.
- Each bullet must contain: the capability/outcome, validation method/evidence, and any confirmed threshold.
- Use the same module names and requirement terminology as Scope of Work.
- Collectively cover:
  - end-to-end workflow completion;
  - data ingestion/migration/reconciliation where relevant;
  - each major module's functional outcome;
  - integration behavior where relevant;
  - AI/ML quality and human-review behavior where relevant;
  - security/compliance control evidence where relevant;
  - stakeholder demonstration/UAT/sign-off boundary when supplied.

VALIDATION EVIDENCE

Use applicable evidence such as demonstration records, UAT scenarios, test reports, benchmark-dataset comparison, reconciliation reports, processing logs, monitoring evidence, audit logs, accuracy reports, or stakeholder sign-off.

METRIC RULES

- Preserve supplied accuracy, latency, throughput, availability, volume, quality, and error thresholds exactly.
- If no threshold is supplied, describe the evidence to be demonstrated and label any proposed target `proposed for baseline confirmation`.
- Do not use complexity-based default accuracy, latency, availability, or success rates.
- Do not claim production operation or decommissioning unless production rollout is explicitly in scope.
- Avoid vague outcomes such as `works as expected`, `improved performance`, or `successful implementation`.

FORMAT RULES

- Bullet list only; no table, grouped heading, or acceptance boilerplate.
- Do not add a separate testing or deliverable-acceptance section.

[META_TABLE]
## 10. AWS Pricing

PURPOSE
Reproduce source-backed cloud pricing with the restrained reference layout, or clearly show what remains pending.

IF A SOURCE-BACKED AWS PRICING CALCULATOR ESTIMATE EXISTS

1. Put `AWS Pricing Calculator Link:` and the editable estimate link above every table; never fabricate an estimate URL.
2. Add `### Estimated Volume Metrics` and reproduce the source-backed business sizing basis in this structure:

| Metric | Estimated Volume |
|---|---|

Include only relevant sourced metrics such as annual/monthly interactions, turns per interaction, AI/deterministic routing share, handovers, backend calls, users, peak concurrency, and retention.

3. Add `### AWS Cost Summary` using this table structure:

| Item | MRR and ARR in the calculator currency |
|---|---|
| AWS Pricing Calculator | <confirmed amount> |
| AWS MRR | <confirmed amount> |
| AWS ARR | <confirmed amount> |

4. Preserve the exact MRR. Calculate ARR only when mathematically implied as MRR x 12 and make no other adjustment or unsupported currency conversion.
5. Reproduce the confirmed volume, environment, and calculator assumptions. Clearly distinguish DEV/UAT/Production or other environments only when supplied.

IF NO SOURCE-BACKED ESTIMATE EXISTS

- Put the generic AWS Pricing Calculator link above the tables.
- Always emit the standard Estimated Volume Metrics rows. Populate source-backed values and leave every unavailable value cell blank without commentary.
- When time-based business volumetrics exist, show a broad, non-binding volumetric planning range. If no defensible workload volume exists, retain blank calculator, MRR and ARR cells.
- Do not expose raw AWS Calculator service fields, unresolved parameters, or a confirmation-needed column in the SOW. Route unresolved material inputs to Open Clarifications instead.

PROHIBITIONS

- Do not use a complexity-only MRR range without a time-based business workload volume.
- Do not invent a single "realistic" number, AWS funding status, discount, approval, service-level cost breakdown, or false precision.
- Do not treat implementation fees as AWS consumption.

[META_GENERATED]
## Customer Responsibilities

List only the customer-owned activities needed for the selected POC scope. Cover applicable
account and environment access, representative data, source-system support, business and technical
decisions, security/privacy review, user participation, validation, approvals, licences, and
acceptance evidence. State the responsible customer role where known and use `To be confirmed`
otherwise. Do not invent response times, named people, procurement commitments, or production
operating obligations.

[META_TABLE]
## 11. {AUTHOR_ORG_SHORT} Project Team Effort

PURPOSE
Show the delivery roles and effort basis using the reference SOW's compact staffing table without turning an inferred team into a commitment.

REQUIRED TABLE

| Resource | Resource Count | Effort Duration in Weeks |
|---|---|---|

SOURCE-BACKED STAFFING

- Reproduce supplied roles, counts, and durations exactly.
- Preserve role naming such as Solution Architect, AI/ML Lead, Cloud Engineer, Fullstack Engineer, UI/UX Developer, Database Engineer, Technical Project Manager, and QA Engineer when supplied.
- Do not add rates, pricing, funding status, or utilization unless supplied.

WHEN STAFFING IS NOT SUPPLIED

- Provide a clearly labelled `Proposed delivery team - subject to effort estimation and commercial confirmation`.
- Derive roles from the actual modules, architecture, integrations, data work, UI, AI, quality, security, and project-governance needs.
- Include a role only when it has material work in scope.
- Use conservative whole-number resource counts.
- For duration, use a supplied project duration when available. Otherwise write `TBC` rather than inventing weeks.
- Do not force the four resource types from the old template and do not assume all workstreams run for the same duration.

AFTER THE TABLE

- Add one short paragraph explaining the effort basis and identifying any open assumptions affecting staffing.
- Do not add implementation cost, rate card, timeline, or commercial-commitment language.

[META_STATIC]
## Project Plan Termination

Termination rights and notice periods are governed by the applicable master agreement. On
termination, the parties will agree an orderly handover of completed work, approved deliverables,
data, access, environments, and outstanding obligations. Any fees or expenses remain subject to
the governing agreement and an approved commercial schedule.

[META_STATIC_TABLE]
## Contacts and Reporting

| Organisation | Role | Name | Email | Responsibilities |
|---|---|---|---|---|
| {COMPANY_NAME_SHORT} | Project Sponsor | To be nominated | To be confirmed | Direction, decisions and escalation |
| {COMPANY_NAME_SHORT} | Product/Acceptance Owner | To be nominated | To be confirmed | Requirements, validation and acceptance |
| {AUTHOR_ORG_SHORT} | Engagement Lead | To be nominated | To be confirmed | Delivery coordination and reporting |
| {AUTHOR_ORG_SHORT} | Solution Architect | To be nominated | To be confirmed | Design authority and technical assurance |

The project kickoff will confirm the reporting cadence, governance forums, escalation path, and
distribution list. No reporting interval is committed unless supplied in the approved baseline.

[META_STATIC]
## Terms and Conditions

- This SOW is governed by the applicable master agreement or other agreement executed by the parties.
- Commercials, invoicing, taxes, expenses, travel, working location, and working hours remain subject to that agreement or an approved commercial schedule.
- AWS and third-party availability, pricing, licensing, and service levels are governed by their providers.
- Customer data will be handled under the agreed confidentiality, privacy, security, residency, retention, and deletion obligations.
- Intellectual property, warranties, liability, indemnities, and order of precedence are governed by the applicable agreement.

[META_STATIC_TABLE]
## Acceptance and Signatories to Statement of Work

"Client" verifies that the terms of this Statement of Work/Proposal and Service Level Agreements are acceptable. The parties hereto are each, acting with proper authority by their respective companies.IN WITNESS WHEREOF, {AUTHOR_ORG_SHORT} and Client have executed this SOW on the Execution Date.

| {AUTHOR_ORG_SHORT} | {COMPANY_NAME_SHORT} |
|--------------------|----------------------|
| Name: | Name: |
| Title: | Title: |
| Signature: | Signature: |
| Date of acceptance: | Date of acceptance: |
