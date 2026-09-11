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

Statement of Work - POC to Production Transition

Prepared for {COMPANY_NAME}
Prepared by {AUTHOR_NAME}, {AUTHOR_ORG}
{DOCUMENT_DATE} | Version {VERSION}

[META_STATIC_TABLE]
## Table_of_contents

1. Document Version Control
2. About {AUTHOR_ORG_SHORT}
3. About {COMPANY_NAME}
4. Objective
5. POC Evidence and Outcomes
6. Production Gap Assessment
7. Scope of Work
8. Technical Specifications and System Design
9. Architecture and Integrations
10. Data Migration and Readiness
11. Security, Privacy and Compliance
12. Migration, Cutover and Rollback
13. Customer Dependencies
14. Assumptions
15. Open Clarifications
16. Out of Scope
17. Timelines and Deliverables
18. Testing and Acceptance Plan
19. AWS Pricing
20. Customer Responsibilities
21. Duration of Work
22. Shellkode Implementation Cost
23. Success Criteria
24. Risks and Mitigations
25. Day-2 Operations and Support
26. Deliverable Acceptance
27. Change Management
28. Project Plan Termination
30. Contacts and Reporting
31. Marketing Authorization
32. Terms and Conditions
33. Acceptance and Signatories to Statement of Work

[META_GENERATED]
## Document Version Control

Create document control and purpose/source-basis sections. Identify the uploaded POC as evidence,
not automatically as an approved production baseline. Define Confirmed POC Evidence, Proposed
Production Requirement, Planning Assumption, and Open Clarification. Do not invent approval status.

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
## Objective

Explain the POC-to-production decision, demonstrated capability, remaining hardening work, target
production outcome, principal risks/dependencies, migration approach, and acceptance basis. Clearly
separate what the POC demonstrated from what production must still prove.

[META_GENERATED]
## POC Evidence and Outcomes

Use only the ingested POC evidence. Include:
### POC Evidence Summary
Use concise bullets for implemented scope, demonstrated workflow/architecture, measured outcomes,
known limitations/deferred items and reusable assets. If the source lacks results, state that evidence is unavailable.
### Evidence Register
Use Evidence ID, POC Claim/Artifact, Source Location/Description, Confidence, Production Relevance,
and Verification Needed.

[META_GENERATED]
## Production Gap Assessment

Compare POC evidence with production readiness. Use a matrix: Domain, POC State, Production Need,
Gap, Required Work, Evidence/Decision, Priority. Cover architecture, scale/performance, security,
compliance, data, integrations, reliability/recovery, deployment, testing, observability, support,
documentation, governance, and commercials. Do not imply POC behavior meets production SLAs.

[META_GENERATED]
## Scope of Work

Use the shared architect-generated work breakdown. When it contains more than one deliverable, begin with one compact table using `#`, `Deliverable`, `Included Modules`, and `Core Outcome`; omit this table for a single deliverable. Group the detailed scope by `### Deliverable 1 - <Name>` and place its cohesive mini-problems under `#### <Module Name>`. A top-level deliverable requires an independent phase, deployment, hand-off, or acceptance boundary; contractual capability rows that transition and are accepted together remain modules or outputs. Determine the number and boundaries from the source without a fixed limit or generic lifecycle taxonomy. Reason internally about the problem, objective, actors, inputs, requirements, production approach, outputs, dependencies and validation, but express the result as concise direct implementation-scope bullets. Do not create standalone pseudo-sections such as Proposed Approach, Key Outputs, Dependencies or Validation Evidence. Integrate unique boundaries, status and validation into the relevant bullet, merge repeated obligations, and use an inline bold lead-in only for one cohesive sub-capability. State the POC disposition wherever applicable and preserve source-specific workflows, rules, data, integrations, exceptions, evidence status and phase boundaries. Use tables only for indispensable comparable source records.

[META_GENERATED]
## Technical Specifications and System Design

Define production specifications for components, APIs, data model, AI/rules if applicable,
environment/configuration, CI/CD, infrastructure as code, backup/recovery, retention/deletion,
availability/scaling, and design decisions. Number NFRs and label unsupplied targets as proposed.

[META_GENERATED]
## Architecture and Integrations

Provide concise context for the generated target-architecture visual: POC-to-production component
disposition, data flow, environment and trust boundaries, integration contracts, resilience,
observability, and significant trade-offs. Do not duplicate every visual node in prose. Distinguish
confirmed and proposed AWS services.

[META_GENERATED]
## Data Migration and Readiness

Cover POC data disposition, source profiling, ownership, mapping, cleansing, migration waves,
reconciliation, production seeding, rollback, archival/deletion, and validation. State what POC
test data cannot be promoted and why. Use a migration inventory table.

[META_GENERATED]
## Security, Privacy and Compliance

Create a control matrix covering identity, secrets, encryption, network, audit/logging,
vulnerability management, data privacy/classification, threat modeling, incident response,
and evidence/approvals. Contrast POC controls with production needs. Mention frameworks only if confirmed.

[META_GENERATED]
## Migration, Cutover and Rollback

Provide POC asset transition, release prerequisites, deployment/data sequence, rehearsal,
go/no-go criteria and authority, smoke/business validation, communications, rollback triggers and
steps, recovery validation, hypercare, and handover. Make unknown change windows explicit.

[META_GENERATED]
## Customer Dependencies

Create a dependency register covering production accounts/environments, POC artifact access,
connectivity, data, SMEs, integration owners, security/compliance decisions, licenses, change
windows, UAT, go-live and operations readiness. Include owner role, needed-by, impact, mitigation, status.

[META_GENERATED]
## Assumptions

Write only the POC-to-production assumptions needed for this project, with owner/impact. Address reusability of POC assets,
source completeness, environment access, data rights, decisions, test windows, change controls,
operational ownership, and schedule basis without presenting assumptions as facts.

[META_GENERATED]
## Open Clarifications

Create a decision log with ID, Clarification, Why It Matters, Owner Role, Required By, Affected
Sections, Status. Include gaps from the source POC and every material production open item as a
direct answerable question. Never state that information was not provided, specified, stated,
supplied, available or confirmed; leave an unavailable status/value cell blank.

[META_GENERATED]
## Out of Scope

Include only source-supported or expressly agreed production exclusions and clearly state which POC
features/assets are not production-ready. Never exclude a requested production deliverable. Treat
conflicts, optional items and unconfirmed boundaries as Open Clarifications unless explicitly deferred.
Label architect-proposed boundaries `Proposed - subject to baseline confirmation`; reconcile them with
the gap assessment and requirements register before routing additions through Change Management.

[META_TABLE]
## Timelines and Deliverables

Build a planning schedule across confirmed duration or planning_duration_weeks with no gaps.
Columns: Timeframe, Phase/Objective, POC Asset Disposition/Activities, Deliverables/Evidence,
Customer Inputs, Exit Criteria. Include evidence validation, gap closure, hardening, security,
migration, multiple test cycles, rehearsal, go-live, hypercare and handover as applicable.

[META_GENERATED]
## Testing and Acceptance Plan

Define regression against POC behavior plus production functional, integration, data/AI quality,
performance/resilience, security, migration, UAT, cutover and operational acceptance. Include test
data/evidence, defects/retest, entry/exit criteria, authority, and a traceability matrix. Do not reuse
POC results as production evidence without explicit applicability and revalidation.

[META_TABLE]
## AWS Pricing

Put the editable AWS Pricing Calculator link above all tables. Show only a two-column
`Estimated Volume Metrics` table of source-backed business workload measures such as interactions,
turns, inference share, handovers, backend calls, users, concurrency and retention. Follow it with a
two-column `AWS Cost Summary` containing the calculator estimate, AWS MRR and AWS ARR in the
calculator currency. Do not expose raw service configuration fields, unresolved calculator
parameters, or a confirmation-needed column. Route unresolved material inputs to Open Clarifications.
Always retain the standard workload and cost rows, leaving unavailable values blank without commentary.
Use a broad non-binding fallback only when time-based business volumetrics support it. Distinguish
POC, transition/test and production usage only where sourced. Never invent approved funding,
precise calculator totals, or an unsupported currency conversion.

[META_STATIC]
## Customer Responsibilities

- Nominate executive, product, technical, security, data, operations, and acceptance owners.
- Provide the complete POC repository, artifacts, configurations, test evidence, known defects, environments, and access required for assessment and transition.
- Approve reuse/refactor/replace decisions, target architecture, security controls, migration, change windows, rollback, and go-live.
- Confirm data ownership, lawful use, classification, privacy, retention, residency, and applicable controls.
- Supply production-representative data and execute customer-owned UAT and go/no-go responsibilities.
- Prepare operational teams for knowledge transfer and assume agreed ownership at handover.

[META_GENERATED]
## Duration of Work

State confirmed dates if supplied; otherwise state the planning horizon and baseline conditions.
Reconcile evidence assessment, remediation, migration, test cycles, approvals, change windows,
go-live and hypercare. Never infer calendar dates from the POC document unless explicitly stated as future dates.

[META_TABLE]
## Shellkode Implementation Cost

Create an indicative role/loading table consistent with the production gap and schedule. Use
Commercial Status = To be confirmed unless source-backed. Include roles warranted by transition,
engineering, data/AI, platform/DevOps, quality, security, architecture and delivery; frontend only if required.

[META_GENERATED]
## Success Criteria

Create SC-identified production acceptance criteria with confirmed/proposed target, measurement,
evidence, test window, and authority. Cover gap closure, retained POC behavior, functional/integration,
data/AI, performance/resilience, security, migration, deployment/rollback, operations and handover.

[META_GENERATED]
## Risks and Mitigations

Create a legible six-column risk register: ID, Risk / Trigger, Likelihood / Impact, Mitigation,
Contingency, Owner Role. Emphasize incomplete POC evidence, non-production code/design, data drift,
integration constraints, security/compliance gaps, scale, migration, cutover/rollback, operations,
dependency, schedule and cost.

[META_GENERATED]
## Day-2 Operations and Support

Define target service ownership, monitoring/alerting, incident model, runbooks, backup/recovery,
patch/vulnerability, capacity/cost, model/data monitoring where relevant, maintenance/change,
service reviews, knowledge, support hours/SLA status, hypercare, and separate-support boundary.

[META_STATIC]
## Deliverable Acceptance

The Customer will review each deliverable against its documented acceptance criteria and provide
written acceptance or a consolidated rejection notice identifying unmet criteria within ten (10)
calendar days, unless another period is approved. POC evidence does not waive production acceptance testing.

[META_STATIC]
## Change Management

Changes to the approved gap baseline, POC asset disposition, production scope, assumptions,
deliverables, architecture, migration, schedule, support, resources, or commercials require a
mutually approved written change record describing rationale, impact, revised criteria and effective date.

[META_STATIC]
## Project Plan Termination

Termination is governed by the applicable master agreement. The parties will agree an orderly
handover of completed work, POC and production artifacts, data, access, environments, and open obligations.

[META_STATIC_TABLE]
## Contacts and Reporting

| Organization | Role | Name | Email | Responsibilities |
|---|---|---|---|---|
| {COMPANY_NAME_SHORT} | Executive Sponsor | To be nominated | To be confirmed | Direction and escalation |
| {COMPANY_NAME_SHORT} | Product/Acceptance Owner | To be nominated | To be confirmed | Scope, UAT and acceptance |
| {COMPANY_NAME_SHORT} | Technical/Security/Operations Owners | To be nominated | To be confirmed | Target platform and operations |
| {AUTHOR_ORG_SHORT} | Engagement Lead | {AUTHOR_NAME} | To be confirmed | Delivery and reporting |
| {AUTHOR_ORG_SHORT} | Solution Architect | To be nominated | To be confirmed | Gap assessment and design authority |

[META_STATIC]
## Marketing Authorization

No public reference, customer name/logo use, case study, press release, or marketing statement is
authorized by this SOW alone. Any such use requires separate prior written Customer approval.

[META_STATIC]
## Terms and Conditions

- This SOW is governed by the applicable master agreement or other agreement executed by the parties.
- AWS and third-party availability, pricing, and service levels are governed by their providers.
- Customer data and POC/production artifacts remain subject to agreed ownership, confidentiality, privacy, security, retention, and deletion obligations.
- Intellectual property, warranties, liability, indemnities, payment, and order of precedence are governed by the applicable agreement.

[META_STATIC_TABLE]
## Acceptance and Signatories to Statement of Work

The authorized representatives acknowledge this POC-to-production scope, evidence/gap basis,
responsibilities, assumptions, deliverables, acceptance criteria, schedule basis, and commercials.

| For {AUTHOR_ORG_SHORT} | For {COMPANY_NAME_SHORT} |
|---|---|
| Name: | Name: |
| Title: | Title: |
| Signature: | Signature: |
| Date: | Date: |
