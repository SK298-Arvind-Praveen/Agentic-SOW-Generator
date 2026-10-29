"""Local, bounded ELK layout; shared geometry for PNG and editable draw.io."""
import json
import hashlib
import math
import os
from pathlib import Path
import shutil
import subprocess
import time

from PIL import Image, ImageDraw


def build_graph(spec, config, direction='RIGHT', flow_direction=None, compact=False, iconic=False):
    from app.diagram.service import _architecture_role, _architecture_scope, _font, _wrapped_lines
    draw = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    scale = max(1, min(1.25, spec.spacing_scale))
    options = {
        'elk.algorithm': 'layered', 'elk.direction': direction,
        'elk.edgeRouting': 'ORTHOGONAL', 'elk.hierarchyHandling': 'INCLUDE_CHILDREN',
        'elk.padding': '[top=44,left=14,bottom=14,right=14]',
        'elk.spacing.nodeNode': str(36 * scale),
        'elk.layered.spacing.nodeNodeBetweenLayers': str(40 * scale),
        'elk.spacing.edgeNode': '20', 'elk.spacing.edgeEdge': '16',
        'elk.randomSeed': '1',
    }
    graph = {'id': 'root', 'layoutOptions': options, 'children': [], 'edges': []}
    containers = {}
    parents = {}
    connected = {key for edge in spec.edges for key in (edge.source, edge.target)}
    plan = spec.architecture_plan
    flow_labels = {f['id']: f.get('label') or f['id'] for f in plan.get('flows', [])}
    def boundary_id(prefix, *parts):
        if not any(parts):
            return prefix
        digest = hashlib.sha256(json.dumps(parts).encode('utf-8')).hexdigest()[:16]
        return prefix + '_' + digest
    def group(key, label, parent):
        if key not in containers:
            # ELK H_LEFT reserves the entire label width down the left side at
            # every nesting level. Reserve a top header row instead; renderers
            # paint its badge and caption left-aligned within that clear row.
            group_options = {**options, 'elk.padding': '[top=9,left=14,bottom=14,right=14]'}
            if flow_direction in {'RIGHT', 'DOWN'} and (key.startswith('__vpc') or '__elk_az_' in key):
                group_options['elk.direction'] = flow_direction
            item = {'id': key, 'children': [], 'layoutOptions': group_options,
                    'labels': [{'text': label, 'width': max(120, len(label)*9+46), 'height': 30,
                                'layoutOptions': {'elk.nodeLabels.placement': 'INSIDE H_CENTER V_TOP'}}]}
            parent['children'].append(item)
            containers[key] = item
            parents[key] = parent['id']
        return containers[key]

    for node in spec.nodes:
        parent = graph
        role = _architecture_role(node, {g.id: g for g in spec.groups})
        scope = _architecture_scope(node, role)
        if scope != 'external':
            cloud = group('__aws_cloud', 'AWS Cloud', graph)
            account = group(boundary_id('__aws_account', node.account), 'AWS Account', cloud)
            parent = account if scope == 'global' else group(
                boundary_id('__region', node.account, node.region), 'Region', account)
            if role in {'security', 'operations'} and node.id not in connected and scope not in {'vpc', 'az'}:
                # Pack disconnected shared controls together instead of letting
                # ELK stack them down the entire left edge of the runtime graph.
                parent = group(boundary_id('__shared_controls', parent['id']),
                               'Account security' if scope == 'global' else 'Security and monitoring', parent)
                parent['layoutOptions']['elk.algorithm'] = 'org.eclipse.elk.box'
                parent['layoutOptions']['elk.aspectRatio'] = '3'
                parent['layoutOptions']['elk.padding'] = '[top=44,left=24,bottom=24,right=24]'
            if scope in {'vpc', 'az'}:
                parent = group(boundary_id('__vpc', node.account, node.region, node.vpc), node.vpc or 'VPC', parent)
                # Only show an AZ explicitly present in the plan; never invent HA/subnets.
                if node.availability_zone:
                    zone = str(node.availability_zone)
                    parent = group(parent['id'] + '__elk_az_' + zone, 'Availability Zone ' + zone, parent)
                if node.subnet in {'public', 'private', 'isolated'}:
                    parent = group(parent['id'] + '_' + node.subnet, node.subnet.title() + ' subnet', parent)
            # flow_id guides placement only; it does not establish a boundary.
        label_lines = _wrapped_lines(draw, node.label, _font(config, True, 26),
                                     190 if node.icon_key else 176, 99)
        subtitle_lines = _wrapped_lines(draw, node.subtitle, _font(config, False, 18), 176, 99) if node.subtitle else []
        height = max(140, 90 + len(label_lines)*30 + len(subtitle_lines)*22) if node.icon_key else max(112, 30 + len(label_lines)*30 + len(subtitle_lines)*22)
        card_width = 204
        if compact:
            card_width = 260
            text_width = 180 if node.icon_key else 232
            label_lines = _wrapped_lines(draw, node.label, _font(config, True, 22), text_width, 99)
            subtitle_lines = _wrapped_lines(draw, node.subtitle, _font(config, False, 16), text_width, 99) if node.subtitle else []
            height = max(88, 24 + len(label_lines)*26 + len(subtitle_lines)*20)
        if iconic:
            card_width = 168
            label_lines = _wrapped_lines(draw, node.label, _font(config, True, 22), 154 if node.icon_key else 140, 99)
            subtitle_lines = _wrapped_lines(draw, node.subtitle, _font(config, False, 16), 140, 99) if node.subtitle else []
            height = max(112, (80 if node.icon_key else 24) + len(label_lines)*26 + len(subtitle_lines)*20)
        compact_global = iconic and scope == 'global' and node.id not in connected
        if compact_global:
            card_width = 260
            label_lines = _wrapped_lines(draw,node.label,_font(config,True,22),180,99)
            subtitle_lines = _wrapped_lines(draw,node.subtitle,_font(config,False,16),180,99) if node.subtitle else []
            height = max(88,24+len(label_lines)*26+len(subtitle_lines)*20)
        parent['children'].append({'id': node.id, 'width': card_width, 'height': height,
                                   'flowId': node.flow_id, 'iconicAnchor': bool(iconic and node.icon_key and not compact_global)})
        parents[node.id] = parent['id']
    font = _font(config, False, 18)
    for i, edge in enumerate(spec.edges):
        item = {'id': 'e' + str(i), 'sources': [edge.source], 'targets': [edge.target]}
        if edge.label:
            box = draw.textbbox((0, 0), edge.label, font=font)
            item['labels'] = [{'text': edge.label, 'width': box[2]-box[0]+18,
                               'height': 32, 'layoutOptions': {'elk.edgeLabels.placement': 'CENTER'}}]
        def ancestors(key):
            result = []
            while key in parents:
                key = parents[key]
                result.append(key)
            return result
        target_ancestors = set(ancestors(edge.target))
        common = next(key for key in ancestors(edge.source) if key in target_ancestors)
        owner = graph if common == 'root' else containers[common]
        owner.setdefault('edges', []).append(item)
    return graph


def layout(spec, config, timeout_seconds=None, _direction='RIGHT', _optimize=True, _flow_direction=None, _compact=False, _packed=False, _compound=False, _iconic=False):
    started = time.monotonic()
    node = shutil.which('node')
    if not node:
        raise RuntimeError('ELK requires Node.js on the backend PATH')
    worker = Path(__file__).resolve().parents[3] / 'tools' / 'architecture-layout' / 'layout.cjs'
    timeout = min(30, max(1, float(timeout_seconds or 30)))
    env = {k: v for k, v in os.environ.items() if k.upper() in
           {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'COMSPEC'}}
    print(f'[DIAGRAM][ELK] Layout start; nodes={len(spec.nodes)}; edges={len(spec.edges)}', flush=True)
    graph = build_graph(spec, config, _direction, _flow_direction, _compact, _iconic)
    if _compound:
        graph['compactHierarchy'] = True
        graph['externalSides'] = _flow_direction in {'SIDES', 'LANES'}
        graph['flowLanes'] = _flow_direction == 'LANES'
        graph['flows'] = spec.architecture_plan.get('flows', [])
    if _packed:
        # A long cross-boundary path can stretch layered layout across the page.
        # Compare a compact, still nested ELK box layout with separately checked
        # orthogonal routing. Never change ownership, subnet membership or edges.
        def pack(item):
            item.pop('edges', None)
            if 'children' in item:
                item['layoutOptions'].update({'elk.algorithm': 'org.eclipse.elk.box',
                                             'elk.aspectRatio': '1.4',
                                             'elk.padding': '[top=44,left=18,bottom=18,right=18]'})
                for child in item['children']:
                    pack(child)
        pack(graph)
    result = subprocess.run([node, str(worker)], input=json.dumps(graph),
                            text=True, encoding='utf-8', capture_output=True, timeout=timeout,
                            env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode:
        raise RuntimeError('ELK worker failed; run npm ci --prefix tools/architecture-layout. ' + result.stderr[:500])
    data = json.loads(result.stdout)
    positions, boxes, paths, labels, captions = {}, {}, {}, {}, {}
    containment = {}
    def visit(item, ox=30, oy=30):
        x, y = ox + item.get('x', 0), oy + item.get('y', 0)
        if item['id'] != 'root':
            rect = (x, y, item['width'], item['height'])
            if 'children' in item:
                boxes[item['id']] = rect
                captions[item['id']] = item['labels'][0]['text']
            else:
                positions[item['id']] = rect
        for edge in item.get('edges', []):
            sections = edge.get('sections', [])
            if len(sections) != 1:
                raise ValueError('ELK returned an incomplete or branching edge')
            section = sections[0]
            points = [section['startPoint'], *section.get('bendPoints', []), section['endPoint']]
            paths[edge['id']] = [(p['x']+x, p['y']+y) for p in points]
            if edge.get('labels'):
                label = edge['labels'][0]
                labels[edge['id']] = (label['x']+x, label['y']+y, label['width'], label['height'])
        for child in item.get('children', []):
            containment[child['id']] = item['id']
            visit(child, x, y)
    visit(data)
    if set(positions) != {n.id for n in spec.nodes} or (not (_packed or _compound) and set(paths) != {'e'+str(i) for i in range(len(spec.edges))}):
        raise ValueError('ELK dropped a component or connection')
    width, height = math.ceil(data['width']+60), math.ceil(data['height']+60)
    if width * height > 24_000_000 or min(width, height) < 1:
        raise ValueError('ELK canvas exceeds safe image dimensions')
    all_values = [v for box in list(positions.values()) + list(boxes.values()) for v in box]
    all_values += [v for points in paths.values() for point in points for v in point]
    if not all(math.isfinite(v) and v >= 0 for v in all_values):
        raise ValueError('ELK returned invalid geometry')
    from app.diagram.review import geometry_report
    if _packed or _compound:
        from app.diagram.review import local_routes, layout_quality
        ordered = local_routes(spec, positions, boxes, containment, width, height, started+timeout, captions, _iconic)
        # Barycentres are a starting point, not a final ordering. Try bounded
        # peer swaps on the external top rail; a hub between two sources can
        # otherwise force a connector over another external-system box.
        external = [n.id for n in spec.nodes if containment.get(n.id) == 'root']
        if _compound and 1 < len(external) <= 4 and len({positions[k][1] for k in external}) == 1:
            from itertools import combinations
            best_score = layout_quality(geometry_report(spec, positions, ordered))
            initial = positions.copy()
            for a,b in combinations(external, 2):
                trial = initial.copy()
                ax,ay,aw,ah = trial[a]
                bx,by,bw,bh = trial[b]
                if aw != bw:
                    continue
                trial[a],trial[b] = (bx,ay,aw,ah),(ax,by,bw,bh)
                try:
                    trial_paths = local_routes(spec, trial, boxes, containment, width, height, started+timeout, captions, _iconic)
                except TimeoutError:
                    break
                except ValueError:
                    continue
                trial_metrics = geometry_report(spec, trial, trial_paths)
                score = layout_quality(trial_metrics)
                if not trial_metrics['node_overlaps'] and not trial_metrics['connector_node_intersections'] and score < best_score:
                    positions,ordered,best_score = trial,trial_paths,score
        if any(not math.isfinite(v) or v < 0 or v > bound
               for path in ordered for point in path for v, bound in zip(point, (width, height))):
            raise ValueError('Packed routing escaped canvas')
    else:
        ordered = [paths['e'+str(i)] for i in range(len(spec.edges))]
    metrics = geometry_report(spec, positions, ordered)
    metrics['workflow_lanes'] = sum(key.startswith('__flowlane_') for key in boxes)
    # Approximate main labels and smaller captions at a 6.5 x 8 inch Word figure.
    # Geometry can pass yet be unreadable after shrinking to the page.
    metrics['estimated_label_pt'] = round((22 if _compact or _iconic else 26) * min(468 / width, 576 / height), 2)
    metrics['estimated_caption_pt'] = round(18 * min(468 / width, 576 / height), 2)
    metrics['estimated_subtitle_pt'] = round((16 if _compact or _iconic else 18) * min(468 / width, 576 / height), 2)
    metrics['page_readability_warning'] = metrics['estimated_label_pt'] < 7 or metrics['estimated_subtitle_pt'] < 6
    metrics['out_of_bounds'] = sum(x+w > width or y+h > height for x, y, w, h in positions.values())
    rectangles = {**boxes, **positions}
    metrics['containment_violations'] = sum(
        not (rectangles[parent][0] <= rect[0] and rectangles[parent][1] <= rect[1]
             and rect[0] + rect[2] <= sum((rectangles[parent][0], rectangles[parent][2])) + .01
             and rect[1] + rect[3] <= sum((rectangles[parent][1], rectangles[parent][3])) + .01)
        for key, rect in rectangles.items()
        if (parent := containment.get(key)) in boxes)
    if metrics['node_overlaps'] or metrics['connector_node_intersections'] or metrics['out_of_bounds'] or metrics['containment_violations']:
        raise ValueError('ELK returned obstructed geometry: ' + str(metrics))
    print(f'[DIAGRAM][ELK] Complete; canvas={width}x{height}; metrics={metrics}; elapsed={time.monotonic()-started:.2f}s', flush=True)
    selected = {'geometry': (positions, boxes, width, height), 'paths': ordered,
            'compact_nodes': [n.id for n in spec.nodes if _iconic and n.scope == 'global'
                              and not any(n.id in (e.source,e.target) for e in spec.edges)],
            'labels': [labels.get('e'+str(i)) for i in range(len(spec.edges))],
            'captions': captions, 'metrics': metrics, 'parents': containment,
            'card_style': 'iconic' if _iconic else ('compact' if _compact else 'vertical')}
    # Compare actual routed geometry, not an LLM's guess at coordinates. One
    # bounded local alternatives; never remove an edge or alter containment.
    remaining = timeout - (time.monotonic() - started)
    if _optimize and remaining > 2:
      for direction, compact, packed, compound, iconic, external_sides in [
                ('RIGHT', False, False, True, True, 'LANES'),
                ('RIGHT', False, False, True, True, False), ('DOWN', False, False, True, True, False),
                ('RIGHT', False, False, True, True, True), ('DOWN', False, False, True, True, True),
                ('RIGHT', False, True, False, True, False), ('DOWN', False, False, False, True, False),
                ('RIGHT', True, False, True, False, False), ('DOWN', False, False, False, False, False)]:
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 2:
            break
        try:
            alternate = layout(spec, config, min(5, remaining), direction, False,
                               external_sides if isinstance(external_sides, str) else ('SIDES' if external_sides else None),
                               compact, packed, compound, iconic)
            other = alternate['metrics']
            best = selected['metrics']
            from app.diagram.review import layout_quality
            if layout_quality(other) < layout_quality(best):
                selected = alternate
                print(f'[DIAGRAM][ELK] Selected direction={direction}, compact={compact}, iconic={iconic}, compound={compound}, packed={packed}: '
                      'better readability/connector locality', flush=True)
        except (RuntimeError, ValueError, TimeoutError, subprocess.TimeoutExpired) as exc:
            print(f'[DIAGRAM][ELK] Alternative rejected; retained validated layout: {exc}', flush=True)
    return selected
