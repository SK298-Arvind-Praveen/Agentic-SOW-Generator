from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.diagram.service import validate_spec
from app.diagram.elk import build_graph


def logical_plan():
    return {
        'nodes': [
            {'id': 'legacy', 'label': 'I-Leverage', 'scope': 'external'},
            {'id': 'stage', 'label': 'Amazon S3', 'scope': 'managed', 'flow_id': 'migration'},
            {'id': 'crm', 'label': 'Connect CRM', 'scope': 'external'},
            {'id': 'adapter', 'label': 'AI adapter', 'scope': 'managed', 'flow_id': 'ai'},
            {'id': 'model', 'label': 'Amazon Bedrock', 'scope': 'managed', 'flow_id': 'ai'},
            {'id': 'iam', 'label': 'AWS IAM', 'scope': 'global', 'placement_role': 'security'},
        ],
        'edges': [{'source': s, 'target': t} for s, t in
                  [('legacy', 'stage'), ('stage', 'crm'), ('crm', 'adapter'), ('adapter', 'model')]],
        'architecture_plan': {'view': 'logical', 'reference_pattern': 'crm-integration',
            'decisions': [{'topic': 'hosting', 'status': 'unresolved', 'choice': 'CRM hosting'}],
            'flows': [
                {'id': 'migration', 'label': 'Historical migration', 'kind': 'migration',
                 'paths': [['legacy', 'stage', 'crm']]},
                {'id': 'ai', 'label': 'Runtime AI', 'kind': 'runtime',
                 'paths': [['crm', 'adapter', 'model']]},
            ]},
    }


def test_overview_preserves_distinct_lambda_functions_in_same_boundary():
    from app.diagram.plan_contract import validate_plan
    raw = logical_plan()
    raw['nodes'][3]['icon_key'] = 'aws.service.compute.aws-lambda'
    raw['nodes'].append(dict(raw['nodes'][3], id='second_handler'))
    raw['edges'].append({'source':'crm','target':'second_handler'})
    raw['architecture_plan']['flows'][1]['paths'].append(['crm','second_handler'])
    assert validate_plan(raw)['view'] == 'logical'
    spec = validate_spec(raw, 'CRM')
    assert {'adapter','second_handler'} <= {n.id for n in spec.nodes}


def test_service_primary_label_comes_from_icon_catalogue():
    from app.diagram.aws_icons import IconCandidate
    key = 'aws.service.compute.aws-lambda'
    raw = logical_plan()
    raw['nodes'][3].update(icon_key=key, label='Call Tagging Lambda')
    candidate = IconCandidate(key, 'AWS Lambda', 'compute', '', 'inferred', 'integration')
    spec = validate_spec(raw, 'CRM', {key: candidate})
    assert next(n for n in spec.nodes if n.id == 'adapter').label == 'AWS Lambda'
    assert next(n for n in spec.nodes if n.id == 'crm').label == 'Connect CRM'


def test_contract_round_trip_and_lanes_preserve_ownership():
    spec = validate_spec(logical_plan(), 'CRM')
    assert validate_spec(spec.as_dict(), 'CRM').architecture_plan == spec.architecture_plan
    graph = build_graph(spec, SimpleNamespace(ASSETS_DIR=Path(__file__).resolve().parents[1] / 'assets'))
    parents, labels = {}, {}
    def walk(item):
        labels[item['id']] = item.get('labels', [{}])[0].get('text', '')
        for child in item.get('children', []):
            parents[child['id']] = item['id']
            walk(child)
    walk(graph)
    assert parents['crm'] == parents['legacy'] == 'root'
    assert labels[parents['stage']] == 'Region'
    assert parents['adapter'] == parents['model']
    assert parents['stage'] == parents['adapter']
    assert parents[parents['iam']].startswith('__aws_account')
    assert not any(k.startswith('__vpc') for k in parents)


def test_storage_cannot_claim_to_perform_an_import():
    from app.diagram.plan_contract import validate_plan
    raw = logical_plan()
    raw['nodes'][1]['icon_key'] = 'aws.service.storage.amazon-simple-storage-service'
    raw['edges'][1]['label'] = 'Import files'
    with pytest.raises(ValueError, match='passive storage'):
        validate_plan(raw)
    raw['edges'][1]['label'] = 'Read files'
    assert validate_plan(raw)['view'] == 'logical'


@pytest.mark.parametrize('mutation', ['reverse', 'unknown', 'uncovered', 'bad_membership', 'bad_status'])
def test_reject_contradictory_plans(mutation):
    raw = deepcopy(logical_plan())
    if mutation == 'reverse':
        raw['architecture_plan']['flows'][0]['paths'] = [['crm', 'stage', 'legacy']]
    elif mutation == 'unknown':
        raw['architecture_plan']['flows'][0]['paths'][0].append('invented')
    elif mutation == 'uncovered':
        raw['nodes'].append({'id': 'dashboard', 'label': 'Dashboard'})
    elif mutation == 'bad_membership':
        raw['nodes'][1]['flow_id'] = 'ai'
    else:
        raw['architecture_plan']['decisions'][0]['status'] = 'probably'
    with pytest.raises(ValueError):
        validate_spec(raw, 'CRM')


def test_never_fabricate_chain_when_all_edges_invalid():
    raw = logical_plan()
    raw['edges'] = [{'source': 'missing', 'target': 'crm'}]
    with pytest.raises(ValueError, match='refusing to invent'):
        validate_spec(raw, 'CRM')


def test_explicit_edges_missing_from_checklist_do_not_trigger_generic_fallback():
    raw = logical_plan()
    raw['edges'].append({'source': 'crm', 'target': 'model', 'label': 'Additional interface'})
    spec = validate_spec(raw, 'CRM')
    assert ('crm', 'model') in {(e.source, e.target) for e in spec.edges}
    assert spec.architecture_plan['unclassified_connections'] == [['crm', 'model']]


def test_connected_node_omitted_from_checklist_is_not_discarded():
    raw = logical_plan()
    raw['nodes'].append({'id': 'agent', 'label': 'Agent', 'scope': 'external'})
    raw['edges'].append({'source': 'agent', 'target': 'crm'})
    spec = validate_spec(raw, 'CRM')
    assert 'agent' in {n.id for n in spec.nodes}


def test_advisory_flow_category_does_not_discard_valid_architecture():
    raw = logical_plan()
    raw['architecture_plan']['flows'][0]['kind'] = 'call-context'
    spec = validate_spec(raw, 'CRM')
    assert len(spec.nodes) == len(raw['nodes'])
    assert spec.architecture_plan['flows'][0]['kind'] == 'call-context'


def test_connected_orchestrator_missing_from_flow_checklist_is_preserved():
    raw = logical_plan()
    raw['nodes'].append({'id': 'orchestrator', 'label': 'Orchestrator',
                         'flow_id': raw['architecture_plan']['flows'][0]['id']})
    raw['edges'].append({'source': 'orchestrator', 'target': 'stage'})
    spec = validate_spec(raw, 'CRM')
    assert 'orchestrator' in {n.id for n in spec.nodes}


def test_control_role_does_not_delete_escalation_paths():
    from app.diagram.service import DiagramService
    nodes = [{'id': 'cases', 'placement_role': 'data'},
             {'id': 'escalation', 'placement_role': 'operations'},
             {'id': 'manager', 'placement_role': 'external'}]
    edges = [{'source': 'cases', 'target': 'escalation', 'label': 'TAT feed'},
             {'source': 'escalation', 'target': 'manager', 'label': 'Escalate'}]
    assert len(DiagramService._simplify_architecture_edges(nodes, edges)) == 2


def test_invalid_json_gets_format_retry_not_generic_fallback(monkeypatch):
    from app.diagram.service import DiagramService
    from app.diagram.aws_icons import AwsIconRegistry
    service = DiagramService.__new__(DiagramService)
    service.config = SimpleNamespace(WRITER_MODEL_ID=None)
    service.icon_registry = AwsIconRegistry(Path(__file__).resolve().parents[1] / 'assets')
    calls = []
    def generate(prompt, **kwargs):
        calls.append(kwargs['call_name'])
        return SimpleNamespace(text='{"diagrams": invalid}' if len(calls) == 1 else json.dumps(logical_plan()))
    service.llm = SimpleNamespace(generate=generate)
    monkeypatch.setattr(service, '_eligible_types', lambda *args: ['architecture_overview'])
    result, fallback = service._generate_specs({}, {}, 'CRM integration')
    assert not fallback and len(result[0][2].nodes) == 6
    # Initial generation now uses the same bounded retry contract for malformed
    # JSON, truncation and transient provider failures, with a log per attempt.
    assert calls == ['Architecture Diagram', 'Architecture Diagram']


def test_common_words_and_negated_products_are_not_confirmed_aws_services():
    from app.diagram.aws_icons import AwsIconRegistry
    registry = AwsIconRegistry(Path(__file__).resolve().parents[1] / 'assets')
    candidates = registry.candidates({'overview': 'Connect CRM supports batch uploads and customer support.',
        'planning_assumptions': ['Connect CRM is not Amazon Connect.']}, '')
    explicit = {c.label for c in candidates if c.selection == 'explicit'}
    assert not {'Amazon Connect', 'AWS Batch', 'AWS Support'} & explicit


def test_client_crm_is_not_given_amazon_connect_icon():
    from app.diagram.service import DiagramService
    from app.diagram.aws_icons import AwsIconRegistry
    service = DiagramService.__new__(DiagramService)
    service.icon_registry = AwsIconRegistry(Path(__file__).resolve().parents[1] / 'assets')
    candidates = service.icon_registry.candidates({'aws_services': ['Amazon Connect']}, '')
    raw = logical_plan()
    raw['nodes'][2]['icon_key'] = next(c.key for c in candidates if 'connect' in c.key)
    result = service._enrich_diagram(raw, 'architecture_overview', {c.key: c for c in candidates})
    assert result['nodes'][2]['icon_key'] == ''
    assert result['nodes'][2]['scope'] == 'external'


def test_omitted_repeated_boundary_does_not_create_an_extra_account():
    from app.diagram.service import DiagramService
    from app.diagram.aws_icons import AwsIconRegistry
    service = DiagramService.__new__(DiagramService)
    service.icon_registry = AwsIconRegistry(Path(__file__).resolve().parents[1] / 'assets')
    raw = logical_plan()
    raw['nodes'][1].update(account='Proposed Account', region='Selected Region')
    result = service._enrich_diagram(raw, 'architecture_overview', {})
    model = next(n for n in result['nodes'] if n['id'] == 'model')
    assert model['account'] == 'Proposed Account'
    assert model['region'] == 'Selected Region'
    assert next(n for n in result['nodes'] if n['id'] == 'legacy').get('account', '') == ''


def test_ambiguous_account_ownership_is_not_guessed():
    from app.diagram.service import DiagramService
    from app.diagram.aws_icons import AwsIconRegistry
    service = DiagramService.__new__(DiagramService)
    service.icon_registry = AwsIconRegistry(Path(__file__).resolve().parents[1] / 'assets')
    raw = logical_plan()
    raw['nodes'][1]['account'] = 'Account One'
    raw['nodes'][3]['account'] = 'Account Two'
    result = service._enrich_diagram(raw, 'architecture_overview', {})
    assert next(n for n in result['nodes'] if n['id'] == 'model').get('account', '') == ''


def test_long_labels_are_not_cut_in_middle_of_words():
    from app.diagram.service import _clean_label
    assert _clean_label('Customer history and email attachments', limit=25) == 'Customer history and…'


def test_deployment_view_does_not_split_vpc_into_flow_lanes():
    raw = logical_plan()
    raw['architecture_plan']['view'] = 'deployment'
    raw['nodes'][3].update(scope='vpc', vpc='Application VPC', subnet='private')
    graph = build_graph(validate_spec(raw, 'CRM'), SimpleNamespace(ASSETS_DIR=Path(__file__).resolve().parents[1] / 'assets'))
    def ids(item):
        return [item['id']] + [k for child in item.get('children', []) for k in ids(child)]
    assert not any(k.startswith('__flow') for k in ids(graph))
    assert any(k.endswith('_private') for k in ids(graph))


@pytest.mark.parametrize('repair_succeeds', [True, False])
def test_plan_repair_is_bounded_and_only_runs_for_invalid_graph(monkeypatch, repair_succeeds):
    from app.diagram.service import DiagramService
    from app.diagram.aws_icons import AwsIconRegistry
    service = DiagramService.__new__(DiagramService)
    service.config = SimpleNamespace(WRITER_MODEL_ID=None)
    service.icon_registry = AwsIconRegistry(Path(__file__).resolve().parents[1] / 'assets')
    invalid = logical_plan()
    invalid['edges'] = []
    calls = []
    def generate(prompt, **kwargs):
        calls.append(kwargs['call_name'])
        raw = logical_plan() if len(calls) == 2 and repair_succeeds else invalid
        return SimpleNamespace(text=json.dumps(raw))
    service.llm = SimpleNamespace(generate=generate)
    monkeypatch.setattr(service, '_eligible_types', lambda *args: ['architecture_overview'])
    monkeypatch.setattr(service, '_fallback_for_type', lambda *args: validate_spec(logical_plan(), 'CRM'))
    result, fallback = service._generate_specs({}, {}, 'Existing CRM with migration and AI adapters')
    assert calls == ['Architecture Diagram'] + ['Architecture Plan Correction'] * (1 if repair_succeeds else 3)
    assert fallback is not repair_succeeds
    assert result[0][2].architecture_plan['view'] == 'logical'
