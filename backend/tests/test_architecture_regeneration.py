import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.diagram.reliability import architecture_evidence, publication_issues, structured_retry
from app.preview.architecture_regeneration import regenerate


def good_asset():
    return {'image_base64': 'image', 'spec': {'nodes': [], 'edges': [], 'architecture_plan': {'view': 'logical'}},
            'layout_metrics': {'estimated_label_pt': 10, 'connector_crossings': 0},
            'vision_review': {'image_reviewed': True, 'status': 'reviewed_no_issues'}}


def snapshot():
    return {'status': 'ready', 'metadata': {}, 'edit_count': 0,
            'content': {'architecture_diagram': '- Existing design.', 'scope_of_work': '- Build application.',
                        'terms_conditions': 'STATIC', 'architecture_diagram_assets': [good_asset()]},
            'final_state': {'validated_requirements': {'key_features': ['Chat']},
                            'supporting_context': 'Customer requires chat and private application connectivity.'}}


def revision():
    return {'sections': {'architecture_diagram': '- Use **private subnets** for the application.',
                         'scope_of_work': '- Deploy the application in **private subnets**.'},
            'reviewed_sections': ['architecture_diagram', 'scope_of_work'], 'changes': ['Moved application to private subnets']}


def test_structured_retry_supplies_errors_and_stops_after_success():
    responses = iter(['bad', '{"ok":false}', '{"ok":true}'])
    calls = []
    def call(prompt):
        calls.append(prompt)
        return next(responses)
    def validate(v):
        if not v.get('ok'):
            raise ValueError('ok must be true')
        return v
    assert structured_retry(call, 'contract', validate)['ok']
    assert len(calls) == 3 and 'ok must be true' in calls[-1]


def test_structured_retry_is_bounded():
    call = Mock(return_value='not json')
    with pytest.raises(ValueError):
        structured_retry(call, 'contract', lambda v: v)
    assert call.call_count == 3


@pytest.mark.parametrize('key,value', [('connector_crossings', 26), ('ambiguous_connector_pairs', 1),
    ('estimated_label_pt', 5.18), ('connector_node_intersections', 1), ('missing_connector_labels', 1)])
def test_cosmetic_geometry_does_not_block_publication(key, value):
    asset = good_asset()
    asset['layout_metrics'][key] = value
    assert not publication_issues(asset)


def test_structural_failure_or_generic_plan_cannot_be_published():
    for delta in [{'used_fallback': True}, {'image_base64': ''},
                  {'layout_metrics': {'containment_violations': 1}},
                  {'layout_metrics': {'node_overlaps': 1}},
                  {'layout_metrics': {'out_of_bounds': 1}},
                  {'vision_review': {'unresolved_architecture': ['Wrong resource ownership']}},
                  {'vision_review': {'status': 'repair_failed', 'issues': [{'kind': 'architecture', 'problem': 'Wrong boundary'}]}}]:
        assert publication_issues({**good_asset(), **delta})
    assert not publication_issues(good_asset())


@pytest.mark.parametrize('status', ['review_unavailable', 'repair_failed', 'reviewed_no_safe_repair',
    'repair_rejected_geometry_regression', 'repair_rejected_visual_check', 'disabled'])
def test_failed_cosmetic_review_keeps_valid_original_available(status):
    asset = good_asset()
    asset['vision_review'] = {'status': status, 'issues': [{'kind': 'visual', 'problem': 'Long connectors'}]}
    asset['layout_metrics'].update(ambiguous_connector_pairs=7, connector_crossings=5,
                                   missing_connector_labels=2, estimated_label_pt=5.18, max_connector_detour=2.88)
    assert not publication_issues(asset)


def test_label_size_does_not_affect_layout_score():
    from app.diagram.review import layout_quality
    assert layout_quality({'estimated_label_pt': 3, 'estimated_subtitle_pt': 2}) == layout_quality(
        {'estimated_label_pt': 12, 'estimated_subtitle_pt': 10})


def test_proposals_are_not_promoted_to_confirmed_facts():
    original = {'confirmed_aws_services': ['AWS Lambda'], 'aws_services': ['AWS Lambda', 'Amazon Bedrock']}
    result = architecture_evidence(original)
    assert result['confirmed_aws_services'] == []
    assert result['proposed_aws_services'] == ['AWS Lambda', 'Amazon Bedrock']
    assert original['confirmed_aws_services'] == ['AWS Lambda']


def mock_service(responses, asset=None):
    service = Mock()
    service.generate_assets.return_value = [asset or good_asset()]
    service.llm.generate.side_effect = [SimpleNamespace(text=json.dumps(r)) for r in responses]
    return service


def test_regeneration_updates_diagram_and_all_affected_sections_without_mutating_original():
    original = snapshot()
    baseline = copy.deepcopy(original)
    service = mock_service([revision(), {'consistent': True, 'problems': []}])
    with patch('app.preview.architecture_regeneration.DiagramService', return_value=service):
        result = regenerate(original, 'Move app to private subnets', object())
    assert original == baseline
    assert result['content']['scope_of_work'] == revision()['sections']['scope_of_work']
    assert result['content']['terms_conditions'] == 'STATIC'
    assert result['final_state']['poc_content'] == result['content']
    assert result['final_state']['architecture_revision_history'][0]['instructions'] == 'Move app to private subnets'
    assert service.generate_assets.call_args.args[0]['architecture_source_context'] == baseline['final_state']['supporting_context']


def test_protected_section_patch_retried_not_applied():
    bad = revision()
    bad['sections']['terms_conditions'] = 'Changed legal clause'
    service = mock_service([bad, revision(), {'consistent': True, 'problems': []}])
    with patch('app.preview.architecture_regeneration.DiagramService', return_value=service):
        result = regenerate(snapshot(), '', object())
    assert result['content']['terms_conditions'] == 'STATIC'
    assert service.llm.generate.call_count == 3


def test_inconsistent_text_is_corrected_and_rechecked():
    service = mock_service([revision(), {'consistent': False, 'problems': ['Old subnet reference']},
                            revision(), {'consistent': True, 'problems': []}])
    with patch('app.preview.architecture_regeneration.DiagramService', return_value=service):
        regenerate(snapshot(), '', object())
    assert service.llm.generate.call_count == 4


def test_persistent_inconsistency_keeps_original():
    original = snapshot()
    baseline = copy.deepcopy(original)
    service = mock_service([revision(), {'consistent': False, 'problems': ['Contradiction']},
                            revision(), {'consistent': False, 'problems': ['Contradiction']}])
    with patch('app.preview.architecture_regeneration.DiagramService', return_value=service), pytest.raises(ValueError):
        regenerate(original, '', object())
    assert original == baseline


def test_failed_diagram_does_not_rewrite_text():
    service = mock_service([], {'status': 'unavailable'})
    with patch('app.preview.architecture_regeneration.DiagramService', return_value=service), pytest.raises(ValueError):
        regenerate(snapshot(), '', object())
    service.llm.generate.assert_not_called()


def test_architecture_changes_invalidate_existing_pricing():
    original = snapshot()
    original['final_state']['pricing_result'] = {'status': 'estimated', 'region': 'us-east-1'}
    asset = good_asset()
    asset['spec']['nodes'] = [{'id': 'new'}]
    service = mock_service([revision(), {'consistent': True, 'problems': []}], asset)
    with patch('app.preview.architecture_regeneration.DiagramService', return_value=service), \
         patch('app.pricing.render_aws_pricing_section', return_value='Updated pricing required'):
        result = regenerate(original, '', object())
    assert result['final_state']['pricing_result']['stale']


def test_regeneration_endpoint_is_idempotent_while_running():
    from app.core import server
    live = snapshot()
    with patch.object(server, 'preview_storage', {'p1': live}), patch.object(server, '_preview_denied', return_value=None), \
         patch.object(server.threading, 'Thread') as thread:
        for _ in range(2):
            with server.app.test_request_context('/api/preview/p1/architecture-regeneration', method='POST', json={'instructions': ''}):
                response, status = server.regenerate_preview_architecture('p1')
                assert status == 202
        assert thread.call_count == 1
    assert live['status'] == 'architecture_regenerating'


def test_regeneration_endpoint_checks_access_before_starting():
    from app.core import server
    with patch.object(server, 'preview_storage', {'p1': snapshot()}), \
         patch.object(server, '_preview_denied', return_value=('forbidden', 403)), \
         patch.object(server.threading, 'Thread') as thread:
        with server.app.test_request_context('/api/preview/p1/architecture-regeneration', method='POST', json={}):
            assert server.regenerate_preview_architecture('p1') == ('forbidden', 403)
        thread.assert_not_called()


@pytest.mark.parametrize('path,method,body', [('/api/finalize', 'POST', {'preview_id': 'p1'}),
    ('/api/edit', 'POST', {'preview_id': 'p1'}), ('/api/preview/p1/content', 'PUT', {}),
    ('/api/preview/p1', 'DELETE', {})])
def test_competing_writes_are_blocked(path, method, body):
    from app.core import server
    live = {**snapshot(), 'architecture_job': {'status': 'running'}}
    with patch.object(server, 'preview_storage', {'p1': live}), patch.object(server, '_preview_denied', return_value=None):
        with server.app.test_request_context(path, method=method, json=body):
            response, status = server.protect_architecture_revision()
            assert status == 409


def test_worker_failure_restores_ready_without_changing_content():
    from app.core import server
    live = {**snapshot(), 'status': 'architecture_regenerating', 'architecture_job': {'id': 'j', 'status': 'running'}}
    baseline = copy.deepcopy(live['content'])
    with patch.object(server, 'preview_storage', {'p1': live}), \
         patch('app.preview.architecture_regeneration.regenerate', side_effect=ValueError('bad diagram')):
        server._run_architecture_revision('p1', 'j', copy.deepcopy(live), '')
    assert live['content'] == baseline and live['status'] == 'ready'
    assert live['architecture_job']['status'] == 'failed'


@pytest.mark.parametrize('persist_success', [True, False])
def test_revision_persists_same_draft_then_publishes_atomically(tmp_path, persist_success):
    from app.core import server
    file = tmp_path / 'revision.docx'
    file.write_bytes(b'rendered document')
    live = snapshot()
    live.update(status='architecture_regenerating', architecture_job={'id': 'job', 'status': 'running'})
    live['metadata'] = {'draft_document_id': 'd1', 'project_id': 'project'}
    candidate = copy.deepcopy(live)
    candidate.update(edit_count=1, _architecture_job_id='job')
    candidate['content']['scope_of_work'] = 'Revised scope.'
    record = {'document_id': 'd1', 'status': 'draft', 's3_url': 's3://files/old.docx'}
    with (patch.object(server, 'preview_storage', {'p1': live}),
          patch.object(server, 'DynamoDBHandler') as db,
          patch('app.core.nodes.pdf_build_node', return_value={'output_path': str(file)}),
          patch.object(server, 'upload_to_s3', return_value={'s3_url': 's3://files/new.docx', 'bucket': 'files'}),
          patch.object(server, 'get_s3_client') as s3,
          patch.object(server, 'parse_s3_location', side_effect=lambda location: ('files', location.split('files/', 1)[-1])),
          patch.object(server, '_semantic_index_metadata', return_value={}),
          patch.object(server, 'AccountHandler') as accounts,
          patch.object(server, '_cleanup_replaced_draft_artifacts') as cleanup,
          patch.object(server, 'save_to_dynamodb', return_value={'success': persist_success, 'document_id': 'd1', 'version': 3}) as save):
        db.return_value.query_by_task_id.return_value = record
        db.return_value.get_document_by_id.return_value = record
        # Failure in a secondary dashboard link must not roll back a committed draft.
        accounts.return_value.link_sow_to_project.side_effect = RuntimeError('secondary link unavailable')
        result = server._save_preview_as_draft('p1', automatic=True, revision_candidate=candidate)
        assert save.call_args.kwargs['existing_document_id'] == 'd1'
        assert save.call_args.kwargs['metadata']['status'] == 'draft'
        persisted = json.loads(s3.return_value.put_object.call_args.kwargs['Body'])
        assert persisted['content'] == candidate['content']
        assert result['success'] == persist_success
        assert live['status'] == 'ready'
        if persist_success:
            assert live['content'] == candidate['content'] and live['edit_count'] == 1
            assert live['metadata']['version'] == 3
            cleanup.assert_called_once()
            s3.return_value.delete_object.assert_not_called()
        else:
            assert live['content'] == snapshot()['content'] and live['edit_count'] == 0
            cleanup.assert_not_called()
            assert s3.return_value.delete_object.call_count == 2


def test_old_text_edit_cannot_overwrite_new_revision():
    from app.preview import preview_handler
    live = {**snapshot(), 'edit_count': 2}
    with patch.object(preview_handler, 'preview_storage', {'p1': live}):
        assert not preview_handler.update_preview_data('p1', {'scope_of_work': 'old'}, expected_edit_count=1)
    assert live['content'] == snapshot()['content']


def test_worker_persistence_failure_does_not_publish_candidate():
    from app.core import server
    live = {**snapshot(), 'status': 'architecture_regenerating', 'architecture_job': {'id': 'j', 'status': 'running'}}
    candidate = copy.deepcopy(live)
    candidate['content']['scope_of_work'] = 'Never published'
    with patch.object(server, 'preview_storage', {'p1': live}), \
         patch('app.preview.architecture_regeneration.regenerate', return_value=candidate), \
         patch.object(server, '_save_preview_as_draft', return_value={'success': False}):
        server._run_architecture_revision('p1', 'j', copy.deepcopy(live), '')
    assert live['content'] == snapshot()['content']
    assert live['architecture_job']['status'] == 'failed'


def test_transient_errors_retry_but_access_denied_does_not():
    from botocore.exceptions import ClientError
    call = Mock(side_effect=[ClientError({'Error': {'Code': 'ServiceUnavailableException'}}, 'Converse'), '{"ok":true}'])
    assert structured_retry(call, 'contract', lambda v: v)['ok']
    denied = Mock(side_effect=ClientError({'Error': {'Code': 'AccessDeniedException'}}, 'Converse'))
    with pytest.raises(ClientError):
        structured_retry(denied, 'contract', lambda v: v)
    assert denied.call_count == 1
