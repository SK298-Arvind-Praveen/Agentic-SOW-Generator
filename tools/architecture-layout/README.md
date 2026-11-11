# Local architecture layout

This worker uses pinned `elkjs` (EPL-2.0; see its bundled LICENSE.md). Keep
dependency license notices when redistributing. AWS icons remain subject to
AWS's architecture-icon terms; this worker does not download or alter them.

From the repository root, with Node.js/npm installed:

```powershell
npm ci --prefix tools/architecture-layout --omit=dev --ignore-scripts
```

Set `ARCHITECTURE_DIAGRAM_ENGINE=elk` in `backend/config/.env` or your backend
environment, then restart the backend. Docker installs the dependency automatically.
Non-Docker deployments must install it separately. No WSL, Graphviz, API key,
external diagram service or new LLM calls are required. Normal hosting and existing
Bedrock planning/review costs still apply.

The planner supplies components, deployment scope and directed connections. ELK
computes nested account/Region/VPC/explicit-AZ placement and orthogonal routes;
the Python renderer uses the existing AWS icon registry. External systems remain
outside the account. Managed services are not placed inside a VPC. This is a
layout engine, not an architecture designer; it never adds/removes services/edges.
Only architecture_overview uses ELK; other flowcharts retain their current renderer.

PNG and draw.io share geometry. Actual ELK geometry is used in vision-review
comparisons. A worker has a maximum 30-second deadline, no retries, a bounded
canvas, a minimal environment with no AWS credentials, and never executes
model-generated code. If it fails, the built-in renderer draws the same plan and
logs the reason in `[DIAGRAM][ELK]` and `renderer_fallback`. Crossings are counted,
not guaranteed absent. Long horizontal layouts try a vertical alternative locally.

Offline smoke test from `backend` (no AWS calls):

```powershell
.\venv\Scripts\python.exe scripts/smoke_elk.py
# Or replay an existing diagram review's original/selected architecture:
.\venv\Scripts\python.exe scripts/smoke_elk.py path/to/review.json
.\venv\Scripts\python.exe -m pytest tests/test_elk.py -q
```

Outputs go to `backend/output/elk-smoke/` as PNG, editable draw.io, and metrics.

Rollback: set `ARCHITECTURE_DIAGRAM_ENGINE=builtin`, or `aws_arch_kit` with its
previous runtime settings. Existing documents/drafts are not regenerated.

Architecture generation uses a functional overview for supported single-account,
single-region managed and VPC deployments. Private/AZ captions retain deployment
context; the second editable page records every component's physical scope and
every directed service connection in an editable register. It does not route
dense control fan-out, so a detail-page layout cannot discard the overview.
Other deployment shapes retain the compound physical renderer.

Each model stage has at most two calls (initial plus one corrective retry), shared
across pipeline resumes. Initial graph planning and semantic graph correction
have separate allowances, so a transport retry cannot prevent correction.
Rendering also retries a failed export once. Cosmetic retries retain the validated
overview instead of discarding it and spending its planning allowance again.
Image review allows two calls per candidate (up to two candidates), so a transient
failure on the first image cannot consume the corrected image's review budget.
Cancellation is never retried. After exhaustion, structural/architecture failures
and generic fallback images are withheld. Cosmetic findings and unavailable visual
reviews preserve the real diagram with a visible warning. Diagnostics are retained.
The surrounding SOW remains available and the diagram can be regenerated.
Sonnet 5.5 diagram calls start with at least 32,768 output tokens, including adaptive
reasoning, and expand to at least 65,536 on retry (provider ceiling 128,000).
This avoids reserving the full ceiling for every request. Transport defaults to
Converse, matching the successful fresh cross-BRD tests. For controlled tests,
`BEDROCK_DIAGRAM_TRANSPORT=auto` uses ConverseStream first and Converse on retry;
`converse` or `stream` pins the transport. A stream without
a completion event is rejected. Lowercase streaming error names are retryable too.

`backend/scripts/verify_architecture_delivery.py --run <pipeline-output>` verifies
preview serialization and exact PNG embedding through the production DOCX builder.

Configurable seconds (all bounded to 10–600):

| Environment variable | Default |
| --- | ---: |
| `ARCHITECTURE_MODEL_TIMEOUT_SECONDS` | 300 |
| `ARCHITECTURE_COMPOSITION_TIMEOUT_SECONDS` | 300 |
| `ARCHITECTURE_REVIEW_TIMEOUT_SECONDS` | 300 |
| `ARCHITECTURE_RENDER_TIMEOUT_SECONDS` | 300 |
| `ARCHITECTURE_LAYOUT_TIMEOUT_SECONDS` | 120 |

Audits in `backend/output/diagram-debug` include model-stage call counts, pipeline
attempts, render failures, review findings and layout metrics. Input snapshots and
raw model responses are in `backend/output/llm-debug`.
