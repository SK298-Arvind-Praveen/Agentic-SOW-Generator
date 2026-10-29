from unittest.mock import patch
import json
import pytest


def test_finalize_finds_durable_draft_after_preview_cleanup():
    from app.core import server
    record = {"document_id": "draft-1", "status": "draft"}
    with (patch.object(server, "preview_storage", {}),
          patch.object(server, "DynamoDBHandler") as handler,
          patch.object(server, "_resource_denied", return_value=None)):
        handler.return_value.query_by_task_id.return_value = record
        with server.app.test_request_context('/api/finalize', method='POST', json={"preview_id": "p1"}):
            response, status = server.finalize_document()
        assert status == 200
        assert response.json["code"] == "PREVIEW_SAVED_AS_DRAFT"
        assert response.json["document_id"] == "draft-1"


def test_repeat_draft_request_reports_processing_without_error():
    from app.core import server
    with (patch.object(server, "preview_storage", {"p1": {"status": "draft_saving"}}),
          patch.object(server, "DynamoDBHandler") as handler):
        handler.return_value.query_by_task_id.return_value = None
        result = server._save_preview_as_draft("p1")
    assert result["processing"] is True
    assert "error" not in result


def test_automatic_draft_ignores_recent_heartbeat_and_attempts_save():
    from app.core import server
    preview = {"status": "ready", "last_activity_at": server.time.time()}
    with (patch.object(server, "preview_storage", {"p1": preview}),
          patch.object(server, "DynamoDBHandler") as handler,
          patch('app.core.nodes.pdf_build_node', side_effect=RuntimeError('storage unavailable')) as build):
        handler.return_value.query_by_task_id.return_value = None
        result = server._save_preview_as_draft("p1", automatic=True)
    assert not result["success"]
    assert preview["status"] == "ready"
    build.assert_called_once()


def test_cached_draft_requires_access():
    from app.core import server
    with (patch.object(server, "DynamoDBHandler") as handler,
          patch.object(server, "_resource_denied", return_value=True)):
        handler.return_value.query_by_task_id.return_value = {"status": "draft"}
        assert not server._save_preview_as_draft("p1")["success"]


@pytest.mark.parametrize('automatic', [False, True])
def test_draft_save_persists_reopenable_snapshot_before_cleanup(tmp_path, automatic):
    from app.core import server
    file = tmp_path / "draft.docx"
    file.write_bytes(b"test")
    preview = {"status": "ready", "mode": "POC", "metadata": {"project_title": "Test"},
               "content": {"scope_of_work": "Build the agreed workflow."}}
    with (patch.object(server, "preview_storage", {"p1": preview}),
          patch.object(server, "DynamoDBHandler") as handler,
          patch('app.core.nodes.pdf_build_node', return_value={"output_path": str(file)}),
          patch('app.core.nodes.clear_token_usage'),
          patch.object(server, "upload_generated_document") as drive,
          patch.object(server, "upload_to_s3", return_value={"s3_url": "s3://files/draft.docx", "bucket": "files"}),
          patch.object(server, "get_s3_client") as s3,
          patch.object(server, "_semantic_index_metadata", return_value={}),
          patch.object(server, "save_to_dynamodb", return_value={"success": True, "document_id": "d1"}) as save,
          patch.object(server, "get_task", return_value=None),
          patch.object(server, "delete_preview_data") as cleanup):
        handler.return_value.query_by_task_id.return_value = None
        result = server._save_preview_as_draft("p1", automatic=automatic)
    assert result["success"] and result["status"] == "draft"
    assert save.call_args.kwargs["metadata"]["status"] == "draft"
    assert save.call_args.kwargs["metadata"]["draft_preview_s3_url"].startswith("s3://files/draft-previews/p1-")
    snapshot = json.loads(s3.return_value.put_object.call_args.kwargs["Body"])
    assert snapshot["content"] == preview["content"]
    if automatic:
        cleanup.assert_not_called()
        assert preview['status'] == 'ready'
        assert preview['metadata']['draft_document_id'] == 'd1'
    else:
        cleanup.assert_called_once_with("p1")
    drive.assert_not_called()


def test_cached_autosave_attaches_record_without_rebuilding():
    from app.core import server
    preview = {'status': 'draft_pending', 'metadata': {}}
    with (patch.object(server, 'preview_storage', {'p1': preview}),
          patch.object(server, 'DynamoDBHandler') as handler,
          patch('app.core.nodes.pdf_build_node') as build):
        handler.return_value.query_by_task_id.return_value = {'document_id': 'd1', 'status': 'draft'}
        assert server._save_preview_as_draft('p1', automatic=True)['success']
    assert preview['status'] == 'ready'
    assert preview['metadata']['draft_document_id'] == 'd1'
    build.assert_not_called()


@pytest.mark.parametrize('persist_success', [True, False])
def test_finalize_promotes_autosaved_record_and_preserves_preview_on_failure(tmp_path, persist_success):
    from app.core import server
    file = tmp_path / 'final.docx'
    file.write_bytes(b'test')
    metadata = {'company_name': 'Test', 'project_title': 'Demo', 'author_name': 'User',
                'document_date': '2026-09-29', 'draft_document_id': 'd1'}
    preview = {'status': 'ready', 'mode': 'POC', 'metadata': metadata,
               'content': {'scope_of_work': 'Build the workflow.'}}
    with (patch.object(server, 'preview_storage', {'p1': preview}),
          patch.object(server, 'get_preview_data', return_value=preview),
          patch.object(server, '_preview_denied', return_value=None),
          patch.object(server, 'get_task', return_value=None),
          patch.object(server, 'create_task'), patch.object(server, 'update_task'),
          patch('app.core.nodes.pdf_build_node', return_value={'output_path': str(file)}),
          patch('app.core.nodes.get_token_usage', return_value={'total_tokens': 12}),
          patch('app.core.nodes.clear_token_usage'),
          patch.object(server, 'upload_generated_document', return_value=None),
          patch.object(server, 'upload_to_s3', return_value={'https_url': 'https://files.s3.amazonaws.com/final.docx'}),
          patch.object(server, '_semantic_index_metadata', return_value={}),
          patch.object(server, 'save_to_dynamodb', return_value={'success': persist_success, 'document_id': 'd1'}) as save,
          patch.object(server, 'delete_preview_data') as cleanup):
        with server.app.test_request_context('/api/finalize', method='POST', json={'preview_id': 'p1'}):
            response, status = server.finalize_document()
    assert save.call_args.kwargs['existing_document_id'] == 'd1'
    assert save.call_args.kwargs['metadata']['status'] == 'completed'
    if persist_success:
        assert status == 200 and response.json['success']
        cleanup.assert_called_once_with('p1')
    else:
        assert status == 500
        cleanup.assert_not_called()
        assert preview['status'] == 'ready'
