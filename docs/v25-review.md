# V25 review and changes

Reviewed the supplied Tata CLiQ v25, Amneal, Avanse and Kotak SOWs, plus the generation log. Counts below are approximate extracted body words, including table text; they are not page-layout measurements.

## Findings

The log records 1,034,343 tokens (977,742 input, 56,601 output), 40 calls and 791.75 seconds. Most tokens were repeated inputs, not final prose. V25 has roughly 7,743 extracted words and nine tables. Amneal is approximately 8,016 words, Avanse 5,012 and Kotak 4,398: not every reference is shorter. Amneal also includes substantial support/AMC content. A page target alone would therefore be misleading.

| Section | V25 issue compared with the references | Revision direction |
|---|---|---|
| Service Agreement / About ShellKode | Deliberately fixed text, not a verbosity defect | Preserve approved wording |
| About Client | 131 words; acceptable length, but the opening describes teams evaluating platforms rather than clearly introducing the business | Keep two factual company paragraphs; avoid engagement framing |
| Objective | 180 words; not much longer than reference objectives, but enumerates features again | State the solution, users and result; leave feature detail in Scope |
| Current State | 292 words; individual bullets for related CRM fields, survey templates and channels | Group existing systems and retain only integration-boundary facts |
| Business Benefits | 206 words, comparable to Amneal's 216; several bullets are features rewritten as benefits | Keep distinct business outcomes, not a second feature list or unsupported future extensibility promise |
| Solution Architecture | 644 words versus Avanse's 826; length alone is not the defect | Explain logical layers and interactions rather than one bullet per service; do not conflate IAM permissions with application-user SSO |
| Scope of Work | 1,475 words versus roughly 708/719 in Avanse/Kotak; Amneal is more detailed | Retain distinct obligations but combine repetitive controls, reporting metrics and training actions; avoid restating the complete architecture |
| Customer Dependencies | 227 words, comparable to Avanse/Kotak | Consolidate related access; move approvals and stakeholder participation to Responsibilities |
| Assumptions | 309 words; includes a large pricing-input inventory and settled assertions about choices still questioned elsewhere | Keep only critical adopted baselines; keep detailed volumes in Pricing; do not resolve source conflicts silently |
| Out of Scope | 247 words, comparable to references; repeats voice/Genesys exclusion and overlaps ongoing-support scope | Merge related exclusions and preserve the distinction between included support and separately contracted work |
| Timeline | Nine rows, repetitive milestone descriptions; eight-week planning estimate appears alongside production commitments in a POC | Milestone-level outcomes only; preserve the selected delivery phase and agreed dates |
| AWS Pricing | Empty volume and cost tables despite volumetric assertions elsewhere; generic calculator homepage presented as editable estimate | This is an unresolved pricing-data consistency issue, not a prose-length issue; no claim that a live estimate exists |
| Customer Responsibilities | 362 words versus 227/273 in Kotak/Amneal; many individual confirmations and sign-offs | Group decisions, reviews and acceptance responsibilities; unresolved questions belong in Clarifications |
| Project Team Effort | Table is appropriate; avoid unsupported effort values | Keep a compact table and no role-by-role narrative |
| Open Clarifications | 218 words; repeats questions already discussed as assumptions/responsibilities | Keep only decisions affecting scope, price, design or acceptance; avoid routine discovery questions |
| Success Criteria | 495 words versus 109/154/178 in references; effectively a detailed test script | Use end-to-end acceptance outcomes and actual thresholds; do not replay every feature or test procedure |
| RACI | 475 words, two repeated 16-row tables, seven party columns | One Workstream / Shellkode / Client table with combined responsibility codes; consolidate workstreams |
| Change Order / Termination / Marketing / Terms | Exact approved reference clauses; Terms alone is about 874 words | Keep unchanged, including placeholders; shortening needs separate approval |
| Contacts / Signatories | Compact structured information | Preserve placeholders without explanatory filler |

Several v25 sentences join clauses without punctuation. Concision must not mean deleting punctuation or qualifications. Selective inline bold should highlight a useful system, obligation or threshold within a sentence, not reintroduce a redundant bold label followed by a colon.

The POC document also promises production deployment and ongoing SLA support. This may reflect the broader sources, but the scope needs phase reconciliation rather than automatically importing every production requirement. The three references are style examples, not authority for Tata CLiQ commitments.

## Draft defect

The history query projected draft fields but the response formatter discarded status, preview ID and snapshot location. Frontends then defaulted the record to completed. The formatter now preserves these fields. No live DynamoDB row was changed during this investigation. Existing correctly stored drafts should display after backend restart and records refresh.

## Diagram defects and corrections

The embedded overview places App/Web and WhatsApp inside AWS, leaves an empty VPC/workload box, and compresses all regional services into a narrow rail. The integration view clips two nodes because five nodes were placed on a row sized for four. The reviewer reported these defects but its permitted layout repairs could not remove the empty boundaries or enlarge the canvas.

Code now gives explicit external scope priority, uses a full-width regional/serverless layout without an empty VPC when no VPC-bound nodes exist, and sizes the hub canvas for all peers. Review reports distinguish unresolved issues from a clean review. Topology and branch correctness still require validation; a zero-crossing metric alone is not proof of a correct diagram.

## Efficiency changes

- Remove duplicated raw-source and internal transport fields from writer and diagram prompts while retaining structured requirements.
- Send targeted evidence to ancillary sections; retain fuller evidence and module detail for Scope.
- Send deliverable summaries rather than all module expansions to ancillary sections.
- Use draft-only context for concise rewrites instead of resending the entire authoring prompt.
- Route supporting sections and editorial/visual review to the configured Haiku profile; keep primary scope and architecture authoring on Sonnet.
- Replace the 150-minute per-request read timeout with a configurable five-minute timeout and three total SDK attempts. This is not a guaranteed end-to-end deadline.

These are local code changes, not measured live improvements. A fresh generation is required to assess final page count, factual fidelity, token cost and latency. The supplied DOCX was inspected structurally and its embedded diagrams visually; it was not regenerated or fully page-rendered in this review.
