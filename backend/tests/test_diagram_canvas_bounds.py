from app.diagram.service import DiagramSpec, Node, Edge, _geometry


def test_nine_integration_peers_fit_canvas():
    peers = [Node(f'p{i}', f'System {i}', 'external', 0) for i in range(9)]
    spec = DiagramSpec('Integrations', tuple([Node('hub','Platform','application',1)] + peers),
                       tuple(Edge('hub', p.id) for p in peers))
    positions, width, height = _geometry(spec)
    assert len(positions) == 10
    for x,y,w,h in positions.values():
        assert x >= 0 and y >= 0 and x+w <= width and y+h <= height
