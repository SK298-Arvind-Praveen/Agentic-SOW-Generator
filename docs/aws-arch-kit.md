# Optional AWS architecture kit renderer

Set `ARCHITECTURE_DIAGRAM_ENGINE=aws_arch_kit` to use the kit (configured locally).
This mode uses the existing BRD-derived
requirements and solution architecture narrative to build a validated plan, then
compiles that plan into drawing instructions for the kit's diagram MCP. It does
not use the smoke-test architecture or execute model-written
Python. MCP is a renderer, not an independent architect; good layout and correct
architecture still depend on the plan. No diagram engine guarantees correctness.

## This Windows machine (VS Code)

The working Ubuntu installation can be used directly. Add these to the backend
`.env`, then restart the backend:

```dotenv
ARCHITECTURE_DIAGRAM_ENGINE=aws_arch_kit
AWS_ARCH_KIT_WSL_DISTRO=Ubuntu
AWS_ARCH_KIT_WSL_PYTHON=/home/admin1212/aws-arch-kit-test.Tkq6wd/env/bin/python3
AWS_ARCH_KIT_TIMEOUT_SECONDS=90
ARCHITECTURE_VISION_REVIEW_ENABLED=true
```

No manual MCP server or port is needed. Generate a SOW with Solution Architecture
selected. The terminal prints `[DIAGRAM][ARCH-KIT] Starting` followed by `Complete`.
If the renderer fails, a logged fallback uses the same plan with the built-in
renderer. Flowcharts remain on the built-in renderer. Assets record the actual
`layout_engine` and any `renderer_fallback` reason.

For an offline test, set the same runtime variables in your VS Code terminal and
run `python scripts/smoke_arch_kit.py` from `backend` with the backend venv active.
It writes `backend/output/arch_kit_smoke.png`; this is only a test fixture, not a
proposed architecture for a client. The script does not load `.env` itself.

To revert, set `ARCHITECTURE_DIAGRAM_ENGINE=builtin` and restart. The retired
`ARCHITECTURE_LAYOUT_ENGINE` variable does not activate this mode.

## Linux / Render Docker

Build with `INSTALL_AWS_ARCH_KIT=true` (Docker build argument), and set:

```dotenv
ARCHITECTURE_DIAGRAM_ENGINE=aws_arch_kit
AWS_ARCH_KIT_PYTHON=/opt/aws-arch-kit/bin/python
AWS_ARCH_KIT_TIMEOUT_SECONDS=90
```

Do not set the WSL variables on Render. If your hosting build does not expose build
arguments, change the Dockerfile's optional argument default to `true` before
deploying. Leave it false when using the built-in renderer. The optional package
is the same pinned legacy version used by the downloaded kit, isolated from the
backend; review/upgrade it before relying on it for production.

## Bounded vision review

After the architecture overview renders, a separate reviewer sees its actual PNG,
the validated component/connection plan, geometry measurements and a short extract
of the Solution Architecture narrative. It checks readability, crossings, grouping,
containment and agreement with the design. Flowcharts are not sent for image review.

- Uses the configured fast model (Haiku profile) by default. Override with
  `BEDROCK_DIAGRAM_REVIEW_MODEL_ID` if necessary; the profile must support Converse images.
- One image call only. No model fallback, SDK retry or output-expansion retry.
- Architecture findings can trigger one short placement-validation call to the
  diagram planner. Only evidence-quoted scope/role corrections are allowed. Missing
  components, incorrect connections or ownership changes remain findings for human
  follow-up, rather than being invented or silently rewritten.
- One re-render maximum. Reordering, modest spacing increases and validated
  placements preserve every node, edge, label and icon. Geometry regressions or a
  failed kit re-render keep the original image.
- A shared 60-second additional-work budget limits review/repair scheduling and
  rendering; Bedrock read timeout is at most 22 seconds with no retries. This is a
  bounded best-effort budget, not a guarantee against OS/network scheduling delays.
- A repaired image is **not visually re-reviewed**. The log says so; geometry
  acceptance is not a claim that the diagram is perfect or architecturally certified.
- Failure or timeout in review never discards the existing diagram or fails the SOW.
- Review token usage uses the normal per-SOW tracker. Audit files live under
  `backend/output/llm-outputs/diagram-reviews/<run>/`: `before.png`, optional
  `candidate.png`, and `review.json` (findings, proposed changes, acceptance/rejection,
  before/after geometry, and selected specification). Raw model text also uses the
  normal `llm-debug` logger. These local files can contain client design information;
  apply the same retention/access policy as other debug outputs.
- Set `ARCHITECTURE_VISION_REVIEW_ENABLED=false` to turn review off independently
  of the renderer. To revert rendering too, use `ARCHITECTURE_DIAGRAM_ENGINE=builtin`.

Image payload sizing follows the [Bedrock Converse image limits](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Message.html).

## Renderer safety

- Source text is passed as escaped labels, never executable code.
- Each job has a temporary directory, deleted after completion or ordinary errors.
- Rendering children receive no application AWS credentials and use empty AWS
  profile paths. This is process isolation, not an OS security sandbox.
- Tool errors, deadlines, output paths, image size and PNG validity are checked.
- Rendering is capped at 90 seconds by default (configurable 15–180 seconds,
  with up to 20 seconds for process startup/cleanup), then falls back.
- The PNG is embedded normally; editable draw.io data retains the same plan and
  geometry, although the visual styling differs slightly.
- No paid Bedrock calls are needed to smoke-test the renderer itself.
