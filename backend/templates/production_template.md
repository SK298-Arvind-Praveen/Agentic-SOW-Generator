<!-- BEGIN_GLOBAL_TEMPLATE_CONTRACT -->
# DOCUMENT-WIDE LANGUAGE STANDARD

Use British Indian English throughout, never US spelling. Prefer forms such as `organisation`, `organise`, `centralised`, `analyse`, `behaviour`, `colour`, `programme`, `licence` (noun), and `fulfilment`. Preserve official product names, API fields, quoted source text, and identifiers exactly as supplied.
<!-- END_GLOBAL_TEMPLATE_CONTRACT -->

[META_STATIC]
## {PROJECT_TITLE}

Statement of Work - Production Implementation

Prepared for {COMPANY_NAME}
Prepared by {AUTHOR_NAME}, {AUTHOR_ORG}
{DOCUMENT_DATE} | Version {VERSION}

[META_STATIC_TABLE]
## Table_of_contents

1. Document Control and Basis
2. About {AUTHOR_ORG_SHORT}
3. About {COMPANY_NAME}
4. Executive Summary and Project Overview
5. Current State and Business Context
6. Scope at a Glance
7. Detailed Scope of Work
8. Technical Specifications and System Design
9. Architecture and Integrations
10. Data Migration and Readiness
11. Security, Privacy and Compliance
12. Customer Dependencies
13. Assumptions
14. Open Clarifications
15. Out of Scope
16. Timelines and Deliverables
17. Testing and Acceptance Plan
18. Deployment, Cutover and Rollback
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
29. Contacts and Reporting
30. Marketing Authorization
31. Terms and Conditions
32. Acceptance and Signatories to Statement of Work

[META_GENERATED]
## Document Control and Basis

Create a document-control table with Document, Customer, Delivery Partner, Version, Status,
Date, Engagement Type, Planning Horizon, and Governing Source. Add Purpose and Intended Audience,
Source Basis, Requirements Classification, and Approval Basis. Define Confirmed, Proposed,
Planning Assumption, and Open Clarification. Do not invent approval or source documents.

[META_HYBRID]
## About {AUTHOR_ORG_SHORT}

{AUTHOR_ORG_DESCRIPTION}

[META_HYBRID]
## About {COMPANY_NAME}

{COMPANY_DESCRIPTION}

[META_GENERATED]
## Executive Summary and Project Overview

Write a decision-oriented production summary covering business problem, target operating outcome,
solution boundary, production qualities, migration approach, principal dependencies, measurable
acceptance basis, and intended handover. Use 4-6 short paragraphs plus a key-facts table. Do not
claim projected benefits have already been achieved.

[META_GENERATED]
## Current State and Business Context

Document known current-state processes, systems, actors, volumes, pain points, constraints,
existing controls, and operational impact. Separate facts, inferences, and gaps. Include Current-
State Workflow, Pain Points and Root Causes, Business/Technical Drivers, and Evidence Gaps.

[META_GENERATED]
## Scope at a Glance

Create a one-page orientation view: objectives; in-scope capabilities; user groups; data sources;
integrations; target environments; proposed AWS service families; explicit exclusions; production
quality attributes; planning duration; deployment approach; and acceptance authority.

[META_GENERATED]
## Detailed Scope of Work

Build a complete, testable work breakdown:
### Mobilization, Discovery and Baseline
### Functional Requirements
Use IDs FR-01 onward with Requirement, Source/Status, Delivery Response, Output, Validation Method.
### Application and Workflow Engineering
### Data and AI Engineering
### Integration Engineering
### User Experience
Include only if ui_required is true.
### Platform Engineering and Infrastructure as Code
### Security and Compliance Implementation
### Observability and Operational Readiness
### Documentation, Training and Knowledge Transfer
### Deliverables Register
Use DEL-01 onward with Description, Format, Owner, Acceptance Evidence, and Timing.

[META_GENERATED]
## Technical Specifications and System Design

Define reviewable specifications rather than generic technology prose:
### Functional Component Specifications
### API and Interface Contracts
### Data Model and Storage Design
### AI/ML or Rules Design
Include only if applicable; distinguish model selection from model training/fine-tuning.
### Non-Functional Requirements
Use NFR-01 onward with Quality Attribute, Target/Proposed Target, Measurement, Environment, Status.
### Environment and Configuration Strategy
### CI/CD and Infrastructure as Code
### Backup, Recovery, Retention and Deletion
### Design Decisions and Trade-offs

[META_GENERATED]
## Architecture and Integrations

Do not create a diagram. Provide Architecture Principles, Logical Component Map, End-to-End Data
Flow, Network/Account/Environment Boundaries, Integration Contract Matrix, Security Trust
Boundaries, High Availability and Scaling, Observability, and Alternatives/Trade-offs. Tables must
distinguish confirmed components from proposals and state purpose, data, control, owner, and status.

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

Write 10-15 concrete assumptions as bullets. State owner and impact. Distinguish planning
assumptions from facts; cover environment, data, integrations, availability of decision-makers,
test windows, deployment approvals, support readiness, and timeline inputs without inventing values.

[META_GENERATED]
## Open Clarifications

Create a decision log: ID, Clarification, Why It Matters, Decision Owner Role, Required By,
Affected Sections, and Status. Carry forward every material unknown and do not answer it for the customer.

[META_GENERATED]
## Out of Scope

Group relevant exclusions under Functional, Data/AI, Integration, Platform, Migration, Security/
Compliance, Operations/Support, and Commercial. Reconcile exclusions with the deliverables register
and route additions through Change Management.

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

Create 8-12 acceptance criteria SC-01 onward with Criterion, Confirmed/Proposed Target,
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
