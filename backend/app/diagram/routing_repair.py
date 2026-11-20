"""Turn visual-review failures into bounded renderer changes, not new topology."""
import copy
import time


def repair_level(value):
    """Read the saved first-repair strategy record or a newer candidate level."""
    return 1 if isinstance(value, dict) and value else int(value or 0)


def prepare(saved, review):
    from app.diagram.service import DiagramSpec, Node, Edge
    from app.diagram.tiered_deployment import enabled
    issues = review.get('issues') or []
    if review.get('unresolved_architecture') or any(i.get('kind') == 'architecture' for i in issues):
        return saved
    if not any(i.get('kind') == 'visual' for i in issues):
        return saved
    try:
        spec = DiagramSpec(saved['title'], tuple(Node(**n) for n in saved['nodes']),
                           tuple(Edge(**e) for e in saved['edges']), architecture_plan=saved['architecture_plan'])
    except (KeyError,TypeError,ValueError):
        return saved  # Unsupported legacy assets retain their existing recovery path.
    if not enabled(spec) or spec.architecture_plan.get('routing_repair'):
        return saved
    result = copy.deepcopy(saved)
    result['architecture_plan']['routing_repair'] = {
        'version': 1, 'strategy': 'separate_runtime_and_egress',
        'findings': [str(i.get('description', ''))[:1000] for i in issues if i.get('kind') == 'visual'],
    }
    print('[DIAGRAM][ROUTING-REPAIR] Visual review activated subnet protection, wider corridors and runtime-first routing', flush=True)
    return result


def options(spec, positions, boxes, parents):
    if not spec.architecture_plan.get('routing_repair'):
        return {}
    nodes = {n.id:n for n in spec.nodes}
    def ancestors(key):
        chain = set()
        while key in parents:
            key = parents[key]; chain.add(key)
        return chain
    obstacles, sides = {}, {}
    for edge in spec.edges:
        a,b = nodes[edge.source],nodes[edge.target]
        allowed = ancestors(a.id) | ancestors(b.id)
        # Cross-AZ SQL may enter BOTH actual endpoint zones, but reports and
        # ingress must not masquerade as traversing unrelated subnet workloads.
        avoid_zones = a.placement_role == 'entry' or a.scope == 'external'
        obstacles[(a.id,b.id)] = [rect for key,rect in boxes.items() if key not in allowed
            and ('_subnet_' in key or (avoid_zones and '_az_' in key))]
        if ((a.placement_role == 'entry' and b.placement_role == 'compute') or
                (a.placement_role == 'compute' and b.placement_role == 'data' and b.scope in {'vpc','az'})):
            if positions[b.id][1] > positions[a.id][1]+positions[a.id][3]:
                sides[(a.id,b.id)] = {a.id:{'bottom'},b.id:{'top'}}
    return {'edge_obstacles':obstacles,'terminal_sides':sides}


def routes(spec, positions, boxes, parents, width, height, deadline, captions,header_sizes=None):
    from dataclasses import replace
    from app.diagram.review import local_routes, geometry_report
    nodes = {n.id:n for n in spec.nodes}
    def priority(edge):
        a,b = nodes[edge.source],nodes[edge.target]
        if a.placement_role == 'entry' and b.placement_role == 'compute': return 0
        if a.placement_role == 'compute' and b.placement_role == 'data' and b.scope in {'vpc','az'}: return 1
        if a.placement_role == b.placement_role == 'data': return 2
        if a.placement_role == 'network' or b.placement_role == 'network': return 4
        return 3
    order = sorted(range(len(spec.edges)),key=lambda i:priority(spec.edges[i]))
    best, best_score = None, None
    for penalty in (350,1200,4000):
        for sequence in (order,list(reversed(order))):
            if best is not None and time.monotonic()>deadline-2:
                return best
            candidate = replace(spec,edges=tuple(spec.edges[i] for i in sequence))
            constraints = options(candidate,positions,boxes,parents)
            try:
                try:
                    paths = local_routes(candidate,positions,boxes,parents,width,height,deadline,captions,
                        False,True,24,True,crossing_penalty=penalty,header_sizes=header_sizes,**constraints)
                except ValueError:
                    # Port preferences may relax, but subnet protection remains.
                    constraints['terminal_sides'] = {}
                    paths = local_routes(candidate,positions,boxes,parents,width,height,deadline,captions,
                        False,True,24,True,crossing_penalty=penalty,header_sizes=header_sizes,**constraints)
            except (ValueError,TimeoutError):
                continue
            result = [None]*len(sequence)
            for i,path in zip(sequence,paths): result[i] = path
            m = geometry_report(spec,positions,result)
            score = (m['connector_node_intersections'],m['ambiguous_connector_pairs'],
                m['connector_crossings']*50+m['connector_length_normalized']*20+
                m['connector_bends']*2+m['long_connector_count']*60)
            if best is None or score<best_score:
                best,best_score=result,score
    if best is None:
        raise ValueError('No unobstructed repair route with subnet protection')
    return best
