<!-- BEGIN_GLOBAL_TEMPLATE_CONTRACT -->
CONCISE, RELEVANT, SIMPLE — CLIENT DELIVERY AGREEMENT
Selecting a section authorises its subject; it does not require a full checklist or a page of content.
Give every detail one primary home. Scope owns the work; other sections add only a different contractual fact.
Before retaining a point, ask: what specific scope boundary, delivery condition, acceptance decision or customer duty would be lost if this were removed?
If the answer is none, remove it. A true fact is not automatically relevant to this section.
Merge points describing the same action or boundary, retaining distinct obligations and exceptions.
Use familiar verbs: build, connect, check, store, test, hand over. Avoid 'enterprise-grade', 'comprehensive', 'robust', 'posture', 'governance baseline' and repeated 'evidenced by'.
Use one short sentence per bullet. Never prefix a bullet with a bold summary label and colon; write the sentence directly.
In every generated narrative bullet, use one meaningful inline **bold** phrase, usually 1-2 words, highlighting the key action, outcome or delivery condition, not just a product name. Never bold whole sentences or add label-and-colon prefixes. Keep About Client as two factual paragraphs with sparse emphasis; leave static/legal content unchanged. Tables do not need bold in every cell.
Write at agreement level, not test-plan or operational-runbook level. Combine related actions and approvals, keep each fact in its primary section, and omit implementation microsteps unless they change acceptance or scope.
Do not shorten prose by dropping qualifiers, negation, units, thresholds, human review or phase boundaries.
Tables are for values people compare (pricing, staffing, schedule, contacts); narrative commitments use bullets.
Never turn a list of processes into a tracking register with invented IDs, owners, status, impact and evidence columns.
Do not add minimum counts, arbitrary page limits or an item for every module in every section.
No comments about missing inputs, source documents, generation, confirmation status or how the SOW was written.
Keep undecided matters undecided; never convert a question into an assumption or exclusion to shorten it.
Style examples only, never copy their facts into another project:
- Long: 'Implement comprehensive monitoring covering platform health ... Configure alerting mechanisms ... Establish real-time dashboards ...'
  Concise: 'Configure health monitoring and alerts for the platform and its integrations.'
- Repeated prerequisites: API credentials, API documentation, sandbox credentials for each system.
  Concise: 'Provide API documentation and sandbox access for the agreed integrations.' Keep any unique access constraint.
- Weak assumption: 'The chatbot will include reporting dashboards.' Delete: this is a scope feature.
- Relevant assumption: 'Capacity is based on 500 concurrent sessions.' Retain only if this is an adopted sizing baseline, not an invented value.
- Relevant exclusion: 'Migration to another AI model after acceptance is excluded.' Include only if applicable and compatible with the agreed support scope.

Use British Indian English; preserve official names and exact regulatory language. Preserve source qualifications internally without printing provenance labels. Do not turn optional work into a commitment or select a value to resolve conflicting sources. Scope boundaries follow independently accepted delivery packages, not one deliverable per feature. Preserve POC versus production and build versus support boundaries.
<!-- END_GLOBAL_TEMPLATE_CONTRACT -->

[META_STATIC]
## {PROJECT_TITLE}

Statement of Work - Proof of Concept

Prepared for {COMPANY_NAME}
Prepared by {AUTHOR_NAME}, {AUTHOR_ORG}
{DOCUMENT_DATE} | Version {VERSION}

[META_STATIC_TABLE]
## Table_of_contents

2. Service Agreement
3. About ShellKode
4. About {COMPANY_NAME}
5. Objective
6. Business Benefits
7. Solution Architecture
8. Scope of Work
9. Open Clarifications
10. Out of Scope
11. Customer Dependencies
12. Assumptions
13. Project Timeline
14. Success Criteria
15. AWS Pricing
16. Customer Responsibilities
17. {AUTHOR_ORG_SHORT} Project Team Effort
18. Roles and Responsibilities
19. Change Order
20. Project Plan Termination
21. Contacts and Reporting
22. Marketing Authorization
23. Terms & Conditions
24. Acceptance and Signatories to Statement of Work

[META_GENERATED]
## Service Agreement

This document describes the proposal for engagement to be executed by and between SHELLCODE Private Limited, having its registered office at 10/17, 3rd street Neelikonampalayam, Coimbatore, TamilNadu, India - 641033, hereinafter referred to as “ShellKode” and {COMPANY_NAME}, having its registered office at [address], hereinafter referred to as the “Client”.  This proposal applies to the services described herein and is effective from  (“Effective Date”) and ends by (“Expiration Date”). This proposal is the complete and exclusive agreement between the parties regarding the subject matter of this Agreement and replaces any prior, oral, or written communications, representations, understandings, warranties, promises, covenants, commitments, or agreements between the Parties concerning the subject matter of this Agreement.

[META_STATIC]
## About ShellKode

ShellKode is a cloud-native company with a global presence, delivering services from multiple strategic locations worldwide. We empower organizations to embrace change, accelerate innovation, and unlock holistic business value by placing Cloud and Data at the core of their digital transformation. At ShellKode, we are committed to continuous improvement and innovation, consistently exploring new ways to leverage modern technologies to drive agility, resilience, and long-term success for our customers.

[META_GENERATED]
## About {COMPANY_NAME}

Write exactly two short factual paragraphs about {COMPANY_NAME}: its identity, products and established operations. No bullets, subsection headings or tables. Keep only confirmed company facts; never add project requirements, engagement commentary, invented scale or generic praise. Never pad sparse evidence to fill two paragraphs.

[META_GENERATED]
## Objective

State the solution being delivered, who uses it and its end result. Do not enumerate modules, test evidence, dependencies or controls.
Use concise, plain-English bullets unless the section specifically needs a comparison table. Include only relevant content, not one item per category or module. Keep source-specific commitments and constraints; never invent values to fill a table.

[META_GENERATED]
## Business Benefits

Return only brief one-sentence bullets describing distinct customer, agent or operational outcomes. Merge related benefits instead of listing every feature. No introduction, headings, chunky paragraphs or bold lead-in labels. Do not repeat implementation steps or objectives, discuss pain points, or invent savings, ROI, accuracy or time improvements.

[META_GENERATED]
## Solution Architecture

Normally use 4-6 short design bullets, not one bullet per service or processing step. Keep implementation detail in Scope. Before writing, check the chosen runtime's VPC, subnet, ingress, egress and private-endpoint needs; include necessary deployment decisions without inventing sizing or redundancy. Explain one main flow and only material security/data decisions.

Return short, one-sentence Markdown bullets only, with no opening or closing paragraphs. Explain the main request flow and relevant integration, data, handover and security choices; do not turn each AWS service into its own point. Never join the bullets into flowing prose during review.

The diagram is supplied separately by the diagram generator. Write only the concise solution description here; do not produce ASCII art, Mermaid, diagram code, box drawings or a duplicate text diagram. Explain component interactions, not a service-by-service catalogue table.

After the diagram, use short bullet points to explain how inputs reach the application, are processed and produce outputs. Name relevant AWS services in context, combining related services in the same design point rather than describing each separately. Include deployment, storage, integrations, security and operations only when they explain a material design choice. Preserve agreed choices and distinguish new components from existing systems; do not invent sizing, regions, environments or redundancy. Do not repeat Scope of Work or add generic cloud benefits.
Use concise, plain-English bullets unless the section specifically needs a comparison table. Include only relevant content, not one item per category or module. Keep source-specific commitments and constraints; never invent values to fill a table.

[META_GENERATED]
## Scope of Work

Use the shared architect-generated work breakdown. For multiple deliverables begin with a compact Deliverable / Outcome table, followed by `### Deliverable N - <Name>` and `#### <Module Name>`; for one deliverable omit the wrapper and use `### <Module Name>`. Do not list all modules again in the summary table. Own the implementation commitments. Group related actions under meaningful modules; preserve distinct business rules, interfaces, exceptions and outputs once. Do not add a bullet for each reasoning dimension or a test record for every action.
Reason about inputs, outputs, dependencies and tests internally; do not create separate mini-sections for them. Write short action bullets, not implementation runbooks. Preserve distinct business rules, thresholds, exceptions, interfaces and support boundaries. Cross-cutting setup, logging and testing are stated once, not appended to every module. Never force a fixed number of deliverables, modules or bullets.

[META_GENERATED]
## Open Clarifications

Ask only unresolved decisions that block scope agreement, architecture sizing, price or acceptance. Merge questions about the same decision. API field mappings, survey copy, log schemas, workshop scheduling and implementation tuning belong in discovery, not a contract questionnaire. Do not carry every upstream unknown forward.
Use concise, plain-English bullets unless the section specifically needs a comparison table. Include only relevant content, not one item per category or module. Keep source-specific commitments and constraints; never invent values to fill a table.

[META_GENERATED]
## Out of Scope

State only relevant work outside the agreed deliverables: explicit exclusions or plausible adjacent work that could reasonably be mistaken as included. Check every exclusion against Scope, phase boundaries and Assumptions; never exclude included work or infer exclusion from silence. Do not mirror each scope feature or assumption with its negative. Remove generic absent technologies, hardware and certifications unless genuinely relevant. Keep distinct boundaries separate and remove duplicate exclusions. Post-acceptance model migration is appropriate only when relevant and not already included in agreed support. Use short one-sentence bullets; no quota or filler.
Use concise, plain-English bullets unless the section specifically needs a comparison table. Include only relevant content, not one item per category or module. Keep source-specific commitments and constraints; never invent values to fill a table.

[META_GENERATED]
## Customer Dependencies

Own concrete prerequisites such as integration access and test data. Combine access for related systems in one bullet. Do not create dependency IDs, timing/impact columns or a separate row per credential. Decisions belong in Open Clarifications and ongoing customer duties in Customer Responsibilities.
Use concise, plain-English bullets unless the section specifically needs a comparison table. Include only relevant content, not one item per category or module. Keep source-specific commitments and constraints; never invent values to fill a table.

[META_GENERATED]
## Assumptions

State only material gap-filling delivery premises Shellkode relies on for the agreed work. A premise must identify a project-specific condition whose failure would change delivery effort, design, cost or acceptance, such as usable linked customer data, representative test cases or compatible existing interfaces. Do not turn confirmed features, launch channels, languages, phases or platform choices into assumptions merely to repeat Scope. Use a capacity, format or retention baseline only when evidenced and materially relied upon; never invent quantities or treat model planning guesses as customer agreement. State the condition directly, without saying information was missing or explaining the rationale. Access checklists belong in Dependencies; exclusions belong in Out of Scope. Keep genuinely unresolved material decisions in Open Clarifications. Use short one-sentence bullets with one meaningful bold phrase; no quota or filler.
Use concise, plain-English bullets unless the section specifically needs a comparison table. Include only relevant content, not one item per category or module. Keep source-specific commitments and constraints; never invent values to fill a table.

[META_GENERATED]
## Project Timeline

Follow the user-selected timeline_format; default to table. Output only the selected format.

TABLE FORMAT: One milestone table: Timeframe | Milestone | Outcome. Group related activities. Preserve input dates/durations and leave unsupported timing blank. No additional prose.

GANTT FORMAT: One grid: S.No | Activity | W1 ... Wn (weeks) or M1 ... Mn (months), using only the input schedule's horizon and unit. Concise phase/activity rows; ■ for active delivery cells (light green), ◆ for explicitly included hypercare/support (blue), blank inactive cells. Grey headers. Preserve source-supported overlaps, not invented allocation. Never copy the example's activities or eight-month duration. If timing is unsupported, leave cells blank; without a horizon use a blank Timeframe column. No legend, second table or prose.

[META_GENERATED]
## Success Criteria

Use a minimal Markdown bullet list (normally 3-5 bullets; fewer when evidence supports fewer). Include quantifiable success targets explicitly stated in the BRD/user inputs, preserving the supplied target, unit, baseline and period. Also include descriptive success criteria grounded in explicitly stated functional requirements or required outcomes; when no numerical targets exist, use these observable functional outcomes instead. Each bullet is one short, factual sentence describing what successful delivery demonstrates, not an implementation task or a general benefit. Every criterion must be traceable to the BRD/user inputs; never derive commitments from proposed architecture, templates, industry norms or assumptions. Do not infer targets from workload volumes or architecture sizing. Do not invent percentages, baselines, SLAs, test counts, performance guarantees, acceptance processes or X% placeholders. Preserve conditions, exclusions and phase boundaries; do not turn optional/future requirements into current commitments. Deduplicate outcomes and do not repeat a descriptive equivalent of the same quantitative criterion. No tables, paragraphs, introductory labels or source/meta commentary. If neither quantitative targets nor supported functional outcomes exist, leave the section body blank without commentary.

[META_TABLE]
## AWS Pricing

PURPOSE
Use tables only, with no paragraphs before, between or after them. Start with the monthly cost table. Put AWS region, material sizing metrics, planning range and estimate qualifications in a second compact Pricing basis | Details table.

| Item | Monthly (<actual currency>) | Estimate |
|---|---:|---|
| <supported workload or environment> | <amount or blank> | <linked AWS Pricing Calculator or planning estimate label> |

Use only supported workload/environment rows; do not invent separate POC and production estimates or divide an aggregate estimate between environments.
Put the genuine calculator estimate hyperlink in the Estimate cell. Never label a homepage link as an estimate.
Keep only the few material business sizing assumptions as table rows; no prose notes, generic ten-row volume checklist, repeated MRR/ARR totals or service-request details.
Keep fallback figures explicitly labelled as non-binding planning estimates, not calculator quotes. Partial calculator totals must be labelled as components only, never whole-workload totals.
Leave unavailable prices blank. Do not mention missing inputs, pending confirmation, source documents or the generation process.
Preserve the calculated currency and values. Never copy pricing, dates, throughput, funding claims or commercial commitments from a reference SOW.

[META_GENERATED]
## Customer Responsibilities

Keep access and test-material prerequisites in Customer Dependencies. Combine customer design decisions, business acceptance, content ownership and live-agent operations into distinct duties without repeating the integration inventory. Existing staffing figures do not authorise a UAT staffing commitment.

Return only brief one-sentence customer duties. Combine related approvals, UAT participation and operational ownership. Do not repeat Dependencies, list every system, enumerate tests or add a discovery questionnaire. No introduction, subsection headings, invented response deadlines or staffing commitments.
Use concise, plain-English bullets unless the section specifically needs a comparison table. Include only relevant content, not one item per category or module. Keep source-specific commitments and constraints; never invent values to fill a table.

[META_TABLE]
## {AUTHOR_ORG_SHORT} Project Team Effort

Show the compact resource/count/effort table only. Do not narrate each role or invent counts or durations. Leave unavailable numeric cells blank.
Use concise, plain-English bullets unless the section specifically needs a comparison table. Include only relevant content, not one item per category or module. Keep source-specific commitments and constraints; never invent values to fill a table.

[META_TABLE]
## Roles and Responsibilities

Aim for 5-8 delivery-stage rows, not a feature inventory. Combine related implementation work with the same ownership; keep client business acceptance separate from Shellkode technical testing. No legend.

Both party columns must contain only R/A/C/I codes (for example RA and CI), never duty descriptions. Cover delivery workstreams, not individual systems or features; do not add migration or other excluded work. Keep business acceptance separate from technical implementation because ownership differs.

Return exactly one Markdown table with columns Workstream | Shellkode | {COMPANY_NAME}, with no legend, code definitions, introduction or closing paragraph. Use combined codes such as RA, CI, RAC or I, not individual job-role columns. Group work by distinct accountability boundaries (design, build/integrate, customer prerequisites, technical testing, business acceptance, handover and included support); merge rows when both parties have the same responsibilities, while keeping distinct acceptance ownership; do not make a row for each module, integration, feature or security control. Shellkode normally owns design, implementation and technical testing (RA), with the client consulted/informed (CI). The client owns business acceptance, access provision and policy approval where applicable; reflect Shellkode's support in those rows. Separate implementation from acceptance only when accountability differs. Do not assign the client CI for every activity or invent responsibilities. No extra tables or commentary.

[META_STATIC]
## Change Order

Changes to project scope, incorrect assumptions, or missing prerequisites may affect cost, resources, or scheduling. Other circumstances may arise beyond ShellKode’s control that may cause it to be unable to accomplish the project objectives and would require a modification to this proposal. Any such modification shall be memorialized in a mutually executed change order that details material changes to staff requirements, deliverables, fees, and milestones, as applicable. If the parties do not agree to such a proposed change order, then either may suspend the Services to allow time for the parties to agree on an alternative change order. Should Services be suspended for a consecutive period of five (5) business days, either party may thereafter terminate this proposal immediately upon notice
[META_STATIC]
## Project Plan Termination

Upon termination of this Project Plan executed in accordance with the terms of the Agreement, Client shall pay ShellKode for any Customer-approved Services performed and expenses incurred up to the date of the termination and any expenses necessarily and reasonably incurred by ShellKode in terminating Customer-approved obligations to third parties.

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
## Marketing Authorization

Upon successful completion of the project, Customer agrees to provide a reference for ShellKode for services provided under this SOW. ShellKode agrees to follow the Customer’s terms and conditions for the use of such reference and the Customer’s name and logo.

[META_STATIC]
## Terms & Conditions

### Change Management:

It may become necessary to amend this Statement of Work for reasons including, but not limited to: changes to the Project Schedule, Scope or Budget; changes in key {COMPANY_NAME} stakeholders assigned to the project; or changes in {COMPANY_NAME} priorities (external or internal to the project) that impact the project.

In the event a change is necessary, the following process will be followed:

A Project Change Request (PCR), raised by e-mail or support ticket, will be used to communicate the change.

The PCR must describe the change, the reasons for it, and its effect on the project, including scheduling and pricing impact.

Any such change shall be formally communicated to ShellKode by {COMPANY_NAME} and carried out subject to mutually agreed terms.

Scope changes in Design, Implementation, Testing or Managed Services will be mutually understood and agreed; changes proposed by {COMPANY_NAME} beyond the scope defined in this agreement may be charged in addition to the price under the Commercial section, upon mutual agreement. 

### Jurisdiction

This Agreement shall be governed and interpreted in accordance with the laws of India and courts at Bangalore shall have the exclusive jurisdiction to decide upon any dispute or litigation between the Parties to this Agreement.

### Travel

Any Travel expenses for travel outside Bangalore the cost of travel on actuals will be reimbursed by the {COMPANY_NAME}. The travel cost will include Flight Tickets, Boarding/ Lodging, Food, Cabs etc. 

### Working hours

Standard work hours are 10 am - 07 pm IST Monday to Friday. 

If the resource has to be summoned before or after the specified business hour prior notice is to be issued.

### Third-Party & Platform SLAs

The SLAs of cloud services and any third-party platforms leveraged for this engagement (including AWS Bedrock, ElevenLabs, and (Telephone to be confirmed with customers)) are governed and owned by the respective platform provider directly, and not by ShellKode.

### Effort & Scope

The effort estimate is limited to the understood scope of work as defined in this Statement of Work. Any substantial change in scope may lead to a corresponding change in commercials and effort, to be mutually agreed in writing per Section 18.1.

### Indemnification

The indemnification obligations set forth in this Section shall be the parties' exclusive rights and remedies with respect to this Agreement.

Indemnity by {COMPANY_NAME}: {COMPANY_NAME} shall indemnify and hold harmless ShellKode, its affiliates, and each of their respective officers, directors, members, agents and employees from and against any and all claims, demands, liabilities, obligations, losses, damages, penalties and fines of any kind and nature whatsoever (including reasonable attorneys' fees) brought by a third party under any theory of legal liability arising out of or related to: (i) the actual or alleged use of the Services in violation of this Agreement or applicable law, or (ii) any breach by {COMPANY_NAME} of its obligations under this Agreement.

Reciprocal Indemnification: Each party shall indemnify and hold harmless the other party, its affiliates, and each of their respective officers, directors, members, agents and employees from and against any and all claims, demands, liabilities, obligations, losses, damages, penalties and fines of any kind and nature whatsoever (including reasonable attorneys' fees) brought by a third party under any theory of legal liability arising out of or related to the indemnifying party's actual or alleged: (i) gross negligence, (ii) willful misconduct, or (iii) infringement or misappropriation of a third party's copyright, trade secret, patent, trademark or other intellectual property right.

### Termination

This Agreement will be in effect from the date of signing until completion of the implementation phase and expiry of the associated AMC term, unless terminated earlier in accordance with this Section. This Agreement may be terminated on the occurrence of any of the events below:

Either party commits breach of any provision of this Agreement or fails to perform any obligation under it, and the party alleged to have committed such breach or failed in performance is served thirty (30) days' notice in writing by the other party.

Either party may terminate this Agreement — for Consulting/Implementation, upon written notice of thirty (30) days to the other party; for Managed Services (if applicable), upon written notice of sixty (60) days to the other party. The duties of non-disclosure set forth herein shall continue during the term of this Agreement and shall survive for a period of one (1) year from termination or expiry of this Agreement.

On termination for whatever reason, {COMPANY_NAME} will be responsible for all fees payable to ShellKode and all expenses incurred by ShellKode on behalf of {COMPANY_NAME} up to the date termination takes effect.

### Confidentiality

This proposal contains proprietary and confidential information of ShellKode and shall not be used, disclosed, or reproduced, in whole or in part, for any purpose other than to evaluate this proposal, without the prior written consent of authorized ShellKode personnel. All information contained herein remains at all times the property of ShellKode.

[META_STATIC_TABLE]
## Acceptance and Signatories to Statement of Work

"Client" verifies that the terms of this Statement of Work/Proposal and Service Level Agreements are acceptable. The parties hereto are each, acting with proper authority by their respective companies.IN WITNESS WHEREOF, {AUTHOR_ORG_SHORT} and Client have executed this SOW on the Execution Date.

| {AUTHOR_ORG_SHORT} | {COMPANY_NAME_SHORT} |
|--------------------|----------------------|
| Name: | Name: |
| Title: | Title: |
| Signature: | Signature: |
| Date of acceptance: | Date of acceptance: |
