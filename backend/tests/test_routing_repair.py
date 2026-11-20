import copy
import json
import time
from dataclasses import replace
from pathlib import Path

from app.diagram import routing_repair
from app.diagram.service import DiagramService, DiagramSpec, Node, Edge
from app.diagram.narrative_boundaries import geometry, projection
from app.diagram.review import geometry_report, hits_box


def saved():
    return json.loads((Path(__file__).parent/'fixtures/tiered_routing_review.json').read_text())


def value(raw):
    return DiagramSpec(raw['title'],tuple(Node(**n) for n in raw['nodes']),
        tuple(Edge(**e) for e in raw['edges']),architecture_plan=raw['architecture_plan'])


def finding(stage, description):
    return {'kind': 'architecture' if stage == 'graph' else 'visual', 'stage': stage,
        'rule_id': stage+'.test', 'severity': 'important', 'description': description,
        'node_ids': ['ecs_a'], 'edge_ids': ['e0'], 'step_ids': [],
        'evidence': description, 'repair_instruction': 'Correct the identified '+stage+' issue.'}


def test_visual_review_activates_renderer_repair_without_changing_architecture():
    raw=saved();original=copy.deepcopy(raw)
    repaired=routing_repair.prepare(raw,{'issues':[{'kind':'visual','description':'SQL crosses reports'}]})
    assert repaired['architecture_plan']['routing_repair']['version']==1
    assert repaired['nodes']==raw['nodes'] and repaired['edges']==raw['edges']
    assert raw==original
    assert routing_repair.prepare(repaired,{'issues':[{'kind':'visual'}]})==repaired
    assert routing_repair.prepare(raw,{'issues':[{'kind':'architecture'}]})==raw
    assert routing_repair.prepare(raw,{'issues':[]})==raw


def test_review_retry_changes_renderer_instead_of_only_rephrasing_groups():
    service=DiagramService.__new__(DiagramService);raw=saved();calls=[]
    def generate(requirements,metadata,narrative):
        calls.append(copy.deepcopy(requirements))
        spec=requirements.get('_architecture_retry_spec',raw)
        return [{'spec':spec,'image_base64':'rendered','layout_engine':'narrative_drawio',
            'vision_review':{'status':'reviewed','issues':[] if len(calls)==2 else
                [finding('layout', 'Route crosses another subnet')]}}]
    service._generate_assets_once=generate
    result=service._generate_assets_bounded({}, {}, '')
    assert len(calls)==2
    assert calls[1]['_architecture_retry_spec']['architecture_plan']['routing_repair']
    assert not result[0]['vision_review']['issues']


def test_repaired_routes_preserve_graph_and_avoid_unrelated_subnets():
    raw=routing_repair.prepare(saved(),{'issues':[{'kind':'visual','description':'Crossed SQL, ingress and reports'}]})
    spec=value(raw);p,b,parents,w,h,captions,kinds=geometry(spec)
    links,coverage=projection(spec)
    view=replace(spec,edges=tuple(l['edge'] for l in links))
    paths=routing_repair.routes(view,p,b,parents,w,h,time.monotonic()+30,captions)
    constraints=routing_repair.options(view,p,b,parents)['edge_obstacles']
    assert len(paths)==len(view.edges)
    for e,path in zip(view.edges,paths):
        assert not any(hits_box(a,z,box) for a,z in zip(path,path[1:]) for box in constraints[(e.source,e.target)])
    metrics=geometry_report(view,p,paths)
    assert metrics['connector_node_intersections']==metrics['ambiguous_connector_pairs']==0
    # A third short crossing is preferable to the two-crossing candidate's
    # long detour through the outside corridor. Containment remains strict.
    assert metrics['connector_crossings']<=3
    assert metrics['long_connector_count']==metrics['detouring_connector_count']==0
    assert parents['vpce']=='vpc_0'
    assert p['ecs_a'][0]+p['ecs_a'][2]<p['vpce'][0]<p['ecs_b'][0]
    assert p['cognito'][0] - (b['vpc_0'][0]+b['vpc_0'][2]) >= 100
    assert spec.nodes==value(saved()).nodes and spec.edges==value(saved()).edges


def test_visual_repair_is_not_lost_when_architecture_retry_was_already_spent():
    service=DiagramService.__new__(DiagramService);raw=saved();calls=[]
    def generate(requirements,metadata,narrative):
        calls.append(copy.deepcopy(requirements))
        issues=([finding('graph', 'Initial graph needs correction')] if len(calls)==1
                else [finding('layout', 'SQL crosses reports')] if len(calls)==2 else [])
        return [{'spec':requirements.get('_architecture_retry_spec',raw),'image_base64':'rendered',
            'layout_engine':'narrative_drawio','vision_review':{'status':'reviewed','issues':issues}}]
    service._generate_assets_once=generate
    result=service._generate_assets_bounded({}, {}, '')
    assert len(calls)==3
    assert calls[2]['_architecture_retry_spec']['architecture_plan']['routing_repair']
    assert not result[0]['vision_review']['issues']


def test_failed_geometry_correction_is_bounded_and_retains_an_image():
    service=DiagramService.__new__(DiagramService);raw=saved();calls=[]
    def generate(requirements,metadata,narrative):
        calls.append(1)
        return [{'spec':requirements.get('_architecture_retry_spec',raw),'image_base64':'rendered',
            'layout_engine':'narrative_drawio','vision_review':{'status':'reviewed','issues':[
                finding('layout', 'Remaining visible issue')]}}]
    service._generate_assets_once=generate
    result=service._generate_assets_bounded({}, {}, '')
    assert len(calls)==3 and result[0]['image_base64']
    assert result[0]['retry_exhausted']
