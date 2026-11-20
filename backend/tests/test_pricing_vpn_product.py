from types import SimpleNamespace

import pytest

from app.pricing.service import AwsPricingService


@pytest.mark.parametrize('name', ['AWS Site-to-Site VPN', 'Site to Site VPN', 'Amazon VPC Site-to-Site VPN'])
def test_site_to_site_vpn_resolves_to_catalog_connection_product(name):
    assert AwsPricingService._calculator_service_code(name) == ('vpnConnectionVpc', 'VPN Connection')


@pytest.mark.parametrize('name', ['AWS Client VPN', 'Client VPN endpoint', 'VPN appliance'])
def test_other_vpn_products_are_not_mapped_to_site_to_site(name):
    assert AwsPricingService._calculator_service_code(name) is None


def test_estimated_vpn_uses_live_fields_without_empty_search_results():
    class Client:
        def call(self, tool, args):
            assert tool == 'get_service_fields'
            assert args['service'] == 'vpnConnectionVpc'
            return {'fields': [{'id': 'numberOfSiteToSiteVPNConnections', 'type': 'numericInput'},
                {'id': 'averageDurationForEachConnection', 'type': 'frequency',
                 'options': [{'id': 'perMonth', 'label': 'hours per month'}]}]}

    class LLM:
        def generate(self, prompt, **kwargs):
            assert kwargs['call_name'].startswith('AWS Pricing Estimated Fields')
            return SimpleNamespace(text='{"config":{"numberOfSiteToSiteVPNConnections":"1","averageDurationForEachConnection":{"value":"730","unit":"perMonth"}},"sizing":[{"input":"VPN connections","value":"1 connection at 730 hours/month","status":"Approximated","reason":"One private POC connection"}]}')

    service = AwsPricingService(SimpleNamespace(), llm=LLM())
    item = {'service_name': 'AWS Site-to-Site VPN', '_estimate_missing': True}
    entry, missing = service._prepare_service(Client(), item, 'ap-south-1')
    assert not missing
    assert entry['service'] == 'vpnConnectionVpc'
    assert entry['config']['numberOfSiteToSiteVPNConnections'] == '1'
    assert entry['config']['averageDurationForEachConnection'] == {'value': '730', 'unit': 'perMonth'}


@pytest.mark.parametrize('name', ['AWS Identity and Access Management (IAM)',
    'AWS Identity and Access Management (AWS IAM)', 'Amazon VPC (VPC)',
    'AWS Identity and Access Management'])
def test_full_name_with_redundant_acronym_retains_no_charge_classification(name):
    class NoCall:
        def call(self, *args):
            raise AssertionError('No-charge service must not search for a paid product')
        def generate(self, *args, **kwargs):
            raise AssertionError('No-charge service must not invoke sizing model')
    service = AwsPricingService(SimpleNamespace(), llm=NoCall())
    item = {'service_name': name, '_estimate_missing': True}
    entry, missing = service._prepare_service(NoCall(), item, 'ap-south-1')
    assert entry is None and not missing and item['_no_direct_charge']
