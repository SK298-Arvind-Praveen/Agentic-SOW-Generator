# V28 content review

Reviewed: `Tata CLiQ  _ AI _ Agentic Customer Support Platform - POC v28.docx`.
This is a text, heading and table review, not a rendered-page or architecture-geometry sign-off. The attached document has not been rewritten. Changes apply to future generation.

## Overall finding

V28 is not yet client-ready. It restores two deliverables, and About Client has two paragraphs. However, the Objective explicitly excludes production and managed support while Scope and Timeline include them. The reviewer produced corrections but included invalid section keys and invalid RACI cells; previously, a single invalid correction discarded the entire batch. The document builder also failed to resolve the renamed Roles and Responsibilities heading to the saved `raci_matrix` content, leaving section 17 absent.

## Section-by-section findings

| Section | Finding |
|---|---|
| About ShellKode | Matches the requested single static paragraph; retain. |
| About Client | Two paragraphs restored, but generic descriptions of scale and regulatory context add little. Prefer concrete company identity and established operations; no vendor-evaluation narrative. |
| Objective | Too many persona-specific paragraphs. Critical contradiction: an eight-week evaluation excludes the production/support deliverables that follow. Align to the agreed delivery plan; do not infer scope from the POC template label. |
| Current State | Useful system facts, but opening/closing commentary is redundant. A sentence ends with a dangling semicolon after disclaimer removal. |
| Business Benefits | Ten long feature-oriented statements rather than grouped outcomes. “Without operational cost” is an unjustified absolute. The integration diagram also interrupts this outcome section. |
| Solution Architecture | Roughly 716 words repeat channel, integration and security details later restated in Scope. Alternatives and unresolved design choices remain; the prose is not a validated final technical design. Visual diagram quality remains unverified in this review. |
| Scope of Work | Two deliverables are now present. Roughly 1,584 words across 13 modules are still repetitive: channel continuity, API routing, audit logging, monitoring and analytics recur. Preserve distinct obligations, not repeated architecture explanations. |
| Customer Dependencies | Access and documentation are legitimate prerequisites, but system-by-system inventories and staffing requests can be grouped. |
| Assumptions | Repeats languages, channels and exclusions; treats unified bots, geography and sizing as settled while clarifications still ask about them. Only adopted material baselines belong here. |
| Out of Scope | Voice/IVR exclusion appears twice; several clauses repeat channel/language boundaries. Model migration exclusion must remain compatible with included model improvements and upgrades. |
| Timeline and Deliverables | One table is correct, but outcomes replay the scope and service catalogue. Eight weeks should not become an agreed duration when clarification still requests it. |
| AWS Pricing | A homepage link is described as if it contains editable estimate inputs. “60–70% of conversations” is not a count of backend API calls. The USD 800–9,500 range is a planning estimate, not a verified calculator quote. No live price verification performed. |
| Customer Responsibilities | Shorter than V27, but still repeats access inventories and several approval/UAT duties. Existing agent counts must not become staffing commitments without agreement. |
| Project Team Effort | Compact table followed by a redundant role-by-role paragraph. Nine staff and 64 person-weeks require an approved estimation basis; they are not established merely by appearing in generated text. |
| Open Clarifications | Remove introductory editorial commentary. Reconcile questions about channels, bot topology, residency and duration with statements elsewhere rather than presenting both as settled and unresolved. |
| Success Criteria | End-to-end tests are useful, but repeated test detail and absolute promises (“nothing re-asked”) overstate acceptance. Do not introduce a single-cycle UAT obligation without agreement. |
| Roles and Responsibilities | Missing from the body despite TOC numbering. Raw output contains many feature-level rows and prose instead of responsibility codes. Fix rendering alias and strengthen code-only, workstream-level authoring. |
| Change Order | Protected reference wording retained; it lacks terminal punctuation in the original template. No unilateral legal rewrite. |
| Project Plan Termination | Brief protected clause retained. |
| Contacts and Reporting | Compact table is appropriate; keep unavailable contact fields blank. |
| Marketing Authorization | Brief protected clause retained. |
| Terms & Conditions | Inherited reference text mentions ElevenLabs/telephone and Section 18.1, which do not align with this SOW. These were requested word-for-word earlier and need approval before changing the legal master. |
| Acceptance and Signatories | Signature table is appropriate, but inherited text joins “companies.IN WITNESS”. Static wording remains unchanged. |

## Implemented changes

- Resolve Roles and Responsibilities to the legacy saved content key in Word generation.
- Validate reviewer corrections independently per section, preserving valid corrections when another section is invalid; log the specific rejection reason.
- Explicitly supply permitted output keys to the reviewer, preventing confusion between section categories and actual saved keys.
- Allow inline bold company names in valid two-paragraph profiles.
- Strengthen shared authoring/review rules for delivery-boundary consistency, outcome-only benefits, grouped duties, compact timeline outcomes, table-only staffing, and non-repetitive scope.
- Update all three templates with code-only RACI and customer-duty ownership instructions.
- Repair dangling semicolons when a trailing source/missing-information clause is removed, preserving ordinary valid semicolons.
- Preserve percentage units in pricing workload labels and distinguish calculator-homepage links from estimate links.

## Verification and remaining limits

70 backend regression tests passed, including new V28 cases; two dependency deprecation warnings remain. No additional model calls or retry loops were introduced. No live Bedrock generation was run, so improved wording and reviewer completion must be verified on the next SOW. Invalid corrections still retain the original section rather than inventing a replacement. Static legal clauses and visual diagram quality remain explicit review items; these changes do not constitute a client-readiness guarantee. Changes are local, not pushed.
