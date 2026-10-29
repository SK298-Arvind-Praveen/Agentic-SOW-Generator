import ast
import base64
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from app.diagram import arch_kit
from app.diagram.arch_kit_worker import compile_diagram
from app.diagram.aws_icons import AwsIconRegistry
from app.diagram.service import DiagramService, validate_spec


@pytest.fixture
def service():
    service = DiagramService.__new__(DiagramService)
    service.config = SimpleNamespace(ASSETS_DIR=Path(__file__).parents[1] / 'assets')
    service.icon_registry = AwsIconRegistry(service.config.ASSETS_DIR)
    return service


@pytest.fixture
def spec():
    return validate_spec({'title': 'Support', 'nodes': [
        {'id': 'user', 'label': 'Customer', 'kind': 'actor', 'layer': 0},
        {'id': 'app', 'label': 'Application', 'kind': 'application', 'layer': 1}],
        'edges': [{'source': 'user', 'target': 'app'}]}, 'Support', {})


def png():
    output = io.BytesIO()
    Image.new('RGB', (100, 100), 'white').save(output, 'PNG')
    return output.getvalue()


def test_labels_are_data_not_executable_code(tmp_path):
    code = compile_diagram({'height': 600, 'groups': [], 'edges': [], 'nodes': [
        {'label': '\"); __import__("os").system("oops") #', 'box': [0, 0, 200, 100]}]}, tmp_path)
    tree = ast.parse(code)
    calls = [node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
    assert calls == ['Diagram', 'Node']


def test_optional_mode_and_no_replanning(service, spec, monkeypatch):
    monkeypatch.setenv('ARCHITECTURE_DIAGRAM_ENGINE', 'aws_arch_kit')
    calls = []
    monkeypatch.setattr(service, '_generate_specs', lambda *args: (calls.append(args) or [('architecture_overview', 'Solution Architecture', spec)], False))
    monkeypatch.setattr(arch_kit, 'render_arch_kit', lambda *args: png())
    assets = service.generate_assets({'features': ['Support']}, {}, 'Architecture')
    assert len(calls) == 1
    assert assets[0]['layout_engine'] == 'aws_arch_kit'
    assert assets[0]['renderer_fallback'] == ''


def test_failure_uses_same_plan(service, spec, monkeypatch):
    monkeypatch.setenv('ARCHITECTURE_DIAGRAM_ENGINE', 'aws_arch_kit')
    def fail(*args):
        raise TimeoutError('render deadline')
    monkeypatch.setattr(arch_kit, 'render_arch_kit', fail)
    asset = service._asset('architecture_overview', 'Solution Architecture', spec, {}, False)
    assert asset['layout_engine'] == 'legacy'
    assert 'deadline' in asset['renderer_fallback']
    assert asset['spec'] == spec.as_dict()
    Image.open(io.BytesIO(base64.b64decode(asset['image_base64']))).verify()


@pytest.mark.parametrize('response', [{'error': 'tool error'}, {'image_base64': base64.b64encode(b'x'*200).decode()}])
def test_worker_error_and_invalid_png_rejected(service, spec, monkeypatch, response):
    monkeypatch.setattr(arch_kit, 'worker_command', lambda: ['python', 'worker'])
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'must-not-forward')
    def run(*args, **kwargs):
        assert 'AWS_SECRET_ACCESS_KEY' not in kwargs['env']
        assert kwargs['timeout'] <= 200
        return SimpleNamespace(returncode=0, stdout=json.dumps(response))
    monkeypatch.setattr(arch_kit.subprocess, 'run', run)
    with pytest.raises(Exception):
        arch_kit.render_arch_kit(spec, service.icon_registry)


def test_non_architecture_assets_remain_builtin(service, spec, monkeypatch):
    monkeypatch.setenv('ARCHITECTURE_DIAGRAM_ENGINE', 'aws_arch_kit')
    monkeypatch.setattr(arch_kit, 'render_arch_kit', lambda *a: pytest.fail('Unexpected MCP call'))
    assert service._asset('data_flow', 'Flow', spec, {}, False)['layout_engine'] == 'legacy'
