"""Local renderer contract; live Desktop smoke test is scripts/smoke_drawio.py."""
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from app.diagram import drawio_renderer as renderer
from app.diagram.service import DiagramService, DiagramSpec, Node, Edge, drawio_xml


def xml():
    return drawio_xml(DiagramSpec('Test', (Node('a', 'Input', 'external', 0),
                                          Node('b', 'Worker', 'service', 1)), (Edge('a', 'b'),)))


def test_desktop_explicit_missing_path_is_not_silently_ignored(monkeypatch):
    monkeypatch.setenv('DRAWIO_DESKTOP_BINARY', '/does-not-exist/drawio')
    with pytest.raises(RuntimeError, match='DRAWIO_DESKTOP_BINARY'):
        renderer.desktop_binary()


def test_mcp_must_preserve_graph_labels_and_geometry():
    source = xml()
    renderer.validate_processed_xml(source, source)
    for changed in (source.replace('source="a"', 'source="b"'),
                    source.replace('value="Worker"', 'value="Other"'),
                    source.replace('width="', 'width="1', 1)):
        with pytest.raises(ValueError):
            renderer.validate_processed_xml(source, changed)


def test_page_scoped_ids_and_page_order_are_preserved():
    from xml.etree import ElementTree as ET
    root = ET.fromstring(xml())
    second = ET.fromstring(xml()).find('diagram')
    second.set('id','details')
    second.set('name','Connection detail')
    root.append(second)
    source = ET.tostring(root,encoding='unicode')
    renderer.validate_processed_xml(source,source)
    with pytest.raises(ValueError,match='pages'):
        renderer.validate_processed_xml(source,source.replace('Connection detail','Other'))
    second.find('.//root').append(ET.Element('mxCell',{'id':'0'}))
    with pytest.raises(ValueError,match='identifiers'):
        renderer._cells(ET.tostring(root,encoding='unicode'))


@pytest.mark.parametrize('content', ['<!DOCTYPE x><root/>', '<root/>',
    '<root><mxCell id="a" style="image=https://external/image.png;"/></root>'])
def test_reject_empty_entities_and_external_images(content):
    with pytest.raises(ValueError):
        renderer._cells(content)


def test_real_engine_exports_drawio_and_does_not_substitute_on_failure(monkeypatch):
    from app.diagram import hybrid, service as module
    monkeypatch.setenv('ARCHITECTURE_DIAGRAM_ENGINE', 'hybrid_drawio')
    service = DiagramService.__new__(DiagramService)
    service.config = SimpleNamespace(ASSETS_DIR=Path(__file__).parents[1] / 'assets')
    service.icon_registry = None
    spec = DiagramSpec('Test', (Node('a', 'Input', 'external', 0, scope='external'),), ())
    monkeypatch.setattr(hybrid, 'layout', lambda *a, **k: {
        'geometry': ({'a': (20,20,120,80)}, {}, 180,140), 'paths': [], 'labels': [],
        'metrics': {}, 'parents': {'a': 'root'}, 'captions': {},
    })
    # The shared caption-placement pass uses Pillow metrics, but its raster
    # must never replace the actual Desktop export.
    monkeypatch.setattr(module, 'render_png', lambda *a,**k: b'caption-pass-only')
    png = io.BytesIO()
    Image.new('RGB', (100,100), 'white').save(png, format='PNG')
    monkeypatch.setattr(renderer, 'render_drawio', lambda source, **k:
                        (png.getvalue(), source, {'mcp_version': '1.10.0'}))
    asset = service._asset('architecture_overview', 'Solution Architecture', spec, {}, False)
    assert asset['layout_engine'] == 'hybrid_drawio'
    assert asset['renderer_details']['mcp_version'] == '1.10.0'
    assert not asset['renderer_fallback']
    import base64
    assert base64.b64decode(asset['image_base64']) == png.getvalue()
    def failed(*args, **kwargs):
        raise RuntimeError('Desktop unavailable')
    monkeypatch.setattr(renderer, 'render_drawio', failed)
    with pytest.raises(RuntimeError, match='Desktop unavailable'):
        service._asset('architecture_overview', 'Solution Architecture', spec, {}, False)


@pytest.mark.parametrize('output', ['missing', 'empty', 'corrupt', 'valid'])
def test_export_validates_output_and_uses_private_temp_directory(monkeypatch, output):
    monkeypatch.setattr(renderer, 'desktop_binary', lambda: 'drawio.exe')
    monkeypatch.setenv('DRAWIO_NODE_BINARY', 'node')
    # No installation required for this unit test.
    exists = Path.is_file
    monkeypatch.setattr(Path, 'is_file', lambda p: True if str(p).endswith('src/index.js') else exists(p))
    locations = []
    def run(command, **kwargs):
        assert 'AWS_SECRET_ACCESS_KEY' not in kwargs['environment']
        if kwargs.get('input_text'):
            return json.dumps({'xml': json.loads(kwargs['input_text'])['xml'], 'mcp_version':'1.10.0'})
        target = Path(command[command.index('--output') + 1])
        locations.append(target.parent)
        assert command[-1].endswith('.drawio') and '--disable-update' in command
        assert command[command.index('--page-index')+1] == '1'
        if output == 'empty':
            target.write_bytes(b'')
        elif output == 'corrupt':
            target.write_bytes(b'not-png' * 100)
        elif output == 'valid':
            Image.new('RGB', (100,100), 'white').save(target)
        return ''
    monkeypatch.setattr(renderer, '_run', run)
    if output == 'valid':
        png, processed, details = renderer.render_drawio(xml())
        assert png.startswith(b'\x89PNG') and processed == xml()
    else:
        with pytest.raises((RuntimeError, OSError)):
            renderer.render_drawio(xml())
    assert locations and all(not path.exists() for path in locations)


@pytest.mark.parametrize('failures',[1,2])
def test_local_mcp_transient_failure_retries_same_xml_once(monkeypatch,failures):
    monkeypatch.setattr(renderer,'desktop_binary',lambda:'drawio.exe')
    monkeypatch.setenv('DRAWIO_NODE_BINARY','node')
    exists=Path.is_file
    monkeypatch.setattr(Path,'is_file',lambda p:True if str(p).endswith('src/index.js') else exists(p))
    inputs=[]
    def run(command,**kwargs):
        if kwargs.get('input_text'):
            inputs.append(json.loads(kwargs['input_text'])['xml'])
            if len(inputs)<=failures:raise TimeoutError('cold start')
            return json.dumps({'xml':inputs[-1],'mcp_version':'test'})
        Image.new('RGB',(100,100),'white').save(Path(command[command.index('--output')+1]))
        return ''
    monkeypatch.setattr(renderer,'_run',run)
    if failures==1:
        png,processed,_=renderer.render_drawio(xml())
        assert png.startswith(b'\x89PNG') and processed==xml()
    else:
        with pytest.raises(TimeoutError):renderer.render_drawio(xml())
    assert inputs==[xml(),xml()]
