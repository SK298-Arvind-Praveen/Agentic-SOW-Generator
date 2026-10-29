# V29 review and corrective changes

Reviewed the V29 DOCX and the matching 5 October 2026 generation logs. The reviewer audit is `backend/llm-outputs/20261005T060754_172040Z_305183adff5d_sow_review.json`.

## What caused the reported defects

| Defect | Evidence | Attribution |
|---|---|---|
| Scope became large paragraphs | Original deliverable logs and the audit's `before` text have Markdown bullets. The applied `scope_of_work` correction replaces them with multi-sentence module paragraphs. | Reviewer introduced it; validation protected headings but not bullet structure. |
| Deliverables summary disappeared | The audit's original scope starts with a Deliverable/Outcome table. The applied replacement removes it. | Reviewer introduced it. |
| Architecture contains broken tables and ASCII borders | `0010_SOW_Section_-_Solution_Architecture.txt` starts with a fenced ASCII diagram. The cleaner removed fences; Word parsing treated any pipe-enclosed lines as table rows. | Writer produced it; cleanup and renderer mishandled it. |
| Architecture and other contradictions survived review | The batch owning architecture, profile, objective, current state, dependencies, assumptions, exclusions, effort, clarifications and success criteria failed with `ReadTimeoutError`. | Reviewer missed them because the ten-section batch did not finish. |

The reviewer took 41.89 seconds. Five section corrections were applied. Text declined from 7,057 to 6,618 whitespace-delimited words, but reduced word count did not mean improved layout or contractual consistency.

## Section-by-section findings

| Section | Assessment |
|---|---|
| Service Agreement | Static clause present with reusable blanks; preserved under the previous word-for-word requirement. |
| About ShellKode | Requested static paragraph retained. |
| About Client | Two paragraphs, but the second discusses the need to evolve support rather than just the company. Its review timed out. |
| Objective | Repeats the capability list and describes a POC preceding a production decision, while scope commits to production deployment and ongoing support. |
| Current State | Useful existing-system facts mixed with staffing detail and a redundant closing integration summary. |
| Business Benefits | Improved to six short outcome bullets. Self-service and proactive notifications still overlap on contact-volume reduction, but this is materially better. |
| Solution Architecture | Redundant ASCII drawing rendered as seven malformed tables. Roughly 729 extracted words including drawing text; prose repeats channel, integration, security and reporting details. |
| Scope of Work | Two deliverables and module hierarchy remain, but reviewer collapsed action bullets into paragraphs and deleted the overview table. Monitoring, audit logging, context handling and reporting repeat across modules. |
| Customer Dependencies | Repeated API/sandbox credentials across systems and duplicated live-agent access; can group prerequisites. |
| Assumptions | English and Hindi conflict with English-only scope. Retention, RTO/RPO, region, topology and REST connectivity are treated as baselines while other sections ask for decisions on them. Some are sizing assumptions rather than approved acceptance targets. |
| Out of Scope | Knowledge-content migration exclusion conflicts with knowledge loading/dependency wording. Model-version migration exclusion needs a clear boundary against included platform/model upgrades. |
| Timeline | Still lengthy implementation descriptions inside cells. Production deployment contradicts Objective; the 500-session target is promoted into validation without distinguishing assumption from agreed acceptance. |
| AWS Pricing | Workload and costs are blank although the pricing plan contains volumes. `50k` versus `50000`, and lakh notation, fail the numeric evidence comparison. This is independent of the reviewer, which cannot edit pricing. Exact source-quote matching and live calculator availability still need their own verification. |
| Customer Responsibilities | Some consolidation occurred, but credentials repeat Dependencies and decisions repeat Open Clarifications. Customer ownership of updates overlaps Shellkode's managed-update scope; approval/content ownership should be distinguished from execution. |
| Project Team Effort | Role table followed by a redundant narrative; allocations and duration need an approved estimate basis. Review timed out. |
| Open Clarifications | Seventeen questions, including matters already asserted as assumptions/exclusions. The Tata Neu question explicitly mentions conflicting RFQ/Technical Sheet inputs, which is inappropriate tool/source commentary. |
| Success Criteria | About 499 words resembling a test inventory. Hindi coverage contradicts scope. Repeated controls and absolute response-quality promises need consolidation and qualification against agreed acceptance criteria. |
| Roles and Responsibilities | Now renders correctly with codes and no legend. Still fourteen rows; related build workstreams can be consolidated while preserving distinct customer acceptance ownership. |
| Change Order / Termination / Marketing Authorization | Protected reference clauses retained. Change Order's missing final full stop is inherited, not introduced by review. |
| Contacts and Reporting | Compact and suitable; unavailable contact fields remain blank. |
| Terms & Conditions | Inherited ElevenLabs/telephone references and Section 18.1 cross-reference do not fit this document. Not changed because the legal master was explicitly requested word-for-word. |
| Signatories | Table is suitable; inherited `companies.IN WITNESS` spacing remains in protected text. |

## Implemented

- Reviewer patches cannot remove deliverable/module headings, the existing deliverables summary table, or scope module action bullets. Multi-sentence scope/benefit/duty bullets are also rejected rather than applied as paragraph-shaped bullets.
- Added deterministic ASCII box removal before architecture cleanup and at Word export. Genuine Markdown comparison tables remain intact.
- Word table parsing now requires a Markdown header separator instead of treating arbitrary pipe-separated drawing rows as tables.
- Architecture authoring rules in all three templates explicitly prohibit duplicate text diagrams; the dedicated diagram pipeline owns the visual.
- Replaced the overloaded reviewer catch-all with up to six focused parallel groups under the same 50-second shared deadline, with no retry loop. This increases the potential number of Haiku calls from three to six; live latency and token impact remain to be measured.
- Reviewer can use an exact passage patch for local edits instead of rewriting a whole long section. It explicitly checks language, delivery phase, source-system role, migration boundaries, ownership and assumption-versus-acceptance conflicts.
- Audit logs and internal quality metadata record unfinished review, rejected corrections and remaining detected formatting problems instead of claiming a clean pass. These are internal diagnostics, not client-facing SOW commentary.
- Pricing volume validation now recognises equivalent explicit magnitudes, such as `50k` and `50000`, without estimating new values or relaxing exact quote matching.

## Verification limits

Automated regression tests exercise export parsing, ASCII cleanup, table preservation, scope layout protection, audit completeness, reviewer grouping and volume equivalence. No live Bedrock regeneration was performed. The bundled DOCX renderer could not run because bundled LibreOffice is unavailable, so no full-page visual sign-off is claimed. The supplied V29 file is unchanged; fixes apply to subsequent generation/export. These checks reduce known failure modes but cannot guarantee semantic correctness or client readiness without reviewing the next output. Changes are local, not pushed.
