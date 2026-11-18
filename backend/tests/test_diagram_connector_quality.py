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


def test_outbound_integrations_enter_from_top_without_under_box_loops():
    positions = {'runtime':(200,50,300,200),'a':(40,420,120,95),
                 'b':(300,420,120,95),'c':(580,420,120,95)}
    spec = SimpleNamespace(nodes=[], edges=[SimpleNamespace(source='runtime',target=k) for k in ('a','b','c')])
    sides = {('runtime',k):{'runtime':{'bottom'},k:{'top'}} for k in ('a','b','c')}
    paths = local_routes(spec,positions,{}, {},760,560,max_terminal_gap=32,terminal_sides=sides)
    assert all(path[0][1] == 250 and path[-1][1] == 420 for path in paths)
    assert all(y <= 420 for path in paths for x,y in path)
    assert geometry_report(spec,positions,paths)['connector_node_intersections'] == 0


def test_aligned_icons_do_not_jog_due_to_different_incident_counts():
    positions = {'a':(20,100,168,132),'b':(300,100,168,132),'c':(20,300,168,132)}
    spec = SimpleNamespace(nodes=[SimpleNamespace(id=k,icon_key='aws-icon') for k in positions],
        edges=[SimpleNamespace(source='c',target='a'),SimpleNamespace(source='a',target='b')])
    paths = local_routes(spec,positions,{}, {},550,500,iconic=True)
    assert len(paths[1]) == 2
    assert paths[1][0][1] == paths[1][1][1]
    assert geometry_report(spec,positions,paths)['connector_node_intersections'] == 0


def test_short_routes_win_over_page_wide_routes_with_slightly_fewer_parallel_pairs():
    long = dict(connector_crossings=3, ambiguous_connector_pairs=11,
                connector_length_normalized=5.8, connector_bends=41,
                long_connector_count=3, longest_connector_fraction=1.0)
    compact = dict(connector_crossings=3, ambiguous_connector_pairs=17,
                   connector_length_normalized=4.2, connector_bends=36,
                   long_connector_count=0, longest_connector_fraction=.65)
    assert layout_quality(compact) < layout_quality(long)


def test_vertical_actor_group_path_does_not_jog_due_to_incident_offsets():
    positions={'actor':(180,20,180,80),'group':(100,300,500,180),'peer':(680,300,100,80)}
    spec=SimpleNamespace(nodes=list(positions),edges=[SimpleNamespace(source='actor',target='group'),
        SimpleNamespace(source='peer',target='group')])
    paths=local_routes(spec,positions,{}, {},850,550)
    assert len(paths[0])==2 and paths[0][0][0]==paths[0][1][0]
    assert geometry_report(spec,positions,paths)['connector_node_intersections']==0


def test_vertical_shortcut_never_goes_through_an_intervening_node():
    positions={'actor':(180,20,180,80),'group':(100,350,500,180),'blocker':(160,170,220,100)}
    spec=SimpleNamespace(nodes=list(positions),edges=[SimpleNamespace(source='actor',target='group')])
    paths=local_routes(spec,positions,{}, {},800,600)
    assert len(paths[0])>2
    assert geometry_report(spec,positions,paths)['connector_node_intersections']==0


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


def test_physical_routes_can_cross_empty_sibling_boundaries_without_page_detours():
    positions={'app':(50,160,100,80),'report':(700,160,100,80),'db':(340,330,100,80)}
    boxes={'az_a':(20,80,180,400),'az_b':(240,80,350,400)}
    parents={'app':'az_a','db':'az_b','report':'region'}
    spec=SimpleNamespace(nodes=list(positions),edges=[SimpleNamespace(source='app',target='report')])
    paths=local_routes(spec,positions,boxes,parents,850,550,boundary_transit=True)
    assert len(paths[0])==2  # The empty AZ corridor is not a service or a wall.
    assert geometry_report(spec,positions,paths)['connector_node_intersections']==0
    assert parents=={'app':'az_a','db':'az_b','report':'region'}


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


def test_straight_shortcut_does_not_steal_a_later_edges_terminal():
    positions={'a':(100,300,180,120),'b':(600,300,180,120),
               'c':(100,100,180,120),'d':(100,500,180,120)}
    spec=SimpleNamespace(nodes=list(positions),edges=[
        SimpleNamespace(source=k,target='b') for k in ('a','c','d')])
    paths=local_routes(spec,positions,{}, {},900,700)
    assert len({path[-1] for path in paths})==3
    assert geometry_report(spec,positions,paths)['ambiguous_connector_pairs']==0


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


def test_external_relationship_routes_outside_cloud_without_blocking_internal_flow():
    from app.diagram.review import hits_box
    positions = {'staff':(120,10,80,70), 'crm':(260,440,80,70),
                 'app':(100,220,80,70), 'data':(300,220,80,70)}
    cloud = (40,130,400,240)
    spec = SimpleNamespace(nodes=list(positions), edges=[
        SimpleNamespace(source='staff',target='crm'),
        SimpleNamespace(source='app',target='data')])
    paths = local_routes(spec,positions,{}, {},500,560,
        edge_obstacles={('staff','crm'):[cloud]})
    assert not any(hits_box(a,b,cloud) for a,b in zip(paths[0],paths[0][1:]))
    assert len(paths[1]) == 2
    assert geometry_report(spec,positions,paths)['connector_node_intersections'] == 0


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
