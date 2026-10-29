"""Executable checks on the architect's short design contract, not visual taste.

Old saved specifications remain readable. New plans carry explicit directed paths
and ownership decisions so a renderer cannot silently invent the architecture.
"""
import copy


PLAN_CONTRACT = """
Return architecture_plan alongside nodes and edges:
{"view":"logical|deployment", "reference_pattern":"matched reference ID or none",
 "adaptation":"one sentence: what structure was reused and what was not",
 "decisions":[{"topic":"hosting/networking/ownership/ingress/egress/data/identity/availability",
   "status":"confirmed|proposed|unresolved|not_applicable", "choice":"short decision",
   "basis":"brief source fact or design dependency, never invented evidence"}],
 "flows":[{"id":"migration", "label":"Historical migration", "kind":"migration|runtime|analytics|lifecycle|control",
   "paths":[["source_node","processor_node","destination_node"]]}]}
These are concise design decisions, not a reasoning transcript. Each adjacent pair
in each path MUST be an actual directed edge. Branching dependencies are separate
paths, not a fabricated sequence. Cover every non-control node with a meaningful
path. Shared controls may be unconnected; do not add fake security traffic.
Use node field flow_id only for a component dedicated to one flow; shared nodes
have an empty flow_id and must not be copied into multiple lanes.

Design in this order:
1. Preserve exact existing platform identities and owners. Separate confirmed
   requirements, proposed implementation choices and unresolved interfaces.
2. Choose the smallest coherent view: logical for managed integrations or unknown
   hosting; deployment when workload networking matters. Never invent a VPC to
   make a logical diagram look more sophisticated, or omit one for private EC2.
3. Identify the system of record and source/destination of EACH independent flow.
   Migration begins at the legacy source, ends at the target import interface.
   Runtime AI begins at the calling application and returns through its adapter.
   Analytics begins at the reporting/export source, not an unrelated model node.
4. Select reference patterns by workload AND hosting, not keyword resemblance.
   Reuse containment and composition; explicitly adapt differences in ownership,
   phase and interfaces. References never establish product choices or scope.
5. Specify hosting, network ingress/egress, private access, storage, identity and
   availability decisions. Unknown values stay unresolved, not silently defaulted.
6. Compose a compact processing spine with nearby branches; use whitespace rather
   than a box per flow. Keep truly shared resources single, but use separate
   Lambda functions for distinct business responsibilities, scaling or permissions.
   Multiple instances of one AWS service are not duplicates. Deployment boundaries take
   precedence over functional grouping.
7. Walk every directed path and cross-boundary interface before returning. A
   connection is invocation/data transfer, never mere association.

Few-shot design distinctions (conditional patterns, not mandatory services):
- CRM migration + AI + reporting: legacy -> staging -> importer -> target CRM;
  CRM -> AI adapter -> model; CRM exports -> analytics store -> query -> dashboard.
  Do not route migration through model inference just because AI is also in scope.
- RAG assistant: runtime branches to retrieval store, inference and business API;
  ingestion -> chunk/embed -> retrieval store is a separate indexing path.
- Batch analytics: scheduler -> workers; source -> workers -> results; model
  training/approval is separate from inference. ECR stores images, not model versions.
- Private compute: worker -> endpoint -> managed service; private worker -> NAT
  -> internet destination only when outbound internet is required. IGW belongs to
  the VPC boundary; NAT is not ingress. A public API does not imply a public database.
Do not force these examples onto a project or copy their technology choices.
"""


def validate_plan(raw):
    """Return a copy of a valid contract; reject contradictions before rendering."""
    plan = raw.get('architecture_plan')
    if plan is None:  # Legacy persisted graphs and older adapters.
        return {}
    if not isinstance(plan, dict) or plan.get('view') not in {'logical', 'deployment'}:
        raise ValueError('Architecture plan requires a logical or deployment view')
    nodes = {n['id']: n for n in raw.get('nodes', [])}
    edges = {(e['source'], e['target']) for e in raw.get('edges', [])}
    for edge in raw.get('edges', []):
        source = nodes.get(edge['source'], {})
        if ('amazon-simple-storage-service' in source.get('icon_key','')
                and any(word in edge.get('label','').casefold() for word in ('import','load records'))):
            raise ValueError('S3 is passive storage, not an import worker. Show the actual worker '
                             'importing into the target, or explicitly label a consumer read. '
                             'Do not depict S3 autonomously importing records or files.')
    flows = plan.get('flows')
    if not isinstance(flows, list) or not flows:
        raise ValueError('Architecture plan requires meaningful flows')
    ids, covered, explained_edges = set(), set(), set()
    for flow in flows:
        if not isinstance(flow, dict):
            raise ValueError('Each architecture flow must be an object')
        fid = flow.get('id')
        if not isinstance(fid, str) or not fid or fid in ids:
            raise ValueError('Architecture flow IDs must be unique and nonempty')
        ids.add(fid)
        # Kind is an advisory label, not topology. A model's "integration" or
        # "call-context" category must not discard a valid graph. The checks
        # below still reject missing nodes, reversed paths and missing edges.
        if flow.get('kind') not in {'migration', 'runtime', 'analytics', 'lifecycle', 'control'}:
            print(f'[DIAGRAM][PLAN-NOTE] Preserving flow {fid} with advisory kind '
                  f'{str(flow.get("kind"))[:60]}', flush=True)
        if not isinstance(flow.get('paths'), list) or not flow['paths']:
            raise ValueError(f'Flow {fid} requires directed paths')
        for path in flow['paths']:
            if not isinstance(path, list) or len(path) < 2 or any(not isinstance(n, str) or n not in nodes for n in path):
                raise ValueError(f'Flow {fid} has an invalid path')
            for pair in zip(path, path[1:]):
                if pair not in edges:
                    raise ValueError(f'Flow {fid} declares missing directed edge {pair}')
                explained_edges.add(pair)
            covered.update(path)
    for nid, node in nodes.items():
        fid = node.get('flow_id')
        if fid and (fid not in ids or (nid in covered and not any(
                nid in p for f in flows if f['id'] == fid for p in f['paths']))):
            raise ValueError(f'Node {nid} has inconsistent flow membership')
        if (nid not in covered and not any(nid in pair for pair in edges)
                and node.get('placement_role') not in {'security', 'operations'}):
            raise ValueError(f'Non-control node {nid} has no explained flow')
    # The graph is the connection authority. A missing entry in the redundant
    # checklist does not make an otherwise explicit connection invalid. Preserve
    # it, record it for review, and never replace the whole architecture for this.
    uncovered_edges = sorted((source, target) for source, target in edges - explained_edges
                             if not any(nodes[n].get('placement_role') in {'security', 'operations'}
                                        for n in (source, target)))
    decisions = plan.get('decisions', [])
    if not isinstance(decisions, list):
        raise ValueError('Architecture decisions must be a list')
    for decision in decisions:
        if not isinstance(decision, dict) or decision.get('status') not in {'confirmed', 'proposed', 'unresolved', 'not_applicable'}:
            raise ValueError('Architecture decision requires an explicit evidence status')
    result = copy.deepcopy(plan)
    if uncovered_edges:
        result['unclassified_connections'] = [list(pair) for pair in uncovered_edges]
        print(f'[DIAGRAM][PLAN-NOTE] Preserving {len(uncovered_edges)} explicit connections '
              'not repeated in flow metadata', flush=True)
    return result
