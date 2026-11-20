import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.diagram.service_design import ensure_service_design, validate_design, validate_diagram_coverage
from app.diagram.aws_icons import AwsIconRegistry
from app.diagram.service import DiagramSpec, Node, expand_security_icons


SOURCE = 'Extract fields from scanned multipage PDFs. Record failed jobs and retry safely.'


def test_canonical_services_do_not_resolve_to_similarly_named_resources():
    icons = registry()
    assert icons.named_service('Amazon Elastic Container Service').key == 'aws.service.containers.amazon-elastic-container-service'
    assert icons.named_service('Amazon VPC').key == 'aws.service.networking-content-delivery.amazon-virtual-private-cloud'
    assert icons.match('S3 Gateway Endpoint')['key'] == 'aws.resource.networking-content-delivery.amazon-vpc-endpoints'


def test_candidate_limit_cannot_remove_selected_service_or_alb_resource():
    icons = registry()
    candidates = icons.candidates({'service_design': {'services':[
        {'name':'Amazon Elastic Container Service'}, {'name':'Amazon Cognito'}]}}, '', limit=1)
    keys = {c.key for c in candidates}
    assert icons.named_service('Amazon Elastic Container Service').key in keys
    assert icons.named_service('Amazon Cognito').key in keys
    assert icons.match('Application Load Balancer')['key'] in keys


@pytest.mark.parametrize('name,label', [
    ('Amazon EC2 Auto Scaling', 'Catalogue scaling'),
    ('Application Load Balancer', 'Internal ALB'),
    ('Amazon Aurora PostgreSQL', 'Booking database'),
    ('Amazon S3 Gateway VPC Endpoint', 'Private storage access'),
])
def test_named_aws_resources_validate_by_identity_not_display_label(name, label):
    icons = registry()
    expected = icons.named_service(name)
    assert expected is not None and expected.key.startswith('aws.resource.')
    spec = DiagramSpec('Test', (Node('resource', label, 'service', 1,
        icon_key=expected.key, scope='regional'),), (), architecture_plan={
            'service_mapping': [{'service_id':'selected', 'node_ids':['resource']}]})
    value = {'status':'ready', 'services':[{'id':'selected', 'name':name}], 'workflows':[]}
    assert validate_diagram_coverage(spec,value,icons)
    from dataclasses import replace
    unrelated = replace(spec,nodes=(replace(spec.nodes[0],icon_key=icons.named_service('Amazon S3').key),))
    with pytest.raises(ValueError,match='unrelated node'):
        validate_diagram_coverage(unrelated,value,icons)


def test_unregistered_product_allows_vendor_prefix_only():
    icons = registry()
    value = {'status':'ready','services':[{'id':'cur','name':'AWS Cost and Usage Reports'}]}
    spec = DiagramSpec('Test',(Node('cur','Cost and Usage Reports','service',1,scope='regional'),),(),
        architecture_plan={'service_mapping':[{'service_id':'cur','node_ids':['cur']}]})
    assert validate_diagram_coverage(spec,value,icons)
    from dataclasses import replace
    with pytest.raises(ValueError,match='accurately named'):
        validate_diagram_coverage(replace(spec,nodes=(replace(spec.nodes[0],label='Cost Explorer'),)),value,icons)


def test_service_accepts_its_own_resource_icons_but_not_another_family():
    icons = registry()
    parent = icons.named_service('AWS Systems Manager').key
    children = [key for key in icons.by_key if key.startswith('aws.resource.')
        and key.rsplit('.',1)[-1].startswith(parent.rsplit('.',1)[-1]+'-')]
    assert children
    value = {'status':'ready','services':[{'id':'ssm','name':'AWS Systems Manager'}]}
    for child in children:
        spec = DiagramSpec('Test',(Node('ssm','Private operations','service',1,scope='regional',icon_key=child),),(),
            architecture_plan={'service_mapping':[{'service_id':'ssm','node_ids':['ssm']}]})
        assert validate_diagram_coverage(spec,value,icons)
    from dataclasses import replace
    with pytest.raises(ValueError,match='unrelated node'):
        validate_diagram_coverage(replace(spec,nodes=(replace(spec.nodes[0],icon_key=icons.named_service('Amazon S3').key),)),value,icons)


def test_vpc_service_can_be_represented_by_its_scoped_network_resources():
    icons = registry()
    node = Node('nat', 'NAT Gateway', 'service', 1, scope='vpc', vpc='Booking VPC',
                placement_role='network', icon_key=icons.match('NAT Gateway')['key'])
    spec = DiagramSpec('Booking', (node,), (), architecture_plan={
        'service_mapping':[{'service_id':'vpc', 'node_ids':['nat']}]})
    value = {'status':'ready','services':[{'id':'vpc', 'name':'Amazon VPC', 'purpose':'Private networking'}]}
    assert validate_diagram_coverage(spec, value, icons).nodes == spec.nodes
    from dataclasses import replace
    with pytest.raises(ValueError, match='Service coverage'):
        validate_diagram_coverage(replace(spec,nodes=(replace(node,scope='external'),)),value,icons)


def test_alb_resource_icon_is_valid_for_selected_load_balancer_but_glue_is_not_dms():
    icons = registry()
    chosen = {'status':'ready','services':[{'id':'alb','name':'Elastic Load Balancing (Application Load Balancer)'}]}
    spec = DiagramSpec('Private application', (Node('alb','Internal ALB','service',0,scope='vpc',
        icon_key='aws.resource.networking-content-delivery.elastic-load-balancing-application-load-balancer'),), (),
        architecture_plan={'service_mapping':[{'service_id':'alb','node_ids':['alb']}]})
    assert validate_diagram_coverage(spec,chosen,icons)
    chosen['services'][0]['name'] = 'AWS DMS'
    with pytest.raises(ValueError,match='unrelated node'):
        validate_diagram_coverage(spec,chosen,icons)


def test_dms_database_export_is_distinct_from_media_file_copy():
    from app.diagram.service import Edge
    from dataclasses import replace
    icons = registry()
    chosen = {'status':'ready','services':[{'id':'dms','name':'AWS DMS'}, {'id':'s3','name':'Amazon S3'}]}
    spec = DiagramSpec('Migration', tuple(Node(s['id'],s['name'],'service',0,scope='regional',
        icon_key=icons.named_service(s['name']).key) for s in chosen['services']),
        (Edge('dms','s3','Migrate media'),),
        architecture_plan={'service_mapping':[{'service_id':s['id'],'node_ids':[s['id']]} for s in chosen['services']]})
    with pytest.raises(ValueError,match='file-copy worker'):
        validate_diagram_coverage(spec,chosen,icons)
    assert validate_diagram_coverage(replace(spec,edges=(Edge('dms','s3','Export database records'),)),chosen,icons)


def test_top_level_service_mapping_is_normalized_without_inventing_associations():
    from app.diagram.service import DiagramService
    service = DiagramService.__new__(DiagramService)
    service.icon_registry = registry()
    raw = {'nodes':[{'id':'ocr','label':'Amazon Textract','kind':'service','scope':'regional'}],
        'edges':[], 'architecture_plan':{'view':'logical'},
        'service_mapping':[{'service_id':'selected_ocr','node_ids':['ocr']}]}
    result = service._enrich_diagram(raw,'architecture_overview',{})
    assert result['architecture_plan']['service_mapping'] == raw['service_mapping']
    assert 'service_mapping' not in raw['architecture_plan']


def design():
    return {'summary': 'Document extraction', 'status': 'ready',
        'capabilities': [{'id': 'ocr', 'evidence_quote': 'Extract fields from scanned multipage PDFs.',
            'service_ids': ['textract'], 'implementation': 'Start job, wait, retrieve pages; persist errors'}],
        'services': [{'id': 'textract', 'name': 'Amazon Textract', 'status': 'proposed',
            'purpose': 'OCR fields', 'capability_ids': ['ocr'], 'rationale': 'Managed document extraction'}],
        'workflows': [{'steps': ['Start OCR', 'Await completion', 'Get results'],
                       'failure_handling': 'Persist failed state and retry'}]}


def test_rejects_fabricated_requirement_quote_and_orphan_service():
    value = design()
    value['capabilities'][0]['evidence_quote'] = 'All clients require an OCR system.'
    with pytest.raises(ValueError, match='exact source quote'):
        validate_design(value, SOURCE)
    value = design()
    value['services'][0]['capability_ids'] = ['invented']
    with pytest.raises(ValueError, match='capability basis'):
        validate_design(value, SOURCE)


def test_reuses_shared_design_but_invalidates_source_or_change_request():
    llm = Mock()
    llm.generate.return_value = SimpleNamespace(text=json.dumps(design()))
    req = {'aws_services': ['AWS Lambda']}
    planned = ensure_service_design(llm, req, {}, SOURCE)
    from app.diagram.reliability import architecture_evidence
    req['service_design'] = planned
    assert ensure_service_design(llm, architecture_evidence(req), {}, SOURCE) == planned
    assert llm.generate.call_count == 1
    ensure_service_design(llm, {**req, 'architecture_change_request': 'Use an approved OCR provider'}, {}, SOURCE)
    assert llm.generate.call_count == 2
    ensure_service_design(llm, req, {}, SOURCE + ' Encrypt results.')
    assert llm.generate.call_count == 3


def test_failure_is_audited_as_needs_review_not_empty_success():
    llm = Mock()
    llm.generate.side_effect = RuntimeError('provider unavailable')
    result = ensure_service_design(llm, {}, {}, SOURCE)
    assert result['status'] == 'needs_review'
    assert 'provider unavailable' in result['error']


def test_multiple_handlers_share_one_inventory_entry_without_losing_roles():
    value = design()
    value['services'].append({**value['services'][0], 'id': 'textract2', 'purpose': 'Extract page provenance'})
    value['capabilities'][0]['service_ids'].append('textract2')
    result = validate_design(value, SOURCE)
    assert len(result['services']) == 1
    assert 'Extract page provenance' in result['services'][0]['purpose']
    assert result['capabilities'][0]['service_ids'] == ['textract']


def registry():
    return AwsIconRegistry(Path(__file__).resolve().parents[1] / 'assets')


def test_selected_specialist_cannot_be_dropped_or_mapped_to_lambda():
    icons = registry()
    lambda_icon = icons.named_service('AWS Lambda').key
    spec = DiagramSpec('Test', (Node(id='worker', label='AWS Lambda', kind='service',
        icon_key=lambda_icon, layer=1, scope='regional'),), (), architecture_plan={})
    with pytest.raises(ValueError, match='needs service_mapping'):
        validate_diagram_coverage(spec, design(), icons)
    spec.architecture_plan['service_mapping'] = [{'service_id': 'textract', 'node_ids': ['worker']}]
    with pytest.raises(ValueError, match='unrelated node'):
        validate_diagram_coverage(spec, design(), icons)


def test_bundled_controls_preserve_cloudwatch_cloudtrail_and_budgets():
    spec = DiagramSpec('Test', (Node(id='controls', label='IAM KMS Secrets CloudWatch CloudTrail Budgets',
        kind='group', layer=0, scope='regional'),), ())
    expanded = expand_security_icons(spec, registry())
    assert {n.label for n in expanded.nodes} == {'AWS Identity and Access Management',
        'AWS Key Management Service', 'AWS Secrets Manager', 'Amazon CloudWatch', 'AWS CloudTrail', 'AWS Budgets'}
    assert all(n.icon_key for n in expanded.nodes)
    assert len(expand_security_icons(expanded, registry()).nodes) == 6


def test_pricing_uses_selected_design_without_keyword_based_extras():
    from app.pricing.service import AwsPricingService
    req = {'service_design': design(), 'aws_services': ['Amazon Bedrock']}
    assert AwsPricingService._candidate_services(req, {}, 'An agentic workflow') == ['Amazon Textract']
    assert AwsPricingService._candidate_services(req, {'pricing_include_proposed': False}) == []


def test_non_ocr_solution_does_not_get_a_fixed_document_stack():
    value = design()
    value['capabilities'][0].update(evidence_quote='Migrate the catalogue database.', service_ids=['dms'])
    value['services'] = [{'id': 'dms', 'name': 'AWS Database Migration Service',
        'status': 'proposed', 'purpose': 'Database replication', 'capability_ids': ['ocr'],
        'rationale': 'Full load and changes'}]
    assert validate_design(value, 'Migrate the catalogue database.')['services'][0]['id'] == 'dms'


def test_missing_selected_service_causes_graph_repair(monkeypatch):
    from app.diagram.service import DiagramService
    service = DiagramService.__new__(DiagramService)
    service.config = SimpleNamespace(WRITER_MODEL_ID=None)
    service.icon_registry = registry()
    monkeypatch.setattr('app.diagram.service_design.ensure_service_design', lambda *a: design())
    incomplete = {'nodes': [{'id': 'user', 'label': 'User', 'scope': 'external'},
        {'id': 'worker', 'label': 'AWS Lambda', 'kind': 'service', 'scope': 'regional'}],
        'edges': [{'source': 'user', 'target': 'worker'}],
        'architecture_plan': {'view': 'logical', 'decisions': [],
            'flows': [{'id': 'runtime', 'kind': 'runtime', 'paths': [['user', 'worker']]}]}}
    corrected = json.loads(json.dumps(incomplete))
    corrected['nodes'].append({'id': 'ocr', 'label': 'Amazon Textract', 'kind': 'service', 'scope': 'regional'})
    corrected['edges'].append({'source': 'worker', 'target': 'ocr'})
    corrected['architecture_plan']['flows'][0]['paths'][0].append('ocr')
    corrected['architecture_plan']['service_mapping'] = [{'service_id': 'textract', 'node_ids': ['ocr']}]
    calls = []
    def generate(prompt, **kwargs):
        calls.append(kwargs['call_name'])
        return SimpleNamespace(text=json.dumps(incomplete if len(calls) == 1 else corrected))
    service.llm = SimpleNamespace(generate=generate)
    plans, fallback = service._generate_specs({}, {}, '')
    assert not fallback
    assert calls == ['Architecture Diagram', 'Architecture Plan Correction']
    assert plans[0][2].architecture_plan['service_design']['status'] == 'ready'
    assert 'Amazon Textract' in {n.label for n in plans[0][2].nodes}


def test_overview_keeps_more_than_sixteen_required_components():
    from app.diagram.service import validate_spec
    raw = {'nodes': [{'id': str(i), 'label': f'Service {i}'} for i in range(22)],
           'edges': [{'source': str(i), 'target': str(i+1)} for i in range(21)]}
    spec = validate_spec(raw, 'Complete architecture')
    assert len(spec.nodes) == 22 and len(spec.edges) == 21


def test_runtime_dependency_cannot_be_missing_from_service_inventory():
    value = design()
    value['workflows'][0]['failure_handling'] = 'Amazon CloudWatch sends failure alarms'
    with pytest.raises(ValueError, match='Amazon CloudWatch'):
        validate_design(value, SOURCE)
    value['workflows'][0]['failure_handling'] = 'SNS delivers completion notifications'
    with pytest.raises(ValueError, match='Notification'):
        validate_design(value, SOURCE)


def test_excluded_and_existing_identity_options_are_not_new_dependencies():
    from app.diagram.service_design import unlisted_dependencies
    value = design()
    value['capabilities'][0]['implementation'] = (
        'Amazon Textract extracts documents. This avoids standing up a new AWS Organizations or Identity Center deployment. '
        'Reuse of an existing IAM Identity Center remains a prerequisite decision for AWS console access only.')
    assert unlisted_dependencies(value) == []
    value['capabilities'][0]['implementation'] += ' AWS IAM Identity Center authenticates staff.'
    assert unlisted_dependencies(value) == ['AWS IAM Identity Center']
    value['capabilities'][0]['implementation'] += ' IAM execution roles restrict service calls.'
    assert 'AWS Identity and Access Management' in unlisted_dependencies(value)


@pytest.mark.parametrize('optional', [
    'Existing IAM Identity Center can be reused if TUL already operates one.',
    'An existing Amazon OpenSearch Service domain may be reused if the client already operates one.',
])
def test_conditional_existing_service_reuse_does_not_add_inventory_dependency(optional):
    from app.diagram.service_design import unlisted_dependencies
    value = design()
    value['capabilities'][0]['implementation'] = (
        'Vendor operator access to AWS uses IAM roles with MFA and session logging. '
        + optional + ' AWS CloudTrail records API activity.')
    # The optional existing alternative must not hide either selected mechanism
    # in its neighboring sentences or force a new deployment into inventory.
    assert set(unlisted_dependencies(value)) == {'AWS Identity and Access Management', 'AWS CloudTrail'}


@pytest.mark.parametrize('implementation', [
    'AWS IAM Identity Center authenticates staff.',
    'Existing IAM Identity Center is reused for operator access.',
    'Deploy AWS IAM Identity Center if the client needs operator access.',
])
def test_optional_reuse_exception_does_not_hide_actual_identity_dependency(implementation):
    from app.diagram.service_design import unlisted_dependencies
    value = design()
    value['capabilities'][0]['implementation'] = implementation
    assert unlisted_dependencies(value) == ['AWS IAM Identity Center']


def test_failure_prevention_is_not_mistaken_for_service_exclusion():
    from app.diagram.service_design import unlisted_dependencies
    value = design()
    value['capabilities'][0]['implementation'] = 'Avoid data loss by storing documents in Amazon S3.'
    assert 'Amazon Simple Storage Service' in unlisted_dependencies(value)


def test_source_quote_restores_original_punctuation_without_changing_words():
    value = design()
    value['capabilities'][0]['evidence_quote'] = 'Extract fields from scanned multipage PDFs'
    result = validate_design(value, 'Extract fields, from scanned multipage PDFs.')
    assert result['capabilities'][0]['evidence_quote'] == 'Extract fields, from scanned multipage PDFs'


def test_overview_preparation_preserves_canonical_handlers_and_connections():
    from app.diagram.service_design import consolidate_overview_handlers
    raw = {'nodes': [{'id': 'a', 'label': 'Intake Lambda', 'region': 'Region'},
                     {'id': 'b', 'label': 'Extract Lambda', 'region': 'Region'},
                     {'id': 'other', 'label': 'AWS Lambda', 'region': 'Other Region'},
                     {'id': 'ocr', 'label': 'Amazon Textract'}],
           'edges': [{'source': 'a', 'target': 'b'}, {'source': 'b', 'target': 'ocr'}],
           'architecture_plan': {'service_mapping': [{'service_id': 'lambda', 'node_ids': ['a', 'b', 'other']}],
             'flows': [{'id': 'processing', 'paths': [['a', 'b', 'ocr']]}]}}
    result = consolidate_overview_handlers(raw)
    assert {n['id'] for n in result['nodes']} == {'a', 'b', 'other', 'ocr'}
    assert result['edges'] == raw['edges']
    assert result['architecture_plan']['flows'][0]['paths'] == [['a', 'b', 'ocr']]
    assert result['architecture_plan']['service_mapping'][0]['node_ids'] == ['a', 'b', 'other']
    assert len(raw['nodes']) == 4  # Saved source graph is not mutated.


def test_selected_static_hosting_and_async_ocr_keep_their_storage_dependencies():
    from dataclasses import replace
    from app.diagram.service import Edge
    icons = registry()
    value = design()
    value['services'] += [{'id': 's3', 'name': 'Amazon S3', 'purpose': 'Documents and static UI assets'},
                          {'id': 'cdn', 'name': 'Amazon CloudFront', 'purpose': 'UI delivery'}]
    value['workflows'][0]['steps'] = ['StartDocumentAnalysis', 'Await completion', 'Get results']
    spec = DiagramSpec('Test', tuple(Node(id=s['id'], label=s['name'], kind='service',
        icon_key=icons.named_service(s['name']).key, layer=1, scope='regional') for s in value['services']), (),
        architecture_plan={'service_mapping': [{'service_id': s['id'], 'node_ids': [s['id']]}
                                               for s in value['services']]})
    with pytest.raises(ValueError, match='origin connection'):
        validate_diagram_coverage(spec, value, icons)
    spec = replace(spec, edges=(Edge('cdn', 's3'), Edge('textract', 's3')))
    assert validate_diagram_coverage(spec, value, icons).architecture_plan['service_design'] == value
