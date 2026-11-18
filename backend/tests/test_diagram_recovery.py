import base64
import io
import json
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET

from PIL import Image
from app.diagram.service import DiagramService, DiagramSpec, Node, Edge, local_fallback_asset
from app.diagram.aws_icons import AwsIconRegistry


ASSETS = Path(__file__).parents[1] / 'assets'


def test_busy_interfaces_keep_overview_and_all_connections():
    from app.diagram.narrative import overview_xml
    raw = json.loads((Path(__file__).parent/'fixtures/busy_narrative_interfaces.json').read_text(encoding='utf-8-sig'))
    spec = DiagramSpec(raw['title'], tuple(Node(layer=0, **n) for n in raw['nodes']),
        tuple(Edge(**e) for e in raw['edges']), architecture_plan=raw['architecture_plan'])
    xml, metrics = overview_xml(spec, AwsIconRegistry(ASSETS))
    assert metrics['node_overlaps'] == metrics['connector_node_intersections'] == metrics['out_of_bounds'] == 0
    assert metrics['functional_groups'] == 4
    coverage = json.loads(ET.fromstring(xml).find('.//mxGraphModel').get('edgeCoverage'))
    indices = coverage['internal'] + coverage['shared']
    indices += [i for link in coverage['links'] for i in link['edge_indices']]
    assert sorted(indices) == list(range(len(spec.edges)))


def test_local_renderer_failure_preserves_original_graph(monkeypatch):
    spec = DiagramSpec('Recovery', (Node('a', 'Input', 'external', 0), Node('b', 'Processing', 'service', 1)), (Edge('a','b'),))
    def fail(*a, **k): raise RuntimeError('draw.io and icon renderer unavailable')
    monkeypatch.setattr('app.diagram.service.render_png', fail)
    asset = local_fallback_asset(SimpleNamespace(ASSETS_DIR=ASSETS), {}, {}, 'Primary renderer timed out', spec)
    assert asset['status'] == 'review_required'
    assert asset['spec'] == spec.as_dict()
    assert asset['retained_planned_spec']
    assert 'Primary renderer timed out' in asset['diagnostic']
    assert 'Local renderer failed' in asset['diagnostic']
    Image.open(io.BytesIO(base64.b64decode(asset['image_base64']))).verify()
    edges = ET.fromstring(asset['drawio_xml']).findall('.//mxCell[@edge="1"]')
    assert [(e.get('source'), e.get('target')) for e in edges] == [('a','b')]


def test_unexpected_pipeline_exception_returns_local_picture(monkeypatch):
    service = DiagramService.__new__(DiagramService)
    service.config = SimpleNamespace(ASSETS_DIR=ASSETS)
    def fail(*a, **k): raise RuntimeError('Bedrock unavailable')
    monkeypatch.setattr(service, '_generate_assets', fail)
    asset = service.generate_assets({'aws_services':['Amazon S3']}, {'project_title':'Storage'}, '')[0]
    assert asset['image_base64'] and asset['drawio_xml']
    assert asset['status'] == 'review_required'
    assert 'Bedrock unavailable' in asset['diagnostic']


def test_unverified_recovery_does_not_rewrite_architecture_text():
    from app.diagram.architecture_text import synchronize
    content = {'architecture_diagram':'Original agreed architecture'}
    asset = {'used_fallback':True,'status':'review_required','spec':{}}
    synchronize(None, content, [asset])
    assert content['architecture_diagram'] == 'Original agreed architecture'
    assert asset['text_alignment']['status'] == 'preserved'


def test_renderer_failure_retry_preserves_planned_architecture():
    service=DiagramService.__new__(DiagramService)
    spec=DiagramSpec('Accepted architecture',(Node('a','API','service',0),Node('b','Data','service',1)),(Edge('a','b'),))
    calls=[]
    def attempt(requirements,metadata,narrative):
        calls.append(requirements)
        return [{'spec':spec.as_dict(),'image_base64':'rendered',
                 'used_fallback':len(calls)==1,'retained_planned_spec':True}]
    service._generate_assets_once=attempt
    result=service._generate_assets_bounded({}, {}, '')
    assert len(calls)==2
    assert calls[1]['_architecture_retry_spec']==spec.as_dict()
    assert not result[0]['used_fallback']


def test_recovery_picture_is_embedded_in_download():
    from docx import Document
    from app.document.document_builder import DocumentBuilder
    asset = local_fallback_asset(SimpleNamespace(ASSETS_DIR=ASSETS),
        {'aws_services':['Amazon S3']}, {'project_title':'Storage'}, 'Planner unavailable')
    builder = DocumentBuilder.__new__(DocumentBuilder)
    builder.doc = Document()
    assert builder._add_architecture_diagram(asset) is not None
    assert len(builder.doc.inline_shapes) == 1


def test_exhausted_model_budget_keeps_valid_composition(monkeypatch):
    from app.diagram import narrative
    from app.diagram.reliability import model_attempts
    raw = json.loads((Path(__file__).parent/'fixtures/busy_narrative_interfaces.json').read_text(encoding='utf-8-sig'))
    spec = DiagramSpec(raw['title'], tuple(Node(layer=0, **n) for n in raw['nodes']),
        tuple(Edge(**e) for e in raw['edges']), architecture_plan={**raw['architecture_plan'],'retry_feedback':'Improve crossings'})
    monkeypatch.setattr(narrative, 'improve_rows', lambda s,r:s)
    token = model_attempts.set({'Architecture Narrative Composition':2})
    try:
        actual = narrative.prepare(SimpleNamespace(icon_registry=AwsIconRegistry(ASSETS)), spec)
        assert actual.architecture_plan['narrative_view'] == spec.architecture_plan['narrative_view']
        assert not actual.architecture_plan.get('narrative_diagnostic')
    finally:
        model_attempts.reset(token)
