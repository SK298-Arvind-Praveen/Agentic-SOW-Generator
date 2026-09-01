from unittest.mock import MagicMock

from app.db.dynamodb_handler_optimized import DynamoDBHandlerOptimized


def _handler_with_table(table):
    handler = object.__new__(DynamoDBHandlerOptimized)
    handler.table = table
    return handler


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
