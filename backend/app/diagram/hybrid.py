"""Constrained model composition + deterministic containment and connector routing.

The model can arrange siblings, never invent coordinates, change membership or
drop an edge. PNG and draw.io consume the same checked geometry. ELK remains a
bounded independent candidate and offline fallback.
"""
import json
import math
import subprocess
import time
from dataclasses import replace

from app.diagram.elk import build_graph
from app.diagram.review import geometry_report, layout_quality, local_routes


COMPOSITION_RULES = '''Arrange this FIXED architecture as a compact readable AWS reference diagram.
Return JSON only: {"grids":{"container_id":[["child_id","child_id"],["child_id",""]]},
"external_sides":{"external_node_id":"left|right|top|bottom"}}.
Each grid positions immediate children, with empty strings as empty slots. Include
each listed child exactly once; NEVER put a descendant in its ancestor's grid.
Use 2-4 columns for workloads; align consecutive migration stages left-to-right.
Keep shared adapters close to their external client and put model inference on a
short side branch, not between the adapter and client. Incoming sources on left;
a caller that also receives imports belongs on the SAME side as its adapter, not
at the opposite edge of the canvas. External nodes are aligned with their peers.
Controls are packed separately below the workload. Do not include them in grids.
Boundaries are fixed by the architect. Do not invent VPCs, AZs, services or arrows.
No titles, legends, prose, feature boxes or colored category containers.
Choose placement by the complete graph, including feedback/request edges.
Use the supplied workflows to identify the main user-to-outcome spine BEFORE
placing dependencies or routing. Put consecutive stages next to one another,
then place each store/tool/identity provider beside its actual caller. Workflow
text cannot create edges or override boundaries. Choose compact rows before
considering detours; never stretch a connector to compensate for poor placement.
Avoid page-wide return arrows, crossings and long loops. Service names remain unchanged.
Start with starting_composition; return it unchanged if it already reads clearly.
Build the composition container-first: arrange Region/VPC/AZ/subnet siblings,
then their workloads. Align peer AZ columns and corresponding subnet tiers when
present; never manufacture an AZ or move a child out of its real parent.
Use empty grid slots only for needed connector corridors, not decorative spacing.
Keep labels and icons out of corridors. Put high-degree workloads beside their
data/model dependencies; avoid a cramped subnet next to a mostly empty Region.
Place external ticketing/device systems on the side nearest their actual adapter.
Do not use a page-wide route when a different peer ordering shortens it. Read the
primary request, data access and external integration paths separately before
choosing grids. Avoid stacked return paths through labels and false junctions.
Compact the Cloud/Region footprint; a single global service must not force a
large unused area. Preserve the fixed security/global packing managed by code.
The existing grid schema is authoritative: do not emit coordinates, new style
fields, renamed services, replacement icons or routing code.
external_sides keys MUST come from external_ids only. Security controls are AWS
resources, NOT externals. Leave their fixed auto-packing alone. A path entering
from an external system on the right may run right-to-left in its own row.
'''


def tree_for(spec, config):
    graph = build_graph(spec, config, iconic=True)
    # A solitary IAM icon needs no additional 'Account security' card/boundary.
    def flatten(item):
        children = []
        for child in item.get('children', []):
            flatten(child)
            if child['id'].startswith('__shared_controls') and item['id'].startswith('__aws_account'):
                children.extend(child['children'])
            else:
                children.append(child)
        if 'children' in item:
            item['children'] = children
    flatten(graph)
    cloud = next((c for c in graph['children'] if c['id']=='__aws_cloud'),None)
    if cloud and len(cloud['children']) == 1 and cloud['children'][0]['id'].startswith('__aws_account'):
        # A single account adds no ownership distinction. AWS Cloud represents
        # it; retain explicit account boxes when there are multiple accounts.
        cloud['children'] = cloud['children'][0]['children']
    return graph


def hierarchy(graph):
    groups = {}
    def visit(item):
        if 'children' in item:
            groups[item['id']] = [c['id'] for c in item['children']
                if not c['id'].startswith('__shared_controls')]
            for child in item['children']:
                visit(child)
    visit(graph)
    return groups


def validate_composition(value, graph):
    if not isinstance(value, dict) or set(value) - {'grids', 'external_sides'}:
        raise ValueError('Composition supports grids and external_sides only')
    groups = hierarchy(graph)
    grids = value.get('grids', {})
    if not isinstance(grids, dict):
        raise ValueError('grids must be an object')
    for key, rows in grids.items():
        if key not in groups or key == 'root' or key.startswith('__shared_controls'):
            raise ValueError('Unknown or non-arrangeable boundary: ' + key)
        if not isinstance(rows, list) or not 1 <= len(rows) <= 8:
            raise ValueError('Invalid grid rows')
        if any(not isinstance(row, list) or not 1 <= len(row) <= 8
               or any(not isinstance(n, str) for n in row) for row in rows):
            raise ValueError('Invalid grid cells')
        ids = [n for row in rows for n in row if n]
        if len(ids) != len(set(ids)) or set(ids) != set(groups[key]):
            raise ValueError('Grid must preserve every immediate child exactly once: ' + key)
    externals = {c['id'] for c in graph['children'] if 'children' not in c}
    sides = value.get('external_sides', {})
    if not isinstance(sides, dict):
        raise ValueError('external_sides must be an object')
    invalid = {k:v for k,v in sides.items() if k not in externals or v not in {'left','right','top','bottom'}}
    if invalid:
        raise ValueError('Invalid external side assignment: ' + json.dumps(invalid)
                         + '. Allowed external IDs: ' + json.dumps(sorted(externals))
                         + '. Allowed values: left, right, top, bottom. Internal services stay in grids.')
    return value


def composition_context(spec, config):
    graph = tree_for(spec, config)
    return {'workflows': (spec.architecture_plan.get('service_design') or {}).get('workflows', []),
            'containers': {k:v for k,v in hierarchy(graph).items()
                          if k != 'root' and not k.startswith('__shared_controls')},
            'external_ids':[c['id'] for c in graph['children'] if 'children' not in c],
            'nodes': [{'id': n.id, 'service': n.label, 'scope': n.scope,
                       'role': n.placement_role} for n in spec.nodes],
            'edges': [e.__dict__ for e in spec.edges],
            'starting_composition': topology_composition(spec,config)}


def topology_composition(spec, config):
    """Compact reference-style processing rows; no domain-specific node IDs."""
    graph = tree_for(spec,config)
    grids = {}
    nodes = {n.id:n for n in spec.nodes}
    def visit(item):
        children = item.get('children',[])
        for c in children:
            visit(c)
        body = [c for c in children if not c['id'].startswith('__shared_controls')]
        if not body or item['id'] == 'root' or item['id'].startswith('__shared_controls'):
            return
        if item['id'].startswith('__aws_account'):
            grids[item['id']] = [[c['id']] for c in sorted(body,key=lambda c: c['id'] in nodes)]
        elif all('children' not in c for c in body):
            ids = [c['id'] for c in body]
            # Dedicated business paths form rows, not boxes. A request entering
            # from a shared target on the right runs right-to-left locally; it
            # should not loop across the whole figure just to face the same way.
            declared_rows, assigned = [], set()
            for flow in spec.architecture_plan.get('flows', []):
                row = []
                for path in flow.get('paths', []):
                    for key in path:
                        if key in ids and nodes[key].flow_id == flow['id'] and key not in row and key not in assigned:
                            row.append(key)
                if not row:
                    continue
                incoming_external = [e.source for e in spec.edges if e.target == row[0]
                                     and e.source in nodes and nodes[e.source].scope == 'external']
                if incoming_external and all(
                    sum(e.target==external for e in spec.edges) >= sum(e.source==external for e in spec.edges)
                    for external in incoming_external):
                    row.reverse()
                declared_rows.append(row)
                assigned.update(row)
            if len(declared_rows) >= 2 and assigned == set(ids):
                grids[item['id']] = declared_rows
                return
            adjacency = {k:[e.target for e in spec.edges if e.source==k and e.target in ids] for k in ids}
            incoming = {k:sum(k in targets for targets in adjacency.values()) for k in ids}
            roots = [k for k in ids if not incoming[k]]
            rows,seen = [],set()
            for start in roots+ids:
                if start in seen:
                    continue
                row,key = [],start
                while key not in seen:
                    seen.add(key); row.append(key)
                    nxt = [k for k in adjacency[key] if k not in seen]
                    if len(nxt)!=1:
                        break
                    # Terminal dependency is a nearby downward branch when its
                    # parent also communicates with an external application.
                    if (not adjacency[nxt[0]] and 'artificial-intelligence' in nodes[nxt[0]].icon_key
                            and any(e.source==key and e.target not in ids for e in spec.edges)):
                        break
                    key=nxt[0]
                rows.append(row)
            # Put terminal branches under their parent, without creating boxes.
            for r,row in enumerate(rows):
                if len(row)==1:
                    parent=next((e.source for e in spec.edges if e.target==row[0] and e.source in ids),None)
                    previous=next((earlier for earlier in rows[:r] if parent in earlier),None)
                    if previous:
                        # Diagonal dependency: side -> top connection avoids a
                        # U-turn around the service caption below the parent.
                        rows[r]=['']*(previous.index(parent)+1)+row
            grids[item['id']]=rows
    visit(graph)
    return {'grids':grids,'external_sides':{}}


def prepare(service, spec):
    """One small layout-only call; no BRD replay or generated drawing code."""
    spec = replace(spec, nodes=tuple(replace(n, subtitle='') for n in spec.nodes))
    if spec.architecture_plan.get('visual_layout') or not hasattr(service, 'bedrock'):
        return spec
    try:
        from app.agents.architecture_reviewer_agent import _call
        from app.diagram.reliability import structured_retry
        from app.diagram.budgets import seconds
        deadline = time.monotonic() + seconds('composition')
        value = structured_retry(
            lambda prompt: _call(service, prompt, deadline, planner=True, call_name='Architecture Composition'),
            COMPOSITION_RULES+'\n'+json.dumps(composition_context(spec,service.config))
            +'\nPrevious attempt findings (correct placement only):\n'+str(spec.architecture_plan.get('retry_feedback','')),
            lambda value: validate_composition(value, tree_for(spec, service.config)),
            attempts=2, deadline=deadline)
        return replace(spec, architecture_plan={**spec.architecture_plan,'visual_layout':value})
    except Exception as exc:
        print('[DIAGRAM][HYBRID] Composition unavailable; use local candidates: '+str(exc)[:300],flush=True)
        return spec


def compose(spec, config, value, deadline):
    graph = tree_for(spec, config)
    validate_composition(value, graph)
    grids = value.get('grids', {})
    positions, boxes, parents, captions = {}, {}, {}, {}
    global_ids = {n.id for n in spec.nodes if n.scope == 'global'}
    def arrange(item):
        if 'children' not in item:
            # Use uniform bare icons, including IAM, not a compact prose card.
            if item['id'] in global_ids:
                item['width'], item['height'] = 168, 132
            return
        for child in item['children']:
            arrange(child)
        controls = [c for c in item['children'] if c['id'].startswith('__shared_controls')]
        body = [c for c in item['children'] if c not in controls]
        if item['id'].startswith('__region') and not (
                spec.architecture_plan.get('review_composition') and item['id'] in grids):
            # A VPC is a tall deployment block. Do not let its height create a
            # full-height empty column beneath every regional managed service.
            nodes_by_id = {n.id: n for n in spec.nodes}
            networks = [c for c in body if 'children' in c]
            entry = [c for c in body if c['id'] in nodes_by_id and
                     (nodes_by_id[c['id']].placement_role == 'entry' or any(
                         token in nodes_by_id[c['id']].icon_key.lower()
                         for token in ('waf', 'cognito', 'api-gateway')))]
            entry.sort(key=lambda c: next((i for i, token in enumerate(
                ('waf', 'api-gateway', 'cognito')) if token in nodes_by_id[c['id']].icon_key.lower()), 9))
            managed = [c for c in body if c not in networks and c not in entry]
            # A managed agent/runtime is often the hub, with only its enterprise
            # adapter inside a VPC. Putting that VPC first reverses the actual
            # request flow. Place the hub before that network and put its leaf
            # dependencies above and the reporting chain below.
            hubs = [c for c in managed if nodes_by_id[c['id']].placement_role == 'compute']
            degree = lambda c: sum(c['id'] in (e.source,e.target) for e in spec.edges)
            hub = max(hubs,key=degree,default=None)
            if networks and hub is not None and degree(hub) >= 4:
                rest = [c for c in managed if c is not hub]
                outgoing = {c['id']:[e.target for e in spec.edges if e.source == c['id']
                            and any(other['id']==e.target for other in rest)] for c in rest}
                starts = [c for c in rest if outgoing[c['id']] and any(
                    e.source==hub['id'] and e.target==c['id'] for e in spec.edges)]
                chain,seen = [],set()
                for start in starts:
                    key = start['id']
                    while key not in seen:
                        seen.add(key)
                        chain.append(next(c for c in rest if c['id']==key))
                        next_keys = outgoing[key]
                        if len(next_keys)!=1:
                            break
                        key = next_keys[0]
                leaves = [c for c in rest if c['id'] not in seen]
                hub['x'],hub['y'] = 275,280
                for index,child in enumerate(entry):
                    child['x'],child['y'] = 24,280-index*190
                for index,child in enumerate(networks):
                    child['x'],child['y'] = 540+index*(child['width']+65),245
                for index,child in enumerate(leaves):
                    child['x'],child['y'] = 275+(index%2)*265,60+(index//2)*190
                # If there are too many leaves for the upper rail, use the
                # general packing below rather than overlap the main spine.
                if len(leaves)<=2 and len(entry)<=2:
                    bottom = max(c['y']+c['height'] for c in [hub]+networks+leaves+entry)
                    for index,child in enumerate(chain):
                        child['x'],child['y'] = 24+(index%3)*255,bottom+65+(index//3)*185
                    bottom = max(c.get('y',0)+c['height'] for c in body)
                    for child in controls:
                        child['x'],child['y'] = 24,bottom+35
                        bottom += child['height']+35
                    item['width'] = max(c['x']+c['width'] for c in item['children'])+24
                    item['height'] = bottom+24
                    return
            if networks and managed:
                top = 60
                x = 24
                for child in entry:
                    child['x'], child['y'] = x, top
                    x += child['width'] + 60
                top += max((c['height'] for c in entry), default=0) + (55 if entry else 0)
                nx = 24
                for child in networks:
                    child['x'], child['y'] = nx, top
                    nx += child['width'] + 70
                right = nx
                max_right, bottom = nx, top
                for index, child in enumerate(managed):
                    col, row = index % 2, index // 2
                    child['x'], child['y'] = right + col * 235, top + row * 185
                    max_right = max(max_right, child['x'] + child['width'])
                    bottom = max(bottom, child['y'] + child['height'])
                bottom = max(bottom, *(c['y'] + c['height'] for c in networks))
                for child in controls:
                    child['x'], child['y'] = 24, bottom + 35
                    bottom += child['height'] + 35
                    max_right = max(max_right, child['width'] + 24)
                item['width'], item['height'] = max(x, max_right + 24), bottom + 24
                return

        if item['id'].startswith('__shared_controls'):
            rows = [[c['id'] for c in body]]
        elif item['id'].startswith('__aws_account') or (
                item['id']=='__aws_cloud' and any(c['id'] in global_ids for c in body)):
            # Keep global controls in a compact footer outside Region, not a
            # full-height column that makes the whole figure unreadably wide.
            regions=[c['id'] for c in body if 'children' in c]
            globals_=[c['id'] for c in body if 'children' not in c]
            # Edge services lead into the regional runtime; never place ingress
            # below it, which creates a perimeter-sized return connector.
            node_by_id = {n.id: n for n in spec.nodes}
            ingress = [key for key in globals_ if any(token in node_by_id[key].icon_key.lower()
                       for token in ('cloudfront', 'route-53', 'waf', 'shield'))]
            shared = [key for key in globals_ if key not in ingress]
            ingress.sort(key=lambda key: next((i for i, token in enumerate(
                ('route-53', 'cloudfront', 'waf', 'shield')) if token in node_by_id[key].icon_key.lower()), 9))
            if ingress and len(regions) == 1:
                # Align the global delivery service with the regional ingress.
                # A separate full-width row above Region produces huge U-turns.
                region = next(c for c in body if c['id'] == regions[0])
                def entry_y(container, offset=0):
                    found = []
                    for child in container.get('children', []):
                        y = offset + child.get('y',0)
                        if 'children' in child:
                            found.extend(entry_y(child,y))
                        elif child['id'] in node_by_id and node_by_id[child['id']].placement_role == 'entry':
                            found.append(y)
                    return found
                lane_width = max(c['width'] for c in body if c['id'] in ingress)+64
                region['x'], region['y'] = lane_width+32, 44
                target_y = min(entry_y(region),default=region['height']/2)+44
                by_key = {c['id']:c for c in body}
                primary = [k for k in ingress if 'waf' not in node_by_id[k].icon_key.lower()]
                protection = [k for k in ingress if k not in primary]
                for index,key in enumerate(primary):
                    by_key[key]['x'], by_key[key]['y'] = 16, target_y+index*170
                for index,key in enumerate(protection):
                    by_key[key]['x'], by_key[key]['y'] = 16, target_y+185+index*170
                bottom = max(c.get('y',0)+c['height'] for c in body if c['id'] not in shared)
                for index,key in enumerate(shared):
                    by_key[key]['x'], by_key[key]['y'] = 16+index*195,bottom+32
                for child in controls:
                    child['x'],child['y'] = 16,bottom+32
                    bottom += child['height']+32
                item['width'] = max(c.get('x',0)+c['width'] for c in item['children'])+24
                item['height'] = max(c.get('y',0)+c['height'] for c in item['children'])+24
                return
            rows=([ingress] if ingress else [])+[[key] for key in regions]+([shared] if shared else [])
        else:
            # Default is a row, never a surprise nested feature lane.
            rows = grids.get(item['id'], [[c['id'] for c in body]])
            # Bound the width of unmanaged service rows. Wide regional rows
            # stretch every boundary and every external integration connector.
            rows = [row[start:start+4] for row in rows for start in range(0, len(row), 4)]
        by_id = {c['id']: c for c in body}
        horizontal_gap = 24 if item['id'].startswith('__shared_controls') else 80
        cols = max((len(row) for row in rows), default=1)
        widths = [max((by_id[row[i]]['width'] for row in rows if i < len(row) and row[i]), default=0)
                  for i in range(cols)]
        y = 44
        for row in rows:
            row_height = max((by_id[k]['height'] for k in row if k), default=0)
            x = 16
            for col, key in enumerate(row):
                if key:
                    child = by_id[key]
                    child['x'], child['y'] = (x if child['id'] in global_ids else x+(widths[col]-child['width'])/2), y
                x += widths[col]+horizontal_gap
            y += row_height+32
        width = sum(widths)+horizontal_gap*max(0, cols-1)+32
        y = max(44, y-32)
        for child in controls:
            child['x'], child['y'] = 16, y+24
            y += child['height']+24
            width = max(width, child['width']+32)
        item['width'], item['height'] = max(180, width), y+16
    # Root is special: external nodes must never be packed inside Cloud.
    for child in graph['children']:
        arrange(child)
    clouds = [c for c in graph['children'] if 'children' in c]
    external = [c for c in graph['children'] if 'children' not in c]
    cursor = 0
    for cloud in clouds:
        cloud['x'], cloud['y'] = cursor, 0
        cursor += cloud['width']+80
    def collect(item, ox=0, oy=0, parent='root'):
        x, y = ox+item.get('x', 0), oy+item.get('y', 0)
        rect = (x,y,item['width'],item['height'])
        parents[item['id']] = parent
        if 'children' in item:
            boxes[item['id']] = rect
            captions[item['id']] = item.get('labels', [{'text':item['id']}])[0]['text']
            for child in item['children']:
                collect(child,x,y,item['id'])
        else:
            positions[item['id']] = rect
    for cloud in clouds:
        collect(cloud)
    max_x = max((x+w for x,y,w,h in boxes.values()), default=400)
    max_y = max((y+h for x,y,w,h in boxes.values()), default=200)
    buckets = {k:[] for k in ('left','right','top','bottom')}
    nodes_by_kind = {n.id: n.kind for n in spec.nodes}
    for child in external:
        key = child['id']
        degree = sum(key in (e.source,e.target) for e in spec.edges)
        # Shared external systems need real space for each interface; do not
        # squeeze four directions into a small card's central few pixels.
        child['height'] = max(child['height'],40+32*degree)
        peers = [e.target if e.source == key else e.source for e in spec.edges
                 if key in (e.source,e.target)]
        peers = [positions[p] for p in peers if p in positions]
        cx = sum(x+w/2 for x,y,w,h in peers)/len(peers) if peers else max_x/2
        cy = sum(y+37 for x,y,w,h in peers)/len(peers) if peers else max_y/2
        # Source systems enter from the left; an existing application receiving
        # imports remains on the right even when it also initiates AI calls.
        # Barycentre alone incorrectly put that shared target beside the sources.
        incoming = sum(e.target == key for e in spec.edges)
        outgoing = sum(e.source == key for e in spec.edges)
        default_side = ('left' if nodes_by_kind.get(key) in {'actor', 'channel'} or not incoming else 'right')
        side = value.get('external_sides',{}).get(key, default_side)
        if peers and nodes_by_kind.get(key) not in {'actor', 'channel'}:
            # Place an external integration at the nearest cloud boundary to
            # its actual adapters, rather than beyond unrelated analytics.
            distances = {'left': cx, 'right': max_x-cx, 'top': cy, 'bottom': max_y-cy}
            nearest = min(distances, key=distances.get)
            if distances[side] > distances[nearest] + 140:
                side = nearest

        buckets[side].append((cx,cy,child))
    for side, children in buckets.items():
        end = 0
        for cx,cy,child in sorted(children,key=lambda t:t[1 if side in {'left','right'} else 0]):
            w,h = child['width'],child['height']
            if side in {'left','right'}:
                x = -w-80 if side == 'left' else max_x+80
                y = max(end,cy-h/2)
                end = y+h+44
            else:
                x = max(end,cx-w/2)
                y = -h-80 if side == 'top' else max_y+80
                end = x+w+64
            positions[child['id']] = (x,y,w,h)
            parents[child['id']] = 'root'
    all_boxes = list(positions.values())+list(boxes.values())
    dx = 32-min(r[0] for r in all_boxes)
    dy = 32-min(r[1] for r in all_boxes)
    positions = {k:(x+dx,y+dy,w,h) for k,(x,y,w,h) in positions.items()}
    boxes = {k:(x+dx,y+dy,w,h) for k,(x,y,w,h) in boxes.items()}
    width = math.ceil(max(x+w for x,y,w,h in all_boxes)+dx+32)
    height = math.ceil(max(y+h for x,y,w,h in all_boxes)+dy+32)
    if width*height > 24_000_000:
        raise ValueError('Composition canvas exceeds limit')
    paths = local_routes(spec,positions,boxes,parents,width,height,deadline,captions,True)
    metrics = geometry_report(spec,positions,paths)
    if set(positions) != {n.id for n in spec.nodes} or len(paths) != len(spec.edges):
        raise ValueError('Composition lost a component or connection')
    containment = sum(not (boxes[p][0] <= x and boxes[p][1] <= y
                      and x+w <= boxes[p][0]+boxes[p][2]
                      and y+h <= boxes[p][1]+boxes[p][3])
                      for k,(x,y,w,h) in {**boxes,**positions}.items()
                      if (p := parents.get(k)) in boxes)
    outside = sum(not (0 <= x <= width and 0 <= y <= height)
                  for path in paths for x,y in path)
    if containment or outside or any(a[0] != b[0] and a[1] != b[1]
                                    for path in paths for a,b in zip(path,path[1:])):
        raise ValueError('Invalid containment or connector geometry')
    if metrics['node_overlaps'] or metrics['connector_node_intersections']:
        raise ValueError('Composition has obstructed nodes or connectors')
    metrics.update(out_of_bounds=0,containment_violations=0,workflow_lanes=0,
                   estimated_label_pt=round(22*min(468/width,576/height),2),
                   estimated_subtitle_pt=round((16 if any(n.subtitle for n in spec.nodes) else 22)*min(468/width,576/height),2))
    return {'geometry':(positions,boxes,width,height),'paths':paths,
            'labels':[None]*len(paths),'captions':captions,'parents':parents,
            'metrics':metrics,'card_style':'iconic','compact_nodes':[],
            'composition':value,'candidate_source':'model_composition'}


def layout(spec, config, timeout_seconds=None):
    from app.diagram.elk import layout as elk_layout
    from app.diagram.budgets import seconds
    deadline = time.monotonic()+min(seconds('layout'),max(2,timeout_seconds or seconds('layout')))
    candidate_budget = max(2, (deadline-time.monotonic()) / 4)
    candidates, failures = [], []
    try:
        reference = compose(spec,config,topology_composition(spec,config),min(deadline,time.monotonic()+candidate_budget))
        reference['candidate_source'] = 'reference_topology'
        candidates.append(reference)
    except (ValueError,KeyError,TypeError,TimeoutError) as exc:
        failures.append('reference_topology: '+str(exc))
    composition = spec.architecture_plan.get('visual_layout')
    if composition:
        try:
            candidates.append(compose(spec,config,composition,min(deadline,time.monotonic()+candidate_budget)))
        except (ValueError,KeyError,TypeError,TimeoutError) as exc:
            failures.append('composition: '+str(exc))
    # Independent baseline: never let the first candidate failing skip alternatives.
    for mode in ('LANES','SIDES'):
        remaining = deadline-time.monotonic()
        if remaining < 2:
            break
        try:
            candidate = elk_layout(spec,config,min(candidate_budget,remaining),_optimize=False,
                                   _compound=True,_iconic=True,_flow_direction=mode)
            candidate.update(candidate_source='elk_'+mode.lower())
            candidates.append(candidate)
        except (ValueError,RuntimeError,TimeoutError,subprocess.TimeoutExpired) as exc:
            failures.append(mode+': '+str(exc))
    if not candidates:
        raise ValueError('No valid hybrid geometry: '+'; '.join(failures))
    # Put each external system at its nearest cloud edge, independently. Forcing
    # all integrations below the cloud made top-row adapters cross the whole page.
    for baseline in list(candidates):
        if deadline-time.monotonic() < 2:
            break
        try:
            positions, boxes, width, height = baseline['geometry']
            positions = dict(positions)
            externals = [n for n in spec.nodes if n.scope == 'external' and n.kind not in {'actor','channel'}]
            if not externals:
                continue
            cloud_boxes = [r for k,r in boxes.items() if baseline['parents'].get(k) == 'root']
            cloud_boxes = cloud_boxes or list(boxes.values())
            left = min(x for x,y,w,h in cloud_boxes)
            top = min(y for x,y,w,h in cloud_boxes)
            right = max(x+w for x,y,w,h in cloud_boxes)
            bottom = max(y+h for x,y,w,h in cloud_boxes)
            occupied = [positions[n.id] for n in spec.nodes if n.scope == 'external' and n not in externals]
            for node in externals:
                peers = [e.target if e.source == node.id else e.source for e in spec.edges if node.id in (e.source,e.target)]
                peers = [positions[key] for key in peers if key in positions]
                if not peers:
                    continue
                _,_,w,h = positions[node.id]
                cx = sum(px+pw/2 for px,py,pw,ph in peers)/len(peers)
                cy = sum(py+37 for px,py,pw,ph in peers)/len(peers)
                choices = [(cx-w/2,top-h-65,w,h), (right+65,cy-h/2,w,h),
                           (cx-w/2,bottom+65,w,h), (left-w-65,cy-h/2,w,h)]
                choices = [r for r in choices if not any(
                    r[0] < a+c+35 and r[0]+w > a-35 and r[1] < b+d+35 and r[1]+h > b-35
                    for a,b,c,d in occupied)]
                if not choices:
                    continue
                rect = min(choices,key=lambda r:sum(abs(r[0]+w/2-(px+pw/2))+
                    abs(r[1]+h/2-(py+37)) for px,py,pw,ph in peers))
                positions[node.id] = rect
                occupied.append(rect)
            dx = max(0,32-min(x for x,y,w,h in positions.values()))
            dy = max(0,32-min(y for x,y,w,h in positions.values()))
            positions = {k:(x+dx,y+dy,w,h) for k,(x,y,w,h) in positions.items()}
            boxes = {k:(x+dx,y+dy,w,h) for k,(x,y,w,h) in boxes.items()}
            width = max(x+w for x,y,w,h in list(positions.values())+list(boxes.values()))+32
            height = max(y+h for x,y,w,h in list(positions.values())+list(boxes.values()))+32
            paths = local_routes(spec,positions,boxes,baseline['parents'],width,height,
                                 min(deadline,time.monotonic()+5),baseline.get('captions'),True)
            metrics = geometry_report(spec,positions,paths)
            if metrics['node_overlaps'] or metrics['connector_node_intersections']:
                continue
            metrics.update(out_of_bounds=0,containment_violations=0)
            candidates.append({**baseline,'geometry':(positions,boxes,width,height),'paths':paths,
                               'labels':[None]*len(paths),'metrics':metrics,
                               'candidate_source':baseline['candidate_source']+'_near_integrations'})
        except (ValueError,KeyError,TimeoutError):
            continue
    # Improve proximity before routing: exchange equally sized siblings only.
    # This cannot change ownership, nesting, service identities or connections.
    for candidate in candidates:
        positions,_,width,height = candidate['geometry']
        candidate['metrics']['canvas_area_per_node'] = width*height/max(1,len(positions))
    baseline = min(candidates,key=lambda c:layout_quality(c['metrics']))
    if deadline-time.monotonic() > 2:
        try:
            positions, boxes, width, height = baseline['geometry']
            positions = dict(positions)
            parents = baseline['parents']
            internal = [n.id for n in spec.nodes if n.scope != 'external' and n.id in positions]
            pairs = [(a,b) for i,a in enumerate(internal) for b in internal[i+1:]
                     if parents.get(a) == parents.get(b) and positions[a][2:] == positions[b][2:]]
            def wire_cost():
                lengths = [abs(positions[e.source][0]-positions[e.target][0])+
                           abs(positions[e.source][1]-positions[e.target][1]) for e in spec.edges]
                return sum(d+d*d/max(width,height) for d in lengths)
            current = wire_cost()
            for _ in range(8):
                best, move = current, None
                for a,b in pairs:
                    positions[a], positions[b] = positions[b], positions[a]
                    cost = wire_cost()
                    positions[a], positions[b] = positions[b], positions[a]
                    if cost < best-1:
                        best, move = cost, (a,b)
                if move is None:
                    break
                a,b = move
                positions[a], positions[b] = positions[b], positions[a]
                current = best
            paths = local_routes(spec,positions,boxes,parents,width,height,
                min(deadline,time.monotonic()+5),baseline.get('captions'),True)
            metrics = geometry_report(spec,positions,paths)
            if not metrics['node_overlaps'] and not metrics['connector_node_intersections']:
                metrics.update(out_of_bounds=0,containment_violations=0,
                               canvas_area_per_node=width*height/max(1,len(positions)))
                candidates.append({**baseline,'geometry':(positions,boxes,width,height),'paths':paths,
                    'labels':[None]*len(paths),'metrics':metrics,'candidate_source':'adjacent_dependencies'})
        except (ValueError,KeyError,TimeoutError):
            pass
    selected = min(candidates,key=lambda c:layout_quality(c['metrics']))
    # Near-equivalent routes: prefer the tighter page composition, not a large
    # mostly-empty canvas that makes normalized connector distances look small.
    best_score = layout_quality(selected['metrics'])
    peers = [c for c in candidates if layout_quality(c['metrics']) <= best_score+.5
             and all(c['metrics'].get(k,0) <= selected['metrics'].get(k,0)
                     for k in ('connector_crossings','ambiguous_connector_pairs'))]
    selected = min(peers,key=lambda c:c['geometry'][2]*c['geometry'][3])
    if spec.architecture_plan.get('review_composition'):
        # A reviewer repair must be evaluated as that repair, not silently
        # replaced by the original winning layout. The reviewer separately
        # rejects geometry regressions and checks the resulting image.
        selected = next((c for c in candidates if c['candidate_source']=='model_composition'),selected)
    selected['candidate_audit'] = [{'source':c['candidate_source'],'metrics':c['metrics'],
                                   'score':round(layout_quality(c['metrics']),2)} for c in candidates]
    selected['candidate_failures'] = failures
    print('[DIAGRAM][HYBRID] selected='+selected['candidate_source']+' '+json.dumps(selected['candidate_audit']),flush=True)
    return selected
