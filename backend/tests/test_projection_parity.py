from dataclasses import replace
from app.diagram.service import DiagramSpec, Node, Edge


def test_projection_uses_paths_and_not_renderer_id_prefixes():
    from app.diagram.projection import connections_from_xml
    spec = DiagramSpec('test', (Node('a', 'A', 'service', 1), Node('b', 'B', 'service', 2)), (Edge('a', 'b'),))
    for attrs in ('id="internal_1" overviewSource="a" overviewTarget="b"',
                  'id="flow_3" sourceNode="a" targetNode="b" originalEdgePaths="[[0]]"'):
        xml = f'<mxfile><diagram><mxGraphModel><root><mxCell edge="1" {attrs}/></root></mxGraphModel></diagram></mxfile>'
        result = connections_from_xml(xml, spec)
        assert result[0]['edge_paths'] == [[0]]
        assert result[0]['source'] == 'a' and result[0]['target'] == 'b'


def test_overview_selection_retains_exact_detail_and_replica_membership():
    from app.diagram.projection import select_links
    from app.diagram.contracts import freeze
    spec = DiagramSpec('test', (Node('a', 'A', 'service', 1), Node('b', 'B', 'service', 2)),
        (Edge('a', 'b', 'Call'), Edge('b', 'a', 'Reply')), architecture_plan={
            'process_story': {'steps': [{'edge_ids': ['e0'], 'node_ids': ['a', 'b']}]}})
    version = freeze(spec)['version']
    links = [{'edge': e, 'paths': [[i]]} for i, e in enumerate(spec.edges)]
    visible = select_links(spec, links)
    assert len(visible) == 1 and visible[0]['paths'] == [[0]]
    assert freeze(spec)['version'] == version and len(spec.edges) == 2
