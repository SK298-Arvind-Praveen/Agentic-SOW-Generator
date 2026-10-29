import base64
import io
import json
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET

from PIL import Image
import pytest

from app.diagram import elk
from app.diagram.service import DiagramService, DiagramSpec, Node, Edge, drawio_xml
from app.diagram.aws_icons import AwsIconRegistry


@pytest.fixture
def service():
    result = DiagramService.__new__(DiagramService)
    result.config = SimpleNamespace(ASSETS_DIR=Path(__file__).parents[1] / 'assets')
    result.icon_registry = AwsIconRegistry(result.config.ASSETS_DIR)
    return result


@pytest.fixture
def spec():
    return DiagramSpec('Support', (
        Node('user', 'Customer', 'actor', 0, scope='external'),
        Node('app', 'Support Application', 'application', 1, scope='vpc', availability_zone='A'),
        Node('model', 'Amazon Bedrock', 'service', 2, scope='vpc'),
        Node('data', 'Amazon S3', 'data', 2, scope='managed'),
        Node('crm', 'Existing CRM', 'external', 2, scope='external'),
    ), (Edge('user', 'app', 'HTTPS'), Edge('app', 'model', 'Inference'),
        Edge('app', 'data', 'Documents'), Edge('app', 'crm', 'Orders')))


def test_hierarchy_keeps_regional_services_outside_vpc(service, spec):
    graph = elk.build_graph(spec, service.config)
    cloud = next(n for n in graph['children'] if n['id'] == '__aws_cloud')
    region = cloud['children'][0]['children'][0]
    vpc = next(n for n in region['children'] if n['id'] == '__vpc')
    assert vpc['children'][0]['children'][0]['id'] == 'app'
    assert {'model', 'data'} <= {n['id'] for n in region['children']}
    assert {'user', 'crm'} <= {n['id'] for n in graph['children']}


def test_boundary_labels_are_generic_but_distinct_regions_remain_distinct(service):
    spec = DiagramSpec('Example', (
        Node('a', 'S3', 'data', 0, scope='managed', account='Proposed', region='ap-south-1'),
        Node('b', 'S3', 'data', 0, scope='managed', account='Proposed', region='us-east-1'),
    ), ())
    graph = elk.build_graph(spec, service.config)
    account = graph['children'][0]['children'][0]
    assert account['labels'][0]['text'] == 'AWS Account'
    assert len(account['children']) == 2
    assert {n['labels'][0]['text'] for n in account['children']} == {'Region'}
    assert account['children'][0]['id'] != account['children'][1]['id']
    assert spec.nodes[0].region == 'ap-south-1'


def test_real_layout_and_editable_export(service, spec, monkeypatch):
    monkeypatch.setenv('ARCHITECTURE_DIAGRAM_ENGINE', 'elk')
    data = elk.layout(spec, service.config)
    assert data['metrics']['node_overlaps'] == 0
    assert data['metrics']['connector_node_intersections'] == 0
    assert len(data['paths']) == len(spec.edges)
    xml = ET.fromstring(drawio_xml(spec, service.icon_registry, layout_data=data))
    for node in spec.nodes:
        geometry = xml.find(f".//mxCell[@id='{node.id}']/mxGeometry")
        assert float(geometry.get('x')) == data['geometry'][0][node.id][0]
        size = 22 if data.get('card_style') in {'compact', 'iconic'} else 26
        assert f'fontSize={size};' in xml.find(f".//mxCell[@id='{node.id}']").get('style')
    assert data['metrics']['estimated_caption_pt'] < data['metrics']['estimated_label_pt']
    assert 'fontSize=18;' in xml.find(".//mxCell[@id='edge_1']").get('style')
    asset = service._asset('architecture_overview', 'Solution Architecture', spec, {}, False)
    assert asset['layout_engine'] == 'elk', asset['renderer_fallback']
    Image.open(io.BytesIO(base64.b64decode(asset['image_base64']))).verify()
    assert asset['spec'] == spec.as_dict()
    assert asset['rendered_membership']['user'] == []
    assert asset['rendered_membership']['crm'] == []
    assert 'AWS Cloud' in asset['rendered_membership']['model']


def test_worker_timeout_uses_same_plan_without_llm(service, spec, monkeypatch):
    monkeypatch.setenv('ARCHITECTURE_DIAGRAM_ENGINE', 'elk')
    def fail(*args, **kwargs):
        raise TimeoutError('ELK deadline')
    monkeypatch.setattr(elk, 'layout', fail)
    asset = service._asset('architecture_overview', 'Solution Architecture', spec, {}, False)
    assert asset['layout_engine'] == 'legacy'
    assert asset['renderer_fallback'] == 'ELK deadline'
    assert asset['spec'] == spec.as_dict()


def test_worker_does_not_receive_credentials(service, spec, monkeypatch):
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'never-forward')
    monkeypatch.setattr(elk.shutil, 'which', lambda _: 'node')
    def run(*args, **kwargs):
        assert 'AWS_SECRET_ACCESS_KEY' not in kwargs['env']
        assert kwargs['timeout'] == 4
        assert json.loads(kwargs['input'])['edges']
        return SimpleNamespace(returncode=1, stderr='test failure')
    monkeypatch.setattr(elk.subprocess, 'run', run)
    with pytest.raises(RuntimeError, match='ELK worker failed'):
        elk.layout(spec, service.config, timeout_seconds=4)


def test_flowcharts_keep_existing_engine(service, spec, monkeypatch):
    monkeypatch.setenv('ARCHITECTURE_DIAGRAM_ENGINE', 'elk')
    monkeypatch.setattr(elk, 'layout', lambda *a, **k: pytest.fail('Unexpected ELK call'))
    assert service._asset('data_flow', 'Data flow', spec, {}, False)['layout_engine'] == 'legacy'


def test_default_is_hybrid(service, spec, monkeypatch):
    monkeypatch.delenv('ARCHITECTURE_DIAGRAM_ENGINE', raising=False)
    assert service._asset('architecture_overview', 'Solution Architecture', spec, {}, False)['layout_engine'] == 'hybrid'


def test_render_has_no_visible_title_or_generated_caveats(service, spec):
    from dataclasses import replace
    from app.diagram.service import render_png
    data = elk.layout(spec, service.config)
    changed = replace(spec, title='THIS MUST NOT APPEAR', note='Hosting requires validation',
                      description='Generated architecture commentary')
    assert render_png(spec, service.config, service.icon_registry, data) == render_png(
        changed, service.config, service.icon_registry, data)


def test_asset_keeps_design_metadata_out_of_visible_commentary(service, spec):
    asset = service._asset('architecture_overview', 'Solution Architecture', spec, {}, False)
    assert asset['description'] == asset['note'] == asset['caption'] == ''


def test_compact_cards_export_the_same_geometry_and_type_size(service, spec):
    data = elk.layout(spec, service.config, _compact=True, _optimize=False)
    xml = ET.fromstring(drawio_xml(spec, service.icon_registry, data))
    assert data['card_style'] == 'compact'
    assert len(data['paths']) == len(spec.edges)
    assert data['metrics']['containment_violations'] == 0
    assert all('fontSize=22;' in xml.find(f".//mxCell[@id='{n.id}']").get('style') for n in spec.nodes)


def test_real_aws_icons_and_cycles(service, monkeypatch):
    monkeypatch.setenv('ARCHITECTURE_DIAGRAM_ENGINE', 'elk')
    key = next(k for k, v in service.icon_registry.by_key.items() if v['label'] == 'Amazon Bedrock')
    spec = DiagramSpec('Cyclic integrations', (
        Node('a', 'Amazon Bedrock', 'service', 1, icon_key=key, scope='managed'),
        Node('b', 'Application', 'application', 1, scope='vpc'),
        Node('c', 'Existing service', 'external', 1, scope='external'),
    ), (Edge('b', 'a', 'Invoke'), Edge('a', 'c', 'Tool call'), Edge('c', 'b', 'Callback')))
    asset = service._asset('architecture_overview', 'Solution Architecture', spec, {}, False)
    assert asset['layout_engine'] == 'elk', asset['renderer_fallback']
    assert 'data:image/svg+xml,' in asset['drawio_xml']
    assert 'data:image/svg+xml;base64,' not in asset['drawio_xml']
    Image.open(io.BytesIO(base64.b64decode(asset['image_base64']))).verify()


def test_reviewer_uses_actual_elk_metrics(service, spec, monkeypatch, tmp_path):
    from app.agents import architecture_reviewer_agent as reviewer
    monkeypatch.setenv('ARCHITECTURE_DIAGRAM_ENGINE', 'elk')
    monkeypatch.setenv('ARCHITECTURE_VISION_REVIEW_ENABLED', 'true')
    monkeypatch.setenv('ARCHITECTURE_REVIEW_OUTPUT_DIR', str(tmp_path))
    asset = service._asset('architecture_overview', 'Solution Architecture', spec, {}, False)
    monkeypatch.setattr(reviewer, 'measurements', lambda *a: pytest.fail('Must not measure built-in geometry'))
    monkeypatch.setattr(reviewer, '_call', lambda *a, **k: json.dumps(
        {'issues': [], 'layout_patch': {'spacing_scale': 1.15}}))
    result = reviewer.review_architecture(service, asset, spec, {}, {}, 'Support architecture')
    assert result['layout_engine'] == 'elk'
    assert result['vision_review']['status'] in {'repaired_not_visually_rechecked', 'repair_rejected_geometry_regression'}


def test_portrait_image_uses_printable_page_height():
    from docx import Document
    from app.document.document_builder import DocumentBuilder
    builder = DocumentBuilder.__new__(DocumentBuilder)
    builder.doc = Document()
    output = io.BytesIO()
    Image.new('RGB', (500, 1000), 'white').save(output, 'PNG')
    asset = {'layout_engine': 'elk', 'image_base64': base64.b64encode(output.getvalue()).decode(),
             'title': 'Architecture', 'description': 'Design overview'}
    assert builder._add_architecture_diagram(asset) is not None
    shape = builder.doc.inline_shapes[0]
    page = builder.doc.sections[-1]
    assert shape.height.inches > 4.75
    assert shape.width <= page.page_width-page.left_margin-page.right_margin
    assert shape.height <= page.page_height-page.top_margin-page.bottom_margin


def test_compact_hierarchy_preserves_real_vpc_az_and_subnet_membership(service):
    spec = DiagramSpec('Private application', (
        Node('client', 'Client', 'external', 0, scope='external'),
        Node('app', 'Application', 'application', 1, scope='vpc', vpc='App VPC',
             availability_zone='A', subnet='private'),
        Node('replica', 'Replica', 'application', 1, scope='vpc', vpc='App VPC',
             availability_zone='B', subnet='private'),
        Node('s3', 'Amazon S3', 'data', 2, scope='managed'),
    ), (Edge('client', 'app', ''), Edge('app', 'replica', ''), Edge('app', 's3', '')))
    data = elk.layout(spec, service.config, _optimize=False, _compound=True, _iconic=True,
                      _flow_direction='SIDES')
    assert len(data['paths']) == 3
    assert data['metrics']['containment_violations'] == 0
    captions = list(data['captions'].values())
    assert {'App VPC', 'Availability Zone A', 'Availability Zone B', 'Private subnet'} <= set(captions)
    assert data['parents']['app'].endswith('_private')
    assert data['parents']['replica'].endswith('_private')
    assert data['parents']['s3'].startswith('__region')


def test_iconic_export_keeps_font_geometry_and_visible_icon_connections(service):
    key = next(k for k,v in service.icon_registry.by_key.items() if v['label'] == 'Amazon Bedrock')
    spec = DiagramSpec('Managed services', (
        Node('app', 'Application', 'external', 0, scope='external'),
        Node('model', 'Bedrock', 'service', 1, scope='managed', icon_key=key),
    ), (Edge('app', 'model', 'Invoke'),))
    data = elk.layout(spec, service.config, _optimize=False, _compound=True, _iconic=True)
    x,y,w,h = data['geometry'][0]['model']
    assert data['paths'][0][-1] in [(x+w/2-32,y+37), (x+w/2+32,y+37), (x+w/2,y+5)]
    xml = ET.fromstring(drawio_xml(spec, service.icon_registry, data))
    assert 'fontSize=22;' in xml.find(".//mxCell[@id='model']").get('style')


def test_workflow_rows_do_not_invent_visible_boundaries(service):
    from app.diagram.service import render_png
    from app.diagram.boundary_style import boundary_style
    key = next(k for k,v in service.icon_registry.by_key.items() if v['label'] == 'Amazon Bedrock')
    spec = DiagramSpec('Assist', (
        Node('client','Client','external',0,scope='external'),
        Node('model','Bedrock','service',1,scope='managed',icon_key=key,flow_id='assist'),
    ), (Edge('client','model','Invoke'),), architecture_plan={
        'view':'logical','flows':[{'id':'assist','label':'AI Assist','paths':[['client','model']]}]})
    data = elk.layout(spec,service.config,_optimize=False,_compound=True,_iconic=True,_flow_direction='LANES')
    assert data['parents']['model'].startswith('__region')
    assert not any(k.startswith('__flowlane_') for k in data['geometry'][1])
    assert data['parents']['client'] == 'root'
    assert data['metrics']['containment_violations'] == 0
    for key in ('__flowlane_test_0', '__shared_controls', 'functional', '__vpc_demo', '__region_demo'):
        assert boundary_style(key)['fill'] == '#FFFFFF'
    assert boundary_style('__vpc_demo_public')['fill'] != '#FFFFFF'
    assert boundary_style('__vpc_demo_private')['fill'] != '#FFFFFF'
