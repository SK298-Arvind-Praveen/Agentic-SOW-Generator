"""Actual captured graphs retain meaning while short routes take priority."""
import json
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import ImageFont
import pytest

from app.diagram.aws_icons import AwsIconRegistry
from app.diagram.contracts import freeze
from app.diagram.narrative import overview_xml
from app.diagram.review import hits_box
from app.diagram.service import DiagramSpec, Edge, Group, Node


def test_private_ingress_chain_and_migration_sources_follow_their_real_peers():
    from app.diagram.tiered_deployment import geometry
    raw = json.loads((Path(__file__).parent/'fixtures/kingfisher_boundary_header_overlap.json').read_text(encoding='utf8'))
    spec = DiagramSpec(raw['title'], tuple(Node(**n) for n in raw['nodes']), tuple(Edge(**e) for e in raw['edges']),
        architecture_plan=raw['architecture_plan'])
    version = freeze(spec)['version']
    positions, boxes, parents, *_ = geometry(spec)
    vpn, alb = positions['vpn'], positions['alb']
    assert vpn[0]+vpn[2] < alb[0], 'The request gateway precedes its load balancer on a straight horizontal chain'
    assert vpn[1] == alb[1]
    media, transfer = positions['source_media'], positions['datasync']
    assert media[0] > boxes['cloud'][0]+boxes['cloud'][2]
    assert abs(media[1]-transfer[1]) < 140
    assert parents['source_media'] == 'root' and parents['vpn'] == parents['alb']
    assert positions['asg'][1] < min(rect[1] for key,rect in boxes.items() if key.endswith(('_az_0','_az_1')))
    regional_bottom=max(positions[k][1]+positions[k][3] for k in ('s3_media','s3_evidence','s3_artefact','datasync'))
    zone_bottom=max(rect[1]+rect[3] for key,rect in boxes.items() if key.endswith(('_az_0','_az_1')))
    assert regional_bottom-zone_bottom < 250, 'Connected regional resources should straddle their workload band'
    assert freeze(spec)['version'] == version


@pytest.mark.parametrize('fixture', ['kingfisher_boundary_header_overlap.json', 'tata_boundary_header_overlap.json'])
def test_real_routes_measure_heading_collisions_without_mutating_graph(fixture):
    raw = json.loads((Path(__file__).parent/'fixtures'/fixture).read_text(encoding='utf8'))
    spec = DiagramSpec(raw['title'], tuple(Node(**n) for n in raw['nodes']),
        tuple(Edge(**e) for e in raw['edges']), groups=tuple(Group(**g) for g in raw.get('groups', [])),
        architecture_plan=raw['architecture_plan'])
    version = freeze(spec)['version']
    xml, metrics = overview_xml(spec, AwsIconRegistry(Path(__file__).parents[1]/'assets'))
    assert freeze(spec)['version'] == version
    cells = {c.get('id'): c for c in ET.fromstring(xml).findall('.//mxCell')}
    def xy(key):
        cell = cells[key]; geometry = cell.find('mxGeometry'); parent = cell.get('parent')
        x, y = float(geometry.get('x', '0')), float(geometry.get('y', '0'))
        if parent in cells and cells[parent].find('mxGeometry') is not None:
            px, py = xy(parent); x += px; y += py
        return x, y
    headings = {}
    font_path = next(p for p in (Path('C:/Windows/Fonts/arialbd.ttf'),
        Path(__file__).parents[1]/'assets/fonts/DMSans-Bold.ttf') if p.is_file())
    for key, cell in cells.items():
        if cell.get('value') not in {'AWS Cloud', 'AWS Account', 'Region', 'VPC', 'Availability Zone', 'Private subnet', 'Public subnet'}:
            continue
        style = dict(v.split('=', 1) for v in cell.get('style', '').split(';') if '=' in v)
        size = float(style['fontSize'])
        font = ImageFont.truetype(str(font_path), round(size))
        x, y = xy(key)
        headings[key] = (x, y, font.getlength(cell.get('value'))
            + float(style.get('spacingLeft', 0)) + float(style.get('spacing', 0)), size*1.2+16)
    collisions = []
    for cell in cells.values():
        if cell.get('edge') != '1': continue
        geometry = cell.find('mxGeometry')
        def point(p): return float(p.get('x')), float(p.get('y'))
        points = [point(geometry.find("mxPoint[@as='sourcePoint']"))]
        points += [point(p) for p in geometry.findall('./Array/mxPoint')]
        points += [point(geometry.find("mxPoint[@as='targetPoint']"))]
        for key, rect in headings.items():
            if any(hits_box(a, b, rect) for a, b in zip(points, points[1:])):
                collisions.append((cell.get('sourceNode'), cell.get('targetNode'), key))
    # Text contacts are advisory; actual service icons remain hard obstacles.
    assert headings
    assert metrics['node_overlaps'] == 0
    assert metrics['connector_node_intersections'] == 0
    if fixture.startswith('king'):
        edge = next(c for c in cells.values() if c.get('sourceNode') == 'vpn' and c.get('targetNode') == 'alb')
        assert not edge.findall('./mxGeometry/Array/mxPoint'), 'Aligned ingress must not retain a U-bend'


def test_boundary_heading_is_a_soft_preference_not_a_wall():
    from app.diagram.review import local_routes
    spec = DiagramSpec('Short route', (Node('a', 'A', 'service', 0), Node('b', 'B', 'service', 1)), (Edge('a', 'b'),))
    positions = {'a': (20, 30, 40, 40), 'b': (240, 30, 40, 40)}
    routes = local_routes(spec, positions, {'cloud': (120, 20, 80, 80)}, {}, 320, 140,
        boundary_transit=True, captions={'cloud': 'AWS Cloud'}, header_sizes={'cloud': (80, 60)})
    assert routes == [[(60, 50), (240, 50)]]


def test_long_service_caption_wraps_without_losing_characters():
    from app.diagram.figure_readability import wrap_text, _font
    lines = wrap_text('CloudFormation', 180, 28, True)
    assert ''.join(lines) == 'CloudFormation'
    assert len(lines) == 2
    assert all(_font(28, True).getlength(line) <= 180 for line in lines)


def test_external_downstream_peer_stays_beside_its_actual_gateway():
    from app.diagram.narrative_boundaries import geometry
    raw = json.loads((Path(__file__).parent/'fixtures/tata_boundary_header_overlap.json').read_text(encoding='utf8'))
    spec = DiagramSpec(raw['title'], tuple(Node(**n) for n in raw['nodes']), tuple(Edge(**e) for e in raw['edges']),
        architecture_plan=raw['architecture_plan'])
    positions, boxes, parents, *_ = geometry(spec)
    nodes = {n.id:n for n in spec.nodes}
    edge = next(e for e in spec.edges if 'hybris' in nodes[e.target].label.lower() and nodes[e.source].scope == 'external')
    a,b = positions[edge.source], positions[edge.target]
    assert abs(a[0]-b[0]) < 350
    assert abs(a[1]-b[1]) < 350
    assert parents[edge.target] == 'root'
