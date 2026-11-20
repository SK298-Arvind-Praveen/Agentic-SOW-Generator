from types import SimpleNamespace
import pytest

from app.pricing.renderer import render_aws_pricing_section
from app.pricing.service import AwsPricingService


def test_partial_estimate_has_one_inr_total_and_explicit_exclusions():
    result = {'status': 'partial_priced', 'calculator_monthly_cost': 236.42,
              'monthly_cost': None, 'currency': 'USD',
              'missing_inputs': [{'field': 'AWS IoT Core'}, {'field': 'Amazon VPC Endpoints'}],
              'presentation': {'currency': 'INR', 'monthly_cost': '22280.22',
                  'fx': {'rate': '94.24', 'date': '2026-11-13', 'source': 'https://www.federalreserve.gov/releases/h10/hist/dat00_in.htm'}}}
    text = render_aws_pricing_section(result)
    assert '| AWS infrastructure | 22,280.22 |' in text
    assert 'Monthly (INR)' in text and text.count('| AWS infrastructure') == 1
    assert 'AWS IoT Core' in text and 'Amazon VPC Endpoints' in text
    assert 'excluded' in text.lower() and '2026-11-13' in text and '94.24' in text
    assert 'Unavailable' not in text and 'Incomplete calculator' not in text
    assert result['monthly_cost'] is None  # Presentation must not falsify complete coverage.


def test_service_attaches_dated_fx_without_changing_native_usd_evidence(tmp_path):
    service = AwsPricingService(SimpleNamespace(OUTPUT_DIR=tmp_path, AWS_PRICING_DISPLAY_CURRENCY='INR',
        AWS_PRICING_FX_REFRESH=False, AWS_PRICING_USD_INR_RATE='94.24',
        AWS_PRICING_FX_DATE='2026-11-13', AWS_PRICING_FX_SOURCE='https://www.federalreserve.gov/releases/h10/hist/dat00_in.htm'), llm=object())
    service._generate = lambda *args: {'status': 'partial_priced', 'currency': 'USD',
        'monthly_cost': None, 'calculator_monthly_cost': 236.42}
    result = service.generate({}, {})
    assert result['presentation']['monthly_cost'] == '22280.22'
    assert result['presentation']['fx']['date'] == '2026-11-13'
    assert result['currency'] == 'USD' and result['monthly_cost'] is None
    assert '22280.22' in (tmp_path / 'logs' / 'pricing.jsonl').read_text()


def test_selected_endpoint_design_expands_billing_products_before_early_return():
    requirements = {'service_design': {'status': 'ready', 'services': [
        {'name': 'Amazon VPC Endpoints', 'status': 'proposed',
         'purpose': 'Interface endpoints for Bedrock and Secrets Manager; gateway endpoints for S3 and DynamoDB'}]}}
    assert AwsPricingService._candidate_services(requirements, {}) == ['AWS PrivateLink', 'Amazon VPC Gateway Endpoint']


def test_iot_mqtt_design_uses_protocol_catalog_product():
    class Client:
        def call(self, tool, args):
            if tool == 'search_services':
                return []
            assert args['service'] == 'awsIoTCoreMqtt'
            return {'fields': [{'id': 'messages', 'type': 'numericInput'}]}
    class LLM:
        def generate(self, prompt, **kwargs):
            return SimpleNamespace(text='{"config":{"messages":"10000"},"sizing":[{"input":"Messages","value":"10000 per month"}]}')
    owner = AwsPricingService(SimpleNamespace(), llm=LLM())
    entry, missing = owner._prepare_service(Client(), {'service_name': 'AWS IoT Core',
        '_estimate_missing': True, '_sizing_context': 'MQTT over WebSocket for station displays'}, 'ap-south-1')
    assert not missing and entry['service'] == 'awsIoTCoreMqtt'


def test_transcribe_zero_without_active_configuration_is_not_free():
    from app.pricing.service import unverified_zero_services
    result = {'calculator_entries': [{'service': 'amazonTranscribe', 'instance': 'Amazon Transcribe',
        'config': {'numberOfStandardStreamMinutes4': {'value': '24000', 'unit': 'perMonth'}}}],
        'monthly_by_service': {'Amazon Transcribe': 0}, 'calculator_config_summaries': {'Amazon Transcribe': None}}
    assert unverified_zero_services(result) == ['Amazon Transcribe']
    result['monthly_by_service']['Amazon Transcribe'] = 24
    assert unverified_zero_services(result) == []


def test_fx_parser_uses_latest_available_observation_not_release_date():
    from app.pricing.currency import parse_federal_reserve_rate
    html = '''Release Date: November 16, 2026<table>
    <tr><th>COUNTRY</th><th>CURRENCY</th><th>Nov. 12</th><th>Nov. 13</th></tr>
    <tr><td>INDIA</td><td>RUPEE</td><td>94.0400</td><td>ND</td></tr></table>'''
    fx = parse_federal_reserve_rate(html)
    assert fx['date'] == '2026-11-12' and fx['rate'] == '94.0400'


def test_fx_refresh_failure_retains_dated_verified_rate(monkeypatch):
    from app.pricing.currency import pricing_presentation
    def unavailable(*args, **kwargs):
        raise OSError('source unavailable')
    monkeypatch.setattr('app.pricing.currency.urlopen', unavailable)
    view = pricing_presentation({'status': 'priced', 'currency': 'USD', 'monthly_cost': 100},
        SimpleNamespace(AWS_PRICING_DISPLAY_CURRENCY='INR'))
    assert view['monthly_cost'] == '9424.00' and view['fx']['date'] == '2026-11-13'
    assert view['fx']['refresh_warning'] == 'source unavailable'


@pytest.mark.parametrize('status', ['fallback_priced', 'hybrid_priced'])
def test_planning_estimate_converts_fallback_amount_and_retains_qualification(status):
    from app.pricing.currency import pricing_presentation
    result = {'status': status, 'currency': 'USD', 'monthly_cost': None,
        'fallback_estimate': {'monthly_base': 100, 'monthly_low': 80, 'monthly_high': 120}}
    result['presentation'] = pricing_presentation(result,
        SimpleNamespace(AWS_PRICING_DISPLAY_CURRENCY='INR', AWS_PRICING_FX_REFRESH=False))
    text = render_aws_pricing_section(result)
    assert 'Monthly (INR)' in text and '| AWS infrastructure | 9,424.00 |' in text
    assert 'Workload planning estimate' in text and 'not an AWS quote' in text
    assert result['status'] == status and result['monthly_cost'] is None


def test_zero_validation_is_general_but_preserves_documented_free_usage():
    from app.pricing.service import unverified_zero_services
    result = {'monthly_by_service': {'AWS Lambda': 0, 'Amazon Cognito': 0},
        'calculator_config_summaries': {'AWS Lambda': None, 'Amazon Cognito': '60 monthly active users'}}
    assert unverified_zero_services(result) == ['AWS Lambda']

