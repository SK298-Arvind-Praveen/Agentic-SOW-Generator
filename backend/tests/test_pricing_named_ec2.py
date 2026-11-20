from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from app.pricing.renderer import render_aws_pricing_section
from app.pricing.service import AwsPricingService


def _node(resource_id, label, scope='vpc', icon='aws.service.compute.amazon-ec2'):
    return {'id': resource_id, 'label': label, 'scope': scope, 'icon_key': icon, 'kind': 'service'}


def _config(instance, resource_ids, quantity, hours, capacity):
    return {
        'instance': instance,
        'resource_ids': resource_ids,
        'monthly_hours': hours,
        'config': {
            'instanceType': 'm6i.large',
            'workload': {'value': {'workloadType': 'consistent', 'data': str(quantity)}},
            'storageAmount': {'value': str(capacity), 'unit': 'gb|NA'},
            'pricingStrategy': 'ondemand',
        },
        'sizing': [
            {'input': 'Monthly runtime', 'value': f'{hours} hours/month', 'status': 'Approximated',
             'reason': 'Sized for the role and planned task windows'},
            {'input': 'EBS storage', 'value': f'{capacity} GB gp3 per instance, retained through the month',
             'status': 'Approximated'},
        ],
    }


class _Llm:
    def __init__(self, estimates):
        self.estimates = iter(estimates)
        self.prompts = []

    def generate(self, prompt, *, call_name, **kwargs):
        if call_name == 'AWS Pricing Estimated Fields - Amazon EC2':
            self.prompts.append(prompt)
            reply = {'configurations': next(self.estimates)}
        elif call_name == 'AWS Pricing Estimated Fields - AWS Lambda':
            reply = {'config': {'monthlyRequests': '800'},
                     'sizing': [{'input': 'Monthly requests', 'value': '800 requests'}]}
        else:
            reply = {'services': []}
        return SimpleNamespace(text=json.dumps(reply))


class _Calculator:
    def __init__(self, partial=False):
        self.builds = []
        self.partial = partial

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def call(self, name, args):
        if name == 'get_service_fields':
            if args['service'] == 'aWSLambda':
                return {'fields': [{'id': 'monthlyRequests', 'type': 'numericInput'}]}
            return {'fields': [{'id': field, 'type': kind} for field, kind in (
                ('instanceType', 'ec2InstanceSelector'), ('workload', 'ec2Workload'),
                ('pricingStrategy', 'ec2AdvPricingStrategyV2'), ('storageAmount', 'fileSize'),
                ('utilization', 'numericInput'),
            )]}
        assert name == 'build_estimate'
        entries = json.loads(args['services'])
        self.builds.append(entries)
        response = {'sharable_url': 'https://calculator.aws/#/estimate?id=verification'}
        if self.partial and len(self.builds) == 1:
            affected = next(entry for entry in entries if entry['service'] == 'ec2Enhancement')
            response['services'] = [{'service': f"ec2Enhancement:{affected['instance']}", 'partial': True}]
        return response


@pytest.fixture
def ec2_configs():
    return [
        _config('App nodes', ['app_a', 'app_b'], 2, 730, 50),
        _config('Migration runner', ['runner'], 1, 73, 120),
        _config('Load generator', ['generator'], 1, 36.5, 20),
    ]


def _estimate(tmp_path, estimates, *, partial=False, include_lambda=False, ec2_names=('Amazon EC2',),
              spot_and_db=False, source='Two Linux application nodes with separate test and migration hosts.'):
    calculator = _Calculator(partial)
    llm = _Llm(estimates)
    pricing = AwsPricingService(SimpleNamespace(OUTPUT_DIR=tmp_path), llm, lambda: calculator)
    pricing._read_cost = lambda url: {'monthlyCost': 321, 'monthlyByService': {'Amazon EC2': 321}}
    nodes = [
        _node('app_a', 'App node EC2'), _node('app_b', 'App node EC2'),
        _node('runner', 'Migration runner EC2'), _node('generator', 'Load generator EC2'),
        _node('external', 'Existing EC2', scope='external', icon='aws.resource.compute.amazon-ec2-spot-instance'),
        _node('asg', 'EC2 Auto Scaling', icon='aws.resource.compute.amazon-ec2-auto-scaling'),
    ]
    if spot_and_db:
        nodes[2]['icon_key'] = 'aws.resource.compute.amazon-ec2-db-instance'
        nodes[3]['icon_key'] = 'aws.resource.compute.amazon-ec2-spot-instance'
    result = pricing.generate({
        'aws_services': list(ec2_names) + (['AWS Lambda'] if include_lambda else []),
        'approved_architecture': {'nodes': nodes},
    }, {'pricing_region': 'ap-south-1'}, source)
    return result, calculator.builds, llm.prompts


def test_repair_replaces_all_ec2_configs_and_preserves_other_services(ec2_configs, tmp_path):
    revised = deepcopy(ec2_configs)
    revised[0]['config']['storageAmount']['value'] = '60'
    revised[1]['monthly_hours'] = 146
    revised[1]['sizing'][0]['value'] = '146 hours/month'
    revised.reverse()
    result, builds, _ = _estimate(tmp_path, [ec2_configs, revised], partial=True, include_lambda=True)
    assert result['status'] == 'priced'
    assert result['calculator_priced_services'] == 2
    assert result['calculator_config_count'] == 4
    assert len(builds) == 2
    before = {(e['service'], e['instance']): e['config'] for e in builds[0]}
    after = {(e['service'], e['instance']): e['config'] for e in builds[1]}
    assert before.keys() == after.keys()
    assert result['calculator_entries'] == builds[1]
    assert after['aWSLambda', 'AWS Lambda'] == before['aWSLambda', 'AWS Lambda']
    coverage = result['resource_coverage']['Amazon EC2']
    assert coverage['complete']
    assert coverage['covered_resource_ids'] == ['app_a', 'app_b', 'generator', 'runner']
    by_resource = {tuple(c['resource_ids']): after['ec2Enhancement', c['instance']] for c in coverage['configurations']}
    assert by_resource['app_a', 'app_b']['storageAmount']['value'] == '60'
    assert by_resource['runner',]['utilization'] == '20'
    assert by_resource['generator',]['utilization'] == '5'
    assert by_resource['app_a', 'app_b']['utilization'] == '100'


def test_selected_ec2_instance_alias_does_not_create_a_second_service(ec2_configs, tmp_path):
    result, builds, _ = _estimate(tmp_path, [ec2_configs], ec2_names=('Amazon EC2 Instance',))
    assert result['status'] == 'priced'
    assert result['calculator_planned_services'] == 1
    assert [entry['service'] for entry in builds[0]] == ['ec2Enhancement'] * 3


def test_spot_and_db_variants_contribute_to_canonical_ec2_coverage(ec2_configs, tmp_path):
    result, builds, _ = _estimate(tmp_path, [ec2_configs], spot_and_db=True,
                                  ec2_names=('Amazon EC2', 'Amazon EC2 Spot Instance', 'Amazon EC2 DB Instance'))
    assert result['status'] == 'priced'
    assert result['calculator_planned_services'] == 1
    assert len(builds[0]) == 3
    coverage = result['resource_coverage']['Amazon EC2']
    assert coverage['covered_resource_ids'] == coverage['required_resource_ids'] == ['app_a', 'app_b', 'generator', 'runner']


@pytest.mark.parametrize('problem', ['missing', 'mismatched', 'unexplained'])
def test_runtime_basis_requires_matching_hours_and_reason(ec2_configs, tmp_path, problem):
    invalid = deepcopy(ec2_configs)
    if problem == 'missing':
        invalid[1]['sizing'].pop(0)
    elif problem == 'mismatched':
        invalid[1]['sizing'][0]['value'] = '4 hours/month'
    else:
        invalid[1]['sizing'][0].pop('reason')
    result, builds, prompts = _estimate(tmp_path, [invalid, ec2_configs])
    assert len(prompts) == 2
    assert len(builds) == 1 and result['status'] == 'priced'
    runtime, = [row for row in result['sizing_details']
                if row['configuration'] == 'Migration runner' and row['input'] == 'Monthly runtime']
    assert runtime['value'] == '73 hours/month'
    assert runtime['reason'] == 'Sized for the role and planned task windows'


def test_runtime_provenance_requires_evidence_for_same_role_and_amount(ec2_configs, tmp_path):
    app_quote = 'App node requires 730 hours/month.'
    unrelated_quote = 'Data transfer batch processing requires 73 hours/month.'
    for config, quote in zip(ec2_configs, [app_quote, unrelated_quote]):
        config['sizing'][0].update(status='Source-backed', evidence_quote=quote)
    result, _, _ = _estimate(tmp_path, [ec2_configs], source=f'{app_quote} {unrelated_quote}')
    runtime = {row['configuration']: row for row in result['sizing_details'] if row['input'] == 'Monthly runtime'}
    assert runtime['App nodes']['status'] == 'Source-backed'
    assert runtime['Migration runner']['status'] == 'Approximated'
    configs = {row['label']: row for row in result['resource_coverage']['Amazon EC2']['configurations']}
    assert configs['App nodes']['runtime_status'] == 'Source-backed'
    assert configs['Migration runner']['runtime_status'] == 'Approximated'
    rendered = render_aws_pricing_section(result)
    assert '| App nodes operating hours | 2 instances × 730 h/month |' in rendered
    assert '| Migration runner operating hours | 1 instance × 73 h/month (Approx.) |' in rendered


def test_invalid_coverage_during_build_repair_omits_affected_ec2_service(ec2_configs, tmp_path):
    incomplete = [ec2_configs[0], ec2_configs[2]]
    result, builds, prompts = _estimate(
        tmp_path, [ec2_configs, incomplete, incomplete], partial=True, include_lambda=True,
    )
    assert 'Missing EC2 resource coverage: runner' in prompts[-1]
    assert len(builds) == 2 and [entry['service'] for entry in builds[1]] == ['aWSLambda']
    assert result['status'] == 'partial_priced'
    assert result['monthly_cost'] is None
    assert result['resource_coverage']['Amazon EC2']['missing_resource_ids'] == ['app_a', 'app_b', 'generator', 'runner']


@pytest.mark.parametrize('invalid', ['missing_runner', 'missing_generator', 'duplicate_resource',
                                    'duplicate_instance', 'quantity_too_small', 'fractional_quantity',
                                    'invalid_hours', 'mixed_roles', 'missing_storage'])
def test_invalid_ec2_coverage_is_not_submitted_or_priced(ec2_configs, tmp_path, invalid):
    if invalid == 'missing_runner':
        ec2_configs.pop(1)
    elif invalid == 'missing_generator':
        ec2_configs.pop(2)
    elif invalid == 'duplicate_resource':
        ec2_configs[0]['resource_ids'].append('app_b')
    elif invalid == 'duplicate_instance':
        ec2_configs[1]['instance'] = ec2_configs[2]['instance']
    elif invalid == 'quantity_too_small':
        ec2_configs[0]['config']['workload']['value']['data'] = '1'
    elif invalid == 'fractional_quantity':
        ec2_configs[0]['config']['workload']['value']['data'] = '2.5'
    elif invalid == 'invalid_hours':
        ec2_configs[1]['monthly_hours'] = 731
    elif invalid == 'mixed_roles':
        ec2_configs[1]['resource_ids'].append('generator')
        ec2_configs[1]['config']['workload']['value']['data'] = '2'
        ec2_configs.pop(2)
    elif invalid == 'missing_storage':
        del ec2_configs[1]['config']['storageAmount']
    result, builds, prompts = _estimate(tmp_path, [ec2_configs, ec2_configs], include_lambda=True)
    assert len(prompts) == 2
    assert len(builds) == 1 and [entry['service'] for entry in builds[0]] == ['aWSLambda']
    assert result['status'] == 'partial_priced'
    assert result['monthly_cost'] is None
    assert not result['resource_coverage']['Amazon EC2']['complete']
    assert result['calculator_priced_services'] == 1


def test_pricing_basis_shows_one_ec2_row_with_per_role_quantities_and_hours(ec2_configs, tmp_path):
    result, _, _ = _estimate(tmp_path, [ec2_configs])
    markdown = render_aws_pricing_section(result)
    rows = [line for line in markdown.splitlines() if 'operating hours |' in line]
    assert len(rows) == 3
    assert '2 instances × 730 h/month' in rows[0]
    assert '1 instance × 73 h/month' in rows[1]
    assert '1 instance × 36.5 h/month' in rows[2]
    assert '(Approx.)' in rows[0]
