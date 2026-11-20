import copy
import json
from dataclasses import replace
from pathlib import Path

from app.diagram import compact_mixed, mixed_deployment, narrative
from app.diagram.service import DiagramSpec, Node, Edge
from app.diagram.review import geometry_report
from app.diagram.aws_icons import AwsIconRegistry
from app.diagram.narrative_boundaries import overview_xml


def architecture():
    raw=json.loads((Path(__file__).parent/'fixtures/large_mixed_architecture.json').read_text())
    return DiagramSpec('Multichannel application',tuple(Node(**n,layer=0) for n in raw['nodes']),
        tuple(Edge(**e) for e in raw['edges']),architecture_plan=raw['architecture_plan'])


def test_story_icons_fit_large_mixed_architecture():
    spec=architecture()
    spec=replace(spec,architecture_plan={**spec.architecture_plan,'story_overview':True})
    registry=AwsIconRegistry(Path(__file__).parents[1]/'assets')
    _,metrics=overview_xml(spec,registry)
    assert metrics['nodes']==len(spec.nodes)
    assert metrics['node_overlaps']==metrics['containment_violations']==metrics['out_of_bounds']==0


def test_placeholders_do_not_disable_narrative_but_two_named_accounts_do():
    spec=architecture()
    assert narrative.eligible(spec)
    assert narrative.validate(spec.architecture_plan['narrative_view'],spec)
    nodes=tuple(replace(n,account='Second account') if n.id=='iam' else n for n in spec.nodes)
    assert not narrative.eligible(replace(spec,nodes=nodes))


def test_compact_grid_keeps_all_scopes_and_parallel_azs():
    spec=architecture();before=copy.deepcopy(spec)
    assert mixed_deployment.enabled(spec) and compact_mixed.enabled(spec)
    p,b,parents,w,h,_,kinds=mixed_deployment.geometry(spec)
    assert set(p)=={n.id for n in spec.nodes}
    assert h/w<1.35
    assert geometry_report(replace(spec,edges=()),p,[])['node_overlaps']==0
    azs=[r for k,r in b.items() if kinds[k]=='az']
    assert len(azs)==2 and azs[0][1]==azs[1][1] and azs[0][0]!=azs[1][0]
    group_boxes=[b[g['id']] for g in spec.architecture_plan['narrative_view']['groups']]
    for i,(x,y,gw,gh) in enumerate(group_boxes):
        for xx,yy,ww,hh in group_boxes[i+1:]:
            assert x+gw<=xx or xx+ww<=x or y+gh<=yy or yy+hh<=y
    for n in spec.nodes:
        chain=[];key=n.id
        while key in parents:key=parents[key];chain.append(key)
        assert ('vpc_0' in chain)==(n.scope in {'vpc','az'})
    assert spec==before


def test_compact_render_covers_graph_with_no_obstructed_or_ambiguous_routes():
    spec=architecture()
    registry=AwsIconRegistry(Path(__file__).parents[1]/'assets')
    _,metrics=overview_xml(spec,registry)
    assert metrics['node_overlaps']==metrics['connector_node_intersections']==0
    assert metrics['containment_violations']==metrics['out_of_bounds']==0
    assert metrics['ambiguous_connector_pairs']==0
    assert metrics['original_edges']==len(spec.edges)
    assert metrics['visible_edge_indices']==list(range(len(spec.edges)))
    assert metrics['boundary_badges']>=10
