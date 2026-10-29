from unittest.mock import MagicMock, patch
import io


def test_proxy_rejects_empty_objects_and_reads_record_consistently():
    from app.core import server
    handler = MagicMock()
    url = 'https://files.s3.amazonaws.com/final.docx'
    handler.table.query.return_value = {'Items': [{'s3_url': url}]}
    s3 = MagicMock()
    s3.get_object.return_value = {'Body': io.BytesIO(b''), 'ContentLength': 0}
    with (patch.object(server, 'DynamoDBHandler', return_value=handler),
          patch.object(server, 'item_is_visible', return_value=True),
          patch.object(server, 'current_identity'),
          patch.object(server, 'parse_s3_location', return_value=('files', 'final.docx')),
          patch.object(server, 'get_s3_client', return_value=s3)):
        with server.app.test_request_context('/api/proxy-download', method='POST', json={'s3_url': url, 'document_id': 'd31'}):
            response, status = server.proxy_download()
    assert status == 500 and 'empty' in response.json['error']
    assert handler.table.query.call_args.kwargs['ConsistentRead'] is True


def test_history_does_not_duplicate_persisted_task():
    from app.core import server
    persisted = {'document_id': 'doc1', 'task_id': 'preview1', 'version': 'v31', 'total_tokens': 123,
                 'timestamp': '2026-10-05T12:00:00'}
    active = {'task': {'task_id': 'preview1'}, 'document': {'document_id': 'preview1'}}
    other = {'task': {'task_id': 'preview2'}, 'document': {'document_id': 'preview2'}}
    with patch.object(server, 'get_active_tasks_as_documents', return_value=[active, other]):
        results = server.merge_with_active_tasks([persisted])
    assert len(results) == 2
    assert [d['document'] for d in results if d['document']['document_id'] == 'doc1'] == [persisted]


def test_upload_checks_nonempty_file_and_completed_remote_size(tmp_path):
    from app.storage.upload1 import S3Uploader
    uploader = S3Uploader.__new__(S3Uploader)
    uploader.s3_client = MagicMock()
    file = tmp_path / 'test.docx'
    file.write_bytes(b'')
    assert uploader.upload_file_to_s3(file) is None
    uploader.s3_client.upload_file.assert_not_called()
    file.write_bytes(b'finished document')
    uploader.s3_client.head_object.return_value = {'ContentLength': 0}
    assert uploader.upload_file_to_s3(file) is None
    uploader.s3_client.head_object.return_value = {'ContentLength': file.stat().st_size}
    assert uploader.upload_file_to_s3(file)['https_url']
