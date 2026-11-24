# Generation reliability repair plan

**Goal:** Repair the recorded Tata CLiQ diagram, timeline and pricing failures without breaking previous BRDs.
**Architecture:** Preserve validated semantic plans and successful assets across presentation failures. Trace grouped diagram connections to the complete graph. Keep calculator schemas variant-specific and timeline markers consistent between preview and export.
**Tech stack:** Python, draw.io XML, Bedrock, Word OOXML, Node calculator tooling.
**Spec:** User's Tata CLiQ v51 failure report in this chat; saved generation diagnostics dated 2026-11-18.

## Constraints
- Preserve approved nodes, edges and source-backed schedules.
- Do not fabricate prices or calculator URLs.
- Bound retries; optional decoration must not discard a usable architecture.
- Retain existing user edits; do not restart services or commit without request.

## Tasks
- [x] Reproduce grouped-connector annotation and decoration failure with regression tests.
- [x] Resolve group interfaces to original graph relationships; retain a successful primary image if decoration fails and surface a warning.
- [x] Reproduce and repair timeline marker loss using actual generation and exported Word data.
- [x] Reproduce and repair OpenSearch variant mismatch without disabling calculator lint.
- [x] Replay Tata through production diagram generation with process flow on and off; inspect resulting image.
- [x] Verify Kingfisher and a third BRD; run relevant regression tests and verify document embedding.
- [x] Report evidence, remaining limitations and deployment prerequisites accurately.

## Review focus
- Group IDs and bidirectional interfaces, not only direct service edges.
- Empty overview relationships or disconnected service inventories.
- Render failure after an otherwise successful primary PNG.
- Gantt symbols cleaned before Word rendering.
- Serverless versus provisioned calculator form selection.

## Verification evidence
- Final combined regression run: 250 passed, 2 subtests passed; one existing LangChain deprecation warning. Calculator JS suite: 8 passed.
- Tata saved generation replay through `preview.architecture_regeneration.regenerate`: `backend/output/tata-v51-release`, ready, no fallback, 19 process steps, original 38 nodes/38 edges preserved, live review issues empty.
- Tata process-flow-off render: `backend/output/tata-v51-process-off`. No panel; same architecture.
- Apollo: `backend/output/apollo-process-release-v51`; live review issues empty after correcting generic uploads being described as migration, zero connector crossings.
- Kingfisher: `backend/output/kingfisher-process-final-v51`; same physical architecture, 13 process steps, no fallback.
- Live pricing: `backend/output/verification/tata-pricing-replay.json`, 23 submitted entries, USD 2749.46/month, real saved estimate URL; strict form lint retained.
- Word save/reopen: `backend/output/verification/tata-export-verified.json`, original image bytes retained, 8 weekly periods, 31 delivery cells, 4 support cells, external Open Link relationship retained.
- Independent code review covered pricing template selection and diagram provenance/preservation; identified bidirectional-summary issues were fixed and retested.

## Limits and activation
These checks replay recorded source-derived inputs through production paths; they are not new complete BRD-to-SOW authoring runs. A broad repository suite attempt was stopped because legacy tests invoke slow external renderer paths; three inspected failures assert multiple diagrams/editing controls already removed in HEAD, and their fixtures lack BEDROCK_REGION. Do not claim the full repository suite is green or guarantee external provider availability.

The user chose to restart the backend themselves. No backend restart, commit or push was performed. Existing previews/DOCX files are not rewritten automatically; a fresh preview after restart uses these fixes.
