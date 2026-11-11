"""Lossless connection register accompanying the visual architecture overview.

Dense security/monitoring fan-out is reference information, not a second layout
problem. Every original node and directed edge is retained in editable rows.
"""
from xml.etree import ElementTree as ET


def page(spec):
    diagram = ET.Element('diagram', id='connection_detail', name='Connection detail')
    model = ET.SubElement(diagram, 'mxGraphModel', page='1', pageWidth='1500',
                          pageHeight=str(180 + 56 * (len(spec.edges) + len(spec.nodes))))
    root = ET.SubElement(model, 'root')
    ET.SubElement(root, 'mxCell', id='0')
    ET.SubElement(root, 'mxCell', id='1', parent='0')
    def row(key, values, y, heading=False):
        for col, (value, x, width) in enumerate(zip(values, (30, 500, 970), (460, 460, 500))):
            cell = ET.SubElement(root, 'mxCell', id=f'{key}_{col}', value=value,
                style='text;html=0;whiteSpace=wrap;align=left;verticalAlign=middle;spacing=8;'
                      'fontSize=14;strokeColor=#CBD5E1;fillColor=' + ('#E2E8F0' if heading else '#FFFFFF') + ';',
                vertex='1', parent='1')
            ET.SubElement(cell, 'mxGeometry', x=str(x), y=str(y), width=str(width), height='56', **{'as':'geometry'})
    nodes = {n.id:n for n in spec.nodes}
    label = lambda key: nodes[key].label + ' [' + key + ']'
    row('edges_header', ('Source', 'Directed interaction', 'Destination'), 20, True)
    y = 76
    for i, edge in enumerate(spec.edges):
        row(f'edge_{i}', (label(edge.source), '→ ' + (edge.label or 'Dependency'), label(edge.target)), y)
        entry = root.find(f"mxCell[@id='edge_{i}_1']")
        entry.set('sourceNode', edge.source)
        entry.set('targetNode', edge.target)
        y += 56
    y += 28
    row('nodes_header', ('Component', 'Deployment scope', 'Purpose'), y, True)
    y += 56
    for i, node in enumerate(spec.nodes):
        scope = ' / '.join(str(v) for v in (node.scope, node.account, node.region, node.vpc,
                                            node.subnet, node.availability_zone) if v)
        row(f'node_{i}', (label(node.id), scope, node.subtitle or node.placement_role), y)
        root.find(f"mxCell[@id='node_{i}_0']").set('nodeId', node.id)
        y += 56
    return diagram
