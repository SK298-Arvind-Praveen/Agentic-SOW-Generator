from unittest.mock import MagicMock
from decimal import Decimal

from app.db.dynamodb_handler_optimized import DynamoDBHandlerOptimized


def _handler_with_table(table):
    handler = object.__new__(DynamoDBHandlerOptimized)
    handler.table = table
    return handler


def test_draft_promotion_keeps_document_id_version_and_primary_key():
    table = MagicMock()
    handler = _handler_with_table(table)
    handler.validate_required_fields = MagicMock(return_value=(True, [], ''))
    handler.get_document_by_id = MagicMock(return_value={
        'document_id': 'd1', 'timestamp': 'original', 'status': 'draft',
        'version': 'v20', 'owner_email': 'user@example.com',
    })
    handler.get_next_version = MagicMock()
    handler.find_similar_documents = MagicMock(return_value=[])
    result = handler.save_document_metadata(
        {'company_name': 'Test', 'project_name': 'Demo', 'author_name': 'User',
         'mode': 'POC', 'status': 'completed', 'owner_email': 'user@example.com'},
        's3://files/final.docx', existing_document_id='d1',
    )
    assert result['success']
    assert result['document_id'] == 'd1'
    assert result['version'] == 'v20'
    assert result['timestamp'] == 'original'
    assert table.put_item.call_args.kwargs['Item']['status'] == 'completed'
    assert 'ConditionExpression' in table.put_item.call_args.kwargs
    handler.get_next_version.assert_not_called()


def test_completed_or_deleted_draft_cannot_be_overwritten():
    handler = _handler_with_table(MagicMock())
    handler.validate_required_fields = MagicMock(return_value=(True, [], ''))
    for record in (None, {'status': 'completed'}):
        handler.get_document_by_id = MagicMock(return_value=record)
        result = handler.save_document_metadata({}, 's3://files/test.docx', existing_document_id='d1')
        assert not result['success']
    handler.table.put_item.assert_not_called()


def test_history_projection_includes_draft_state_and_recovery_location():
    table = MagicMock()
    table.scan.return_value = {"Items": []}
    _handler_with_table(table).list_all_documents()
    fields = set(table.scan.call_args.kwargs["ExpressionAttributeNames"].values())
    assert {"status", "draft_preview_s3_url", "preview_id"} <= fields


def test_history_response_preserves_draft_state_not_just_projection():
    table = MagicMock()
    table.scan.return_value = {'Items': [{'document_id':'d1', 'status':'draft',
        'draft_preview_s3_url':'s3://files/preview.json', 'preview_id':'p1'}]}
    record = _handler_with_table(table).list_all_documents()[0]
    assert record['status'] == 'draft'
    assert record['draft_preview_s3_url'] == 's3://files/preview.json'
    assert record['preview_id'] == 'p1'


def test_saving_a_version_does_not_delete_existing_history():
    table = MagicMock()
    handler = _handler_with_table(table)
    handler.validate_required_fields = MagicMock(return_value=(True, [], ""))
    handler.get_next_version = MagicMock(return_value="v14")
    handler.find_similar_documents = MagicMock(return_value=[{"version": "v13"}])
    handler.delete_old_duplicates = MagicMock()

    result = handler.save_document_metadata(
        {
            "company_name": "Axis Securities",
            "author_name": "Arvind",
            "project_name": "CRM Integration",
            "mode": "POC",
            "business_unit": "GenAI",
            "owner_email": "admin@shellkode.com",
            "owner_name": "Sample Admin",
            "total_tokens": 123456,
            "token_usage": {
                "total_input_tokens": 100000,
                "total_output_tokens": 23456,
                "total_tokens": 123456,
                "api_calls": 4,
                "models": {"writer": 4},
            },
            "semantic_search_text": "Customer support automation",
            "semantic_search_embedding": [0.25, -0.5],
            "semantic_search_embeddings": [[0.25, -0.5], [0.75, -0.25]],
            "semantic_embedding_model_id": "titan-profile",
            "semantic_search_text_hash": "abc123",
            "semantic_index_version": 3,
            "status": "draft",
            "draft_preview_s3_url": "s3://documents/draft-previews/preview-1.json",
            "preview_id": "preview-1",
        },
        "s3://documents/v14.docx",
    )

    assert result["success"] is True
    assert result["version"] == "v14"
    assert result["deduplication"]["cleanup_performed"] is False
    handler.delete_old_duplicates.assert_not_called()
    table.put_item.assert_called_once()
    saved = table.put_item.call_args.kwargs["Item"]
    assert saved["business_unit"] == "GenAI"
    assert saved["owner_email"] == "admin@shellkode.com"
    assert saved["owner_name"] == "Sample Admin"
    assert saved["total_tokens"] == 123456
    assert saved["token_usage"]["total_output_tokens"] == 23456
    assert saved["semantic_search_embedding"] == [Decimal("0.25"), Decimal("-0.5")]
    assert saved["semantic_search_embeddings"] == [
        [Decimal("0.25"), Decimal("-0.5")],
        [Decimal("0.75"), Decimal("-0.25")],
    ]
    assert saved["semantic_embedding_model_id"] == "titan-profile"
    assert saved["semantic_index_version"] == 3
    assert saved["status"] == "draft"
    assert saved["draft_preview_s3_url"].endswith("preview-1.json")
    assert saved["preview_id"] == "preview-1"


def test_history_scan_excludes_large_vectors_but_semantic_scan_pages_them():
    table = MagicMock()
    table.scan.side_effect = [
        {"Items": [{"document_id": "one", "timestamp": "1"}],
         "LastEvaluatedKey": {"document_id": "one", "timestamp": "1"}},
        {"Items": [{
            "document_id": "two", "timestamp": "2",
            "semantic_search_embedding": [Decimal("0.1")],
            "semantic_embedding_model_id": "titan-profile",
            "semantic_index_version": 3,
        }]},
    ]
    handler = _handler_with_table(table)

    records = handler.list_all_documents(limit=2, include_semantic_text=True)

    assert table.scan.call_count == 2
    assert "ProjectionExpression" not in table.scan.call_args_list[0].kwargs
    assert records[0]["document_id"] == "two"
    assert records[0]["semantic_search_embedding"] == [Decimal("0.1")]

    table.reset_mock()
    table.scan.side_effect = [{"Items": [{"document_id": "one", "timestamp": "1"}]}]
    handler.list_all_documents(limit=1, include_semantic_text=False)
    assert "ProjectionExpression" in table.scan.call_args.kwargs


def test_company_documents_reads_all_query_pages_and_keeps_newest_first():
    table = MagicMock()
    table.query.side_effect = [
        {
            "Items": [{
                "document_id": "old",
                "timestamp": "2026-08-18T10:00:00",
                "project_name": "CRM Integration",
                "mode": "POC",
                "version": "v1",
            }],
            "LastEvaluatedKey": {"document_id": "old"},
        },
        {
            "Items": [{
                "document_id": "new",
                "timestamp": "2026-09-01T10:00:00",
                "project_name": "CRM Integration",
                "mode": "POC",
                "version": "v13",
            }],
        },
    ]
    handler = _handler_with_table(table)

    grouped = handler.get_company_documents("Axis Securities", limit=100)

    assert table.query.call_count == 2
    versions = grouped["projects"]["CRM Integration"]["POC"]
    assert list(versions) == ["v13", "v1"]
    assert versions["v13"][0]["document_id"] == "new"
