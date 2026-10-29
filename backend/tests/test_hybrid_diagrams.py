from dataclasses import replace
from types import SimpleNamespace
from pathlib import Path
import time

import pytest

from app.diagram.service import DiagramSpec, Node, Edge
from app.diagram.hybrid import compose, tree_for, hierarchy, validate_composition

CONFIG = SimpleNamespace(ASSETS_DIR=Path(__file__).resolve().parents[1] / 'assets')


def sample():
    return DiagramSpec('Test', (
        Node('source','Existing system','external',0,scope='external'),
        Node('worker','AWS Lambda','service',1,scope='managed'),
        Node('model','Amazon Bedrock','service',2,scope='managed'),
        Node('private','Private worker','service',1,scope='vpc',subnet='private',availability_zone='az_a'),
    ), (Edge('source','worker'),Edge('worker','model'),Edge('private','worker')))


def test_composition_preserves_all_nodes_edges_and_nested_membership():
    spec = sample()
    result = compose(spec,CONFIG,{},time.monotonic()+8)
    assert set(result['geometry'][0]) == {n.id for n in spec.nodes}
    assert len(result['paths']) == len(spec.edges)
    assert result['parents']['source'] == 'root'
    assert result['parents']['private'].endswith('_private')
    assert result['metrics']['node_overlaps'] == 0
    assert result['metrics']['connector_node_intersections'] == 0


def test_grid_cannot_drop_duplicate_or_reparent_nodes():
    graph = tree_for(sample(),CONFIG)
    groups = hierarchy(graph)
    region = next(k for k in groups if k.startswith('__region'))
    children = groups[region]
    for row in (children[:-1],children+[children[0]],['source']+children):
        with pytest.raises(ValueError,match='preserve'):
            validate_composition({'grids':{region:[row]}},graph)
    validate_composition({'grids':{region:[children]}},graph)


def test_external_side_cannot_move_aws_service_outside():
    with pytest.raises(ValueError,match='external'):
        validate_composition({'external_sides':{'worker':'left'}},tree_for(sample(),CONFIG))


def test_invalid_composition_does_not_skip_other_candidates(monkeypatch):
    from app.diagram import elk, hybrid
    monkeypatch.setattr(elk,'layout',lambda *a,**kw: {'metrics':{},'geometry':({}, {},100,100)})
    spec = replace(sample(),architecture_plan={'visual_layout':{'grids':{'no-such-group':[['worker']]}}})
    result = hybrid.layout(spec,CONFIG,timeout_seconds=5)
    assert result['candidate_source'].startswith('elk_')
    assert result['candidate_failures']


def test_multiple_accounts_and_az_subnets_preserve_actual_ownership():
    spec = DiagramSpec('Deployment', (
        Node('a','Compute','service',0,scope='vpc',account='delivery',vpc='app',subnet='private',availability_zone='A'),
        Node('b','Compute','service',0,scope='vpc',account='delivery',vpc='app',subnet='private',availability_zone='B'),
        Node('c','Data','data',1,scope='managed',account='customer'),
    ), ())
    graph = tree_for(spec,CONFIG)
    assert len(graph['children'][0]['children']) == 2
    result = compose(spec,CONFIG,{},time.monotonic()+8)
    assert result['parents']['a'] != result['parents']['b']
    assert result['parents']['a'].endswith('_private')
    assert result['metrics']['containment_violations'] == 0


def test_visual_repair_candidate_is_actually_rendered(monkeypatch):
    from app.diagram import elk, hybrid
    monkeypatch.setattr(elk,'layout',lambda *a,**kw: {'metrics':{},'geometry':({}, {},100,100)})
    spec = replace(sample(),architecture_plan={'visual_layout':{},'review_composition':True})
    # Nonempty layout object selects a real validated composition.
    spec = replace(spec,architecture_plan={'visual_layout':{'grids':{}},'review_composition':True})
    result = hybrid.layout(spec,CONFIG,timeout_seconds=5)
    assert result['candidate_source'] == 'model_composition'


def test_png_label_positions_are_reused_in_editable_export():
    from app.diagram.service import render_png, drawio_xml
    from xml.etree import ElementTree as ET
    spec = DiagramSpec('Test', (
        Node('source','Source','external',0,scope='external'),
        Node('worker','Worker','service',1,scope='managed'),
    ), (Edge('source','worker','Read'),))
    data = compose(spec,CONFIG,{},time.monotonic()+8)
    first = render_png(spec,CONFIG,layout_data=data)
    assert data['labels'][0]
    assert first == render_png(spec,CONFIG,layout_data=data)
    xml = ET.fromstring(drawio_xml(spec,layout_data=data))
    assert xml.find(".//mxCell[@id='edge_1']/mxGeometry/mxPoint[@as='offset']") is not None
    style = xml.find(".//mxCell[@id='edge_1']").get('style')
    assert 'noEdgeStyle=1;' in style
    assert 'entryPerimeter=0;' in style and 'exitPerimeter=0;' in style
