# Architecture planning contract

The diagram model now returns a compact design contract in the same call as its
graph. It records the view, reference pattern adaptation, evidence status of design
decisions, and directed paths for independent runtime, migration, analytics and
model-lifecycle flows. This is not a hidden-reasoning transcript or a certification.

The deterministic gate rejects missing paths, contradictory arrow directions,
unknown flow membership and disconnected non-control nodes. Explicit graph connections
missing only from the redundant flow checklist are preserved and logged as
`unclassified_connections`; this bookkeeping omission must not erase the architecture.
It never invents a chain when connections are missing. Invalid specifications get
one correction call; repeated failure uses the existing explicitly marked fallback.
Valid plans need no extra model call. Existing saved graphs remain readable without
the new metadata, and logs label them `view=legacy` rather than checked contracts.

Logical ELK views can group dedicated regional components by flow. Shared systems
remain single nodes, external systems stay external, global controls remain at
account level, and VPC containment takes precedence. Deployment views do not add
functional lane containers. PNG and draw.io continue to use the same geometry.

Prompts distinguish existing product identity from proposed AWS service choices;
reference diagrams supply patterns, not evidence of the customer's deployment.
Design instructions cover ownership, systems of record, ingress, egress, endpoints,
runtime hosting, storage, identity, availability and unresolved interfaces.

Structural checks cannot prove that a source fact or service choice is correct.
The image reviewer and human architecture review remain necessary.

## Live validation and replay

Ten live diagram-stage runs were performed against the Axis BRD-derived objective,
scope boundaries and architecture narrative on 22 October 2026. The first reproduced
the generic fallback. Later runs exposed edge pruning, false service-name matching,
invalid JSON, omitted purpose subtitles and reviewer-induced readability regressions.
The sixth produced ten nodes and ten edges without fallback, overlaps or crossings.
Later runs tested the additional request for proposed private networking, AZs,
subnets and clean figures. Run ten includes private/public subnet membership and
two labelled AZs, but page-size readability and semantic completeness remain open
issues. These are diagnostic outputs, not a certified design or a cross-BRD benchmark.
Saved responses were also replayed locally to compare layout variants without
additional model calls. Those offline replays are not extra live generations.

## Proposed deployment and clean figures

The architect may propose supporting networking, security and availability absent
from the BRD. It must distinguish proposed choices from confirmed client facts and
respect business scope. Network and security icons are optional design candidates,
not evidence of client-owned infrastructure. Global IAM must not be collapsed into
a regional control bundle. Correct AWS service containment still takes precedence.
The guidance uses the AWS [Lambda VPC networking guidance](https://docs.aws.amazon.com/lambda/latest/dg/configuration-vpc-internet.html)
and [ALB subnet requirements](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/application-load-balancers.html).

Titles, generated notes, captions and editing links are not emitted around the
figure in client documents. Diagram metadata remains available for editing/auditing;
the authored Solution Architecture section and its explanatory bullets remain intact.

Every normal diagram invocation now writes an `Architecture Inputs` snapshot beside
raw model logs (except in unit tests). These contain customer project data: keep them
local, excluded from Git, and subject to the same retention controls as existing logs.
Replay exact snapshots with `scripts/iterate_diagram.py --inputs <snapshot>
--output <local-folder> --live`. This invokes the real diagram service and visual
reviewer but does not create SOW records or upload documents. Omit `--live` and supply
`--response <saved-response>` for offline replay. Historical runs without a snapshot
can be reconstructed from requirements/scope/narrative logs using the other flags.

## Conditional networking and compact connections

The subsequent visual-reference feedback supersedes the private-VPC baseline:
enterprise data alone does not mandate customer VPC attachment. Select VPCs,
AZs, subnets, NAT and endpoints for a concrete runtime/private-connectivity need;
managed-serverless designs may legitimately omit them. The visual reviewer must
not report their absence as a violation without a required dependency.

ELK now compares flat layered and independently laid-out nested boundaries, with
external systems aligned to their actual communication partners. Icon-led variants
avoid oversized service cards and optional logical-flow boxes; real AWS ownership
and network boundaries remain intact. All original directed edges are retained.
Shortest orthogonal routing selects facing ports, avoids components/unrelated
containers/header text, and penalises bends, crossings and shared line segments.
Icons receive connectors at their visible glyphs, not invisible caption bounds.

Diagnostics include connector bends, normalized length, longest connector fraction,
detour ratios, crossings and estimated page-size labels. Layout selection balances
these metrics; the vision reviewer cannot accept a materially worse aggregate
layout score. Local alternatives share a bounded layout time budget and make no
additional model calls. This is a quality heuristic, not a guarantee of a perfect
or architecturally certified design.

Three further live Axis diagram-stage runs (11–13) and several saved-response
replays were used for this revision. These are not full SOW runs, nor a benchmark
across all BRDs. The input is the same saved BRD-derived pipeline context.

The final replay retained 14 components and 9 directed connections, with zero
component overlaps, connector/component intersections, or connector crossings.
The longest routed connection decreased from 1.832 to 0.682 times the occupied
diagram's longest dimension on the same plan; estimated main text improved from
7.4pt to 8.73pt at the configured Word figure size. A longer shared-CRM connection
remains. These measurements do not establish parity with every hand-made reference.
The targeted regression suite passes 125 tests, including required private VPC/AZ/
subnet containment. Saved artifacts are under the ignored local
`backend/output/diagram-iterations/axis-reviewed-final/` directory.

### Follow-up: actual visual trace and reference composition

The earlier zero-crossing result was insufficient: connectors followed external
card borders, shared segments looked like junctions, and the CRM loop obscured
the flow. The old result is not a visual acceptance benchmark.

Routing now uses perpendicular visible terminals and distinct ports, scores false
junctions/shared segments, and preserves operation labels instead of deleting
them after five captions. Account/region display names are always `AWS Account`
and `Region`; their distinct metadata identities remain unchanged.

Workflow bands were rejected after inspecting the three human references again.
Only public/private subnets receive pale green/cyan fills. Functional groups and
other boundaries remain white, and flow IDs do not create visible boxes. Choose
a clear processing spine, nearby branches, and peripheral shared controls. Actual
VPC/AZ/subnet boundaries remain intact; references do not justify invented VPCs.
Global controls stay at account level. PNG and draw.io use the same palette.

Official icon-catalogue service names replace feature-specific primary labels.
One AWS Lambda overview icon represents handlers sharing a deployment boundary;
the planner must consolidate their paths, not silently delete nodes or edges.
Distinct deployments remain distinct. Storage buckets with different purposes
are not collapsed merely because their service icon matches. Planning and review
share these composition rules. A clean geometry score alone is not acceptance.

The same captured Axis plan is replayed during layout iteration to isolate renderer
changes from model variability, followed by fresh diagram-only Bedrock tests.
No full SOW, storage upload or database write is needed for these iterations.
