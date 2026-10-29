# AWS architecture pattern library

The active library contains 20 curated, paraphrased patterns from official AWS
reference diagrams and developer guidance plus **10 reviewed user diagram cards**
(6 Data, 4 GenAI) from `Sample arch diagrams.zip`, version 2026-10-14.2. The new
KreditBee screenshot supersedes the earlier card with the same ID; it is not counted
twice. Previous imports from SOW documents are no longer loaded. This is an initial collection,
not a scrape of the entire AWS catalogue or an AWS-certified design library.

Each card records applicability, exclusions, directed flow, placement guidance,
source URL, publication date where available, text-review date and evidence anchors.
Sixteen historical reference diagrams are explicitly marked historical; four
developer/prescriptive guidance pages have no asserted publication date. Do not
infer current service availability or pricing from a historical reference.

Open [the visual catalogue](catalog.html) for all ten images with individual review
notes. `curated-import.json` is the hand-reviewed import manifest. `user-patterns.json`
and `references/upload-20261014/` are the runtime cards and original PNG bytes.
Each card labels category, secondary categories, logical/deployment/mixed view,
phase where visible, generic flow, styling, pitfalls, provenance and SHA-256.
Do not distribute these internal customer reference images as generated SOW content.

Nine images are eligible for visual prompting. The underwriting image is retained
in the catalogue but **text-guidance only** because its blanket VPC containment
would teach incorrect managed-service placement. Other examples carry specific
cautions (missing VPC, icons straddling AZs, functional groups mistaken for subnets).
No Cloud-only image was supplied: Cloud workloads still use applicable official
AWS cards, not an unrelated GenAI image or a fabricated customer example.

## Runtime

`app/diagram/knowledge.py` selects at most three cards using deterministic workload
phrases and synonyms. It ignores source-document transport fields and suppresses
negated/excluded/future capabilities. Explicit exclusions veto positive inventory
matches. This intentionally conservative retrieval may miss an unfamiliar phrase;
in that case the existing source-driven planner continues without reference cards.
It is not embedding similarity search and has no similarity percentage.
Workload categories are multi-label (GenAI/Data/Cloud), with category agreement used
as a ranking tie-break after applicable phrase matches. Category alone never selects
a customer example. Mixed workloads can retrieve both Data and GenAI references.

The Solution Architecture writer and diagram planner independently use the same
selector over their requirements. References are separately labelled advisory,
never merged into authoritative requirements, icon inventory, pricing or scope.
The written solution remains the diagram's design contract. Maximum reference
context is 5,000 characters; no additional model invocation, database, web request
or credentials are required for retrieval. When the selected pattern has a curated
visual, the diagram planner's existing Bedrock request includes one reference PNG
(additional image-input usage applies). The writer receives its generic text card.
The vision reviewer receives the applicable text cards alongside its generated
image, not a second reference image. ELK continues to own layout. This does not restore
the removed SOW RAG functionality or require its DynamoDB table.

The library is cached per process; restart the backend after updating it. Logs
show library version, chosen pattern IDs and context size, not customer documents.
Invalid/unavailable library data falls back to ordinary source-driven planning.

## Validation and maintenance

From `backend`, run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_architecture_knowledge.py tests/test_architecture_planning.py tests/test_elk.py -q
.\venv\Scripts\python.exe scripts/validate_architecture_knowledge.py --online
```

Rebuild this exact reviewed import with:

```powershell
.\venv\Scripts\python.exe scripts/build_curated_architecture_library.py "C:\Users\admin\Desktop\Sample arch diagrams.zip"
.\venv\Scripts\python.exe scripts/smoke_reference_style.py
```

The importer validates the entire ZIP file list, sizes, PNG integrity and pinned
hashes before copying assets. Unknown/changed images require manual review. It does
not extract arbitrary archive paths or send files to a model. The smoke check renders
an illustrative nested topology locally, without Bedrock, under `output/reference-style-smoke/`.

The audit checks all cards, retrieval, context bounds and official source evidence.
Online checks respect robots.txt, use timeouts and bounded downloads, record SHA-256
fingerprints and diagram URLs, and write `output/architecture-knowledge-validation.json`.
Without `--online`, it checks local structure and retrieval only. Online validation
is a manual maintenance operation, never part of SOW generation. A changed hash is
evidence to re-review, not proof that the pattern is invalid.

Review new sources before adding cards. Paraphrase architectural relationships;
do not copy whole articles, reproduce customer-specific examples, or import source
instructions as executable logic. Add workload and exclusion test cases. Bump the
library version when approved content changes. AgentCore guidance replaces reliance
on legacy Agents Classic; historical references must not resurrect retired services.

## Enforced diagram containment

The shared `CONTAINMENT_RULES` in `app/diagram/planning.py` is supplied to the
Solution Architecture writer, diagram planner, vision reviewer and placement
repair planner. It covers ownership, VPC/AZ/subnet membership, global versus
regional services, endpoints, ingress/egress, service control planes, availability,
model lifecycle and readable grouping. It is guidance, not an AWS certification.

The ELK graph uses explicit node `account`, `region`, `vpc`, `availability_zone`
and `subnet` fields. Named accounts/VPCs remain separate; unspecified names use
generic labels. Public/private/isolated subnet containers appear only when declared.
AWS Cloud encloses account views, which enclose regional views; global services
stay at account level. Regional managed services cannot be moved into subnets
by giving them a subnet field. External systems stay outside the AWS cloud.
The actual rendered geometry is checked for parent-child containment. The legacy
renderer remains a fallback and does not support the full named-boundary hierarchy.

Rule sources reviewed 2026-10-13:
- https://docs.aws.amazon.com/vpc/latest/userguide/configure-subnets.html
- https://docs.aws.amazon.com/vpc/latest/privatelink/gateway-endpoints.html
- https://docs.aws.amazon.com/vpc/latest/privatelink/create-interface-endpoint.html
- https://docs.aws.amazon.com/vpc/latest/userguide/vpc-nat-gateway.html
- https://docs.aws.amazon.com/elasticloadbalancing/latest/application/application-load-balancers.html

## Reference limitations

The official AWS card review is **text-based**; source diagram URLs are retained for
human review. Each of the ten new PNGs was visually inspected individually and preserved
with a SHA-256 integrity check; these are user references, not AWS-validated designs.
Generic cards separate control/data paths, private compute, shared security and
model lifecycle. Do not copy customer names, models, region, two-AZ topology or sizing
into unrelated projects. Validation restricts local image paths to this directory;
the online audit does not attempt to fetch private/local references.
Source reachability and tests cannot certify a generated architecture. Validate an
actual BRD-to-diagram run for service choices, meaningful edges, deployment boundaries,
readability and exclusions before accepting it. Reference guidance improves planning;
it cannot guarantee correctness or eliminate every crossing. No paid end-to-end
Bedrock generation is part of the offline regression suite.

See [visual and architectural conventions](CONVENTIONS.md) for the renderer palette,
boundary semantics, review checklist and official documentation supporting the rules.
