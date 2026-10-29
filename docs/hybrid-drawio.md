# Local hybrid draw.io engine

Set `ARCHITECTURE_DIAGRAM_ENGINE=hybrid_drawio` in `backend/config/.env`,
then restart the backend. Roll back by setting it to `hybrid`.
Docker/Render deployment is deliberately unchanged.

## Install once

1. Install draw.io Desktop. Windows auto-detects the standard Program Files
   and per-user locations; alternatively set `DRAWIO_DESKTOP_BINARY` to the
   executable's absolute path.
2. From the repository root, run:
   `npm ci --prefix tools/drawio-renderer --ignore-scripts --no-audit --no-fund`.
3. Node must be on PATH (or set `DRAWIO_NODE_BINARY`). Keep the existing
   `tools/architecture-layout` dependencies installed too.

The latest published official `@drawio/mcp` checked on 28 October 2026 was
1.10.0, pinned in the separate package and lockfile. No runtime `npx latest`
downloads. Source: https://github.com/jgraph/drawio-mcp .

## What changes

The BRD, architecture planner, reference knowledge, hybrid composition, geometry
checks, preview regeneration and vision reviewer remain in use. The new engine
sends the fixed draw.io XML to the official **local stdio MCP** tool
`open_drawio_xml`. It decodes the processed XML from the returned editor URL
without navigating to it, then invokes the local Desktop CLI to export PNG.
The asset retains that exact XML for editing and records the MCP version.

MCP alone does not export PNG. Desktop is the actual raster renderer.
An isolated Node preload suppresses the MCP's browser-launch subprocess side
effect; the installed official package is not modified. This wrapper must not
be loaded into the application or Desktop exporter.

No hosted MCP or cloud export endpoint receives diagrams. The adapter does not
call shape search or optional CDN-based routing. Existing embedded AWS icons,
node placement and connector geometry are retained for a rendering-only
comparison; this is not a new architecture reasoning model or auto-layout pass.

Missing dependencies, failed MCP calls, graph/geometry changes and invalid PNGs
fail visibly through the existing diagram-unavailable/regenerate path. There
is no silent Pillow fallback reported as draw.io success. Each export uses a
unique temporary directory and Desktop profile, a bounded deadline and PNG
validation. Temporary data is cleaned after success/failure. AWS credentials
are not forwarded to the renderer subprocesses.

## Test without a new Bedrock generation

For a synthetic VPC/public/private-subnet export fixture (not an architecture
recommendation), run `python scripts/smoke_drawio.py` from `backend`.

From `backend`, using its virtual environment:

```powershell
$env:ARCHITECTURE_DIAGRAM_ENGINE='hybrid_drawio'
.\venv\Scripts\python.exe -X utf8 scripts/replay_hybrid_diagram.py output/diagram-iterations/axis-hybrid-delivery-22/asset.json --output output/drawio-local-test/axis
```

This reuses a saved architecture plan, not a fresh BRD analysis. Omit `--review`
to avoid a new Bedrock vision call. The output folder contains `diagram.png`,
`diagram.drawio` and `asset.json`; `layout_engine` must be `hybrid_drawio`,
`renderer_details.mcp_version` must be populated, and `renderer_fallback` empty.
