import json
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
import pytest
from app.pricing.service import AwsPricingService
from app.diagram.service import validate_spec, expand_security_icons
from app.diagram.aws_icons import AwsIconRegistry


def test_zero_estimate_is_not_published_and_is_logged(tmp_path):
    service = AwsPricingService.__new__(AwsPricingService)
    service.config = SimpleNamespace(OUTPUT_DIR=tmp_path)
    with patch.object(service, '_generate', return_value={'status': 'priced', 'monthly_cost': 0}):
        result = service.generate({'aws_services': ['Amazon RDS']}, {'pricing_previous_monthly_cost': 123})
    assert result['monthly_cost'] is None
    assert result['status'] == 'needs_input'
    record = json.loads((tmp_path / 'logs/pricing.jsonl').read_text().splitlines()[-1])
    assert record['previous_monthly_cost'] == 123
    assert record['audit_id'] == result['audit_id']
    assert record['result']['error']


def test_pricing_failure_is_logged(tmp_path):
    service = AwsPricingService.__new__(AwsPricingService)
    service.config = SimpleNamespace(OUTPUT_DIR=tmp_path)
    with patch.object(service, '_generate', side_effect=RuntimeError('calculator unavailable')):
        with pytest.raises(RuntimeError):
            service.generate({}, {})
    record = json.loads((tmp_path / 'logs/pricing.jsonl').read_text().splitlines()[-1])
    assert record['result']['error'] == 'calculator unavailable'


def test_regenerated_pricing_does_not_restore_removed_services():
    requirements = {'architecture_design': {'nodes': [{'id': 'lambda'}]},
                    'confirmed_aws_services': [], 'proposed_aws_services': ['AWS Lambda']}
    assert AwsPricingService._candidate_services(requirements, {}, 'Amazon Redshift and Amazon Bedrock') == ['AWS Lambda']


def test_combined_security_controls_have_individual_icons():
    registry = AwsIconRegistry(Path(__file__).parents[1] / 'assets')
    spec = validate_spec({'nodes': [{'id': 'controls', 'label': 'IAM / KMS / Secrets', 'kind': 'service'},
                                   {'id': 'user', 'label': 'User', 'kind': 'actor'}],
                          'edges': [{'source': 'user', 'target': 'controls'}]}, 'Architecture')
    updated = expand_security_icons(spec, registry)
    assert len(updated.nodes) == 4
    assert len({n.icon_key for n in updated.nodes[:3]}) == 3
    assert all(n.icon_key.startswith('aws.service.') for n in updated.nodes[:3])
    assert updated.nodes[0].scope == 'global'


def test_preview_order_uses_document_toc_not_json_sorting():
    from app.core import server
    payload = {'content': {'aws_pricing': 'cost', 'objective': 'goal', 'scope_of_work': 'scope',
                          'architecture_diagram': 'design',
                          'toc_structure': '1. Objective\n2. Scope of Work\n3. Solution Architecture\n4. AWS Pricing'}}
    with server.app.test_request_context('/api/preview/status/test'):
        response = server.include_preview_section_order(server.jsonify(payload))
    assert response.json['preview_section_order'] == ['objective', 'scope_of_work', 'architecture_diagram', 'aws_pricing']
