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
- **Derived:** a necessary synthesis of confirmed facts, such as grouping requirements into modules or identifying an obvious dependency. State it plainly only when the reasoning is direct and low risk.
- **Proposed:** an architect-authored design choice, implementation approach, validation method, sequence, staffing model, or AWS service not confirmed by the source. Label it "Proposed" or "proposed for baseline confirmation" at the point of use.
- **Open:** a fact that changes scope, cost, architecture, acceptance, compliance, or sequencing and cannot safely be inferred. Carry it to Open Clarifications; never answer it on the customer's behalf.

Sparse input is expected. Expand it into a professional SOW by decomposing stated capabilities, mapping actors/inputs/outputs/dependencies, and proposing sensible implementation detail. Do not compensate for sparse input by fabricating customer facts or contractual commitments.

## C. Cross-section consistency rules

- Use British Indian English throughout, not US spelling. Prefer `organisation`, `organise`, `centralised`, `analyse`, `behaviour`, `colour`, `programme`, `licence` (noun), and `fulfilment`. Preserve official product names, API fields, quoted source text, and identifiers exactly as supplied.
- Use the same project name, customer name, module names, requirement IDs, actors, integrations, AWS services, environments, quantities, and status labels everywhere.
- Establish one module/workstream taxonomy in Scope at a Glance and reuse it in Detailed Scope, Architecture, Open Clarifications, Out of Scope, Assumptions, Success Criteria, Pricing inputs, and Team Effort.
- Preserve supplied requirement identifiers. When IDs are absent, create stable IDs using short module prefixes such as `EM-01`, `KB-01`, or `WF-01`; never renumber them differently in another section.
- Do not contradict inclusion boundaries. A baseline capability included in Detailed Scope must not be excluded in Out of Scope; distinguish a limited included capability from an advanced deferred capability.
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
- Prefer concise prose for rationale and bullets for non-comparable items. Use tables only for genuinely comparable records.
- Start a section with no more than one short orienting paragraph. Avoid more than two consecutive prose paragraphs, repeated summaries, and background explanations already established elsewhere.
- Put each bullet on its own Markdown line, keep it to one main idea, and use a real nested Markdown bullet only when the hierarchy is necessary.
- Tables should normally contain two to four columns and must never exceed five. If detail will create narrow prose-heavy cells, split the table or put explanatory prose beneath it.
- Each detailed module should normally contain: objective/boundary, workflow, functional requirements, roles and permissions, data, integrations, business rules and exceptions, AI/human review where relevant, security/compliance where relevant, dependencies, and validation notes. Omit a category only when genuinely inapplicable.
- Use a sequential `Workflow` only where sequence materially aids understanding. A data store, reporting capability, integration layer, or governance capability does not automatically need its own numbered workflow.
- A numbered workflow must contain four to eight meaningful end-to-end steps. Consolidate low-value micro-actions into phases or capability bullets; never create a document-spanning sequence of dozens of sparse items.
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

Document Control
1. Purpose and Scope of This Deliverable
2. Deliverable Scope at a Glance
3. Current State
4. Detailed Scope of Work
5. Solution Architecture — AWS
6. Open Clarifications
7. Out of Scope
8. Assumptions and Dependencies
9. Timeline and Deliverables
10. Success Criteria
11. AWS Pricing
12. {AUTHOR_ORG_SHORT} Project Team Effort
Acceptance and Signatories to Statement of Work

[META_GENERATED]
## Document Control

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

[META_GENERATED]
## About {AUTHOR_ORG_SHORT}

Write a concise, factual profile of {AUTHOR_ORG_SHORT} as the delivery partner. Use supplied
organisation information and project-relevant capabilities only. Do not invent certifications,
partner tiers, awards, customer counts, locations, or delivery claims. If no corporate profile is
supplied, state only the organisation's role in this engagement and the capabilities evidenced by
the selected scope.

[META_GENERATED]
## About {COMPANY_NAME}

Write a concise, source-grounded client profile covering the business context relevant to this
engagement. Do not invent industry position, scale, revenue, locations, products, regulations, or
achievements. When the source provides limited client information, explicitly keep the profile to
the known project context.

[META_GENERATED]
## 1. Purpose and Scope of This Deliverable

PURPOSE
Translate the customer's stated need into the decision and implementation baseline governed by this SOW.

REQUIRED STRUCTURE

Opening narrative - write two to four substantive paragraphs covering:

- the business problem or opportunity and why the POC is being undertaken;
- the exact delivery boundary represented by this SOW;
- the relationship between this POC and any broader programme, existing platform, prior phase, or future production rollout when supplied;
- what this SOW enables: solution design, effort estimation, build, validation, or a go/no-go decision;
- any confirmed supersession or precedence rule, without claiming that this SOW supersedes another document unless the source says so.

### 1.1 Objectives

- Provide four to eight outcome-oriented bullets.
- Each objective must name a capability or business outcome and its intended validation.
- Preserve confirmed outcomes and metrics. If no metric is supplied, state an observable demonstration outcome rather than inventing a number.
- Cover the primary workflow, data/integration outcome, AI outcome where relevant, and operational/governance outcome where relevant.
- Avoid generic objectives such as "improve efficiency" unless followed by the specific mechanism and evidence.

### 1.2 How to Read This Document

- Give one concise paragraph mapping the reader to the sections that actually exist.
- Explain that detailed scope is organized by module/workstream and that Open Clarifications controls unresolved baseline items.
- Do not reference a section absent from the template and do not use stale numbering copied from another SOW.

BOUNDARIES

- Do not create separate company-profile or executive-summary content.
- Do not describe detailed requirements that belong in Section 4.
- Do not state committed dates, costs, or acceptance thresholds unless supplied.

[META_TABLE]
## 2. Deliverable Scope at a Glance

PURPOSE
Provide the benchmark-style orientation view of the complete in-scope solution and its dependency order.

REQUIRED OUTPUT

Start directly with one table using exactly these four columns:

| # | Module/Workstream | Core Outcome | Depends On |
|---|---|---|---|

MODULE DERIVATION RULES

- Derive three to six coherent modules/workstreams from the actual use case, key features, workflow steps, personas, integrations, and data sources. Exceed six only when the source explicitly defines more independently reviewable modules.
- Prefer business-capability names over technology-layer names. Example patterns include `Email and Ticket Management`, `Knowledge Management`, `Agent Assist`, or `Quality Automation`, but use them only when supported by the project.
- Consolidate closely related features into one module; do not create one module per bullet.
- Make the first module the enabling foundation when the evidence supports a foundation/dependency relationship.
- `Core Outcome` must describe the observable result, not an activity list.
- `Depends On` must use confirmed dependencies where available. Architect-derived build order must be labelled `Proposed sequence:`.
- Use `None identified` only when a module is genuinely independent; do not hide unknown integration or data prerequisites.

AFTER THE TABLE

- Add one or two concise paragraphs explaining the build/dependency logic.
- State which workstreams may proceed in parallel and which require an earlier foundation, but label inferred sequencing as proposed.
- Do not introduce a week-by-week timeline.

CONSISTENCY GATE

The module names and order established here are authoritative for Sections 4 through 11. Do not create a different taxonomy later.

[META_GENERATED]
## 3. Current State

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
   - use five to twelve concise bullets when enough evidence exists;
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
## 4. Detailed Scope of Work

PURPOSE
Produce the implementation-grade heart of the SOW. This section should carry most of the document's functional detail and should be materially more detailed than every other generated section.

MODULE TAXONOMY

- Reuse exactly the module/workstream names and order that can be derived from the same requirements used in Section 2.
- Create `### 4.1 <Module Name>`, `### 4.2 <Module Name>`, and so on.
- Where a module contains distinct capability groups, use `#### 4.x.1 <Capability>` subsections.
- Generate three to six modules according to actual scope and complexity. Do not force benchmark-specific CRM modules onto unrelated use cases, and do not promote supporting layers into separate modules when they can be covered within the module they support.
- Preserve source section/requirement identifiers. Otherwise create stable IDs using a short module prefix.

MANDATORY CONTENT FOR EACH MODULE

### Module opening

Write a substantive paragraph covering:

- objective and business boundary;
- actors/personas;
- trigger/input and expected output;
- relationship to the preceding/following modules;
- explicit inclusion and partial-scope boundaries.

### Workflow and functional behavior

- Describe the normal flow in logical order from initiation to completion.
- Cover user/system actions, states, handoffs, decision points, queues, notifications, and exception paths that are supported by the source.
- Add a `#### 4.x.1 Workflow` subsection only when the module has a meaningful sequential process.
- Use four to eight numbered steps. Each step must represent a complete stage or decision, not a single UI click, field, validation, notification, or logging action.
- If a flow would require more than eight steps, group it into three to six named phases and describe the lower-level actions as concise bullets or requirements. Do not continue one workflow index across modules.
- For integration, reporting, data-store, governance, and other non-sequential modules, prefer `#### Capability Behavior`, `#### Processing Rules`, or requirement tables instead of manufacturing a workflow.
- Do not invent screens, states, approval levels, classifications, or business rules absent from the evidence; mark proposed workflow mechanics clearly.

### Functional requirements

Use one or more compact tables with no more than three columns:

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

End each module with `#### Dependencies and Validation` containing:

- confirmed customer inputs/access/approvals;
- upstream/downstream module dependencies;
- the observable demonstration, test record, reconciliation, log, report, or sign-off evidence for the module;
- proposed items clearly labelled for baseline confirmation.

DOCUMENT-WIDE COMPLETENESS CHECK

Before returning the section, verify that every key feature, workflow step, use case, integration, data source, technical requirement, compliance requirement, security requirement, success metric, and expressly in-scope deliverable from the requirements baseline appears in at least one module. Do not omit difficult or ambiguous requirements; preserve them and flag the ambiguity.

EXCLUSIONS

- Do not add standalone timeline, test plan, risk register, customer responsibility, support, change-order, termination, marketing, terms, data ownership, or deliverable-acceptance subsections.
- Do not repeat architecture service catalogues, pricing, or staffing here.
- Do not create diagram placeholders or ASCII diagrams.

[META_GENERATED]
## 5. Solution Architecture — AWS

PURPOSE
Provide concise engineering context for the generated logical architecture visual.

ARCHITECTURE EVIDENCE RULE

- Treat `confirmed_aws_services` as confirmed.
- Treat `proposed_aws_services`, architect-selected patterns, topology, scaling, and availability choices as Proposed unless the source confirms them.
- Never state a deployment region, data residency rule, number of Availability Zones, environment count, service tier, or network path as confirmed unless supplied.
- Use the module taxonomy from Section 2 and show how each module maps to components/services.

REQUIRED STRUCTURE

### 5.1 Architecture Drivers and Constraints

Use three to six bullets for only the material workload, data, integration, compliance and POC constraints. State material unknowns as open items.

### 5.2 High-Level Architecture

Write one short paragraph explaining the principal boundaries and status of the visual. Do not repeat every visual node in prose or add a second component map.

### 5.3 End-to-End Data Flow

Use five to eight numbered steps covering the primary path and material fallback. Include human review, asynchronous processing and audit only when relevant. Do not invent protocols or payload fields.

### 5.4 Design Decisions and Open Boundaries

Use a compact table with `Decision/Boundary`, `Rationale`, and `Status`. Include three to six items only. `Status` must be `Confirmed`, `Proposed`, or `Open`; do not fabricate a decision history.

### 5.5 Non-Functional Design Alignment

List only confirmed or decision-driving performance, availability, security, audit, residency, retention and recovery requirements. When a target is absent, identify the confirmation needed instead of inventing one.

COMPLIANCE BOUNDARY

Repeat the exact source qualification for residency/regulatory expectations when necessary. Architecture language must describe controls and intent, not certify compliance.

OUTPUT RULES

- Do not emit diagram syntax, a placeholder image box, or a prose duplicate of the generated diagram.
- Do not list unrelated AWS services.
- Every named service needs a purpose and Confirmed/Proposed status.
- Do not state a multi-AZ, serverless, container, microservices, or managed-service pattern as decided unless the evidence supports it or it is explicitly labelled Proposed.

[META_TABLE]
## 6. Open Clarifications

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
- State the impact or next action in `Status / Note` and preserve supplied statuses verbatim.
- Use the same module names as Section 2.

PROHIBITIONS

- Do not silently resolve an unknown.
- Do not label a source-confirmed fact open.
- Do not invent customer responses such as `Will check and update`.
- Do not repeat low-impact editorial questions.
- Do not include generic boilerplate such as `requirements to be confirmed` without naming the requirement and impact.

[META_GENERATED]
## 7. Out of Scope

PURPOSE
Make the POC boundary explicit while preserving the nuanced difference between a limited included baseline and an advanced deferred capability.

REQUIRED STRUCTURE

- Write one opening paragraph explaining the basis of exclusion: expressly deferred, outside the stated POC objective, dependent on a later phase, or not supported by the supplied baseline.
- Group meaningful exclusions under numbered subsections such as `### 7.1 <Capability Group>`.
- Use the actual deferred capability names from the source. For each group, state what is excluded and, where needed, what limited related capability remains included.
- Include eight to fifteen concrete exclusions when the evidence supports that breadth; do not inflate a narrow project.

CONDITIONAL COVERAGE

- Functional: workflows/features beyond the agreed use cases.
- Data: volumes, formats, history, enrichment, migration, or labeling beyond the agreed baseline.
- Integration: external systems/interfaces not expressly included.
- AI/ML: fine-tuning, custom-model development, autonomous decisions, or unsupported modalities unless expressly in scope.
- UI/channel: native mobile, portals, dashboards, voice, social, or other channels only when they are outside the stated baseline.
- Operational: production rollout, 24x7 support, managed operations, broad training, or extensive documentation unless expressly included.
- Compliance: certification or legal/regulatory approval unless expressly included.
- Commercial: third-party licenses, cloud consumption, or services not included in the stated commercial boundary, without inventing terms.

RULES

- Do not exclude a capability included in Detailed Scope.
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
## 8. Assumptions

PURPOSE
State the planning conditions used to establish the delivery baseline and the consequences when they do not hold, separated from customer dependencies and unresolved questions.

REQUIRED STRUCTURE

Use only applicable subsections, normally selected from:

### 8.1 Platform and Integration
### 8.2 Data
### 8.3 Access, Security, and Compliance
### 8.4 Governance and Business Inputs
### 8.5 Sequencing and Environments

CONTENT RULES

- Generate eight to sixteen specific items according to project complexity.
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
## 9. Timeline and Deliverables

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
## 10. Success Criteria

PURPOSE
Define observable, reviewable evidence that the POC has demonstrated the in-scope capabilities without manufacturing unagreed numeric commitments.

REQUIRED OUTPUT

- Begin directly with seven to twelve concise bullets for a multi-module POC; use five to eight for a genuinely simple POC.
- Each bullet must contain: the capability/outcome, validation method/evidence, and any confirmed threshold.
- Use the same module names and requirement terminology as Detailed Scope.
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
## 11. AWS Pricing

PURPOSE
Reproduce source-backed cloud pricing with the restrained reference layout, or clearly show what remains pending.

IF A SOURCE-BACKED AWS PRICING CALCULATOR ESTIMATE EXISTS

1. Reproduce the supplied calculator link/label exactly; never fabricate a URL.
2. Use exactly this table structure:

| Item | MRR in USD |
|---|---|
| AWS Pricing Calculator | <confirmed amount> |
| AWS MRR | <confirmed amount> |
| AWS ARR | <confirmed amount> |

3. Preserve the exact MRR. Calculate ARR only when mathematically implied as MRR x 12 and make no other adjustment.
4. Reproduce the confirmed volume, environment, and calculator assumptions. Clearly distinguish DEV/UAT/Production or other environments only when supplied.

IF NO SOURCE-BACKED ESTIMATE EXISTS

- State: `AWS pricing is pending completion of a source-backed AWS Pricing Calculator estimate.`
- Do not produce an amount table with guessed values.
- Provide a compact table of the material confirmed and open sizing inputs, using no more than three columns:

| Pricing Input | Current Basis | Confirmation Needed |
|---|---|---|

- Cover only relevant inputs: region, environments, requests/transactions, users/concurrency, storage/retention, data transfer, model usage, compute pattern, database/search sizing, logging, resilience, and support plan.

PROHIBITIONS

- Do not use complexity-based MRR ranges.
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
## 12. {AUTHOR_ORG_SHORT} Project Team Effort

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
