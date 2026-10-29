"""Retired deployment settings must not activate optional diagram engines."""
import base64
import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from app.diagram.aws_icons import AwsIconRegistry
from app.diagram.service import DiagramService, validate_spec


@pytest.mark.parametrize('old_engine', [None, 'legacy', 'mcp', 'graphviz'])
def test_all_generations_use_builtin_renderer(monkeypatch, old_engine):
    monkeypatch.setenv('ARCHITECTURE_DIAGRAM_ENGINE', 'builtin')
    if old_engine is None:
        monkeypatch.delenv('ARCHITECTURE_LAYOUT_ENGINE', raising=False)
    else:
        monkeypatch.setenv('ARCHITECTURE_LAYOUT_ENGINE', old_engine)
    service = DiagramService.__new__(DiagramService)
    service.config = SimpleNamespace(ASSETS_DIR=Path(__file__).parents[1] / 'assets')
    service.icon_registry = AwsIconRegistry(service.config.ASSETS_DIR)
    spec = validate_spec({
        'title': 'Customer Support',
        'nodes': [
            {'id': 'customer', 'label': 'Customer', 'kind': 'actor', 'layer': 0},
            {'id': 'app', 'label': 'Support Application', 'kind': 'application', 'layer': 1},
        ],
        'edges': [{'source': 'customer', 'target': 'app', 'label': 'Sends request'}],
    }, 'Customer Support', {})
    calls = []

    def plan(requirements, metadata, narrative):
        calls.append(narrative)
        return [('architecture_overview', 'Solution Architecture', spec)], False

    monkeypatch.setattr(service, '_generate_specs', plan)
    assets = service.generate_assets({}, {'project_title': 'Customer Support'}, 'Support architecture')
    assert calls == ['Support architecture']
    assert len(assets) == 1
    asset = assets[0]
    assert asset['layout_engine'] == 'legacy'
    assert asset['diagram_type'] == 'architecture_overview'
    assert not asset['used_fallback']
    assert 'Support Application' in asset['drawio_xml']
    assert 'rounded=1' in asset['drawio_xml']  # Visible logical boxes, not blank icons.
    assert len(asset['spec']['nodes']) == 2
    assert len(asset['spec']['edges']) == 1
    with Image.open(io.BytesIO(base64.b64decode(asset['image_base64']))) as image:
        image.verify()


def test_retired_dependencies_are_not_part_of_docker_build():
    dockerfile = (Path(__file__).parents[2] / 'Dockerfile').read_text(encoding='utf8')
    assert 'ARG INSTALL_AWS_ARCH_KIT=false' in dockerfile
    assert 'if [ "$INSTALL_AWS_ARCH_KIT" = "true" ]' in dockerfile
    assert 'INSTALL_DIAGRAM_MCP' not in dockerfile
    assert 'requirements_diagram_mcp' not in dockerfile
