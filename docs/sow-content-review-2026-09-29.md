# SOW content review and authoring changes

Reviewed the body content and tables of Tata CLiQ POC v22 against the supplied
Amneal, Avanse and Kotak Life SOWs. This is a content review, not rendered page-layout QA.
Reference documents are examples of writing and organisation, not sources of commitments
for another customer.

## Main finding

The problem is duplication and over-enumeration, not simply long sentences.
The generated Tata document contains 20 dependency rows, 30 clarification rows and
25 success criteria. Responsibilities repeats much of Dependencies; assumptions
often repeat features; milestones follow individual modules. Shortening each row
alone would preserve the same bloat.

Avanse and Kotak use direct work descriptions and retain concrete business rules.
Amneal has substantially more distinct scope, including core/advanced modules and
support: it is not evidence that every SOW should fit a small page limit. The
references themselves contain some repetitive boilerplate, which should not be copied.

## Section-by-section decisions

| Section | Observation / change |
|---|---|
| Cover and contents | Leave rendering and heading structure unchanged. |
| Document control | Keep document/customer/version/date; remove revision-basis and audience essays. |
| About ShellKode | Use the user's exact single paragraph in all three built-in templates; keep it static. |
| About client | Retain the two-paragraph company-only profile; no engagement narrative or invented company facts. |
| Objective | State the solution, its users and outcome; leave modules and test evidence to their own sections. |
| Current state | Retain systems/workflows that define the integration or replacement boundary; omit operational inventories unrelated to delivery. |
| Scope | Keep independent deliverables and meaningful modules, with short action bullets. Preserve actual rules, interfaces, thresholds and exceptions. Remove the repeated module catalogue from the deliverable summary table. |
| Architecture | Describe the flow and significant design decisions, not every diagram node or feature. Diagram generation itself is unchanged. |
| Dependencies | Group concrete access/data prerequisites into bullets; remove artificial IDs, role labels and repeated delay-impact columns. |
| Assumptions | Include adopted conditions that materially affect the delivery baseline, not known features, duties or decisions still open. |
| Out of scope | Keep realistic adjacent-work boundaries only; do not generate an absent-feature catalogue or exclude included support. |
| Timeline | Use timeframe/milestone/outcome, not one phase per module with repeated exit evidence. |
| Pricing | Keep calculator and cost rendering untouched. Do not let a prose editor alter financial values. |
| Customer responsibilities | State decisions, UAT participation and operational ownership without repeating the prerequisites list. Production responsibilities are now project-specific rather than a static broad checklist. |
| Team effort | Compact resource/count/effort table; no role essays or invented quantities. |
| Clarifications | Only decisions blocking scope, sizing, price or acceptance; omit routine discovery questions about schemas, copy and tuning. |
| Success criteria | Group independently testable end-to-end outcomes; retain explicit thresholds without copying every scope bullet. |
| Technical/security/migration | Include applicable constraints and work only; remove mandatory generic control/NFR/migration matrices. |
| Test plan, risks and support | Brief agreed approach, project-specific risks and actual support boundaries, not exhaustive registers. |
| Legal, contacts and signatures | Preserve static clauses and existing rendering; no editorial LLM rewrite. |

## Enforcement

- Updated all built-in templates and the POC validation rules to remove conflicting exhaustive instructions.
- Shared section-purpose rules apply to ordinary authoring and the separate per-deliverable scope-writing path.
- One joint editorial pass sees the completed ancillary sections and read-only scope, allowing cross-section de-duplication that independent section calls cannot perform.
- The editor cannot change scope, pricing, static legal/company text or custom-template sections. Unaffected refinement sections remain protected.
- Its response must contain exactly the eligible keys and string bodies, cannot expand sections, and must preserve numeric facts. No partial or truncated JSON repair is applied to this pass.
- Only nonessential assumptions, exclusions, clarifications and risks may become blank after review; required sections cannot disappear.
- If the style pass is unusable, retain the already generated document. Primary generation failures still use existing failure handling. Terminal logging reports edited word counts or retention of the original draft, and the call uses existing token accounting.

## Validation boundary

Automated tests exercise prompting, static text, section selection, protected sections,
editor response validation, scope structure and refinement compatibility. They do not
prove an LLM preserved every non-numeric obligation. A fresh source-to-SOW generation
and human content check remain necessary to judge the final quality; there is no
honest deterministic guarantee of semantic quality or a fixed page count.
