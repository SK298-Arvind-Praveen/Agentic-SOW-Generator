import copy
import hashlib
import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from types import SimpleNamespace

from PIL import Image
import pytest

from app.diagram import knowledge as kb, elk
from app.diagram.aws_icons import AwsIconRegistry
from app.diagram.boundary_style import boundary_style
from app.diagram.service import DiagramSpec, Node, Edge, drawio_xml, render_png
from scripts.build_curated_architecture_library import reviewed_assets


def test_new_archive_replaces_all_document_derived_cards():
    user = json.loads(kb.USER_LIBRARY.read_text(encoding='utf-8'))
    manifest = json.loads(kb.LIBRARY.with_name('curated-import.json').read_text(encoding='utf-8'))
    assert user['source_archive'] == 'Sample arch diagrams.zip'
    assert len(user['patterns']) == len(manifest['references']) == 10
    assert sum(c['category'] == 'data' for c in user['patterns']) == 6
    assert sum(c['category'] == 'genai' for c in user['patterns']) == 4
    assert len(kb.load_library()['patterns']) == 30
    assert len({c['image_sha256'] for c in user['patterns']}) == 10
    for c in user['patterns']:
        assert c['source_archive'] == user['source_archive']
        assert c['source_file'].endswith('.png') and 'source_document' not in c
        assert c['image_path'].startswith('references/upload-20261014/')
        with Image.open(kb.reference_image_path(c)) as im:
            assert list(im.size) == c['image_dimensions']
            im.verify()
    ids = {c['id'] for c in kb.load_library()['patterns']}
    assert not {'data-zero-etl-warehouse', 'genai-underwriting-layers', 'genai-omnichannel-support'} & ids


@pytest.mark.parametrize('query,category,reference', [
    ('Hudi CDC lakehouse', 'data', 'data-cdc-hudi-warehouse'),
    ('Agentic document QA and legibility validation', 'genai', 'genai-document-quality-checks'),
    ('Batch call analytics using speech analytics', 'genai', 'private-batch-call-analytics'),
    ('Credit underwriting', 'genai', 'genai-underwriting-deployment'),
    ('IBM DB2 migration', 'data', 'data-db2-migration'),
])
def test_categories_and_workload_retrieval(query, category, reference):
    req = {'features': [query]}
    assert category in kb.classify_categories(req)
    assert reference in [c['id'] for c in kb.select_patterns(req)]
    assert len(kb.reference_context(req)) <= 5000


def test_mixed_and_unmatched_workloads():
    assert set(kb.classify_categories('GenAI speech analytics data lake')) == {'genai', 'data'}
    assert kb.reference_image({'features': ['Cloud migration landing zone']}) is None
    assert not kb.select_patterns({'features': ['No Hudi.'], 'out_of_scope': ['Credit underwriting']})


def test_rejected_visual_is_text_only():
    req = {'features': ['Credit underwriting']}
    assert 'genai-underwriting-deployment' in kb.reference_context(req)
    assert 'incorrectly encloses' in kb.reference_context(req)
    assert kb.reference_image(req) is None
    assert kb.reference_image({'features': ['Hudi']}).startswith(b'\x89PNG')


@pytest.mark.parametrize('field,value', [('category', 'random'), ('view', 'subnet'), ('visual_enabled', 'yes')])
def test_reject_invalid_review_metadata(field, value):
    data = json.loads(kb.USER_LIBRARY.read_text(encoding='utf-8'))
    data['patterns'][0][field] = value
    with pytest.raises(ValueError):
        kb.validate_library(data)


def test_hash_and_path_tampering_rejected():
    card = copy.deepcopy(json.loads(kb.USER_LIBRARY.read_text(encoding='utf-8'))['patterns'][0])
    card['image_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='changed'):
        kb.reference_image_path(card)
    card['image_path'] = '../../outside.png'
    with pytest.raises(ValueError, match='Invalid'):
        kb.reference_image_path(card)


def test_importer_requires_exact_reviewed_archive(tmp_path):
    card = json.loads(kb.USER_LIBRARY.read_text(encoding='utf-8'))['patterns'][0]
    content = kb.reference_image_path(card).read_bytes()
    source = 'Sample arch diagrams/' + card['source_file']
    manifest = {'references': [{'source_file': card['source_file'], 'sha256': hashlib.sha256(content).hexdigest()}]}
    archive = tmp_path / 'test.zip'
    with ZipFile(archive, 'w') as bundle:
        bundle.writestr(source, content)
    assert len(reviewed_assets(archive, manifest)) == 1
    manifest['references'][0]['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='changed'):
        reviewed_assets(archive, manifest)
    with ZipFile(archive, 'a') as bundle:
        bundle.writestr('../../outside.png', content)
    with pytest.raises(ValueError, match='image list'):
        reviewed_assets(archive, manifest)


def test_real_boundary_badges_shading_and_editable_export():
    config = SimpleNamespace(ASSETS_DIR=Path(__file__).parents[1] / 'assets')
    registry = AwsIconRegistry(config.ASSETS_DIR)
    spec = DiagramSpec('Boundary QA', (
        Node('a', 'EC2 worker', 'service', 1, scope='vpc', availability_zone='az_a', subnet='private'),
        Node('b', 'NAT gateway', 'service', 2, scope='vpc', availability_zone='az_a', subnet='public'),
        Node('c', 'Amazon S3', 'data', 3, scope='managed'),
    ), (Edge('a', 'b'), Edge('a', 'c')))
    layout = elk.layout(spec, config)
    xml = ET.fromstring(drawio_xml(spec, registry, layout_data=layout))
    png = Image.open(BytesIO(render_png(spec, config, registry, layout_data=layout)))
    for group_id in layout['geometry'][1]:
        style = boundary_style(group_id)
        cell = xml.find(f".//mxCell[@id='group_{group_id}']")
        assert f"fillColor={style['fill']}" in cell.get('style')
        assert f"strokeColor={style['colour']}" in cell.get('style')
        assert f"dashed={int(style['dashed'])}" in cell.get('style')
        if style['icon_key']:
            assert style['icon_key'] in registry.group_by_key
            assert style['icon_key'] not in registry.by_key
            assert xml.find(f".//mxCell[@id='badge_{group_id}']") is not None
            assert registry.png(style['icon_key'], 28) is not None
            # Caption repaint must not erase the corner badge after connectors.
            x, y, _, _ = layout['geometry'][1][group_id]
            badge = registry.png(style['icon_key'], 28)
            assert png.getpixel((int(x+10), int(y+10))) == badge.getpixel((2, 2))[:3]
    assert layout['metrics']['containment_violations'] == 0
    assert layout['metrics']['node_overlaps'] == 0
    # Nested boundaries must not each reserve an entire caption-width gutter.
    assert max(layout['geometry'][2:]) < 1400
