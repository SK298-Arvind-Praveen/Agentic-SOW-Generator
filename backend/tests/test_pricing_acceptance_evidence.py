from copy import deepcopy

import pytest

from app.diagram.run_manifest import assert_content_acceptance


def complete_hybrid():
    from app.pricing.bedrock import GUARDRAIL_RATE_METHOD, guardrail_offer_url
    return {
        'status': 'hybrid_priced', 'region': 'ap-south-1', 'currency': 'USD',
        'monthly_cost': 142.5, 'calculator_monthly_cost': 120,
        'estimate_url': 'https://calculator.aws/#/estimate?id=saved123',
        'calculator_priced_services': 1, 'calculator_planned_services': 3,
        'no_direct_charge_services': ['AWS IAM'],
        'services': [{'service': 'amazon', 'name': 'Amazon Bedrock'}],
        'official_rate_components': [{
            'service': 'Amazon Bedrock Guardrails', 'region': 'ap-south-1',
            'method': GUARDRAIL_RATE_METHOD, 'pricebook_url': guardrail_offer_url('ap-south-1'),
            'pricebook_version': '20261111013037', 'pricebook_publication_date': '2026-11-11T01:30:37Z',
            'monthly_cost': 22.5,
            'dimensions': [{'policy': 'Content', 'sku': 'RD4WDA4ZEEVP8KYH', 'rate_code': 'RD4WDA4ZEEVP8KYH.JRTCKXETXF.6YS6EN2CT7',
                            'monthly_text_units': 150000, 'usd_per_text_unit': '0.00015', 'monthly_cost': '22.5'}],
        }],
    }


def check(pricing):
    content = {'aws_pricing': 'AWS Pricing Calculator: [Open Link](https://calculator.aws/#/estimate?id=saved123)'}
    assert_content_acceptance(content, ['aws_pricing'], {'pricing_result': pricing})


def test_complete_official_rate_supplement_passes_full_request_contract():
    check(complete_hybrid())


@pytest.mark.parametrize('defect', ['wrong_total', 'missing_service', 'unverified_source', 'incorrect_region', 'missing_provenance'])
def test_supplement_cannot_hide_incomplete_or_unsupported_pricing(defect):
    result = deepcopy(complete_hybrid())
    if defect == 'wrong_total': result['monthly_cost'] = 141.5
    if defect == 'missing_service': result['calculator_planned_services'] = 4
    component = result['official_rate_components'][0]
    if defect == 'unverified_source': component['pricebook_url'] = 'https://example.com/prices'
    if defect == 'incorrect_region': component['region'] = 'us-east-1'
    if defect == 'missing_provenance': component.pop('pricebook_version')
    with pytest.raises(AssertionError): check(result)
