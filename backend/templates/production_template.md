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
5. Technical Specifications & System Design
6. Architecture & Integrations
7. Customer Dependencies
8. Assumptions
9. Out of Scope
10. Timelines and Deliverables
11. Customer Responsibilities
12. Duration of Work
13. AWS Pricing
14. Shellkode Implementation Cost
15. Success Criteria
16. Day-2 Operations & Support
17. Deliverable Acceptance
18. Change Management
19. Project Plan Termination
20. Contacts and Reporting
21. Marketing Authorization
22. Terms & Conditions
23. Acceptance and Signatories to Statement of Work


[META_HYBRID_company_research]
## About {AUTHOR_ORG_SHORT}

{AUTHOR_ORG_DESCRIPTION}


[META_HYBRID_company_research]
## About {COMPANY_NAME}

{COMPANY_DESCRIPTION}


[META_GENERATED]
## Project Overview

Generate a concise project overview based on objective_analysis fields.
Keep content focused and use bullet points instead of dense paragraphs.

### Solution Overview

Write EXACTLY ONE paragraph of 2-3 sentences:
- Sentence 1: Describe the production-grade platform and the specific business problem it solves
- Sentence 2: Name the core AI/ML capabilities and primary workflow
- Sentence 3: State the production-readiness commitment with key metrics

RULES: Must call it a "production-grade platform". No marketing language. Keep concise.

### Business Objectives

Generate {bullet_count} focused bullet points using ● where:
- simple complexity → 3 bullets
- moderate complexity → 4 bullets  
- complex/enterprise complexity → 4 bullets (reduced from 5)

Each bullet must be ONE clear business outcome in 1-2 lines maximum.

### Technical Objectives

Generate {bullet_count} focused bullet points using ● where:
- simple → 3 bullets with 1 numeric target
- moderate → 4 bullets with 2 numeric targets
- complex → 4 bullets with 2 numeric targets (reduced from 5)
- enterprise → 5 bullets with 3 numeric targets (reduced from 6)

Each bullet must be ONE clear technical objective in 1-2 lines maximum.

### End-State Vision

Write ONE paragraph (2-3 sentences) followed by {bullet_count} capability bullets using ●:
- simple → 3 bullets
- moderate → 3 bullets (reduced from 3-4)
- complex/enterprise → 4 bullets (reduced from 4-5)

Keep paragraph concise. Each bullet must be 1-2 lines maximum.


[META_GENERATED]
## Scope of Work

Generate a focused Scope of Work for PRODUCTION DEPLOYMENT based on objective_analysis fields.
Keep each section concise with clear bullet points instead of dense paragraphs.

BULLET COUNT PER SECTION (based on complexity_context.level):
- simple → 3 bullets (minimum viable production)
- moderate → 3 bullets (standard)
- complex → 4 bullets (enhanced)
- enterprise → 4 bullets (comprehensive, reduced from 4-5)

SECTION TITLES (preserve order, apply conditional naming):

### Application & Backend Implementation
Brief description (1-2 sentences) + bullets per complexity count

### User Access & Interaction Layer
← or "API & Service Integration Layer" if ui_required=false
Brief description (1-2 sentences) + bullets per complexity count

### Infrastructure, Scalability & Operations  
Brief description (1-2 sentences) + bullets per complexity count

### Data Processing & AI Capabilities
Brief description (1-2 sentences) + bullets per complexity count

### Testing, Go-Live & Production Readiness
Brief description (1-2 sentences) + bullets per complexity count

FORMATTING RULES:
- Each section: 1-2 sentence intro + bullet points
- Each bullet: 1-2 lines maximum, specific and actionable
- Use bullet symbol "•"
- Reference specific AWS services and measurable deliverables
- No verbose explanations or sub-bullets
- **CRITICAL: Do NOT add numbers (1., 2., 3., etc.) before subsection titles. Use only the title text.**


[META_GENERATED]
## Technical Specifications & System Design

Generate a concise technical overview based on objective_analysis fields.
Keep each subsection to 2-3 sentences maximum to prevent truncation.

### System Architecture Overview

Describe the overall system architecture in 2-3 sentences:
- Core processing approach (derive from workflow_steps and aws_services)
- Data flow pattern (reference key AWS services from aws_services list)
- Deployment model (reference deployment_environment: serverless/containerized/hybrid)

### Data Processing & Storage

Describe data handling in 2-3 sentences:
- Data formats and volume (use data_characteristics.format and data_volume_description)
- Storage strategy (reference S3, DynamoDB, or RDS from aws_services)
- Processing approach (reference Lambda, Bedrock, or other processing services from aws_services)

### User Access & Interface

Describe user interaction in 2-3 sentences:
- Access method (API-based if ui_required=false, web interface if ui_required=true)
- User roles (reference primary_personas if available)
- Authentication approach (reference IAM or Cognito from aws_services)

### Performance & Scalability

Describe performance characteristics in 2-3 sentences:
- Concurrent user capacity (use concurrent_users from objective_analysis)
- Scaling approach (auto-scaling for serverless, manual scaling for others)
- Availability target (99.9% uptime for production systems)

### Security & Compliance

Describe security measures in 2-3 sentences:
- Data encryption (at rest and in transit using AWS managed services)
- Access controls (IAM roles and policies)
- Compliance framework (reference compliance_requirements if non-empty, else "standard AWS security practices")

### Integration & Monitoring

Describe system integration in 2-3 sentences:
- External integrations (reference integration_details if non-empty, else "internal services only")
- Monitoring approach (CloudWatch and CloudTrail from aws_services)
- Logging strategy (application and infrastructure logs)


[META_GENERATED]
## Architecture & Integrations

Generate based on objective_analysis.aws_services, deployment_environment,
integration_details, compliance_requirements, and complexity_context.

1. Overview paragraph (3–4 sentences):
   - Sentence 1: Describe the multi-AZ, high-availability architecture for {COMPANY_NAME}
     naming the primary AWS region and deployment pattern (serverless/containerised/EC2)
   - Sentence 2: Describe the VPC design (public/private subnets, NAT Gateway)
     ONLY if deployment_environment is NOT serverless; if serverless, describe the
     API Gateway → Lambda → data store flow instead
   - Sentence 3: Reference security layers — include WAF and Shield ONLY for
     complex/enterprise or if ui_required=true; always include Security Groups and IAM
   - Sentence 4: Reference CloudWatch, CloudTrail, and any compliance services (Config,
     GuardDuty, Macie) ONLY if they appear in aws_services

2. Deployment Topology (3 bullets):
   • Multi-AZ: describe AZ spread for the primary compute service from aws_services
     (Lambda=implicit multi-AZ; ECS/EKS=explicit AZ placement; EC2=ASG multi-AZ)
   • VPC Design: public/private subnet split ONLY if deployment_environment uses VPC;
     for pure serverless, describe endpoint isolation instead
   • Security Layers: list ONLY security services present in aws_services
     (WAF, Shield, Security Groups, GuardDuty, KMS, Macie, etc.)

3. Integration Points (conditional — include category ONLY if data exists):
   • Third-party APIs → include ONLY if integration_details contains api_integrations
     or third_party_services; list specific systems from integration_details
   • Legacy Systems → include ONLY if integration_details contains legacy_systems;
     describe migration or coexistence approach
   • Data Sources → include ONLY if data_characteristics.access_pattern is non-empty;
     describe ingestion mechanism
   If ALL three are empty → replace with "Internal Service Communication" describing
   the event-driven or synchronous service-to-service patterns within the platform


[META_GENERATED]
## Customer Dependencies

Generate concise dependencies and responsibilities based on objective_analysis.
Keep all content concise and avoid overly detailed sub-bullets.

### Dependencies

1. Technical Environment
   - AWS console and programmatic access with appropriate permissions
   - IAM roles configured with least-privilege access for project resources
   - Network connectivity to AWS services from customer environment

2. Dataset Access
   - Data volume: {data_volume_description if available, else "Approximately {data_volume_gb} GB total for project implementation"}
   - Format requirements: Customer to provide data in machine-readable format
   - Access permissions: Customer to grant necessary data access permissions before project initiation

### Responsibilities

• Provide timely access to required systems and data sources within agreed timeline windows
• Ensure AWS environment access and configuration is complete prior to project kick-off
• Assign technical point of contact for infrastructure and access-related queries
• Review and approve project deliverables according to agreed timeline
• Participate in regular status meetings and provide timely feedback
• Provide subject matter expertise for {industry} domain requirements
• Ensure all internal approvals are obtained within the specified project timeline


[META_GENERATED]
## Assumptions

Generate 8–12 bullet points using •.

Derive EVERY assumption from objective_analysis. Map each assumption to a specific field:

Data assumptions (from data_characteristics, data_volume_description):
• Customer-provided data will be in {data_characteristics.format} format;
  reformatting or conversion of other formats is out of scope
• Total project data volume will not exceed the specified volume ({data_volume_description if available, else "{data_volume_gb} GB"});
  exceeding this threshold requires a mutually agreed Change Order
• Source data quality is assumed sufficient for {accuracy_floor}% accuracy targets;
  poor quality data (blurred scans, corrupt files) will reduce model performance below
  committed thresholds

Access and dependency assumptions (from aws_services, integration_details, compliance_requirements):
• Customer will provision AWS account access with required IAM permissions within
  {Week 1 for simple/moderate, Week 1-2 for complex/enterprise} of SOW execution
• [If integration_details non-empty] API credentials and sandbox access for
  {integration_details[0]} will be provided before Feature Implementation phase begins
• [If compliance_requirements non-empty] Customer is responsible for defining data
  classification and confirming regulatory scope; any ambiguity will pause
  compliance-related development until resolved
• [If compliance_requirements empty] No personally identifiable information (PII)
  or regulated data will be processed in the POC environment

Delivery and acceptance assumptions (from complexity_context, primary_personas):
• Customer stakeholders from {primary_personas} will participate in weekly reviews;
  unresponsiveness exceeding {3 for simple, 5 for moderate, 7 for enterprise} business
  days will pause the affected delivery phase
• Feedback on submitted deliverables will be provided within
  {3 for simple, 5 for moderate, 7 for enterprise} business days of delivery
• The project scope is limited to English-language content unless explicitly stated
  otherwise in the objective
• Changes to the project objective after Discovery phase will be handled via Change Order
  and may affect cost and timeline

RULES:
- At least 2 bullets must explicitly assign responsibility to the customer
- At least 1 bullet must state consequences of violation (timeline/cost impact)
- Use real numbers from objective_analysis: weeks from complexity_context.duration_weeks,
  data from data_volume_gb, accuracy from success_metrics
- No introductory text, no generic placeholders


[META_GENERATED]
## Out of Scope

Generate 8–10 bullet points using •. EVERY item must be conditional.

CONDITIONAL RULES (apply each independently):

Always include:
• CI/CD pipeline setup and automated deployment configuration beyond basic environment provisioning
• Staff training programs, end-user documentation, and operational runbooks beyond basic handover
• Support or maintenance beyond the contracted Day-2 period without a separate agreement

Conditional items:
• "Model fine-tuning, retraining, or custom model development" →
  INCLUDE ONLY if aws_services contains Bedrock or SageMaker
  If neither → replace with "Custom AI model development outside of managed AWS AI services"

• "Mobile application development (iOS/Android native applications)" →
  INCLUDE ONLY if ui_required=true (web UI is in scope when ui_required=true; native mobile is not)
  If ui_required=false → replace with "Frontend, web portal, or user interface development of any kind"

• "Multi-region deployment, global CDN configuration, and cross-region failover" →
  INCLUDE ONLY if complexity=complex or enterprise
  If complexity=simple/moderate → replace with
  "Production-grade high availability, disaster recovery, and multi-AZ redundancy beyond single-region POC"

• "Performance or load testing at production scale beyond {concurrent_users} concurrent users" →
  Always include; use actual concurrent_users value from objective_analysis

• "{compliance_requirements[0]} compliance certification and third-party audit" →
  INCLUDE ONLY if compliance_requirements is non-empty; name the actual framework
  If empty → replace with "Formal compliance certification or regulatory audit preparation"

• "Legacy data migration, ETL development, or data cleansing for source systems" →
  INCLUDE ONLY if integration_details contains legacy_systems
  If no legacy systems → replace with "Data pre-processing, cleansing, or quality remediation"

• "Advanced BI dashboards, custom reporting, and real-time analytics visualisation" →
  INCLUDE ONLY if analytics is NOT in key_features
  If analytics IS in key_features → replace with
  "Enterprise-grade BI platform integration beyond the defined POC analytics scope"

FORMAT:
- One line per bullet; no explanations or sub-bullets
- No introductory text
- Start directly with •


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
- Each bullet must be maximum 1 line where possible.
- Avoid long bullets over 20 words.
- Do not include raw markdown headings inside the table.


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

Services commence on {START_DATE} and conclude no later than {END_DATE}. All scope changes require a mutually agreed Change Order.


[META_TABLE]
## AWS Pricing

Generate realistic AWS MRR based on objective_analysis.aws_services, data_volume_gb,
concurrent_users, and complexity_context.level.
PROD pricing is higher than POC due to production-grade infrastructure (multi-AZ, monitoring, backups).

MRR ESTIMATION GUIDELINES FOR PRODUCTION:
- simple + low data: $800–$2,000/month
- moderate + medium data: $2,000–$6,000/month
- complex + high data: $6,000–$15,000/month
- enterprise + very high data: $15,000–$50,000/month
- Add $300–$800/month if ui_required=true (CloudFront, WAF, Shield Standard)
- Add $200–$1,000/month per major integration in integration_details
- Add $200–$500/month if compliance_requirements non-empty (Config, GuardDuty, Macie, etc.)

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


[META_TABLE]
## Shellkode Implementation Cost

Generate resource allocation based on complexity_context.level and the total weeks
determined in Timelines and Deliverables. Effort/Week MUST match project duration.

RESOURCE ALLOCATION RULES FOR PRODUCTION:
- simple (8–12 weeks): 1× AIML Engineer; Solution Architect 2–3 weeks
- moderate (12–18 weeks): 1× AIML Engineer + 1× Sr AIML Engineer;
  Solution Architect 3–4 weeks
- complex (18–24 weeks): 1× AIML Engineer + 1× Sr AIML Engineer;
  Solution Architect 4–6 weeks
- enterprise (24–32 weeks): 2× AIML Engineers + 1× Sr AIML Engineer;
  Solution Architect full engagement (proportional weeks)

ADD frontend resource ONLY if ui_required=true:
- simple + ui: add 1× Frontend Developer at full project duration
- moderate/complex/enterprise + ui: add 1× Sr Frontend Developer at full project duration

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
- All Pricing (INR) cells must show "AWS Funded"
- Effort/Week must be specific numbers matching the project timeline


[META_GENERATED]
## Success Criteria

Generate 5–7 measurable bullets using • derived from objective_analysis.success_metrics.
Production criteria are STRICTER than POC criteria.

DERIVATION RULES:
1. Map each item in success_metrics to one bullet with a specific percentage or numeric target
2. Accuracy targets (PROD floors — higher than POC):
   - simple: ≥90% accuracy
   - moderate: ≥93% accuracy
   - complex: ≥97% accuracy
   - enterprise: ≥99.5% accuracy
3. Always include: system uptime ≥99.9% in production environment
4. Always include: processing success rate ≥98% based on data_volume_gb monthly volume
5. If ui_required=true → add: "User acceptance rate ≥85% based on structured UAT
   with {primary_personas[0]} representative group"
6. If compliance_requirements non-empty → add: "100% of security and audit events
   captured in CloudTrail with zero data gaps; {compliance_requirements[0]} controls
   validated during pre-production security review"
7. Performance: "System supports {concurrent_users} concurrent users with
   <{latency}s p95 response time under sustained load"
   Use latency from performance_requirements if available; else use complexity default:
   simple=5s, moderate=3s, complex=2s, enterprise=1s
8. Scalability: "Auto-scaling validated to {concurrent_users × 2} concurrent users
   without manual intervention"

FORMAT: • symbol, one measurable bullet per line, no introductory text


[META_GENERATED]
## Day-2 Operations & Support

Generate concise operational support overview based on complexity_context.level.
Keep all bullet points to maximum 2 lines each.

CONTENT STRUCTURE (4 main sections only):

### Monitoring and Incident Response
• Business hours monitoring (10am-7pm IST, Mon-Fri)
• Incident Response SLAs based on complexity:
  - Simple: P1=4hr, P2=8hr, P3=next business day
  - Moderate: P1=2hr, P2=4hr, P3=8hr  
  - Complex: P1=1hr, P2=2hr, P3=4hr
  - Enterprise: P1=30min, P2=1hr, P3=2hr

### Patch Management and Updates
• Security patches applied according to severity:
  Critical vulnerabilities within 24 hours, standard updates within 30 days
• Monthly maintenance window for non-critical updates
• Patch testing in staging environment before production deployment

### Support Coverage
• L2 Application Support
  Available during business hours for application functionality and performance issues
• L3 Technical Support
  Architecture and infrastructure issues, available for critical escalations

### Service Reviews
• Monthly service review meetings covering:
  System uptime and SLA compliance, cost tracking against budget,
  performance metrics review, pending change requests and updates

BOUNDARY (always include, exact text):
Any support or operational engagement beyond the defined Day-2 period requires a separate Statement of Work or Support Agreement mutually executed by both parties.


[META_STATIC]
## Deliverable Acceptance

Customers will notify {AUTHOR_ORG_SHORT} in writing within ten (10) calendar days of receiving a Deliverable whether it accepts or rejects that Deliverable. If no notification is delivered to ShellKode within this period, the Deliverable will be considered accepted. As a time and materials engagement, changes to a rejected Deliverable constitute billable project time unless the parties determine that such Deliverable was not performed in accordance with good commercial practices.


[META_STATIC]
## Change Management

Changes to project scope, incorrect assumptions, or missing prerequisites may affect cost, resources, or scheduling. Other circumstances may arise beyond {AUTHOR_ORG_SHORT}'s control that may cause it to be unable to accomplish the project objectives and would require a modification to this proposal. Any such modification shall be memorialized in a mutually executed change order that details material changes to staff requirements, deliverables, fees, and milestones, as applicable. If the parties do not agree to such a proposed change order, then either may suspend the Services to allow time for the parties to agree on an alternative change order. Should Services be suspended for a consecutive period of five (5) business days, either party may thereafter terminate this proposal immediately upon notice.


[META_STATIC]
## Project Plan Termination

Upon termination of this Project Plan executed in accordance with the terms of the Agreement, Customer shall pay {AUTHOR_ORG_SHORT} for any Customer-approved Services performed and expenses incurred up to the date of the termination and any expenses necessarily and reasonably incurred by AWS Partner in terminating Customer-approved obligations to third parties.


[META_STATIC_TABLE]
## Contacts and Reporting

| Name | Title | Email | Phone |
|-----|------|------|------|
| Bala | Delivery Head | bala@shellkode.com | +91 95389 16855 |
| Bakrudeen K | AI/ML Head | bakrudeen.k@shellkode.com | +91 78454 06910 |
| Suman Perumal | Solution Architect | suman.p@shellkode.com | +91 97382 41191 |
| Velmurugan S | Delivery Manager | vel@shellkode.com | +91 99946 07336 |


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