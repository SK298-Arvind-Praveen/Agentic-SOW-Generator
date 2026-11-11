"""Physical overview: retain deployment ownership, separate shared controls.

Every resource remains visible. Every connection remains on the editable detail
page. Control fan-out is represented by scoped control rails on the overview.
"""
from dataclasses import replace
from xml.etree import ElementTree as ET


def projection(spec):
    from app.diagram.narrative import support_ids
    support = support_ids(spec) | {n.id for n in spec.nodes
        if n.scope != 'external' and n.placement_role == 'operations'}
    # Authentication is part of an access path, even when tagged security.
    support -= {n.id for n in spec.nodes if 'cognito' in n.icon_key}
    visible, hidden = [], []
    for i, edge in enumerate(spec.edges):
        (hidden if edge.source in support or edge.target in support else visible).append(i)
    nodes = tuple(replace(n, placement_role='operations') if n.id in support
                  and n.placement_role not in {'security', 'operations'} else n for n in spec.nodes)
    plan = {**spec.architecture_plan, 'deployment_overview': True}
    # A layout for the full graph cannot prescribe positions for the projection.
    plan.pop('visual_layout', None)
    return replace(spec, nodes=nodes, edges=tuple(spec.edges[i] for i in visible), architecture_plan=plan), {
        'visible_edge_indices': visible, 'shared_control_edge_indices': hidden,
        'support_ids': sorted(support), 'all_edges_preserved_in_detail': True}


def prepare(service, spec):
    from app.diagram.hybrid import prepare as compose
    projected, coverage = projection(spec)
    projected = compose(service, projected)
    return replace(spec, architecture_plan={**spec.architecture_plan,
        'deployment_overview': {'visual_layout': projected.architecture_plan.get('visual_layout'),
                                'coverage': coverage}})


def render(spec, config, registry, timeout=None):
    import time
    from app.diagram.budgets import seconds
    from app.diagram.hybrid import layout
    from app.diagram.service import drawio_xml, render_png
    from app.diagram.drawio_renderer import render_drawio
    started = time.monotonic()
    projected, coverage = projection(spec)
    composition = spec.architecture_plan['deployment_overview'].get('visual_layout')
    if composition:
        projected = replace(projected, architecture_plan={**projected.architecture_plan, 'visual_layout': composition})
    geometry = layout(projected, config, timeout_seconds=seconds('layout'))
    render_png(projected, config, registry, layout_data=geometry)
    overview = ET.fromstring(drawio_xml(projected, registry, layout_data=geometry))
    page = overview.find('diagram')
    page.set('name', 'Deployment overview')
    # Explicitly disclose aggregation without drawing control wiring through runtime.
    model = page.find('mxGraphModel')
    root = model.find('root')
    _, _, width, height = geometry['geometry']
    cell = ET.SubElement(root, 'mxCell', id='overview_legend', value='Shared controls apply to their enclosing scope. Exact connections: Connection detail page.',
        style='text;html=0;fontSize=14;fontColor=#475569;align=center;whiteSpace=wrap;', vertex='1', parent='1')
    ET.SubElement(cell, 'mxGeometry', x='25', y=str(height+8), width=str(width-50), height='40', **{'as':'geometry'})
    model.set('pageHeight', str(height+60))
    from app.diagram.connection_detail import page as detail_page
    overview.append(detail_page(spec))
    remaining = max(1, (timeout or seconds('render')) - (time.monotonic()-started))
    png, xml, renderer = render_drawio(ET.tostring(overview, encoding='unicode'), timeout_seconds=remaining)
    parents = geometry['parents']
    membership = {}
    for node in spec.nodes:
        chain, parent = [], parents.get(node.id)
        while parent and parent != 'root':
            chain.append(geometry['captions'].get(parent, parent))
            parent = parents.get(parent)
        membership[node.id] = list(reversed(chain))
    return png, xml, {**renderer, 'overview_metrics': geometry['metrics'],
        'projection': coverage, 'rendered_membership': membership,
        'layout_candidates': geometry.get('candidate_audit', []), 'complete_graph_page': 'Connection detail'}
