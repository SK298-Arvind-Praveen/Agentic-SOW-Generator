# Service design efficiency

Approved scope: reduce repeated generation without changing models, retry counts,
source requirements or architecture validation. No browser tests or backend restart.

- [x] Extract source ledger during requirements analysis; assign IDs and citations in code.
- [x] Architect references ledger IDs; expand existing downstream schema in code.
- [x] Remove schedule/staffing estimation from architecture responsibility.
- [x] Repair changed fields/ID rows, then validate the complete merged object.
- [x] Retain validated service design through downstream failures with input/model invalidation.
- [x] Regression and live pipeline verification, recording limitations and timing.

Ruling: retain legacy evidence-extraction path when older callers have no verified
ledger. Do not silently rely on a malformed extraction.

Ruling: retry allowance remains unchanged. A bad patch consumes an existing attempt;
the next remaining attempt requests the complete corrected design.

Baseline: Amneal service design used 3 responses, 73,223 output tokens and
442.281 seconds, including a truncated response. Whole generation approximately
16m44s. Live comparisons must account for changed input and source length.

Review fixes: validate compact types, allow missing schema fields in patches,
permit source-verified requirement additions, and disable compact mode for JSON
recovered from malformed analysis. Cache is bounded, one-hour, memory-only and
isolated by run; it is not a cross-user or cross-restart cache.

Live iteration 1: initially blocked by expired credentials; user refreshed them.
Analysis then repeated requirements and truncated at 12k output. Further change:
materialize legacy requirement arrays from the citation ledger in code. Also
removed the absence-of-UI-keywords veto after it wrongly rejected an explicit
browser review requirement. Existing explicit negative handling remains.

Regression: initial architecture/contract suite 217 passed; review fixes 91 passed.
Broader extraction suite: 99 passed, 2 unrelated failures in existing tests
(unauthenticated preview request now 401; pricing volume fixture expectations).
No authentication or pricing behavior was weakened to make these tests pass.

Measured live Amneal service-design results through the actual fast preview graph:
- Iteration 1: 187.075 s, 26,223 output tokens (21,736 + 4,487 repair), 54 verified requirements.
- Iteration 2: 165.530 s, 23,069 output tokens (21,888 + 1,181 repair), 63 verified requirements including one architect-found omission.
- Previous saved service-design stage: 442.281 s, 73,223 output tokens.

Both runs exposed the old 12k analysis cap truncating the new ledger. Initial
headroom is now 24k (the same size that completed the live expanded retries).
No model, reasoning setting, retry allowance or downstream check was reduced.
This cap change happened after the two runs started; their measured totals still
include the wasted initial analysis attempts. Do not present a projected overall
speedup as measured.

Final verification: 261 relevant regression tests passed, 1 stale unauthenticated
endpoint fixture deselected; the separately observed pricing fixture failure is
also unchanged. Both real preview graph runs completed with no generation halt.
Iteration 1 took 985.284 s (16m25s), pricing succeeded, diagram required visual review.
Iteration 2 took 832.4 s (13m52s), pricing succeeded, diagram status ready, no
fallback, 63 source-verified requirements and no traceability issues. Its service
table covered all 16 rendered components on the first attempt.

These runs replayed the saved source and metadata using standard preview sections;
the replay script now also preserves metadata.selected_sow_sections for subsequent
tests. Do not claim an identical end-to-end comparison with the earlier run's
optional conceptual diagram. Stage-level design measurements are the useful comparison.
No browser tests, backend restart, commit or push performed. Models and existing
retry counts/quality checks remain unchanged.
