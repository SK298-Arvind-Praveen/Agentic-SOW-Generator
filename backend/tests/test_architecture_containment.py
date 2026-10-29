from pathlib import Path
from types import SimpleNamespace

import pytest

from app.diagram import elk
from app.diagram.planning import CONTAINMENT_RULES, ARCHITECTURE_PLANNING_RULES, deployment_scope
from app.diagram.service import DiagramSpec, Node, Edge, DiagramService, validate_spec
from app.agents.architecture_reviewer_agent import placement_patch


CONFIG = SimpleNamespace(ASSETS_DIR=Path(__file__).parents[1] / 'assets')


def paths(graph):
    result = {}
    def visit(item, parents):
        result[item['id']] = parents
        labels = item.get('labels', [])
        chain = parents + ([labels[0]['text']] if labels else [])
        for child in item.get('children', []):
            visit(child, chain)
    visit(graph, [])
    return result


def test_explicit_account_vpc_and_subnet_membership():
    spec = DiagramSpec('Private deployment', (
        Node('a', 'EC2 worker', 'service', 1, scope='vpc', account='POC account',
             region='ap-south-1', vpc='Application VPC', availability_zone='az_a', subnet='private'),
        Node('b', 'EC2 existing', 'service', 2, scope='vpc', account='Customer account',
             region='ap-south-1', vpc='Application VPC', availability_zone='az_a', subnet='isolated'),
        Node('s3', 'Amazon S3', 'service', 2, scope='vpc', account='POC account',
             region='ap-south-1', vpc='Application VPC', subnet='private'),
        Node('iam', 'AWS IAM', 'service', 2, scope='vpc', account='POC account'),
        Node('external', 'Customer CRM', 'external', 0, scope='external'),
    ), (Edge('a', 'b'), Edge('a', 's3')))
    chain = paths(elk.build_graph(spec, CONFIG))
    assert chain['a'] == ['AWS Cloud', 'AWS Account', 'Region', 'Application VPC',
                          'Availability Zone az_a', 'Private subnet']
    assert chain['b'][1] == 'AWS Account'
    assert chain['b'][-1] == 'Isolated subnet'
    assert chain['s3'] == ['AWS Cloud', 'AWS Account', 'Region']
    assert 'Region' not in chain['iam']
    assert len(elk.build_graph(spec, CONFIG)['children'][0]['children']) == 2
    assert chain['external'] == []


def test_named_vpcs_do_not_merge_within_one_account():
    spec = DiagramSpec('Two VPCs', tuple(Node(key, 'EC2', 'service', 1,
        scope='vpc', vpc=label, subnet='private') for key, label in [('a', 'App VPC'), ('b', 'Data VPC')]),
        (Edge('a', 'b'),))
    chain = paths(elk.build_graph(spec, CONFIG))
    assert chain['a'][-2] == 'App VPC'
    assert chain['b'][-2] == 'Data VPC'


def test_schema_round_trip_and_prompt_exposes_boundaries():
    raw = {'title': 'Test', 'nodes': [
        {'id': 'a', 'label': 'EC2', 'account': 'POC', 'region': 'ap-south-1',
         'vpc': 'Workload', 'subnet': 'isolated', 'scope': 'vpc'},
        {'id': 'b', 'label': 'AWS IAM', 'scope': 'global'}], 'edges': [{'source': 'a', 'target': 'b'}]}
    spec = validate_spec(raw, 'Test')
    assert validate_spec(spec.as_dict(), 'Test') == spec
    prompt = DiagramService.__new__(DiagramService)._prompt({}, {}, '', ['architecture_overview'], [])
    for field in ('account', 'region', 'vpc', 'subnet'):
        assert f'"{field}":' in prompt
    assert CONTAINMENT_RULES in prompt and CONTAINMENT_RULES in ARCHITECTURE_PLANNING_RULES
    from app.diagram.planning import DEPLOYMENT_DESIGN_RULES
    assert DEPLOYMENT_DESIGN_RULES in prompt
    assert 'even when their names are absent from the BRD' in prompt


def test_optional_networking_icons_are_not_claimed_as_source_facts():
    from app.diagram.aws_icons import AwsIconRegistry
    candidates = AwsIconRegistry(CONFIG.ASSETS_DIR).candidates({}, '')
    endpoints = [c for c in candidates if c.label == 'Amazon VPC Endpoints']
    assert endpoints and endpoints[0].selection == 'inferred'
    assert all(c.selection == 'inferred' for c in candidates)


@pytest.mark.parametrize('label,expected', [('Amazon CloudFront', 'global'), ('AWS IAM', 'global'),
    ('Amazon Route 53', 'global'), ('Amazon ECR', 'managed'), ('Amazon SQS', 'managed')])
def test_managed_and_global_services_cannot_be_subnet_hosts(label, expected):
    assert deployment_scope(label, 'compute', 'vpc') == expected
    assert deployment_scope(label, 'external', 'external') == 'external'


def test_source_backed_subnet_repair():
    spec = DiagramSpec('Test', (Node('a', 'EC2', 'service', 1, scope='vpc', placement_role='compute'),), ())
    evidence = 'EC2 runs in private subnets.'
    result = placement_patch(spec, [{'node_id': 'a', 'subnet': 'private', 'evidence_quote': evidence}], evidence)
    assert result.nodes[0].subnet == 'private'
    with pytest.raises(ValueError):
        placement_patch(spec, [{'node_id': 'a', 'subnet': 'public', 'evidence_quote': 'Invented placement.'}], evidence)


def test_real_render_keeps_components_inside_declared_boxes():
    spec = DiagramSpec('Private service', (
        Node('user', 'User', 'external', 0, scope='external'),
        Node('app', 'EC2 worker', 'service', 1, scope='vpc', subnet='private', vpc='App VPC'),
        Node('store', 'Amazon S3', 'data', 2, scope='managed'),
    ), (Edge('user', 'app'), Edge('app', 'store')))
    result = elk.layout(spec, CONFIG)
    assert result['metrics']['containment_violations'] == 0
    assert result['metrics']['node_overlaps'] == 0
    assert result['parents']['app'].endswith('_private')
    assert result['parents']['store'] == '__region'
