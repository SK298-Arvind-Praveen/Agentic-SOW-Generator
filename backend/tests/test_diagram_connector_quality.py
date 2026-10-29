from types import SimpleNamespace

import pytest

from app.diagram.review import connector_report, local_routes, geometry_report, layout_quality
from app.diagram.planning import DEPLOYMENT_DESIGN_RULES


def test_networking_is_conditional_not_an_enterprise_default():
    assert 'Do NOT infer a VPC requirement merely from enterprise' in DEPLOYMENT_DESIGN_RULES
    assert 'preferred\nbaseline' not in DEPLOYMENT_DESIGN_RULES
    assert 'Never introduce private adapters, NAT, IGW or duplicate AZ nodes' in DEPLOYMENT_DESIGN_RULES


def test_loop_is_penalised_even_without_crossings():
    positions = {'a': (20, 20, 80, 80), 'b': (200, 20, 80, 80)}
    short = connector_report(positions, [[(100, 60), (200, 60)]])
    loop = connector_report(positions, [[(100,60),(120,60),(120,400),(180,400),(180,60),(200,60)]])
    assert loop['max_connector_detour'] > 6
    assert loop['connector_bends'] == 4
    assert layout_quality(loop) > layout_quality(short)
    assert short['connector_bends'] == 0


def test_router_uses_short_facing_ports_and_preserves_edges():
    positions = {'a': (20,20,80,80), 'b': (200,20,80,80), 'c': (200,180,80,80)}
    spec = SimpleNamespace(nodes=list(positions), edges=[
        SimpleNamespace(source='a', target='b'), SimpleNamespace(source='b', target='c')])
    paths = local_routes(spec, positions, {}, {}, 320, 300)
    assert paths[0][0] == (100,60)
    assert paths[0][-1][0] == 200
    assert paths[1][0][1] == 100
    assert paths[1][-1] == (240,180)
    assert geometry_report(spec, positions, paths)['connector_node_intersections'] == 0


def test_distinct_edges_do_not_share_a_visible_terminal():
    positions = {'a': (40,40,160,100), 'b': (300,40,160,100), 'c': (300,250,160,100)}
    spec = SimpleNamespace(nodes=list(positions), edges=[
        SimpleNamespace(source='a',target='b'), SimpleNamespace(source='a',target='c')])
    paths = local_routes(spec, positions, {}, {}, 550, 420)
    assert paths[0][0] != paths[1][0]
    for edge, path in zip(spec.edges, paths):
        for key, end, neighbor in ((edge.source,path[0],path[1]), (edge.target,path[-1],path[-2])):
            x,y,w,h = positions[key]
            if end[0] in (x,x+w):
                assert end[1] == neighbor[1] and abs(end[0]-neighbor[0]) >= 8
            else:
                assert end[0] == neighbor[0] and abs(end[1]-neighbor[1]) >= 8


def test_false_junctions_and_shared_lines_are_not_a_zero_crossing_pass():
    from app.diagram.review import _ambiguous_contact
    assert _ambiguous_contact([(0,0),(100,0)], [(50,0),(50,100)])
    assert _ambiguous_contact([(0,0),(100,0)], [(20,0),(80,0)])
    assert not _ambiguous_contact([(0,0),(100,0)], [(0,12),(100,12)])
    assert layout_quality({'ambiguous_connector_pairs':1}) > layout_quality({'connector_crossings':1})


def test_fanout_port_order_follows_destinations_not_json_order():
    positions = {'worker':(100,100,168,160), 'crm':(620,330,168,120), 's3':(380,100,168,160)}
    spec = SimpleNamespace(nodes=[SimpleNamespace(id=k,icon_key='icon' if k!='crm' else '') for k in positions],
        edges=[SimpleNamespace(source='worker',target='crm'),SimpleNamespace(source='worker',target='s3')])
    paths = local_routes(spec,positions,{}, {},850,500,iconic=True)
    assert geometry_report(spec,positions,paths)['ambiguous_connector_pairs'] == 0
    assert paths[0][0][1] > paths[1][0][1]


def test_connection_verbs_survive_more_than_five_edges():
    from app.diagram.service import DiagramService
    nodes = [{'id':str(i), 'label':str(i)} for i in range(8)]
    edges = [{'source':str(i), 'target':str(i+1), 'label':'Read data'} for i in range(7)]
    assert [e['label'] for e in DiagramService._simplify_architecture_edges(nodes,edges)] == ['Read data']*7


def test_router_goes_around_unrelated_boundary_not_through_it():
    positions = {'a': (20,100,80,80), 'b': (300,100,80,80)}
    spec = SimpleNamespace(nodes=list(positions), edges=[SimpleNamespace(source='a', target='b')])
    from app.diagram.review import hits_box
    box = (140,70,120,140)
    paths = local_routes(spec, positions, {'unrelated':box}, {}, 420, 300)
    assert not any(hits_box(a,b,box) for a,b in zip(paths[0], paths[0][1:]))
    assert len(paths[0]) <= 6  # Includes visible perpendicular endpoint stubs.


def test_routing_budget_is_enforced():
    spec = SimpleNamespace(edges=[SimpleNamespace(source='a', target='b')])
    with pytest.raises(TimeoutError):
        local_routes(spec, {'a':(20,20,80,80), 'b':(200,20,80,80)}, {}, {}, 320, 140, deadline=0)


def test_shared_target_has_separate_arrowheads_and_approach_tracks():
    positions = {'worker':(312,120,168,112), 'adapter':(312,264,168,112),
                 'crm':(840,198,168,112)}
    spec = SimpleNamespace(nodes=[SimpleNamespace(id=k,icon_key='' if k=='crm' else 'icon') for k in positions],
        edges=[SimpleNamespace(source='worker',target='crm'),
               SimpleNamespace(source='adapter',target='crm'),
               SimpleNamespace(source='crm',target='adapter')])
    paths = local_routes(spec,positions,{}, {},1040,500,iconic=True)
    metrics = geometry_report(spec,positions,paths)
    assert metrics['ambiguous_connector_pairs'] == 0
    assert metrics['connector_crossings'] == 0
    assert len({paths[0][-1],paths[1][-1],paths[2][0]}) == 3
