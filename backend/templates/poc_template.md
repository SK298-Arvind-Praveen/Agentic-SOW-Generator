[META_STATIC]
## {PROJECT_TITLE}

{COMPANY_NAME}

Prepared by: {AUTHOR_NAME}
{DOCUMENT_DATE} [Version {VERSION}]
{AUTHOR_ORG}


[META_STATIC_TABLE]
## Table_of_contents

1. About {AUTHOR_ORG_SHORT}
2. About {COMPANY_NAME}
3. Project Overview
4. Scope of Work
5. Architecture Diagram
6. Customer Dependencies
7. Assumptions
8. Out Of Scope
9. Timelines and Deliverables
10. AWS Pricing
11. Customer Responsibilities
12. Duration of Work
13. Shellkode Implementation Cost
14. Success Criteria
15. Deliverable Acceptance
16. Change Order
17. Project Plan Termination
18. Contacts and Reporting
19. Marketing Authorization
20. Terms & Conditions
21. Acceptance and Signatories to Statement of Work


[META_HYBRID_company_research]
## About {AUTHOR_ORG_SHORT}

{AUTHOR_ORG_DESCRIPTION}


[META_HYBRID_company_research]
## About {COMPANY_NAME}

{COMPANY_DESCRIPTION}


[META_GENERATED]
## Project Overview

Using the project objective and objective_analysis, write EXACTLY 3 sentences:

Sentence 1 — State the specific business problem being solved and why it is urgent for {COMPANY_NAME}.

Sentence 2 — Describe what the POC system does, naming the core AI/ML capability and primary workflow.

Sentence 3 — State ONE measurable outcome the POC will validate with a concrete metric.

RULES:
- Total length: 40–60 words maximum
- One paragraph, no bullet points
- No marketing language
- Keep concise and focused


[META_GENERATED]
## Scope of Work

Generate focused Scope of Work based on objective_analysis fields.
Keep each section concise with clear bullet points.

BULLET COUNT PER SECTION (based on complexity_context.level):
- simple → 2 bullets per section
- moderate → 3 bullets per section
- complex → 3 bullets per section (reduced from 4)
- enterprise → 4 bullets per section (reduced from 4-5)

STRUCTURE (use these titles in order):

### Backend & API Implementation
Brief description (1-2 sentences) + bullets per complexity count

### User Interaction Layer
← conditional: only if ui_required=true OR complexity=complex/enterprise
Brief description (1-2 sentences) + bullets per complexity count

### Infrastructure & Environment Setup
Brief description (1-2 sentences) + bullets per complexity count

### Data Processing & AI Integration
Brief description (1-2 sentences) + bullets per complexity count

### Testing, Validation & Deployment
Brief description (1-2 sentences) + bullets per complexity count

FORMATTING RULES:
- Each section: 1-2 sentence intro + bullet points
- Each bullet: 1-2 lines maximum, specific and actionable
- Use bullet symbol "•"
- Reference specific AWS services and measurable deliverables
- **CRITICAL: Do NOT add numbers (1., 2., 3., etc.) before subsection titles. Use only the title text.**


[META_GENERATED]
## Architecture Diagram

### Overview

Using objective_analysis.aws_services, deployment_environment, integration_details,
security_requirements, and complexity_context, write a 3–4 sentence paragraph:

Sentence 1 — Describe the architecture pattern chosen (serverless-first if deployment_environment
             is serverless, containerized if ecs/eks detected, etc.) and name the primary
             AWS region for deployment.

Sentence 2 — Describe the core data flow referencing the actual workflow_steps from the
             objective analysis (e.g., "Documents are ingested via S3, processed by Lambda,
             enriched by Bedrock, and results stored in DynamoDB").

Sentence 3 — State which architectural alternative was intentionally avoided and why
             (e.g., "EC2-based hosting was avoided in favour of serverless Lambda to eliminate
             instance management overhead for POC scale"; or "monolithic deployment was
             rejected in favour of microservices to allow independent scaling of the AI layer").

Sentence 4 — If compliance_requirements is non-empty, describe the security boundary
             (VPC, KMS encryption, CloudTrail logging). If empty, describe the cost
             optimisation approach instead (S3 Intelligent Tiering, Lambda pay-per-use, etc.).

RULES:
- Name specific AWS services from objective_analysis.aws_services only
- Do not introduce services not in the analysis
- Professional, justification-driven tone; no marketing language
- If ui_required=true, mention CloudFront or API Gateway as the edge layer


[META_GENERATED]
## Customer Dependencies

Generate concise dependencies based on objective_analysis.
Keep content focused and avoid excessive detail.

1. Technical Environment:
   - AWS Console and programmatic access with appropriate permissions
   - IAM role configured with least-privilege access for project resources
   - Network connectivity to AWS services from customer environment

2. Dataset Access:
   - Data volume: {data_volume_description if available, else "Approximately {data_volume_gb} GB total for POC implementation"}
   - Format requirements: Customer to provide data in machine-readable format
   - Access permissions: Customer to grant necessary data access permissions before project initiation

RULES:
- Use specific numbers from data_characteristics when available
- If compliance_requirements non-empty, add: "Customer to confirm data classification and applicable compliance framework"
- Keep all points concise and actionable


[META_GENERATED]
## Assumptions

Generate assumption statements as a simple bullet list only. Do not use tables, grouped headings, or subsection headings.

OUTPUT FORMAT:
- Start directly with bullet points.
- Use the bullet symbol "•".
- Do not include ### headings.
- Do not group assumptions by category.
- Each bullet must be one complete assumption statement.
- Each bullet may be 1–2 sentences if needed for clarity.

MANDATORY RULES:
- Generate 8–12 bullets total.
- Every bullet must be derived from objective_analysis.
- Use real values from objective_analysis such as:
  - data_characteristics.format
  - data_volume_description or data_volume_gb
  - workflow_steps
  - aws_services
  - deployment_environment
  - integration_details
  - compliance_requirements
  - security_requirements
  - concurrent_users
  - primary_personas
  - duration_weeks or timeline
  - success_metrics
- At least 3 bullets must clearly assign responsibility to the Customer.
- At least 1 bullet must mention Shellkode responsibility.
- At least 2 bullets must describe impact if the assumption is not met.
- Include customer review/sign-off timeline using _feedback_sla_days.
- Include AWS access/environment assumption using _access_provision_weeks and aws_services.
- Include data quality and data format assumptions if data_characteristics is available.
- Include integration access assumptions only if integration_details is non-empty.
- Include compliance/security approval assumptions only if compliance_requirements or security_requirements is non-empty.
- Do not duplicate Out of Scope items.
- Do not use generic statements such as “all required information will be provided.”
- Do not use placeholder text.
- Do not include explanations before or after the bullet list.

STYLE RULES:
- Write in formal SOW language.
- Keep the tone contractual but readable.
- Avoid marketing language.
- Use concrete timelines, data volumes, services, metrics, and responsibilities wherever available.
- Prefer wording such as:
  “The Customer will…”
  “Shellkode will…”
  “Any deviation from… may impact…”
  “The provided AWS environment will…”

[META_GENERATED]
## Out of Scope

Generate grouped out-of-scope items based on objective_analysis.

OUTPUT FORMAT:
Use grouped headings and bullets.

GROUPS:
### Functional Exclusions
### Technical Exclusions
### Data Exclusions
### Integration Exclusions
### Operational Exclusions
### Commercial Exclusions

CONDITIONAL RULES:
- Include Functional Exclusions only if ui_required=true or workflow_steps contains user-facing workflow.
- Include Technical Exclusions for all projects.
- Include Data Exclusions if data_characteristics or data_volume_gb is available.
- Include Integration Exclusions only if integration_details is empty OR additional integrations are likely.
- Include Operational Exclusions for production, support, or deployment projects.
- Include Commercial Exclusions for all projects.

MANDATORY ITEMS:
- Exclude work beyond agreed workflow_steps.
- Exclude processing beyond stated data_characteristics and data_volume_gb.
- Exclude performance testing beyond {concurrent_users} concurrent users.
- Exclude additional AWS services not listed in objective_analysis.aws_services unless approved through Change Management.
- Exclude additional third-party integrations beyond integration_details.
- Exclude production support unless support_required=true or Day-2 Operations is included.
- Exclude compliance certification unless explicitly listed in compliance_requirements.
- Exclude staff training and detailed end-user documentation unless explicitly in scope.

AI/ML CONDITIONAL:
- If aws_services contains Bedrock or SageMaker:
  include “Model fine-tuning, retraining, or custom model development is excluded unless explicitly stated in scope.”
- Else:
  include “Custom AI model development outside the agreed managed service approach is excluded.”

UI CONDITIONAL:
- If ui_required=true:
  include “Native mobile application development is excluded.”
- If ui_required=false:
  include “Frontend, web portal, dashboard, or user interface development is excluded.”

FORMAT RULES:
- 8–12 bullets total.
- Each bullet must be one sentence.
- No vague wording.
- Do not use legal-heavy language.


[META_TABLE]
## Timelines and Deliverables

Generate a two-column timeline table.

TABLE FORMAT:
| Timeframe | Milestones |
|----------|------------|
| Week 1 | **{Use-case-specific milestone title}**<br>• {Point 1}<br>• {Point 2}<br>• {Point 3}<br>• {Point 4} |

RULES:
- Use only two columns: Timeframe and Milestones.
- Each Milestones cell must start with one bold use-case-specific subtopic title.
- Under each title, include exactly 3–4 bullet points.
- Use <br> between the title and each bullet.
- Do not use paragraph text before or after the table.
- Do not use old columns: Duration, Phase, Deliverables.
- Do not use generic titles like “Feature Implementation” unless no better use-case-specific title exists.
- Bullet points must be concise and specific to workflow_steps, key_features, aws_services, integrations, data_characteristics, and success_metrics.
- Each bullet must be concise, preferably under 20 words.
- Avoid long bullets over 20 words.
- Do not include raw markdown headings inside the table.

TIMELINE RULES:
- If duration_weeks is specified, use that exact number of weeks.
- If timeline is specified, derive the exact week count from it.
- If neither duration_weeks nor timeline is specified, use complexity-based duration.
- Cover all weeks from Week 1 to the final week with no gaps or overlaps.
- Use "Week X" for single-week milestones.
- Use "Week X-Y" only when one milestone spans multiple weeks.

[META_TABLE]
## AWS Pricing

Generate realistic AWS MRR based on objective_analysis.aws_services, data_volume_gb,
concurrent_users, and complexity_context.level.

MRR ESTIMATION GUIDELINES:
- simple + low data volume: $200–$500/month
- moderate + medium data volume: $500–$1,500/month
- complex + high data volume: $1,500–$5,000/month
- enterprise + very high data volume: $5,000–$15,000/month
- Add $50–$200/month if ui_required=true (CloudFront, WAF)
- Add $100–$500/month per major integration in integration_details

| Item | MRR in USD |
|------|------------|
| AWS Pricing Calculator | {MRR} |
| AWS MRR | {MRR} |
| AWS ARR | {ARR} |

RULES:
- ARR = MRR × 12
- Use a single realistic number (not a range) for MRR
- Do NOT itemise individual service costs in the table
- Preserve table structure exactly


[META_STATIC]
## Customer Responsibilities

• Designate and provide access throughout the project to the Customer individuals serving in project support roles, including the project sponsor and stakeholders, each having suitable skills, experience knowledge, capacity, and subject matter expertise for their role.
• Provide promptly such information, documentation, decisions, approvals, and assistance as requested or necessary for ShellKode's performance and maintenance of project cadence.
• Customer and ShellKode will make every effort to leverage best practices and technologies as needed for effective remote project delivery.
• Provide complete, accurate, and current information and update it promptly and continuously as necessary during the course of the engagement.
• Assume responsibility for any delays, additional costs, or other liabilities caused by or associated with any deficiencies in (i) discharging the Customer Responsibilities, and (ii) the Assumptions.
• Provide subject matter expertise in regard to source systems and other components.
• Provide necessary environments for development, testing, and production.
• Ensure the use and procurement of appropriate licenses(if applicable).


[META_STATIC]
## Duration of Work

Services under this scope of work are expected to begin on {START_DATE} and end no later than {END_DATE}.

Changes to the scope of the Services shall be mutually agreed to in writing between {COMPANY_NAME_SHORT} and {AUTHOR_ORG_SHORT}. Changes to project scope, assumptions, etc. may have cost, resource, or timeline implications. All changes will be documented in a mutually agreed-upon Change Order, as per the agreed terms and conditions.


[META_TABLE]
## Shellkode Implementation Cost

Generate resource allocation based on complexity_context.level and the timeline duration
determined in Timelines and Deliverables. Effort/Week MUST match the total project duration.

RESOURCE ALLOCATION RULES (apply based on complexity_context.level):
- simple: 1× AIML Engineer only; Solution Architect oversight 1–2 weeks
- moderate: 1× AIML Engineer + 1× Sr AIML Engineer; Solution Architect oversight 2–3 weeks
- complex: 1× AIML Engineer + 1× Sr AIML Engineer; Solution Architect involvement 3–4 weeks
- enterprise: 2× AIML Engineers + 1× Sr AIML Engineer; Solution Architect full engagement

ADD frontend resource ONLY if ui_required=true:
- simple + ui: add 1× Frontend Developer at same duration
- moderate/complex/enterprise + ui: add 1× Sr Frontend Developer at same duration

Effort/Week must equal the total weeks from the Timelines section (not a generic number).

| Resource | Effort/Week | Pricing (INR) |
|----------|-------------|---------------|
| AIML Engineer | {total_weeks} weeks | AWS Funded |
| Sr AIML Engineer | {total_weeks} weeks | AWS Funded |
| Solution Architect | {oversight_weeks} weeks | AWS Funded |
| Frontend Developer | {total_weeks} weeks | AWS Funded |

RULES:
- Only 4 resource types: AIML Engineer, Sr AIML Engineer, Solution Architect, Frontend Developer
- Add Frontend Developer row ONLY if ui_required=true (use "Frontend Developer" for simple, "Sr Frontend Developer" for others)
- Omit Sr AIML Engineer row for simple projects
- Pricing column always shows "AWS Funded" for all rows
- Effort/Week must be a specific number matching the project timeline


[META_GENERATED]
## Success Criteria

Generate success criteria as a simple bullet list only. Do not use tables, grouped headings, or subsection headings.

OUTPUT FORMAT:
- Start directly with bullet points.
- Use the bullet symbol "•".
- Do not include ### headings.
- Do not group success criteria by category.
- Each bullet must describe one measurable or clearly testable success condition.
- Each bullet may be 1–2 sentences if needed for clarity.

MANDATORY RULES:
- Generate 5–8 bullets for POC.
- Generate 7–10 bullets for production.
- Every bullet must contain a measurable or clearly testable target.
- Every success criterion must be verifiable through at least one of:
  - UAT execution
  - test reports
  - benchmark dataset comparison
  - processing logs
  - monitoring reports
  - accuracy reports
  - stakeholder sign-off
- Include one workflow completion metric.
- Include one processing success metric.
- Include one performance metric.
- Include one availability or reliability metric.
- Include one acceptance/sign-off metric.
- Include AI/ML accuracy only if aws_services contains Bedrock, SageMaker, Textract, Comprehend, Rekognition, or another AI/ML capability.
- Include integration success only if integration_details is non-empty.
- Include user acceptance only if ui_required=true or primary_personas is non-empty.
- Include security/compliance validation only if compliance_requirements or security_requirements is non-empty.
- Do not use vague phrases such as:
  “system works as expected”
  “improved performance”
  “better user experience”
  “successful implementation”
- Do not invent unrelated KPIs.
- Do not include explanations before or after the bullet list.

ACCURACY TARGETS:
- POC simple: ≥85%
- POC moderate: ≥90%
- POC complex: ≥95%
- POC enterprise: ≥99%
- Production simple: ≥90%
- Production moderate: ≥93%
- Production complex: ≥97%
- Production enterprise: ≥99.5%

PERFORMANCE TARGET:
Use concurrent_users from objective_analysis.
If latency is available in performance_requirements, use it.
If latency is not available:
- simple: p95 response time below 5 seconds
- moderate: p95 response time below 3 seconds
- complex: p95 response time below 2 seconds
- enterprise: p95 response time below 1 second

AVAILABILITY TARGET:
- POC: system availability ≥99% during the validation window.
- Production: system availability ≥99.9% during production readiness or agreed monitoring window.

STYLE RULES:
- Write in formal SOW language.
- Use concrete numbers from objective_analysis wherever available.
- Reference validation method inside the bullet itself.
- Keep each bullet concise and acceptance-oriented.


[META_STATIC]
## Deliverable Acceptance

Customers will notify {AUTHOR_ORG_SHORT} in writing within ten (10) calendar days of receiving a Deliverable whether it accepts or rejects that Deliverable. If no notification is delivered to ShellKode within this period, the Deliverable will be considered accepted. As a time and materials engagement, changes to a rejected Deliverable constitute billable project time unless the parties determine that such Deliverable was not performed in accordance with good commercial practices.


[META_STATIC]
## Project Plan Termination

Upon termination of this Project Plan executed in accordance with the terms of the Agreement, Customer shall pay {AUTHOR_ORG_SHORT} for any Customer-approved Services performed and expenses incurred up to the date of the termination and any expenses necessarily and reasonably incurred by AWS Partner in terminating Customer-approved obligations to third parties.


[META_STATIC]
## Change Order

Changes to project scope, incorrect assumptions, or missing prerequisites may affect cost, resources, or scheduling. Other circumstances may arise beyond {AUTHOR_ORG_SHORT}'s control that may cause it to be unable to accomplish the project objectives and would require a modification to this proposal. Any such modification shall be memorialized in a mutually executed change order that details material changes to staff requirements, deliverables, fees, and milestones, as applicable. If the parties do not agree to such a proposed change order, then either may suspend the Services to allow time for the parties to agree on an alternative change order. Should Services be suspended for a consecutive period of five (5) business days, either party may thereafter terminate this proposal immediately upon notice.


[META_STATIC_TABLE]
## Contacts and Reporting

| Name | Title | Email | Phone |
|------|-------|-------|-------|
| Bala | Delivery Head | bala@shellkode.com | +91 95389 16855  |
| Bakrudeen K | AI/ML Practice Head | bakrudeen.k@shellkode.com | +91 78454 06910  |
| Suman Perumal | Solution Architect | suman.p@shellkode.com | +91 97382 41191  |
| Velmurugan S | Delivery Manager | vel@shellkode.com | +91 99946 07336  |


[META_STATIC]
## Marketing Authorization

Upon successful completion of the project, Customer agrees to provide a reference for {AUTHOR_ORG_SHORT} for services provided under this SOW. {AUTHOR_ORG_SHORT} agrees to follow the Customer's terms and conditions for the use of such reference and the Customer's name and logo.


[META_STATIC]
## Terms & Conditions

• Working hours
  ○ Standard work hours are 10 am - 07 pm IST Monday to Friday.
  ○ If the resource has to be summoned before or after the specified business hour prior notice is to be issued.
  ○ However, the above statement is not applicable during the production release cycle/P1 issues.
• The SLAs of Cloud services are governed and owned by Cloud Platform directly.
• The effort estimate is limited to the understood scope of work. Any substantial change in the scope may lead to the enhancement in the commercials and effort.
• Changes to the scope of the services shall be mutually agreed to in writing between Customer and {AUTHOR_ORG_SHORT}. Changes to project scope, assumptions, etc. may have cost, resource, or timeline implications.
• The client may terminate this agreement or ramp down resources with or without cause upon thirty (30) days written notice to {AUTHOR_ORG_SHORT}.
• The client will provide feedback on the deliverables submitted by the {AUTHOR_ORG_SHORT} team at the earliest During the above-mentioned period, {AUTHOR_ORG_SHORT} resources will be reporting to the Customer directly & his/her work and deliverables are tracked and managed by the Customer. This proposal contains proprietary and confidential information of {AUTHOR_ORG_SHORT} Proprietor and shall not be used, disclosed, or reproduced, in whole or in part, for any purpose other than to evaluate this proposal, without the prior written consent of authorized {AUTHOR_ORG_SHORT} personnel in and to this document and all information contained herein remains at all times in {AUTHOR_ORG_SHORT}.


[META_STATIC_TABLE]
## Acceptance and Signatories to Statement of Work

"Client" verifies that the terms of this Statement of Work/Proposal and Service Level Agreements are acceptable. The parties hereto are each, acting with proper authority by their respective companies.IN WITNESS WHEREOF, {AUTHOR_ORG_SHORT} and Client have executed this SOW on the Execution Date.

| {AUTHOR_ORG_SHORT} | {COMPANY_NAME_SHORT} |
|--------------------|----------------------|
| Signature  | Signature  |


| Bhuvanesh CTO | XXX |


| Date of acceptance: | Date of acceptance: |