# Diagram pipeline v52 implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:executing-plans or superpowers:subagent-driven-development to implement this plan task by task. Preserve existing user edits. No automatic commit, push or restart.

**Goal:** Produce a clear, source-faithful architecture and short process story through the same full request used by the website, with targeted repairs and verified preview/export output.

**Architecture:** Freeze approved semantic design, then derive one shared overview projection and workflow story. Renderers consume that contract; typed findings route repairs to the failing stage. Complete-request tests replace image-exists assertions as acceptance evidence.

**Tech Stack:** Flask/React, Python dataclasses/JSON contracts, configured AWS Bedrock profiles, draw.io XML/Desktop, python-docx, pytest.

**Spec:** `docs/superpowers/specs/2026-11-18-diagram-pipeline-v52-design.md`.

## Global constraints

- Website region wins; preserve source-backed existing systems, assumptions and ownership.
- Keep current model selections: Haiku, Opus, Astra; embedding model unchanged.
- No topology changes for prose/geometry repairs; preserve full graph/detail page and service-table coverage.
- Fixed boundary names/badges, below-icon captions, no connector word labels, aligned process panel, current SOW table styling.
- Target 6–10 process steps, at most 12 in the overview; consolidate excess detail instead of failing the whole SOW.
- At most three presentation candidates and one transport retry per model call; semantic corrections have a separate bounded allowance.
- Real unresolved defects remain visible. An empty warning list must result from a passing final artifact, not bypassed review.

## Review focus

**19 November user priority update:** Minor text overlaps are advisory, including readable captions and boundary headings. Prefer short straight routes over detours to avoid cosmetic contact. Optimize connector count, bends, crossings and whitespace together. Semantic mistakes, detached arrows, icon obstruction and genuinely unreadable/ambiguous labels remain substantive. References below to an empty issue list mean no unresolved substantive findings; recorded cosmetic advisories alone must not reject a usable diagram or trigger model retries.

1. A genuine fresh mixed deployment differs from a saved serverless replay — Stage 1 tests complete manifests and all renderer families.
2. NAT egress, knowledge ingestion/pull and runtime retrieval have different initiators/data directions — Stages 2–3 pin these semantics.
3. Repeated AZ resources share a display row/step but remain separate graph instances — Stage 0 and Stage 3 verify coverage.
4. Text review failures must not cause new service choices; a later candidate must still have a usable budget — Stage 5 fault tests verify hashes and stage calls.
5. A high-resolution image can pass review yet be unreadable or mismatched in Word — Stages 4 and 6 inspect actual document rendering and embedded asset identity.

## Stage 0 — Group equivalent service-table replicas

**Files:** `backend/app/diagram/architecture_text.py`, `backend/tests/test_architecture_table_replicas.py`, `backend/scripts/verify_architecture_service_table.py`.

**Interface:** Existing per-component table-role JSON remains unchanged. Display grouping produces a row with multiple `component_ids`; the table audit records `row_component_ids`, all covered IDs and actual displayed row count. No graph mutation.

- [x] Reproduce the v52 Lambda/NAT pairs and negative cases: writer/standby, different buckets, different account/region/purpose.
- [x] Group only equivalent roles across explicit distinct AZ copies, preserving all component IDs and chronological first occurrence.
- [x] Independently review and run the focused tests; replay the actual v52 role response without new model calls.

**Exit:** Four example rows become two; v52's 31 table component IDs remain covered by 29 displayed rows. Word/preview use the same grouped Markdown. Real role differences remain separate.

**Verified 18 November:** 88 tests and 2 subtests passed across table coverage, regeneration, document building and preview editing; one existing LangChain deprecation warning. Independent review reproduced and then cleared distinct-upstream and second-hop-difference cases. Incoming/outgoing labeled graph neighborhoods are refined until equivalence classes stabilize, so matching prose alone cannot merge different behavior. Exact saved-v52 replay and Word save/reopen evidence: `backend/output/verification/tata-v52-service-table-deduped.json` and `.md`. These are offline table tests, not fresh BRD/model/diagram acceptance runs.

## Stage 1 — Reproduce the website request and define real success

**Files:** create `backend/app/diagram/run_manifest.py`, `backend/scripts/verify_full_sow_request.py`, `backend/tests/test_diagram_run_manifest.py`; update `backend/scripts/replay_preview_http.py`, `backend/scripts/replay_brd_preview.py`; use `frontend/src/services/apiService.ts` and `backend/app/core/server.py` as the request contract.

**Interfaces:** `GenerationManifest` stores schema version, source paths/hashes, company/project/objective/mode, ordered sections, template/timeline/pricing options, selected region, feature flags, effective model IDs, source-extraction digest and code/prompt fingerprints. Configuration capture is an allowlist and excludes credentials/session tokens; never dump `.env`. `assert_diagram_acceptance(asset, manifest)` distinguishes `verified`, `available_with_warning` and `unavailable` and fails tests for the latter two.

- [ ] Test that the v52 manifest retains all 23 sections and the original DOCX/XLSX source set; an architecture-only substitute or hash mismatch must be rejected.
- [ ] Extend multipart reservation/upload/status replay to consume that manifest. Isolate only external archive persistence; exercise the production document builder/finalize path and record the isolation explicitly.
- [ ] Assert all selected sections are present with content appropriate to their contracts. Check architecture assets AND the separately stored `conceptual_flow_asset` when selected: images, successful validation/review according to each diagram contract, no unresolved findings, empty warning list, complete coverage and matching export. A missing conceptual diagram or empty selected timeline must fail acceptance even when the architecture PNG exists. This must also fail on the saved v52 architecture audit.
- [ ] Run a browser transport/download case with the same manifest. Capture one baseline fresh v52 run and every stage artifact under one run ID.

**Verification:** `pytest tests/test_diagram_run_manifest.py -q`; then `python scripts/verify_full_sow_request.py --manifest <v52-manifest.json>`. Baseline is expected to fail acceptance and produce a complete diagnostic bundle. Do not represent it as a passing diagram test.

## Stage 2 — Build a focused context and freeze architecture semantics

**Files:** create `backend/app/diagram/contracts.py`, `backend/app/diagram/context.py`, `backend/tests/test_architecture_context_contract.py`; update `service.py:_prompt/_generate_specs`, `service_design.py`, `plan_contract.py`, `backend/app/core/state.py`, `backend/app/core/graph.py`, `backend/app/core/nodes.py`, `backend/app/preview/architecture_regeneration.py`.

**Interfaces:** `ArchitectureContext` contains source/evidence coverage, requirements, approved service design, assumptions, existing systems and deployment constraints. `FrozenArchitecture` includes version/hash, nodes and stable per-version edge IDs with operation type, initiator, data direction and evidence references. Core state stores `architecture_version` and `artifact_architecture_versions` for scope, pricing, authored architecture-dependent sections, conceptual flow, service table and diagram. Existing stored specs get an explicit compatibility adapter; unknown operation remains unknown rather than inferred as inbound.

- [ ] Test full source/evidence retention and omission of `aws_pricing_result` and unrelated section payloads. Test website region precedence and large source chunk coverage.
- [ ] Produce one accepted canonical graph from the selected service design before scope/pricing/section writing. Verify each service maps to graph instances and each edge to its operation/evidence; preserve source-owned systems and distinguish separate ownership from an unspecified account placeholder.
- [ ] Freeze and hash the accepted graph. Test that prose/layout repair leaves that hash unchanged. A genuine missing-service correction creates a new version and explicitly invalidates affected scope, assumptions, pricing, conceptual flow and table outputs; refresh them before atomic publication. Unrefreshed descendants remain marked stale and cannot pass final acceptance. Preserve the prior complete preview if refresh fails.

**Exit:** No pricing transport blob in the diagram prompt; no silent evidence loss; stable services and ownership through visual retries. Re-run the complete v52 manifest and compare stage inputs to baseline.

## Stage 3 — One projection and a meaningful workflow story

**Files:** create `backend/app/diagram/projection.py`, `backend/app/diagram/process_story.py`, `backend/tests/test_process_story_contract.py`, `backend/tests/test_projection_parity.py`; adapt `narrative.py`, `narrative_boundaries.py`, `mixed_deployment.py`, `tiered_deployment.py`, `process_flow.py`.

**Interfaces:** `OverviewProjection` exposes display-node memberships and `OverviewConnection(id, source, target, edge_paths, category)` where category is `story`, `internal` or `shared_control`. `ProcessStep(id, title, description, node_ids, edge_ids, flow_kind)` maps one story step to one or more genuine paths. The annotator consumes this data directly, never XML ID prefixes.

- [ ] Add the actual v52 failing edges as regressions: outbound connector→NAT→IGW, staging→knowledge-base ingestion, orchestrator→knowledge-base retrieval, chat invocation, conversation-event delivery and warehouse loading.
- [ ] Test that plain, mixed and tiered renderers retain equivalent path coverage and that local wiring does not become dozens of process entries. Expose QuickSight dashboard/query relationships as business flow rather than hiding them as controls.
- [ ] Use Opus to draft concise headings/single-sentence explanations from accepted workflows and typed operations; validate IDs, direction and claims. Consolidate parallel AZ actions and secondary technical detail to meet the overview story budget.
- [ ] Remove semantic sentence generation from renderer keyword rules. Keep layout/annotation deterministic; perform a targeted story correction when its validation/review fails.

**Exit:** V52's process story correctly explains outbound enterprise calls, knowledge ingestion versus answering, chat handling and analytics. No “uses … for invoke” placeholders; all numbered steps trace to graph paths; original nodes/edges remain unchanged.

## Stage 4 — Consistent, page-aware layout and connector contracts

**Files:** update `review.py`, `mixed_deployment.py`, `compact_mixed.py`, `narrative.py`, `narrative_boundaries.py`, `tiered_deployment.py`, `routing_repair.py`, `document/document_builder.py`; create `backend/tests/test_renderer_contract_parity.py`.

**Interfaces:** Every renderer accepts the same frozen graph, projection and process story and returns `RenderedCandidate` with image/XML, icon rectangles, connector anchors/paths, ownership membership, page-size data and diagnostics. Geometry variations never modify semantic contracts.

- [ ] Reproduce detached bottom ports from v52 in every relevant renderer; assert endpoints touch actual visible icon bounds and never captions/whitespace.
- [ ] Route internal links locally, primary story links first, and secondary branches in reserved corridors. Use the existing crossing/length/bend metrics to compare deterministic layout candidates before another model call.
- [ ] Keep parallel AZ resources in correct boundaries while avoiding separate narrative steps for equivalent copies. Keep control fan-out on the detail page.
- [ ] Fit story and architecture to the intended SOW page. Test normal-size Word readability and panel top/bottom alignment; use a dedicated figure page/orientation when needed instead of the fixed 4.75-inch shrink box, restoring surrounding document styling.

**Exit:** No disconnected endpoints, node/caption overlaps, wrong containment or ambiguous shared junctions. V52 meets the existing crossing acceptance bound without deleting real paths. Visual comparison is made on both preview and rendered DOCX pages.

## Stage 5 — Repair the failing stage, with explicit budgets

**Files:** create `backend/app/diagram/repair_controller.py`, `backend/tests/test_targeted_diagram_repair.py`; update `narrative.py:review`, `reliability.py`, `service.py:_generate_assets_bounded`, `core/bedrock_llm.py`, `agents/architecture_reviewer_agent.py`, `core/nodes.py`, `preview/architecture_regeneration.py`.

**Interfaces:** `ReviewFinding(stage, rule_id, severity, node_ids, edge_ids, step_ids, evidence, repair_instruction)`. Stages are `source`, `service_design`, `graph`, `story`, `layout`, `render`, `export`, `provider`. `RepairController` consumes findings and versioned artifacts, preserves accepted upstream outputs and records per-stage allowances separately from transport retries.

- [ ] Test a valid outbound graph with wrong panel text: only story generation runs again, graph hash stays fixed, pricing/section writing are not repeated.
- [ ] Test detached geometry: only layout/render/review runs again. A real missing service or wrong relationship must go through semantic correction and the Stage 2 dependency-version refresh, including scope/assumptions/conceptual input, instead. Assert no fresh asset is published against stale pricing or section semantics.
- [ ] Reproduce the v52 exhausted-call-name scenario and ensure a presentation repair cannot spend or require an architecture correction allowance. Assert maximum candidate count and cancellation responsiveness.
- [ ] Score semantic validity before cosmetic issue counts. Retain the best genuine candidate on outages, but never mark it verified while substantive findings remain.

**Exit:** Reviewer findings produce observable corrections in their own artifact; repeated deterministic prose errors cannot cause three expensive graph replans. Live v52 passes final review with an empty issue list within the bounded repair flow.

## Stage 6 — Complete-request regression and release gate

**Files:** `backend/scripts/verify_full_sow_request.py`, `backend/tests/test_preview_draft_lifecycle.py`, `backend/tests/test_architecture_regeneration.py`, `backend/tests/test_architecture_text.py`, frontend preview/download integration tests, verification artifacts under `backend/output/verification/`.

**Inputs:** Exact manifests for Tata CLiQ (all source files/23 selected sections), Kingfisher, Apollo, Halfords and Wise. Use fresh extraction/service planning; saved graphs are supplementary renderer tests only.

- [ ] Run three independent complete requests per BRD with process flow enabled, then one disabled request per BRD: 20 runs total. Stop at each failure, diagnose its responsible stage, and repeat the affected acceptance set after the fix. Preserve failed-run evidence.
- [ ] Require every selected architecture to be verified-ready with no fallback or unresolved findings; missing review is not a pass. Confirm model/profile/flag fingerprints and source coverage match each manifest.
- [ ] Compare preview, persisted draft and finalized DOCX: same final architecture and conceptual diagrams/versions, every selected section present and meaningful under its own contract, complete deduplicated service coverage, selected populated Gantt, genuine calculator hyperlink when an estimate was saved, existing table styling. Add explicit negative fixtures for an unavailable conceptual asset, empty selected section and stale scope after service correction.
- [ ] Inject model timeout, invalid JSON, renderer failure, review outage, save/export failure and cancellation. Verify bounded retries and truthful degraded status without loss of already generated SOW content.
- [ ] Run the full relevant regression suite, review all changes independently, and render representative Word documents at normal page scale. Record observed latency/cost and unresolved limitations; do not substitute a cherry-picked image for this gate.

**Release condition:** All 20 normal-path manifests pass the actual final-artifact checks, all failure-injection cases preserve content and correctly distinguish degraded output, and no required test failure is waived without a documented reason. Activation/restart remains a separate explicit action; user currently prefers restarting the backend themselves.

## Execution status

Stages 0–5 now have implementation and local regression coverage in the shared checkout. Stage 6 remains incomplete: no complete request has yet met every release check. Refreshed credentials worked in King05/Tata06; both completed the real preview, draft, finalize and download paths but failed strict acceptance. Their pricing coverage, scope review, timeline export and geometry findings have been repaired and independently reviewed. Fresh Tata07/King06 requests are running against frozen application code. No production-readiness claim, backend restart, commit or push has been made.
