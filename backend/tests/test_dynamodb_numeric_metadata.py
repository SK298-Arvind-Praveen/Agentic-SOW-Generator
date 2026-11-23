from decimal import Decimal
from unittest.mock import Mock
from boto3.dynamodb.types import TypeSerializer
from app.db.dynamodb_handler_optimized import DynamoDBHandlerOptimized


def test_save_serializes_nested_timing_and_pricing_without_mutating_preview():
    handler = object.__new__(DynamoDBHandlerOptimized)
    handler.validate_required_fields = Mock(return_value=(True, [], ''))
    handler.find_similar_documents = Mock(return_value=[])
    handler.generate_document_id = Mock(return_value='test-doc')
    captured = []
    def put(**kwargs):
        TypeSerializer().serialize(kwargs['Item'])
        captured.append(kwargs['Item'])
        return {}
    handler.table = Mock()
    handler.table.put_item.side_effect = put
    metadata = {'company_name': 'Example', 'author_name': 'Tester',
                'project_title': 'Inspection', 'mode': 'POC',
                'token_usage': {'stage_metrics': [{'elapsed_seconds': 5.281, 'calls': 2}]},
                'aws_pricing': {'monthly_cost': 12.34}}
    result = handler.save_document_metadata(metadata, 's3://test/output.docx', auto_version=False)
    assert result['success'], result
    assert captured[0]['token_usage']['stage_metrics'][0]['elapsed_seconds'] == Decimal('5.281')
    assert captured[0]['aws_pricing']['monthly_cost'] == Decimal('12.34')
    assert isinstance(metadata['token_usage']['stage_metrics'][0]['elapsed_seconds'], float)
