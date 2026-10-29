import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.diagram.aws_icons import AwsIconRegistry
from app.diagram.planning import deployment_scope
from app.diagram.service import DiagramService


@pytest.mark.parametrize('label,role,supplied,expected', [
    ('Amazon Bedrock', 'compute', 'az', 'managed'),
    ('Amazon S3', 'data', 'vpc', 'managed'),
    ('Amazon API Gateway', 'entry', '', 'managed'),
    ('AWS Lambda', 'compute', '', 'managed'),
    ('AWS Lambda', 'compute', 'vpc', 'vpc'),
    ('Amazon S3 VPC endpoint', 'network', 'vpc', 'vpc'),
    ('Amazon Bedrock', 'external', 'vpc', 'external'),
    ('Amazon Redshift', 'data', 'external', 'external'),
    ('Amazon EC2', 'compute', '', 'vpc'),
])
def test_boundary_rules(label, role, supplied, expected):
    assert deployment_scope(label, role, supplied) == expected


def test_application_fanout_and_shared_store_dependencies_are_not_pruned():
    nodes = [{'id': 'app', 'placement_role': 'compute'}] + [
        {'id': f'd{i}', 'placement_role': 'data'} for i in range(4)
    ] + [{'id': 'other', 'placement_role': 'compute'}]
    edges = [{'source': 'app', 'target': f'd{i}'} for i in range(4)]
    edges.append({'source': 'other', 'target': 'd0'})
    result = DiagramService._simplify_architecture_edges(nodes, edges)
    assert {(e['source'], e['target']) for e in result} == {
        (e['source'], e['target']) for e in edges
    }


def test_compact_plan_is_not_expanded_to_fill_icon_quota(monkeypatch):
    service = DiagramService.__new__(DiagramService)
    service.config = SimpleNamespace(WRITER_MODEL_ID=None)
    service.icon_registry = AwsIconRegistry(Path(__file__).resolve().parents[1] / 'assets')
    requirements = {'aws_services': ['AWS Lambda', 'Amazon S3', 'Amazon Bedrock',
                    'Amazon DynamoDB', 'Amazon CloudWatch', 'Amazon API Gateway']}
    assert len(service.icon_registry.candidates(requirements, '')) >= 6
    raw = {'diagrams': [{'diagram_type': 'architecture_overview', 'title': 'Solution',
        'description': 'Users access the application.', 'nodes': [
            {'id': 'u', 'label': 'Users', 'kind': 'actor', 'scope': 'external'},
            {'id': 'app', 'label': 'Application', 'kind': 'application'}],
        'edges': [{'source': 'u', 'target': 'app'}],
        'architecture_plan': {'view': 'logical', 'decisions': [],
            'flows': [{'id': 'runtime', 'kind': 'runtime', 'paths': [['u', 'app']]}]}}]}
    calls = []
    def generate(prompt, **kwargs):
        calls.append(prompt)
        return SimpleNamespace(text=json.dumps(raw))
    service.llm = SimpleNamespace(generate=generate)
    monkeypatch.setattr(service, '_eligible_types', lambda *args: ['architecture_overview'])
    result, fallback = service._generate_specs(requirements, {}, 'An existing application serves users.')
    assert not fallback
    assert len(calls) == 1 and len(result[0][2].nodes) == 2
    assert 'There is no target node count' in calls[0]
    assert '12-22' not in calls[0]
