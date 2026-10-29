import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.diagram.aws_icons import AwsIconRegistry
from app.diagram.service import DiagramService, ASSET_KEY, LEGACY_ASSET_KEY
from app.document.document_builder import DocumentBuilder


def service():
    result = DiagramService.__new__(DiagramService)
    result.config = SimpleNamespace()
    result.icon_registry = AwsIconRegistry(Path(__file__).resolve().parents[1] / 'assets')
    result.llm = MagicMock()
    return result


def test_workflow_keywords_never_enable_extra_views():
    assert DiagramService._eligible_types(
        {'integrations': ['CRM', 'Email', 'Dashboard']},
        'data flow workflow ingestion pipeline vpc subnet availability zone',
    ) == ['architecture_overview']


def test_llm_extra_flowcharts_are_ignored():
    instance = service()
    diagram = {'nodes': [{'id': 'a', 'label': 'Client', 'kind': 'external', 'layer': 0},
                         {'id': 'b', 'label': 'Processing', 'kind': 'process', 'layer': 1}],
               'edges': [{'source': 'a', 'target': 'b'}],
               'architecture_plan': {'view': 'logical', 'decisions': [],
                   'flows': [{'id': 'runtime', 'kind': 'runtime', 'paths': [['a', 'b']]}]}}
    instance.llm.generate.return_value = SimpleNamespace(text=json.dumps({'diagrams': [
        {**diagram, 'diagram_type': kind} for kind in ('data_flow', 'integration_context', 'architecture_overview')
    ]}))
    plans, fallback = instance._generate_specs({}, {'project_title': 'Example'}, 'workflow ingestion')
    assert not fallback
    assert [plan[0] for plan in plans] == ['architecture_overview']
    prompt = instance.llm.generate.call_args.args[0]
    assert 'Do not generate separate flowcharts' in prompt


def test_fallback_does_not_create_flowcharts():
    instance = service()
    instance.llm.generate.side_effect = RuntimeError('unavailable')
    plans, fallback = instance._generate_specs({}, {'project_title': 'Example'}, 'workflow ingestion')
    assert fallback
    assert [plan[0] for plan in plans] == ['architecture_overview']


def test_saved_drafts_with_old_flowcharts_only_embed_architecture():
    architecture = {'diagram_type': 'architecture_overview', 'image_base64': 'image'}
    old = {'diagram_type': 'data_flow', 'image_base64': 'old'}
    assert DocumentBuilder._architecture_assets({ASSET_KEY: [old, architecture, {'diagram_type': 'integration_context'}]}) == [architecture]
    assert DocumentBuilder._architecture_assets({LEGACY_ASSET_KEY: old}) == []
    assert DocumentBuilder._architecture_assets({LEGACY_ASSET_KEY: {'image_base64': 'legacy'}}) == [{'image_base64': 'legacy'}]
