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
