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
Choose placement by the complete graph, including feedback/request edges. Avoid
page-wide return arrows, crossings and long loops. Service names remain unchanged.
Start with starting_composition; return it unchanged if it already reads clearly.
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
    return {'containers': {k:v for k,v in hierarchy(graph).items()
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
        deadline = time.monotonic() + 60
        value = structured_retry(
            lambda prompt: _call(service, prompt, deadline, planner=True, call_name='Architecture Composition'),
            COMPOSITION_RULES+'\n'+json.dumps(composition_context(spec,service.config)),
            lambda value: validate_composition(value, tree_for(spec, service.config)),
            attempts=3, deadline=deadline)
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
        if item['id'].startswith('__shared_controls'):
            rows = [[c['id'] for c in body]]
        elif item['id'].startswith('__aws_account') or (
                item['id']=='__aws_cloud' and any(c['id'] in global_ids for c in body)):
            # Keep global controls in a compact footer outside Region, not a
            # full-height column that makes the whole figure unreadably wide.
            regions=[c['id'] for c in body if 'children' in c]
            globals_=[c['id'] for c in body if 'children' not in c]
            rows=[[key] for key in regions]+([globals_] if globals_ else [])
        else:
            # Default is a row, never a surprise nested feature lane.
            rows = grids.get(item['id'], [[c['id'] for c in body]])
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
                    child['x'], child['y'] = x+(widths[col]-child['width'])/2, y
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
        default_side = ('right' if incoming >= outgoing and incoming else
                        'left' if outgoing else 'right')
        side = value.get('external_sides',{}).get(key, default_side)
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
    deadline = time.monotonic()+min(30,max(2,timeout_seconds or 30))
    candidates, failures = [], []
    try:
        reference = compose(spec,config,topology_composition(spec,config),min(deadline,time.monotonic()+8))
        reference['candidate_source'] = 'reference_topology'
        candidates.append(reference)
    except (ValueError,KeyError,TypeError,TimeoutError) as exc:
        failures.append('reference_topology: '+str(exc))
    composition = spec.architecture_plan.get('visual_layout')
    if composition:
        try:
            candidates.append(compose(spec,config,composition,min(deadline,time.monotonic()+8)))
        except (ValueError,KeyError,TypeError,TimeoutError) as exc:
            failures.append('composition: '+str(exc))
    # Independent baseline: never let the first candidate failing skip alternatives.
    for mode in ('LANES','SIDES'):
        remaining = deadline-time.monotonic()
        if remaining < 2:
            break
        try:
            candidate = elk_layout(spec,config,min(7,remaining),_optimize=False,
                                   _compound=True,_iconic=True,_flow_direction=mode)
            candidate.update(candidate_source='elk_'+mode.lower())
            candidates.append(candidate)
        except (ValueError,RuntimeError,TimeoutError,subprocess.TimeoutExpired) as exc:
            failures.append(mode+': '+str(exc))
    if not candidates:
        raise ValueError('No valid hybrid geometry: '+'; '.join(failures))
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
