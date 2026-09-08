<!-- BEGIN_GLOBAL_TEMPLATE_CONTRACT -->
# DOCUMENT-WIDE LANGUAGE STANDARD

Use British Indian English throughout, never US spelling. Prefer forms such as `organisation`, `organise`, `centralised`, `analyse`, `behaviour`, `colour`, `programme`, `licence` (noun), and `fulfilment`. Preserve official product names, API fields, quoted source text, and identifiers exactly as supplied.

Write only content needed to define scope, ownership, dependency, boundary, decision, or
validation. Avoid repeated summaries and generic background. Use no more than one short opening
paragraph per section, then concise bullets for non-comparable items or compact tables for genuinely
comparable records. Put each bullet on its own Markdown line and keep it to one main idea.
Default to no subsections. Use at most two direct subsections outside Scope of Work and no nested
subsections. Treat coverage labels in local instructions as bold bullet labels rather than mandatory
headings. Scope of Work may use one heading per deliverable and one nested heading per cohesive module.

Treat only unqualified source assertions as confirmed. Preserve source labels such as Assumption,
Derived, Proposed, To be confirmed, Not stated, Needs clarification, optional, and future. A conflict
between uploaded sources is an Open Clarification, not permission to select a preferred value. Do not
diagnose a current-state gap solely because the target solution requests a capability.

A source table row named a deliverable is a contractual output to preserve, not automatically a
separate architectural delivery package. Separate top-level deliverables require independent phase,
deployment, hand-off, or acceptance boundaries; otherwise cluster the outputs as cohesive modules.
<!-- END_GLOBAL_TEMPLATE_CONTRACT -->

[META_STATIC]
## {PROJECT_TITLE}

Statement of Work - Production Implementation

Prepared for {COMPANY_NAME}
Prepared by {AUTHOR_NAME}, {AUTHOR_ORG}
{DOCUMENT_DATE} | Version {VERSION}

[META_STATIC_TABLE]
## Table_of_contents

1. Document Version Control
2. About {AUTHOR_ORG_SHORT}
3. About {COMPANY_NAME}
4. Objective
5. Current State and Business Context
6. Scope of Work
7. Technical Specifications and System Design
8. Architecture and Integrations
9. Data Migration and Readiness
10. Security, Privacy and Compliance
11. Customer Dependencies
12. Assumptions
13. Open Clarifications
14. Out of Scope
15. Timelines and Deliverables
16. Testing and Acceptance Plan
17. Deployment, Cutover and Rollback
18. AWS Pricing
19. Customer Responsibilities
20. Duration of Work
21. Shellkode Implementation Cost
22. Success Criteria
23. Risks and Mitigations
24. Day-2 Operations and Support
25. Deliverable Acceptance
26. Change Management
28. Project Plan Termination
29. Contacts and Reporting
30. Marketing Authorization
31. Terms and Conditions
32. Acceptance and Signatories to Statement of Work

[META_GENERATED]
## Document Version Control

Create a document-control table with Document, Customer, Delivery Partner, Version, Status,
Date, Engagement Type, Planning Horizon, and Governing Source. Add Purpose and Intended Audience,
Source Basis, Requirements Classification, and Approval Basis. Define Confirmed, Proposed,
Planning Assumption, and Open Clarification. Do not invent approval or source documents.

[META_STATIC]
## About ShellKode

**ShellKode** is a cloud-native technology company focused on helping organizations modernize their IT environments through Cloud, Data, AI/ML, and Generative AI. The company works with businesses to build scalable, enterprise-grade solutions that improve operational efficiency, generate insights, and solve complex technology challenges.

ShellKode’s key capabilities include Cloud Strategy & Consulting, Cloud Migration & Modernization, Data Engineering & Analytics, Machine Learning, Generative AI, and Agentic AI. Its AI offerings include intelligent document processing, RAG-based knowledge systems, AI agents, conversational assistants, speech analytics, computer vision, and multilingual AI solutions.

The company works across industries including BFSI, Retail & E-commerce, Logistics & Supply Chain, and Healthcare, delivering solutions that combine cloud infrastructure, enterprise data, and AI. ShellKode also has a strong AWS focus, with capabilities around AWS cloud migration, modernization, and Generative AI solutions.

[META_GENERATED]
## About {COMPANY_NAME}

Write exactly two brief, source-grounded prose paragraphs about {COMPANY_NAME}. Cover only the
company background and business context relevant to this engagement. Do not use subsections,
bullets, numbered lists, or tables. Do not invent industry position, scale, revenue, locations,
products, regulations, or achievements. When source information is limited, keep both paragraphs
to the confirmed project context and avoid unsupported corporate claims.

[META_GENERATED]
## Objective

Write a decision-oriented production summary covering business problem, target operating outcome,
solution boundary, production qualities, migration approach, principal dependencies, measurable
acceptance basis, and intended handover. Use one brief paragraph followed by only the concise bullets
needed to cover evidenced outcomes; do not add filler to meet a count;
add a key-facts table only when confirmed comparable values exist. Do not
claim projected benefits have already been achieved.

[META_GENERATED]
## Current State and Business Context

Document known current-state processes, systems, actors, volumes, pain points, constraints,
existing controls, and operational impact. Separate facts, inferences, and gaps. Include Current-
State Workflow, Pain Points and Root Causes, Business/Technical Drivers, and Evidence Gaps.

[META_GENERATED]
## Scope of Work

Use the shared architect-generated work breakdown. When it contains more than one deliverable, begin with one compact table using `#`, `Deliverable`, `Included Modules`, and `Core Outcome`; omit this table for a single deliverable. Group the detailed scope by `### Deliverable 1 - <Name>` and place its cohesive mini-problems under `#### <Module Name>`. A top-level deliverable requires an independent phase, deployment, hand-off, or acceptance boundary; contractual capability rows that are built and accepted together remain modules or outputs. Determine the number and boundaries from the source without a fixed limit or generic lifecycle taxonomy. Reason internally about the problem, objective, actors, inputs, requirements, delivery approach, outputs, dependencies and validation, but express the result as concise direct implementation-scope bullets. Do not create standalone pseudo-sections such as Proposed Approach, Key Outputs, Dependencies or Validation Evidence. Integrate unique boundaries, status and validation into the relevant bullet, merge repeated obligations, and use an inline bold lead-in only when it helps group one cohesive sub-capability. Preserve source-specific workflows, rules, data, integrations, exceptions, evidence status and phase boundaries. Use tables only for indispensable comparable source records.

[META_GENERATED]
## Technical Specifications and System Design

Define reviewable specifications rather than generic technology prose:
### Solution Specifications
Use bullets for components, APIs/interfaces, data/storage and applicable AI/ML or rules design. Distinguish model selection from model training/fine-tuning.
### Non-Functional and Operational Specifications
Use NFR-01 onward with Quality Attribute, Target/Proposed Target, Measurement, Environment and Status. Cover environment/configuration, CI/CD, infrastructure as code, backup/recovery, retention/deletion and material design trade-offs as concise bullets.

[META_GENERATED]
## Architecture and Integrations

Provide concise context for the generated architecture visual: material principles and constraints,
the end-to-end flow, trust and environment boundaries, integration contracts, resilience,
observability, and significant trade-offs. Do not duplicate every visual component in prose. Use
compact tables only where comparison is necessary and distinguish confirmed facts from proposals.

[META_GENERATED]
## Data Migration and Readiness

Describe source inventory, ownership, extraction, profiling, cleansing, mapping, transformation,
reconciliation, migration waves, validation, rollback, retention, archival, and deletion. Provide a
migration object table with Source, Object/Data Set, Volume/Status, Method, Owner, Validation,
and Open Issue. If migration is not in scope, state the precise data-readiness work that is.

[META_GENERATED]
## Security, Privacy and Compliance

Create a control-oriented plan covering identity/access, secrets, encryption, network boundaries,
logging/audit, vulnerability management, data classification/privacy, threat modeling, incident
response, evidence, and customer approvals. Use a matrix: Control Area, Requirement, Implementation
Response, Evidence, Owner, Status. Mention a framework only if source-confirmed.

[META_GENERATED]
## Customer Dependencies

Create a dependency register with ID, Dependency, Customer Owner Role, Needed By, Impact if Late,
Mitigation, and Status. Cover accounts/environments, connectivity, data, SMEs, integration owners,
security/compliance decisions, licenses, change windows, UAT participants, and operations readiness.

[META_GENERATED]
## Assumptions

Write only the concrete assumptions needed for this project as bullets. State owner and impact. Distinguish planning
assumptions from facts; cover environment, data, integrations, availability of decision-makers,
test windows, deployment approvals, support readiness, and timeline inputs without inventing values.

[META_GENERATED]
## Open Clarifications

Create a decision log: ID, Clarification, Why It Matters, Decision Owner Role, Required By,
Affected Sections, and Status. Carry forward every material unknown and do not answer it for the customer.

[META_GENERATED]
## Out of Scope

Include only source-supported or expressly agreed exclusions. Never exclude a requested deliverable,
support, training, testing, go-live, analytics, or documentation capability. Treat conflicts, optional
items and unconfirmed boundaries as Open Clarifications unless explicitly deferred. Label any architect-
proposed commercial boundary `Proposed - subject to baseline confirmation`. Reconcile every exclusion
with the requirements and deliverables register and route additions through Change Management.

[META_TABLE]
## Timelines and Deliverables

Build a week-by-week or phase/week plan using confirmed duration or planning_duration_weeks.
Label derived timing as a planning assumption. Columns: Timeframe, Phase/Objective, Activities,
Deliverables/Evidence, Customer Inputs, Exit Criteria. Include design gates, iterative build,
migration/readiness, test cycles, security review, performance test, UAT, cutover rehearsal,
production release, hypercare, documentation, knowledge transfer, and handover as applicable.

[META_GENERATED]
## Testing and Acceptance Plan

Define environments, test ownership, traceability, test-data controls, functional/integration/
regression testing, data/AI quality, performance/resilience, security, migration reconciliation,
UAT, defects/retest, evidence repository, entry/exit criteria, and acceptance authority. Include a
Requirements Traceability Matrix with Requirement/Deliverable ID, Test, Evidence, Owner, Authority.
All unsupplied thresholds must be proposed for baseline confirmation.

[META_GENERATED]
## Deployment, Cutover and Rollback

Provide release prerequisites, deployment sequence, configuration/data migration, smoke tests,
go/no-go criteria, decision authority, communications, rollback triggers, rollback steps, recovery
validation, hypercare, and transition to operations. Use a responsibility/runbook table where helpful.

[META_TABLE]
## AWS Pricing

Use a source-backed estimate when available. Otherwise provide planning ranges by major cost driver
and state the usage variables required for an AWS Pricing Calculator baseline. Columns: Cost Driver,
Usage Assumption, Estimate Status, Monthly Range/Basis, Optimization Lever, Customer Action.
Separate one-time migration/test usage from steady state. Never claim approved funding.

[META_STATIC]
## Customer Responsibilities

- Nominate executive, product, technical, security, data, operations, and acceptance owners.
- Provide approved AWS accounts, environments, connectivity, access, representative data, source-system support, and change windows.
- Confirm data ownership, lawful use, classification, retention, residency, privacy, and applicable control requirements.
- Approve architecture, security, migration, deployment, rollback, and operational-readiness decisions within the agreed cadence.
- Execute customer-owned UAT and production go/no-go responsibilities and provide written acceptance evidence.
- Procure licenses, subscriptions, cloud consumption, certificates, domains, and third-party services not expressly included.
- Ensure customer teams are available for knowledge transfer and assume agreed operational ownership at handover.

[META_GENERATED]
## Duration of Work

State confirmed dates if provided. Otherwise state the planning horizon and that dates require
dependency/resource confirmation. Reconcile with the timeline, feedback windows, change freezes,
deployment approvals, and hypercare. Do not fabricate calendar dates.

[META_TABLE]
## Shellkode Implementation Cost

Create a proposed role/loading table with Role, Responsibilities, Indicative Involvement,
Commercial Status. Use To be confirmed unless a commercial/funding source exists. Reconcile all
roles with scope and timeline; include delivery/project management, architecture, engineering,
quality/security/DevOps/data specialties only as warranted; frontend only when ui_required is true.

[META_GENERATED]
## Success Criteria

Create one acceptance criterion per material testable outcome, numbered SC-01 onward, with Criterion, Confirmed/Proposed Target,
Measurement, Evidence, Test Window, Authority. Cover workflow, functional correctness, data/AI
quality if relevant, integration, performance, availability/resilience, security, migration,
operations, documentation, and acceptance. Do not invent achieved results or agreed SLAs.

[META_GENERATED]
## Risks and Mitigations

Create a legible six-column production risk register with ID, Risk / Trigger,
Likelihood / Impact, Mitigation, Contingency, Owner Role. Cover relevant data, integration, security, compliance,
performance, migration, cutover, rollback, dependency, schedule, adoption, operations, and cost risks.

[META_GENERATED]
## Day-2 Operations and Support

Define the proposed operating model: service ownership; monitoring and alerting; incident severity,
triage and escalation; runbooks; backup/recovery; patch/vulnerability management; capacity/cost;
model/data quality monitoring if relevant; maintenance/change; service reviews; knowledge base;
support hours and SLAs status; and the boundary between included hypercare and a separate support
agreement. Do not invent agreed SLAs.

[META_STATIC]
## Deliverable Acceptance

The Customer will review each deliverable against its documented acceptance criteria and provide
written acceptance or a consolidated rejection notice identifying unmet criteria within ten (10)
calendar days of receipt, unless the approved project plan states another period. Verified non-
conformities within scope will be corrected; new requirements follow Change Management.

[META_STATIC]
## Change Management

Either party may request a change to scope, assumptions, deliverables, dependencies, architecture,
schedule, deployment, support, resources, or commercials. A change becomes effective only through
a mutually approved written change record describing rationale, impacts, revised criteria, owners,
and effective date. Material unresolved changes may pause affected work by mutual agreement.

[META_STATIC]
## Project Plan Termination

Termination rights and notice periods are governed by the applicable master agreement. On
termination, the Customer will pay approved fees and expenses incurred through the effective date,
and both parties will agree an orderly handover of completed work, data, access, environments, and
outstanding obligations, subject to the governing agreement.

[META_STATIC_TABLE]
## Contacts and Reporting

| Organization | Role | Name | Email | Responsibilities |
|---|---|---|---|---|
| {COMPANY_NAME_SHORT} | Executive Sponsor | To be nominated | To be confirmed | Direction and escalation |
| {COMPANY_NAME_SHORT} | Product/Acceptance Owner | To be nominated | To be confirmed | Requirements, UAT and acceptance |
| {COMPANY_NAME_SHORT} | Technical/Security/Operations Owners | To be nominated | To be confirmed | Platform decisions and operational ownership |
| {AUTHOR_ORG_SHORT} | Engagement Lead | {AUTHOR_NAME} | To be confirmed | Delivery coordination and reporting |
| {AUTHOR_ORG_SHORT} | Solution Architect | To be nominated | To be confirmed | Design authority and technical assurance |

The kickoff will confirm reporting cadence, governance forums, escalation path, and distribution list.

[META_STATIC]
## Marketing Authorization

No public reference, customer name/logo use, case study, press release, or marketing statement is
authorized by this SOW alone. Any such use requires separate prior written Customer approval and
must comply with Customer brand and communications policies.

[META_STATIC]
## Terms and Conditions

- This SOW is governed by the applicable master agreement or other agreement executed by the parties.
- Working location/hours, holidays, expenses, invoicing, taxes, payment, and travel are governed by that agreement or an approved commercial schedule.
- AWS and third-party availability, pricing, and service levels are governed by their providers.
- Customer data is handled under agreed ownership, confidentiality, privacy, security, residency, retention, and deletion obligations.
- Intellectual property, confidentiality, warranties, liability, indemnities, and order of precedence are governed by the applicable agreement.

[META_STATIC_TABLE]
## Acceptance and Signatories to Statement of Work

The authorized representatives below acknowledge that they have reviewed this SOW and agree to
its scope, responsibilities, assumptions, deliverables, acceptance criteria, schedule basis,
commercial terms, and production-transition obligations, subject to the governing agreement.

| For {AUTHOR_ORG_SHORT} | For {COMPANY_NAME_SHORT} |
|---|---|
| Name: | Name: |
| Title: | Title: |
| Signature: | Signature: |
| Date: | Date: |
