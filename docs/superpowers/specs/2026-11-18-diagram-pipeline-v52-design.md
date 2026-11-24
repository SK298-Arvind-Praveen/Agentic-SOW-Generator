# Diagram pipeline v52 audit and redesign

Date: 18 November 2026. Scope: the user's Tata CLiQ v52 failure, a staged diagram reliability redesign, and immediate architecture-table replica deduplication.

## What happened, with evidence

The v52 DOCX embeds the same 4093 × 3535 architecture PNG recorded in `backend/output/diagram-debug/20261118T122151_30960ee29f1a.rejected.png`. Its audit JSON records a real primary `narrative_drawio` image, not the recovery fallback: 41 nodes, 44 original edges, 31 visible connectors, 29 numbered process entries, 11 crossings, and `review_required` status.

The three attempts consumed 519.38, 347.12 and 146.08 seconds: 1012.58 seconds total. Attempt one had 38 crossings. Attempt two reduced this to 11 but retained incorrect process prose. Attempt three failed with `Architecture Plan Correction already used its two corrective retries`; the best retained candidate was attempt two. This was not an unavailable Bedrock model or an output-truncation event.

Metadata confirms the configured Opus profile `lwjwoyltuicz` performed graph planning/composition and the configured Astra profile `o8dwriwugus2` reviewed the images. Relevant calls ended with `end_turn`. The initial graph call had 68,148 input tokens and 16,364 output tokens against a requested 32,768 output-token allowance. The source was 33,481 characters, below the 60,000-character source cap in the graph prompt. Removing token limits would not repair these defects.

### Actual production path

`SOWGenerator.tsx → apiService.generatePreview → /api/preview → source extraction → async preview → research → analyze → validate → solution_design → scope_architecture → pricing → section authoring/review → graph planning → composition → rendering → process panel → Astra image review → retry selection → architecture table → draft/export/finalize`.

V52 selected 23 sections, including scope, pricing and conceptual flow. Its recorded input is `backend/output/llm-debug/20261118T120458_730000Z_0054_Architecture_Inputs.txt`.

### Why the earlier tests passed

`scripts/verify_story_layout.py:19-28` either calls `_asset` directly or calls layout-only regeneration with a saved graph. `preview/architecture_regeneration.py:40-43` sets `_architecture_retry_spec`, and `diagram/service.py:2428-2438` bypasses fresh graph planning. It deliberately asserts that the old nodes, edges and text do not change. This is a renderer regression, not a fresh-generation test.

The earlier saved Tata graph was a serverless functional view with 38 nodes. V52 produced a different mixed physical/functional view with connector Lambdas, NAT gateways and two AZs. The same outer service selects different layout/projection branches for those graphs.

Even `replay_brd_preview.py` and `replay_preview_http.py` currently select only `architecture_diagram`, rather than the actual 23 sections. The HTTP harness replaces draft persistence and does not finalize a document. Its final assertion requires a PNG and no fallback, so it would pass this failed v52 image. Workflow completion and diagram acceptance have been conflated in tests.

## Improvement areas

| Area | Observed weakness | Required change |
|---|---|---|
| Test parity | Saved-graph and architecture-only runs omit important production stages and inputs. | Replay a complete, versioned request manifest through upload, preview and export. Keep renderer tests explicitly labelled as renderer tests. |
| Prompt input | `aws_pricing_result` alone adds about 71,086 serialized characters to requirements; the architecture prompt serializes it despite being unrelated to routing. | Build a field-selected architecture context with complete source evidence and approved design; omit calculator transport/result blobs. Record what was included. |
| Design stability | Graphs are regenerated when the underlying graph is valid but panel text is wrong. | Freeze accepted services, relationships, ownership and assumptions; version genuine semantic changes explicitly. |
| Dependent content | Final graph planning currently happens after scope, pricing and SOW writing. A genuine graph correction can leave those outputs on a prior design. | Accept the canonical graph before dependent authoring; propagate its version through scope, pricing, conceptual flow, service table and export. Invalidate and refresh affected descendants when semantics change. |
| Process semantics | `process_flow.describe` maps any `route` to incoming requests and combines `retrieve`, `sync`, `ingest`. Its generic fallback produces “uses … for invoke.” | Generate a short, evidence-backed workflow story from approved capabilities and operations. Distinguish request direction, data movement, ingestion, retrieval and outbound egress. |
| Projection consistency | Plain narrative XML uses `overviewSource` and `internal_`; mixed XML uses `sourceNode` and `flow_`. The decorator infers meaning from these conventions and numbers local plumbing. | Give all renderers a shared projection contract containing original graph paths and link category. Process steps must not depend on XML ID prefixes. |
| Visual hierarchy | V52 exposes local service wiring, repeated AZ egress and subsystem relationships at the same level. | Show a primary workflow with necessary branches; retain the full connection graph on the existing detail page. Parallel replicas may share process steps without losing either deployment. |
| Control classification | V52 puts QuickSight on a shared-control rail and hides its dashboard/query relationships because `placement_role=operations`. | Classify by workflow purpose and service capability. Business reporting is not automatically shared infrastructure control. |
| Connector routing | Renderer branches have different anchor/routing policies; the first v52 review found endpoints detached below icons. | Apply the same actual-icon anchor contract, label obstacles and local routing rules to every renderer; select candidates using verified geometry. |
| Review ownership | Findings only have `visual` or `architecture`; misleading panel prose is treated as a graph defect. | Findings need stage, affected IDs, evidence, severity and an actionable repair target. Route prose repairs to the story and geometry repairs to layout. |
| Retry budgets | Nested correction calls consume a global call-name allowance before later outer attempts can use it. | Budget semantic repair, story repair, geometry candidates and transport retries explicitly; record usage and preserve successful upstream stages. |
| Acceptance/export | A rendered image or completed preview is treated as success by harnesses. Word squeezes this 4093 × 3535 diagram into 5.5 × 4.75 inches. | Test the final accepted asset and actual document readability. Keep available-with-warning distinct from verified-ready. |
| Service table | The model/validator require every instance ID, and the renderer displays every instance as a separate row. | Preserve every component ID for coverage while grouping equivalent AZ replicas into one display row. |

## Design choice

Three approaches were considered:

1. Extend keyword rules and add retries: smallest immediate change, but retains the demonstrated mismatch between semantic errors and their repair owner.
2. Replace the entire renderer with model-authored XML: more layout freedom, but trades existing deterministic ownership/provenance checks for new failure modes and still requires review/repair contracts.
3. **Recommended: retain the existing stack, introduce one typed architecture/projection/story contract, and separate repair stages.** This addresses the observed causes while preserving AWS icons, boundaries, editable detail pages and SOW styling.

This recommendation is an implementation proposal, not a claim that the broad redesign is already complete. The user's replica-table correction is a small, independently authorized fix and is implemented separately.

## Proposed contracts and responsibilities

- **Architecture context:** full relevant source plus evidence-linked requirements, selected services, existing systems, website region, assumptions and constraints. Explicitly exclude pricing result blobs, prior diagnostic images and unrelated section payloads. No arbitrary source truncation; large source must be chunked with coverage records.
- **Frozen graph:** retain current node IDs; assign stable edge IDs within a graph version. Store operation type, initiator, data direction and evidence references. Accept this semantic graph after service design and before scope/pricing/SOW generation. Dependent artifacts record its version. A genuine semantic correction refreshes affected descendants before the new version is published; layout/story changes do not change its graph hash or rerun unrelated authoring.
- **Overview projection:** display groups/nodes, original node memberships, each visible connection's exact directed edge paths, and `story`, `internal` or `shared_control` category. Functional grouping is separate from account/region/VPC/AZ/subnet ownership.
- **Process story:** Opus drafts headings of approximately 2–4 words and one plain sentence per step from approved workflow facts. Each step references graph edge IDs and nodes. Target 6–10 overview steps, with up to 12; additional technical detail remains in the detail graph/table rather than expanding the side panel indefinitely. Parallel AZ copies can share a step. This is a readability target with consolidation, not a new whole-SOW failure gate.
- **Renderer:** owns geometry, icons, labels and anchors only. Number badges use process-step mappings; they do not create relationships. No service selection or semantic prose is generated by the renderer.
- **Review:** deterministic topology/geometry/provenance checks first, Astra semantic/visual review second. A finding has `stage`, `rule_id`, affected node/edge/step IDs, severity, evidence and repair instruction. A panel error cannot implicitly authorize a topology rewrite.
- **Repair:** reuse accepted upstream artifacts; at most three presentation candidates, with at most one transport retry per model call. Real architecture findings get their own bounded semantic correction allowance. Retain successful images during provider/rendering outages and report remaining problems truthfully.
- **Models:** retain the configured Haiku/Opus/Astra choices and default embedding model. Opus owns semantic design/story; Astra checks semantics and the exported image; deterministic code owns rendering and coverage. No model upgrade is proposed as the root fix.

## Publication and production criteria

The normal acceptance outcome is a verified diagram with an empty user-facing issue list, not suppressed warnings. Genuine outages or unresolved semantic defects remain distinguishable; the SOW text stays available. Never relabel a failed review as passed to make the preview quiet.

Preserve architecture logic, fixed AWS boundary names/badges, full-size icons with labels below, no connector word labels, and a process panel aligned to the architecture height. Use a compact story and page-aware figure layout so both diagram and process text are readable in Word; adapt layout/page orientation rather than shrinking a dense image indiscriminately. Keep current table styling and chronological service-role order.

A release test must use the same source files, title/project, selected sections, region, pricing/timeline/template options, feature flags, prompts and effective profiles as the website. It must validate every selected section and selected diagram, including the separate `conceptual_flow_asset`, in the actual final preview and saved DOCX, not an intermediate “good” image. Missing selected content, stale architecture versions and unavailable conceptual diagrams must fail normal-path acceptance even if the architecture PNG is present. Record all failed runs; do not select only successful seeds.

## Replica-table semantics

Combine equivalent AZ copies only when service identity, role/purpose and deployment context match. Keep every original instance ID in the coverage audit. Preserve account/region/VPC/subnet distinctions and different roles such as database writer versus standby, or S3 assets versus evidence.

Expected v52 display:

| AWS service | Role in this project |
|---|---|
| AWS Lambda — AZ A & AZ B | Connector Lambda across private subnets calling Hybris order APIs and enterprise OTP APIs. |
| NAT Gateway — AZ A & AZ B | Provides outbound-only egress for connector calls toward the Internet Gateway. |

## Scope and remaining work

This turn audits and plans the larger pipeline redesign and implements/tests the table deduplication. It does not certify a repaired v52 diagram or silently remove review warnings. No restart, commit, deployment or push is included. The staged implementation plan defines how subsequent work must prove parity and acceptance before claiming a diagram fix.
