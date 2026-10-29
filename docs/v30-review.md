# V30 review and generator corrections

## Evidence and verdict

Reviewed the attached `Tata CLiQ  _ AI _ Agentic Customer Support Platform - POC v30.docx` (the request also mentions V29, but V30 is the newly attached output), the matching 5 October generation logs, and `backend/llm-outputs/20261005T064344_143733Z_f259a15a67a3_sow_review.json`.

V30 improves on V29: scope action bullets and the deliverables summary table survive, the extra ASCII architecture tables are gone, and About Client has two paragraphs. It is still not client-ready. The reviewer completed all six batches in 30.55 seconds and reduced tracked section text from 7,195 to 6,213 words, but completion and shorter text do not establish contractual consistency.

The architecture problem was introduced by the reviewer: its recorded reason explicitly says it replaced enumerated bullets with “fewer, longer narrative paragraphs”. The final architecture contains roughly 497 extracted words including its caption. This is not a timeout problem.

The scope contains **18 build modules and two ongoing-support modules**, not 18 separate deliverables. These are overly granular. The classifier supplied the subdivision, and the reviewer was prohibited from changing module headings. It also proposed four local scope edits; only the first applied because the old patch handler rejected further changes to the same section as duplicates.

## Section-by-section findings

| Section | Finding |
|---|---|
| Service Agreement | Protected reference wording and reusable blanks remain; no material new generation issue identified in extracted text. |
| About ShellKode | Requested single static paragraph retained. |
| About Client | Two factual paragraphs restored. Some operating-volume and technology details repeat Current State; these need only appear where they define the integration context. |
| Objective | Better aligned with production delivery and support than V29, but still a capability inventory rather than a brief statement of the outcome. |
| Current State | Relevant existing-system facts mixed with long paragraphs and a concluding restatement. Keep the integration/replacement boundary, not a second overview of every system. |
| Business Benefits | Seven outcome bullets are better than paragraphs; some still describe implementation capabilities. Combine overlapping agent-efficiency and customer-contact benefits. |
| Solution Architecture | Reviewer converted bullets into six large prose blocks. Existing agent-platform retention and the newly proposed Amazon Connect workspace also need a consistent boundary. |
| Scope of Work | Summary table, two deliverables and action bullets now survive. Eighteen build modules fragment related work; security, reporting, notifications and support repeat. The language heading says English Baseline while its body includes Hindi. |
| Customer Dependencies | Eleven prerequisites still repeat WhatsApp credentials and network connectivity. Group access for related systems; keep customer decisions separate from credentials and test data. |
| Assumptions | Much shorter, but handover-only Agent Assist conflicts with on-request assistance in Scope and Success Criteria. Capacity is a planning assumption, not automatically an agreed acceptance threshold. |
| Out of Scope | More concise. Model/version migration exclusion still needs a precise boundary against included upgrades and optimisation; do not exclude agreed maintenance. |
| Timeline and Deliverables | Nine long rows repeat the implementation plan. A fixed eight-week schedule conflicts with the question asking for committed duration. Dates and staffing must have an agreed basis, not come from a default template. |
| AWS Pricing | Volumetric table returned, but monthly volume is blank despite a 50,000/month candidate in the input plan; inference shares display as 60 and 40 without percent signs; a multi-option annual volume becomes one design point. The link is the calculator homepage, not a saved estimate. |
| Customer Responsibilities | Test-data supply repeats Dependencies. Tata Neu configurations are requested while inclusion remains an open question. Distinguish customer approval/content ownership from Shellkode's included update execution. |
| Project Team Effort | Arithmetic is internally consistent: 7.5 FTE for eight five-day weeks gives 300 person-days. This does not establish that the staffing or duration is approved. |
| Open Clarifications | Shorter, but the reviewer removed corpus-size and retention questions as discovery details even though these can affect architecture and pricing. Keep material unknowns; remove questions about already agreed decisions. |
| Success Criteria | Still approximately 322 words resembling a test inventory. Introduces “once per channel” test execution and moves numeric targets to post-go-live metrics “pending agreement”. Neither should be an editorial invention. Agent Assist availability conflicts with Assumptions. |
| Roles and Responsibilities | Correct three-column format and no legend, but 21 activity rows mirror the scope. Group implementation work with common ownership; keep customer acceptance, prerequisites and support accountability distinct. |
| Change Order | Protected wording retained; missing final punctuation is inherited from the approved static text. |
| Project Plan Termination | Protected clause retained. |
| Contacts and Reporting | Compact table; contact blanks are appropriate. No new material issue identified. |
| Marketing Authorization | Protected clause retained. |
| Terms & Conditions | Inherited ElevenLabs/telephone wording and a Section 18.1 cross-reference do not fit this document. These remain protected under the earlier word-for-word instruction; legal-master correction needs approval. |
| Acceptance and Signatories | Suitable signature table, but inherited `companies.IN WITNESS` spacing remains in protected prose. |

### Pricing caveat

The volumetric fallback log explicitly returns USD 8,000–48,000/month with a USD 22,000 base; the document annualises that to USD 264,000 correctly. The problem is not that annual multiplication: the underlying value is an LLM planning estimate, not a calculator-verified quote. It assumes Connect usage and fixed OpenSearch/Redshift capacity without a service-by-service rate calculation. The generated document does label it non-binding. This review does not validate that estimate or change the pricing engine.

## Sensible scope grouping

The 18 build headings are not all necessary. An illustrative grouping is below; it is a cohesion rule, **not a hardcoded module count**:

- Solution design and deployment approach.
- Conversational engine, knowledge handling and language coverage.
- Channel delivery.
- Enterprise integrations.
- Customer notifications, proactive engagement and feedback.
- Live-agent handover and assistance.
- Identity, API security, history and audit controls.
- Analytics, reporting and operational monitoring, split only where ownership or acceptance differs.
- Testing, go-live, training and operational handover.

Keep ongoing support and continuous improvement in the separate support deliverable. Build-time readiness is different from delivering ongoing support. A grouping alone must never silently delete an obligation, move it into another deliverable, or resolve uncertain commercial scope.

## Implemented locally

1. All three default templates and shared authoring/review instructions now require short, one-sentence architecture bullets, without introductory/concluding paragraphs or a service catalogue.
2. Reviewer patch validation rejects a rewrite that turns architecture bullets into paragraphs, including multi-sentence paragraph-shaped bullets. Invalid style edits retain the previous text and are recorded internally; they do not halt generation.
3. Scope classification explicitly groups cohesive capabilities instead of creating one module per source item, feature or AWS control. No fixed module count was added.
4. Added a structured `module_groups` reviewer operation. The model selects groups; deterministic code requires every original module exactly once under its original deliverable, preserves the summary table and module bodies, and removes only exact duplicate bullet lines within a merged group. Semantic shortening still requires explicit text corrections, not silent code deletion.
5. Multiple disjoint passage corrections to the same section now apply and are individually audited. Overlapping edits, ambiguous passages and edits after regrouping are rejected. Regrouping runs after local corrections so their results survive.
6. Strengthened consistency instructions for heading/body language, Agent Assist availability, duration/staffing, material sizing clarifications, concise responsibility workstreams and acceptance criteria without invented test counts.

The reviewer uses the existing bounded parallel calls. These changes add no new model call or retry loop and do not change model selection. Grouping metadata adds some response tokens; live latency and output quality still need measurement.

## Validation and limitations

- **111 tests passed**, with two existing dependency deprecation warnings, across scope classification, authoring, reviewer audit, templates, refinement and V26–V30 regressions.
- New regression coverage checks architecture bullet protection, valid/invalid module grouping, preservation of obligations and deliverable boundaries, multiple edits, overlap rejection and audit results.
- No live Bedrock regeneration was run. The supplied V30 DOCX remains unchanged; these code changes affect subsequent generation.
- Review used document text/XML and logs. Bundled LibreOffice is unavailable, so there is no full-page visual sign-off or claim that the architecture image is corrected.
- Static legal wording and the pricing estimator remain unchanged. Changes are local and have not been pushed.
