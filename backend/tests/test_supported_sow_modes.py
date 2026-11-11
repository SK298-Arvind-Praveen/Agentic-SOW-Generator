from unittest.mock import patch
import pytest


@pytest.mark.parametrize("endpoint,handler", [
    ("/api/generate", "generate_document"),
    ("/api/preview", "generate_preview"),
])
def test_retired_mode_is_rejected_before_generation(endpoint, handler):
    from app.core import server
    with (patch.object(server, '_business_unit_for_new_record', return_value=('GenAI', None)),
          patch.object(server, '_ownership_metadata', return_value={}),
          patch.object(server, 'create_task') as create):
        with server.app.test_request_context(endpoint, method='POST', data={'mode': 'POC_TO_PROD'}):
            response, status = getattr(server, handler)()
    assert status == 400
    assert 'POC or PROD' in response.json['error']
    create.assert_not_called()


def test_conversion_route_and_graph_node_are_removed():
    from app.core import server, graph
    assert '/api/recent-poc_to_prod' not in {rule.rule for rule in server.app.url_map.iter_rules()}
    for factory in (graph.create_graph, graph.create_preview_graph, graph.create_fast_preview_graph):
        compiled = factory().get_graph()
        assert 'ingest' not in compiled.nodes
        assert any(edge.source == '__start__' and edge.target == 'research' for edge in compiled.edges)



def test_project_creation_rejects_retired_mode_before_starting_task():
    from app.core import server
    with (patch.object(server, 'account_handler') as accounts,
          patch.object(server, '_resource_denied', return_value=None),
          patch.object(server, '_ownership_metadata', return_value={}),
          patch.object(server, 'create_task') as create):
        accounts.get_project.return_value = {'project_name': 'Project', 'business_unit': 'GenAI'}
        with server.app.test_request_context('/api/projects/p1/sows', method='POST', json={'mode': 'POC_TO_PROD'}):
            response, status = server.create_sow_for_project('p1')
    assert status == 400
    create.assert_not_called()


def test_legacy_records_do_not_break_supported_mode_grouping():
    from unittest.mock import Mock
    from app.db.dynamodb_handler_optimized import DynamoDBHandlerOptimized
    handler = DynamoDBHandlerOptimized.__new__(DynamoDBHandlerOptimized)
    handler.table = Mock()
    handler.table.scan.return_value = {'Items': [
        {'mode': mode, 'customer_name': 'Client', 'project_name': 'Project', 'version': 'v1'}
        for mode in ('POC_TO_PROD', 'POC', 'PROD')
    ]}
    grouped = handler.get_companies_grouped()
    assert grouped['Client']['document_count'] == 2
    assert set(grouped['Client']['projects']['Project']) == {'project_name', 'POC', 'PROD'}
