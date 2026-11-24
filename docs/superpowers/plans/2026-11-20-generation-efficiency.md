# Generation efficiency implementation plan

Approved scope: recommendations 1, 2, 3, 5 and 6 from the preceding conversation.
Do not change concurrency, models, quality gates or source completeness.

- Add configurable Converse cache checkpoints to stable prefixes, including writer baseline boundaries. Remove only an exact system-prefix duplicate from user content.
- Reuse validated structured stage responses within the same preview/run, with bounded memory and expiry. Hash complete prompts, model, system rules and configuration. Revalidate hits; never cache errors or unvalidated outputs.
- Keep existing graph-preserving visual repairs; make structural corrections use original contract plus latest rejected candidate instead of accumulating obsolete candidates.
- Record cache read/write tokens and wall time per model/stage alongside existing usage, preserving existing counters.
- Test lossless prompt handling, cache isolation/invalidation/expiry, retry correctness, and existing model/reliability tests. Run a small live Bedrock cache probe if credentials permit. No browser tests or server restarts.
