"""Final v52 review regressions; no live providers or native exports."""
import base64
from copy import deepcopy
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.diagram.contracts import freeze
from app.diagram.service import DiagramService, DiagramSpec, Edge, Node, validate_spec


def operation_graph():
    return {'nodes': [{'id': 'consumer', 'label': 'Runtime', 'kind': 'service', 'layer': 0},
                      {'id': 'storage', 'label': 'Dataset', 'kind': 'service', 'layer': 1}],
            'edges': [{'source': 'consumer', 'target': 'storage', 'label': label,
                       'operation_type': op, 'initiator': 'consumer', 'data_direction': direction}
                      for label, op, direction in [('Read records', 'read', 'target_to_source'),
                                                    ('Persist decision', 'write', 'source_to_target')]]}


@pytest.mark.parametrize('same_label', [False, True])
def test_canonical_operations_survive_enrichment_parsing_and_detail_page(same_label):
    from app.diagram.connection_detail import page
    raw = operation_graph()
    if same_label:
        for edge in raw['edges']: edge['label'] = 'Synchronize records'
    raw['edges'] = DiagramService._simplify_architecture_edges(raw['nodes'], raw['edges'])
    spec = validate_spec(raw, 'Operations')
    assert [op['operation_type'] for op in freeze(spec)['operations']] == ['read', 'write']
    assert len(page(spec).findall('.//mxCell[@sourceNode]')) == 2


def test_canonical_action_is_not_truncated_into_another_operation():
    raw = operation_graph()
    raw['edges'][0]['label'] = 'Read the application records needed for payment decisions'
    raw['edges'][1] = {**raw['edges'][0], 'label': 'Read the application records needed for shipping decisions'}
    spec = validate_spec(raw, 'Operations')
    assert [e.label for e in spec.edges] == [e['label'] for e in raw['edges']]


def test_lambda_rollup_preserves_canonical_instances_and_detail_connections():
    from app.diagram.service_design import consolidate_overview_handlers
    from app.diagram.connection_detail import page
    raw = {'nodes': [{'id': 'a', 'label': 'Intake Lambda', 'kind': 'service', 'layer': 0},
                     {'id': 'b', 'label': 'Extract Lambda', 'kind': 'service', 'layer': 1},
                     {'id': 'ocr', 'label': 'Amazon Textract', 'kind': 'service', 'layer': 2}],
           'edges': [{'source': 'a', 'target': 'b', 'label': 'Invoke extraction'},
                     {'source': 'b', 'target': 'ocr', 'label': 'Read document'}],
           'architecture_plan': {'service_mapping': [{'service_id': 'lambda', 'node_ids': ['a', 'b']}]}}
    result = consolidate_overview_handlers(raw)
    assert result['nodes'] == raw['nodes'] and result['edges'] == raw['edges']
    spec = DiagramSpec('Handlers', tuple(Node(**n) for n in result['nodes']),
                       tuple(Edge(**e) for e in result['edges']), architecture_plan=result['architecture_plan'])
    assert {n['id'] for n in freeze(spec)['nodes']} == {'a', 'b', 'ocr'}
    assert len(page(spec).findall('.//mxCell[@sourceNode]')) == 2


@pytest.mark.parametrize('review', [None, {'status': 'unavailable', 'image_reviewed': False, 'issues': []}])
def test_semantic_regeneration_preserves_published_snapshot_when_review_missing(review):
    from tests.test_architecture_regeneration import snapshot, good_asset, mock_service, revision
    from app.preview.architecture_regeneration import _regenerate
    old = snapshot(); baseline = deepcopy(old)
    asset = good_asset(); asset['vision_review'] = review
    asset['spec']['nodes'] = [{'id': 'new'}]
    asset['image_base64'] = 'new-unreviewed-image'
    result = _regenerate(old, 'Change deployment', object(), lambda _: None,
                         mock_service([revision(), {'consistent': True, 'problems': []}], asset))
    assert old == baseline
    assert result['content'] == baseline['content']
    assert result['final_state'] == baseline['final_state']
    assert result['architecture_revision_candidate']['assets'][0]['image_base64'] == 'new-unreviewed-image'


@pytest.mark.parametrize('refreshed', [
    {'status': 'partial_priced', 'monthly_cost': None, 'missing_inputs': ['EC2 size']},
    {'status': 'priced', 'monthly_cost': None, 'estimate_url': 'https://calculator.aws/#/estimate/new'},
    {'status': 'priced', 'monthly_cost': 200, 'missing_inputs': ['Storage'], 'estimate_url': 'https://calculator.aws/#/estimate/new'},
    {'status': 'hybrid', 'monthly_cost': 200, 'estimate_url': 'https://calculator.aws/#/estimate/new'},
    {'status': 'priced', 'monthly_cost': 200, 'estimate_url': 'https://calculator.aws/#/estimate/new',
     'resource_coverage': {'Amazon EC2': {'complete': False}}},
])
def test_semantic_regeneration_rejects_incomplete_required_calculator_replacement(refreshed):
    from tests.test_architecture_regeneration import snapshot, good_asset, mock_service, revision
    from app.preview.architecture_regeneration import _regenerate
    old = snapshot()
    old['final_state']['pricing_result'] = {'status': 'priced', 'monthly_cost': 125,
                                           'estimate_url': 'https://calculator.aws/#/estimate/old'}
    old['content']['aws_pricing'] = 'Complete old estimate'
    baseline = deepcopy(old)
    with patch('app.pricing.AwsPricingService') as factory:
        factory.return_value.generate.return_value = refreshed
        with pytest.raises(ValueError, match='pricing'):
            _regenerate(old, 'Change deployment', object(), lambda _: None,
                        mock_service([revision(), {'consistent': True, 'problems': []}], good_asset()))
    assert old == baseline


def test_ambiguous_legacy_review_cannot_authorize_new_services():
    from app.diagram.repair_controller import repair_request
    spec = operation_graph()
    result = repair_request({'spec': spec, 'vision_review': {'issues': [{
        'kind': 'architecture', 'description': 'Only the Process flow sentence reverses KB pull; graph is correct.'}]}})
    assert not result['replan']
    assert freeze(result['spec'])['version'] == freeze(spec)['version']


def test_unreviewed_available_architecture_never_retains_ready_status():
    from app.diagram.reliability import retain_with_warning
    asset = {'diagram_type': 'architecture_overview', 'image_base64': 'available-image', 'status': 'ready',
             'spec': operation_graph(), 'vision_review': {'status': 'disabled', 'image_reviewed': False}}
    assert retain_with_warning(asset)['status'] == 'review_required'


def test_region_override_preserves_business_geography_and_source_regions():
    from app.core.authoring_context import restore_target_region
    text = ('- Show appointments in **UK local time** and Europe/London.\n'
            '- Support during **UK business hours**, with test-location measurements in London.\n'
            '- Existing source and replication origin remain in **eu-west-2**.')
    assert restore_target_region(text, {'pricing_region': 'ap-south-1'}) == (text, [])


@pytest.mark.parametrize('edge,kind,text', [
    (Edge('kb', 'staging', 'Sync staged articles', 'ingestion', 'kb', 'target_to_source'),
     'retrieval', 'Customer questions are answered through runtime knowledge retrieval.'),
    (Edge('nat', 'igw', 'Route outward', 'egress', 'nat', 'source_to_target'),
     'ingress', 'Incoming application requests enter the application through the NAT gateway.'),
])
def test_story_rejects_typed_ingestion_and_egress_reversals(edge, kind, text):
    from app.diagram.process_story import validate
    nodes = tuple(Node(i, label, 'service', 0) for i, label in
                  [('kb', 'Knowledge Base'), ('staging', 'Amazon S3'), ('nat', 'NAT Gateway'), ('igw', 'Internet Gateway')])
    value = {'steps': [{'id': 's1', 'title': 'Application flow', 'description': text,
                       'node_ids': [edge.source, edge.target], 'edge_ids': ['e0'], 'flow_kind': kind}]}
    with pytest.raises(ValueError, match='ingestion|egress'):
        validate(value, DiagramSpec('Typed story', nodes, (edge,)))


@pytest.mark.parametrize('second_operation,second_direction,group_count', [
    ('write', 'source_to_target', 4), ('read', 'target_to_source', 2)])
def test_replica_table_compares_typed_operation_and_replica_initiator(second_operation, second_direction, group_count):
    from tests.test_architecture_table_replicas import replica_asset, replica_rows
    from app.diagram.architecture_text import _table_rows
    spec = replica_asset()['spec']
    spec['edges'][0].update(operation_type='read', data_direction='target_to_source', initiator='conn_a')
    spec['edges'][1].update(operation_type=second_operation, data_direction=second_direction, initiator='conn_b')
    assert len(_table_rows(spec, replica_rows(spec))) == group_count


def test_equivalent_numbered_application_replicas_are_not_split_by_display_role_suffix():
    from tests.test_architecture_table_replicas import replica_asset, replica_rows
    from app.diagram.architecture_text import _table_rows
    spec = replica_asset()['spec']
    spec['architecture_plan']['narrative_view']['roles'].update(conn_a='App node A', conn_b='App node B')
    for edge in spec['edges']:
        edge.update(operation_type='egress', data_direction='bidirectional', initiator=edge['source'])
    assert len(_table_rows(spec, replica_rows(spec))) == 2


def test_az_replicas_can_share_one_primary_database_in_another_zone():
    from tests.test_architecture_table_replicas import replica_asset, replica_rows
    from app.diagram.architecture_text import _table_rows
    spec = replica_asset()['spec']; rows = replica_rows(spec)
    spec['nodes'].append({**spec['nodes'][0], 'id': 'primary', 'label': 'RDS primary'})
    rows.append({'node_id': 'primary', 'role': 'Stores application records for both application replicas.'})
    for zone in ('a', 'b'):
        spec['edges'].append({'source': f'conn_{zone}', 'target': 'primary', 'label': 'Query records',
            'operation_type': 'read', 'initiator': f'conn_{zone}', 'data_direction': 'target_to_source'})
    assert len(_table_rows(spec, rows)) == 3


def accepted_snapshot():
    from tests.test_architecture_regeneration import snapshot
    from tests.test_diagram_run_manifest import asset
    old = snapshot(); spec = operation_graph(); version = freeze(spec)['version']
    ready = {**asset(), 'spec': spec, 'architecture_version': version,
             'text_alignment': {'status': 'aligned', 'row_component_ids': [['consumer'], ['storage']]}}
    old['content']['architecture_diagram_assets'] = [ready]
    old['content']['architecture_diagram'] = '| Service | Purpose |\n|---|---|\n| Runtime | Reads records |\n| Dataset | Stores data |'
    old['final_state'].update(architecture_version=version,
        architecture_design=deepcopy(spec),
        artifact_architecture_versions={'architecture_diagram': version, 'service_table': version})
    old['final_state']['validated_requirements']['approved_architecture'] = freeze(spec)
    return old


@pytest.mark.parametrize('instructions,feedback_key', [
    ('Change the process story heading to Order handling', 'story_feedback'),
    ('Straighten the arrows and increase spacing', 'layout_feedback'),
    ('Rewrite the process panel heading for step 4', 'story_feedback'),
    ('Shorten the process flow sentences', 'story_feedback'),
    ('Add a bold heading to each process step', 'story_feedback'),
    ('Remove all connector labels', 'layout_feedback'),
    ('Move the analytics box left', 'layout_feedback'),
    ('Increase the label size', 'layout_feedback'),
    ('Reduce diagram congestion', 'layout_feedback'),
    ('Make the diagram neater', 'layout_feedback')])
def test_presentation_revision_routes_instruction_and_preserves_verified_identity(instructions, feedback_key):
    from tests.test_architecture_regeneration import mock_service
    from app.preview.architecture_regeneration import _regenerate
    from app.diagram.run_manifest import assert_content_acceptance
    old = accepted_snapshot(); new = deepcopy(old['content']['architecture_diagram_assets'][0])
    new.pop('text_alignment'); new.pop('architecture_version')
    service = mock_service([], new)
    result = _regenerate(old, instructions, object(), lambda _: None, service)
    plan = service.generate_assets.call_args.args[0]['_architecture_retry_spec']['architecture_plan']
    assert instructions in plan.get(feedback_key, '')
    service.llm.generate.assert_not_called()
    asset = result['content']['architecture_diagram_assets'][0]
    assert asset['text_alignment'] == old['content']['architecture_diagram_assets'][0]['text_alignment']
    assert asset['architecture_version'] == old['final_state']['architecture_version']
    assert_content_acceptance(result['content'], ['architecture_diagram'], result['final_state'])


@pytest.mark.parametrize('instructions', ['Add NAT Gateway and reduce crossings', 'Move Lambda into private subnets'])
def test_mixed_deployment_and_visual_requests_keep_semantic_revision(instructions):
    from app.preview.architecture_regeneration import layout_only_request
    assert not layout_only_request(instructions)


@pytest.mark.parametrize('original,expected', [
    ('The existing source is deployed in eu-west-2.', 'The existing source is deployed in eu-west-2.'),
    ('Retain the source provisioned in eu-west-2.', 'Retain the source provisioned in eu-west-2.'),
    ('Retain the existing source deployed in eu-west-2.',
     'Retain the existing source deployed in eu-west-2.'),
    ('Keep the external system deployed in London (eu-west-2) and deploy the workload in us-west-2.',
     'Keep the external system deployed in London (eu-west-2) and deploy the workload in ap-south-1.'),
    ('Retain the existing source deployment in eu-west-2.',
     'Retain the existing source deployment in eu-west-2.'),
    ('Deploy the target in the selected AWS Region during UK support hours.',
     'Deploy the target in the selected AWS Region during UK support hours.'),
    ('Migrate the source database from eu-west-2 to us-west-2.',
     'Migrate the source database from eu-west-2 to ap-south-1.'),
    ('Retain the external deployment in London (eu-west-2), and deploy the target in us-west-2.',
     'Retain the external deployment in London (eu-west-2), and deploy the target in ap-south-1.'),
    ('Deploy the target in the AWS Region during London business hours, using UK local time.',
     'Deploy the target in the AWS Region during London business hours, using UK local time.'),
])
def test_region_clause_role_is_attached_to_the_actual_location(original, expected):
    from app.core.authoring_context import restore_target_region
    result, _ = restore_target_region(original, {'pricing_region': 'ap-south-1'})
    assert result == expected


@pytest.mark.parametrize('original,expected', [
    ('Retain the existing source deployment in eu-west-2.', 'Retain the existing source deployment in eu-west-2.'),
    ('Deploy the target in the selected AWS Region during UK support hours.', 'Deploy the target in the selected AWS Region during UK support hours.'),
    ('Migrate the source database from eu-west-2 to us-west-2.', 'Migrate the source database from eu-west-2 to ap-south-1.'),
])
def test_region_scope_guard_runs_through_writer_and_reviewer(tmp_path, original, expected):
    from app.agents.poc_writer_agent import POCWriterAgent, TemplateSection
    from app.agents.sow_reviewer_agent import SOWReviewerAgent
    metadata = {'pricing_region': 'ap-south-1'}
    before, after = '- **Deployment**: '+original, '- **Deployment**: '+expected
    writer = POCWriterAgent.__new__(POCWriterAgent); writer.config = SimpleNamespace()
    writer._build_individual_prompt = lambda *a, **k: 'Write selected section'
    writer._call_bedrock = lambda *a, **k: before
    writer._authoring_issues = lambda *a: []
    section = TemplateSection('Project Overview', '', {'type': 'GENERATED'}, 0)
    assert writer._generate_section(section, {}, metadata, '', []) == '- '+expected
    payload = {'corrections': [{'section': 'overview', 'after': before}]}
    reviewer = SOWReviewerAgent(SimpleNamespace(SOW_REVIEW_LOG_DIR=tmp_path), lambda _: json.dumps(payload))
    result = reviewer.review({'overview': before}, {'overview': 'project_overview'},
        {'metadata': metadata, 'requirements': {'source_region': 'eu-west-2'}})
    assert result['overview'] == after


@pytest.mark.parametrize('fault', ['missing', 'asset_mismatch', 'inventory_mismatch', 'changed_spec'])
def test_acceptance_requires_recomputed_matching_canonical_identity(fault):
    from app.diagram.run_manifest import assert_content_acceptance
    old = accepted_snapshot(); state = old['final_state']; asset = old['content']['architecture_diagram_assets'][0]
    if fault == 'missing': state.update(architecture_version=None, artifact_architecture_versions={})
    elif fault == 'asset_mismatch': asset['architecture_version'] = 'other'
    elif fault == 'inventory_mismatch': state['validated_requirements']['approved_architecture']['version'] = 'other'
    else: asset['spec']['edges'][0]['label'] = 'Changed action'
    with pytest.raises(AssertionError, match='version|identity|canonical'):
        assert_content_acceptance(old['content'], ['architecture_diagram'], state)


def test_acceptance_allows_same_version_and_requests_without_architecture():
    from app.diagram.run_manifest import assert_content_acceptance
    old = accepted_snapshot()
    assert_content_acceptance(old['content'], ['architecture_diagram'], old['final_state'])
    assert_content_acceptance({'assumptions': 'The client supplies the required project evidence.'}, ['assumptions'], {})


def png_bytes(color, size=(800, 600)):
    from PIL import Image
    data = io.BytesIO(); Image.new('RGB', size, color).save(data, 'PNG'); return data.getvalue()


@pytest.mark.parametrize('fault', ['swapped', 'orphan', 'tiny', 'correct'])
def test_export_checks_displayed_image_in_correct_section(tmp_path, fault):
    from docx import Document
    from docx.shared import Inches
    from app.diagram.run_manifest import export_section_failures
    architecture, conceptual = png_bytes('blue'), png_bytes('red')
    content = {'architecture_diagram': 'Approved application services.',
        'architecture_diagram_assets': [{'image_base64': base64.b64encode(architecture).decode()}],
        'conceptual_flow_asset': {'image_base64': base64.b64encode(conceptual).decode()}}
    doc = Document()
    doc.add_heading('Solution Architecture', 1); doc.add_paragraph(content['architecture_diagram'])
    doc.add_picture(io.BytesIO(conceptual if fault == 'swapped' else architecture), width=Inches(.1 if fault == 'tiny' else 6))
    doc.add_heading('Conceptual Flow Diagram', 1)
    if fault != 'orphan': doc.add_picture(io.BytesIO(architecture if fault == 'swapped' else conceptual), width=Inches(6))
    else: doc.part.get_or_add_image(io.BytesIO(conceptual))  # Media exists but is never displayed.
    path = tmp_path/'figures.docx'; doc.save(path)
    failures = export_section_failures(path, content, ['architecture_diagram', 'conceptual_flow_diagram'])
    assert bool(failures) == (fault != 'correct'), failures


def test_actual_quicksight_alias_is_reporting_in_both_projection_families():
    from app.diagram.narrative import support_ids
    from app.diagram.narrative_boundaries import controls
    reporting = Node('quicksight', 'Amazon QuickSight', 'service', 1, placement_role='operations',
                     icon_key='aws.service.business-applications.amazon-quick', scope='regional')
    warehouse = Node('warehouse', 'Amazon Redshift', 'service', 1, scope='regional')
    spec = DiagramSpec('Reporting', (reporting, warehouse), (Edge('quicksight', 'warehouse', 'Query dashboard data'),))
    assert 'quicksight' not in support_ids(spec)
    assert 'quicksight' not in controls(spec)


def test_image_checker_repairs_malformed_story_finding_before_routing_candidate():
    from app.diagram.narrative import review
    from app.diagram.repair_controller import repair_request
    spec = DiagramSpec('Story', (Node('a', 'App', 'service', 0), Node('b', 'Knowledge Base', 'service', 1)),
        (Edge('a', 'b', 'Retrieve'),), architecture_plan={'narrative_view': {'groups': [], 'support': [], 'roles': {}}})
    malformed = {'issues': [{'kind': 'architecture', 'description': 'Only process sentence reverses retrieval; graph is correct.'}]}
    corrected = {'issues': [{'stage': 'story', 'rule_id': 'story.direction', 'severity': 'important',
        'node_ids': ['a', 'b'], 'edge_ids': ['e0'], 'step_ids': [],
        'description': 'Process sentence reverses retrieval.', 'evidence': 'Sentence says the knowledge base calls the app.',
        'repair_instruction': 'Describe the app retrieving knowledge.'}]}
    responses = iter([malformed, corrected])
    calls = []
    def provider(*args, **kwargs):
        calls.append(args[1]); return json.dumps(next(responses))
    asset = {'spec': spec.as_dict(), 'image_base64': base64.b64encode(png_bytes('white')).decode(),
             'layout_engine': 'deployment_drawio', 'rendered_membership': {'a': 'Region', 'b': 'Region'}}
    with patch('app.agents.architecture_reviewer_agent._call', side_effect=provider), \
         patch('app.agents.architecture_reviewer_agent._audit'), \
         patch('app.diagram.deployment.projection', return_value=(spec, {})):
        checked = review(SimpleNamespace(), asset, spec, {})
    assert len(calls) == 2
    assert checked['vision_review']['image_reviewed']
    repair = repair_request(checked)
    assert repair['stage'] == 'story' and not repair['replan']
    assert freeze(repair['spec'])['version'] == freeze(spec)['version']


@pytest.mark.parametrize('raw', [
    '{"corrections":[{"section":"project_overview","after":"- A complete **target** statement."}',
    '{"corrections":[{"section":"project_overview","after":"- Complete **escaped** \\\"quotation\\\"."}',
])
def test_review_parser_closes_only_complete_container_values(raw):
    from app.agents.sow_reviewer_agent import _decode_review_response
    assert _decode_review_response(raw) == json.loads(raw + ']}')


@pytest.mark.parametrize('raw', [
    '{"corrections":[{"section":"project_overview","after":"unfinished',
    '{"corrections":[{"section":"project_overview","after":',
    '{"corrections":[{"section":"project_overview","after":"complete"},',
])
def test_review_parser_never_invents_partial_strings_or_proposals(raw):
    from app.agents.sow_reviewer_agent import _decode_review_response
    with pytest.raises(ValueError): _decode_review_response(raw)


@pytest.mark.parametrize('after,valid', [
    ('- Deploy the **target workload** in eu-west-2.', False),
    ('- Migration moves a sanitised clone to an **isolated account** in eu-west-2.', False),
    ('- Deploy the **target workload** in ap-south-1.', True),
    ('- Keep the **existing source system** in eu-west-2.', True),
    ('- Migrate from the **source environment** in eu-west-2 to the target in ap-south-1.', True),
])
def test_reviewer_preserves_selected_target_region_without_relocating_sources(after, valid):
    from app.agents.sow_reviewer_agent import apply_corrections
    original = {'overview': '- Deploy the **target workload** in ap-south-1. Existing source is in eu-west-2.'}
    facts = {'metadata': {'pricing_region': 'ap-south-1'}}
    payload = {'corrections': [{'section': 'overview', 'after': after}]}
    if valid:
        assert apply_corrections(original, payload, {'overview': 'project_overview'}, facts)['overview'] == after
    else:
        with pytest.raises(ValueError, match='region|Region'):
            apply_corrections(original, payload, {'overview': 'project_overview'}, facts)


@pytest.mark.parametrize('line', [
    '- Migration moves a sanitised clone to an **isolated AWS account** in eu-west-2.',
    '- Grant access to the **AWS account in eu-west-2** before mobilisation.',
    '- **Other AWS Regions** beyond eu-west-2 are excluded.',
])
def test_fresh_writer_applies_website_target_region_to_real_kingfisher_clauses(line):
    from app.agents.poc_writer_agent import POCWriterAgent, TemplateSection
    writer = POCWriterAgent.__new__(POCWriterAgent); writer.config = SimpleNamespace()
    writer._build_individual_prompt = lambda *a, **k: 'Write selected section'
    writer._call_bedrock = lambda *a, **k: line
    writer._authoring_issues = lambda *a: []
    section = TemplateSection('Project Overview', '', {'type': 'GENERATED'}, 0)
    result = writer._generate_section(section, {}, {'pricing_region': 'ap-south-1'}, '', [])
    assert 'ap-south-1' in result and 'eu-west-2' not in result


def test_reviewer_restores_target_region_and_logs_repair_without_losing_other_patches(tmp_path):
    from app.agents.sow_reviewer_agent import SOWReviewerAgent
    old = {'overview': '- Deploy the **target** in ap-south-1.', 'assumptions': '- Keep **access** available.'}
    payload = {'corrections': [
        {'section': 'overview', 'after': '- Deploy the **target** in eu-west-2. Keep the existing source in eu-west-2.'},
        {'section': 'assumptions', 'after': '- Provide **source access** throughout validation.'}]}
    reviewer = SOWReviewerAgent(SimpleNamespace(SOW_REVIEW_LOG_DIR=tmp_path), lambda _: json.dumps(payload))
    result = reviewer.review(old, {'overview': 'project_overview', 'assumptions': 'assumptions'},
                             {'metadata': {'pricing_region': 'ap-south-1'}, 'requirements': {'source_region': 'eu-west-2'}})
    assert result['overview'] == '- Deploy the **target** in ap-south-1. Keep the existing source in eu-west-2.'
    assert result['assumptions'] == payload['corrections'][1]['after']
    record = json.loads(next(tmp_path.glob('*.json')).read_text(encoding='utf8'))
    assert record['review_complete']
    assert record['batches'][0]['changes'][0]['region_repairs']


def test_real_legacy_tata_figure_is_not_falsely_accepted_as_readable(tmp_path):
    from docx import Document
    from app.document.document_builder import DocumentBuilder
    directory = Path(__file__).resolve().parents[1]/'output/verification/tata-full-06'
    if not (directory/'final-state.json').exists(): pytest.skip('Local full-request evidence not distributed')
    state = json.loads((directory/'final-state.json').read_text(encoding='utf8'))
    asset = state['poc_content']['architecture_diagram_assets'][0]
    builder = DocumentBuilder(SimpleNamespace()); builder.doc = Document(); builder._configure_styles()
    original = (builder.doc.sections[-1].page_width, builder.doc.sections[-1].page_height)
    builder._add_architecture_diagram(asset)
    shape = builder.doc.inline_shapes[0]
    from PIL import Image
    with Image.open(io.BytesIO(base64.b64decode(asset['image_base64']))) as im: pixel_width = im.width
    # Honest lower bound from actual exported text, not the old estimated_label_pt metric.
    font = min(float(v) for v in re.findall(r'fontSize=([\d.]+)', asset['drawio_xml'].split('</diagram>')[0]))
    projected_pt = font * 1.5 * 72 * shape.width.inches / pixel_width
    assert projected_pt < 8  # Enlarging the page cannot repair the old reviewed bitmap.
    assert max(s.page_width.inches for s in builder.doc.sections) <= 16.55
    assert max(s.page_height.inches for s in builder.doc.sections) <= 16.55
    assert (builder.doc.sections[-1].page_width, builder.doc.sections[-1].page_height) == original
    from app.diagram.run_manifest import export_section_failures
    builder.doc.paragraphs[0].insert_paragraph_before('Solution Architecture', style='Heading 1')
    path = tmp_path/'old-figure.docx'; builder.doc.save(path)
    assert any('projected type' in item for item in export_section_failures(path,
        {'architecture_diagram_assets': [asset]}, ['architecture_diagram']))


@pytest.mark.parametrize('run', ['tata-full-06', 'kingfisher-full-05', 'tata-full-03'])
def test_captured_graph_layout_plans_at_least_eight_point_meaningful_text(run):
    from app.diagram.narrative import overview_xml
    from app.diagram.process_flow import annotate, remove_line_labels
    from app.diagram.figure_readability import overview_font_sizes
    from app.diagram.aws_icons import AwsIconRegistry
    from xml.etree import ElementTree as ET
    directory = Path(__file__).resolve().parents[1]/'output/verification'/run
    if not (directory/'final-state.json').exists(): pytest.skip('Local full-request evidence not distributed')
    state = json.loads((directory/'final-state.json').read_text(encoding='utf8'))
    raw = state['poc_content']['architecture_diagram_assets'][0]['spec']
    spec = DiagramSpec(raw['title'], tuple(Node(**n) for n in raw['nodes']), tuple(Edge(**e) for e in raw['edges']),
                       architecture_plan=raw['architecture_plan'])
    xml, metrics = overview_xml(spec, AwsIconRegistry(Path(__file__).resolve().parents[1]/'assets'))
    xml, _ = annotate(remove_line_labels(xml), spec)
    model = ET.fromstring(xml).find('./diagram/mxGraphModel')
    width, height = float(model.get('pageWidth')), float(model.get('pageHeight'))
    points = min(overview_font_sizes(xml))*72*min(15.54/width, 10.14/height)
    assert points >= 8, f'{run}: {points:.2f} pt'
    assert metrics['node_overlaps'] == 0
    for cell in model.findall('./root/mxCell'):
        if cell.get('id', '').startswith(('name_', 'regional_support', 'global_support')):
            from app.diagram.figure_readability import wrap_text
            import html
            geometry = cell.find('mxGeometry')
            font = float(re.search(r'fontSize=([\d.]+)', cell.get('style'))[1])
            text = html.unescape(re.sub('<[^>]+>', '', cell.get('value', '')))
            lines = wrap_text(text, float(geometry.get('width')), font, bold=True)
            assert float(geometry.get('height')) >= len(lines)*font*1.1+2, cell.get('id')
        if not cell.get('id', '').startswith('label_'): continue
        geometry = cell.find('mxGeometry')
        font = float(re.search(r'fontSize=([\d.]+)', cell.get('style'))[1])
        lines = cell.get('value', '').count('<br/>')+1
        assert float(geometry.get('height')) >= lines*font*1.2+4, cell.get('id')


def test_external_caption_clears_sibling_cloud_boundary():
    from app.diagram.figure_readability import caption_geometry
    spec = DiagramSpec('caption', (Node('client', 'Client Repositories', 'external', 0, scope='external'),), ())
    positions, boxes, _, _, _ = caption_geometry(spec,
        {'client': (100, 10, 112, 100)}, {'cloud': (25, 135, 900, 300)},
        {'client': 'root', 'cloud': 'root'}, {'cloud': 'AWS Cloud'}, 950, 500)
    assert positions['client'][1] + positions['client'][3] + 14 <= boxes['cloud'][1]

@pytest.mark.parametrize('text, expected', [
    ('Deploy in London (ap-south-1).', 'Deploy in ap-south-1.'),
    ('Deploy in London (eu-west-2). Keep source in London (eu-west-2).',
     'Deploy in ap-south-1. Keep source in London (eu-west-2).'),
    ('Use the target UK AWS region. Display appointments in UK local time.',
     'Use the target ap-south-1 AWS region. Display appointments in UK local time.'),
    ('Deploy the AWS workload in the London Region. UK business hours apply.',
     'Deploy the AWS workload in the ap-south-1 Region. UK business hours apply.'),
])
def test_target_friendly_region_labels_follow_selected_region(text, expected):
    from app.core.authoring_context import restore_target_region
    actual, audit = restore_target_region(text, {'pricing_region': 'ap-south-1'})
    assert actual == expected
    assert audit

