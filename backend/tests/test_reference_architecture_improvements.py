import copy
import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ConnectionClosedError
from app.diagram import knowledge as kb, elk
from app.diagram.aws_icons import AwsIconRegistry
from app.diagram.service import DiagramService, DiagramSpec, Node, Edge, validate_spec
from app.agents.sow_reviewer_agent import bullet_review_checks

ASSETS = Path(__file__).resolve().parents[1] / 'assets'


def test_curated_visual_is_retrieved_only_for_matching_workload():
    assert kb.reference_image({'features': ['batch call analytics']}).startswith(b'\x89PNG')
    assert kb.reference_image({'features': ['document extraction']}) is None
    assert kb.reference_image({'out_of_scope': ['batch call analytics']}) is None
    data = copy.deepcopy(kb.load_library())
    data['patterns'][0]['image_path'] = '../outside.png'
    with pytest.raises(ValueError):
        kb.validate_library(data)


def test_planner_receives_visual_not_just_text():
    service = DiagramService.__new__(DiagramService)
    service.config = SimpleNamespace()
    service.icon_registry = AwsIconRegistry(ASSETS)
    service.llm = MagicMock()
    service.llm.generate.return_value = SimpleNamespace(text=json.dumps({'nodes': [
        {'id': 'a', 'label': 'Caller'}, {'id': 'b', 'label': 'Processing'}],
        'edges': [{'source': 'a', 'target': 'b'}]}))
    service._generate_specs({'features': ['batch call analytics']}, {}, '')
    assert service.llm.generate.call_args.kwargs['image_bytes'].startswith(b'\x89PNG')


def test_ecr_cannot_reuse_ec2_icon():
    registry = AwsIconRegistry(ASSETS)
    ecr = registry.candidate('Amazon ECR', 'explicit', 'AWS services: ECR')
    ec2 = registry.candidate('Amazon EC2', 'explicit', 'AWS services: EC2')
    assert 'container-registry' in ecr.key and ecr.key != ec2.key
    assert registry.match('AWS Batch (GPU, EC2 G6/G6e)')['label'] == 'AWS Batch'
    service = DiagramService.__new__(DiagramService)
    service.icon_registry = registry
    result = service._enrich_diagram({'nodes': [{'id': 'ecr', 'label': 'Amazon ECR',
        'kind': 'service', 'icon_key': ec2.key}]}, 'architecture_overview', {x.key: x for x in (ecr, ec2)})
    assert result['nodes'][0]['icon_key'] == ecr.key


def test_real_layout_subnets_and_compact_controls():
    spec = DiagramSpec('Private workload', (
        Node('client', 'Client', 'external', 0, scope='external'),
        Node('app', 'EC2 worker', 'service', 1, scope='vpc', subnet='private'),
        Node('data', 'Amazon S3', 'data', 2, scope='managed'),
        Node('logs', 'CloudWatch', 'service', 0, placement_role='operations', scope='regional'),
        Node('keys', 'KMS', 'service', 0, placement_role='security', scope='regional'),
    ), (Edge('client', 'app'), Edge('app', 'data')))
    config = SimpleNamespace(ASSETS_DIR=ASSETS)
    result = elk.layout(spec, config)
    assert 'Private subnet' in result['captions'].values()
    assert 'Security and monitoring' in result['captions'].values()
    assert result['metrics']['node_overlaps'] == 0


def test_editorial_checks_detect_profile_problems_and_feature_raci():
    assert bullet_review_checks('Manual work creates bottlenecks.', 'about_client')['engagement_problem_language']
    table = '| Work | Us | Client |\n|---|---|---|\n' + '| Feature | RA | CI |\n' * 15
    assert bullet_review_checks(table, 'raci_matrix')['consolidate_workstreams']


def test_vision_retries_one_transport_failure():
    from app.agents.architecture_reviewer_agent import _call
    client = MagicMock()
    llm = MagicMock()
    llm.generate.side_effect = [ConnectionClosedError(endpoint_url='https://example.test'), SimpleNamespace(text='{}')]
    service = SimpleNamespace(config=SimpleNamespace(BEDROCK_REGION='us-east-1', FAST_MODEL_ID='test'))
    with patch('app.agents.architecture_reviewer_agent.boto3.client', return_value=client), patch('app.agents.architecture_reviewer_agent.BedrockLLM', return_value=llm):
        assert _call(service, 'inspect', time.monotonic() + 60, b'image') == '{}'
    assert llm.generate.call_count == 2
    client.close.assert_called_once()


def test_monthly_audio_volume_can_use_pricing_fallback_but_training_sample_cannot():
    from app.pricing.service import AwsPricingService
    service = AwsPricingService.__new__(AwsPricingService)
    service.config = SimpleNamespace()
    service.llm = MagicMock()
    service.llm.generate.return_value = SimpleNamespace(text=json.dumps({
        'monthly_low': 100, 'monthly_base': 200, 'monthly_high': 400, 'basis': ['Test estimate']}))
    result = service._pricing_fallback({'volume_metrics': [
        {'metric': 'Production target call volume', 'value': '10 million minutes per month'}]}, ['AWS Batch'], 'test')
    assert result['monthly_cost'] == 200
    service.llm.reset_mock()
    service._pricing_fallback({'volume_metrics': [
        {'metric': 'POC call volume', 'value': '500-1,000 hours'}]}, ['AWS Batch'], 'test')
    service.llm.generate.assert_not_called()
