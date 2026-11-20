"""One provenance contract shared by all overview renderers and annotations."""
import json
from xml.etree import ElementTree as ET


def selected_edge_indices(spec):
    story = spec.architecture_plan.get('process_story')
    if not story: return None
    return {int(key[1:]) for step in story['steps'] for key in step['edge_ids']}


def select_links(spec, links):
    selected = selected_edge_indices(spec)
    if selected is None: return links
    # Preserve each retained connector's full path; never splice unrelated edges.
    return [link for link in links if any(i in selected for path in link['paths'] for i in path)]


def merge_reciprocal_links(links):
    """One two-way overview wire for two real, selected opposite paths.

    Merge only after story selection. Keep every directed path independently
    traceable, without changing the source graph or inventing response traffic.
    """
    result=[]
    for link in links:
        edge=link['edge']
        reverse=next((item for item in result if item['edge'].source==edge.target
                      and item['edge'].target==edge.source),None)
        if reverse is None:
            result.append({**link,'paths':list(link['paths'])})
        else:
            reverse['paths'].extend(link['paths'])
            reverse['both']=True
    return result


def connections_from_xml(xml, spec):
    root = ET.fromstring(xml).find('./diagram/mxGraphModel/root')
    if root is None: raise ValueError('Architecture overview XML missing')
    plan = spec.architecture_plan.get('narrative_view') or {}
    owner = {key: group['id'] for group in plan.get('groups', []) for row in group['rows'] for key in row}
    from app.diagram.narrative import support_ids
    support = support_ids(spec)
    result = []
    for cell in root.findall('mxCell'):
        if cell.get('edge') != '1': continue
        source = cell.get('sourceNode') or cell.get('overviewSource') or cell.get('source')
        target = cell.get('targetNode') or cell.get('overviewTarget') or cell.get('target')
        paths = json.loads(cell.get('originalEdgePaths', '[]'))
        if not paths:
            pairs = {(source, target)}
            if 'startArrow=block' in cell.get('style', ''): pairs.add((target, source))
            paths = [[i] for i, e in enumerate(spec.edges) if
                     (e.source, e.target) in pairs or (owner.get(e.source, e.source), owner.get(e.target, e.target)) in pairs]
        if not paths: continue
        if any(not p or any(type(i) is not int or i < 0 or i >= len(spec.edges) for i in p) for p in paths):
            raise ValueError('Invalid original edge path in renderer')
        for path in paths:
            for a, b in zip(path, path[1:]):
                if spec.edges[a].target != spec.edges[b].source:
                    raise ValueError('Overview path is not a directed graph path')
        category = ('shared_control' if source in support or target in support else
                    'internal' if owner.get(source) is not None and owner.get(source) == owner.get(target) else 'story')
        result.append({'id': cell.get('id'), 'source': source, 'target': target,
                       'edge_paths': paths, 'category': category})
    return result
