"""Functional overview is a lossless presentation of a fixed deployment graph."""
import copy
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest

from app.diagram import narrative
from app.diagram.aws_icons import AwsIconRegistry
from app.diagram.service import DiagramService, DiagramSpec, Node, Edge


@pytest.fixture
def architecture():
    registry = AwsIconRegistry(Path(__file__).parents[1] / 'assets')
    services = [('ui','Amazon S3'), ('auth','Amazon Cognito'), ('api','Amazon API Gateway'),
                ('worker','AWS Lambda'), ('workflow','AWS Step Functions'),
                ('cases','Amazon DynamoDB'), ('audit','Amazon DynamoDB'),
                ('ocr','Amazon Textract'), ('notify','Amazon SNS'), ('docs','Amazon S3'),
                ('cdn','Amazon CloudFront'), ('kms','AWS Key Management Service'),
                ('monitor','Amazon CloudWatch'), ('iam','AWS Identity and Access Management')]
    nodes = []
    for key, name in services:
        icon = registry.candidate(name, 'explicit', name)
        nodes.append(Node(key,name,'service',0,scope='global' if key in {'cdn','iam'} else 'regional',
                          icon_key=icon.key if icon else ''))
    nodes += [Node('user','Reviewer','actor',0,scope='external'),
              Node('external','Case system','external',0,scope='external')]
    pairs = [('user','cdn'),('user','auth'),('cdn','ui'),('cdn','api'),('api','auth'),
             ('api','worker'),('worker','workflow'),('workflow','worker'),('worker','cases'),
             ('worker','audit'),('workflow','ocr'),('ocr','notify'),('notify','worker'),
             ('ocr','docs'),('worker','external'),('worker','monitor'),('docs','kms')]
    plan = {'groups':[
        {'id':'front','label':'Upload and review','rows':[['ui'],['auth','api']]},
        {'id':'process','label':'Process cases','rows':[['worker','workflow'],['cases','audit']]},
        {'id':'extract','label':'Extract evidence','rows':[['ocr','notify'],['docs']]}],
        'support':['kms','monitor','iam'],
        'roles':{'ui':'UI assets','docs':'Documents','cases':'Case records','audit':'Audit trail'},
        'links':[{'source':'front','target':'process','label':'Submit case'},
                 {'source':'process','target':'extract','label':'Extract / results'}]}
    spec = DiagramSpec('Document processing', tuple(nodes), tuple(Edge(a,b,'Read') for a,b in pairs),
                       architecture_plan={'narrative_view':plan})
    return spec, plan, registry


def test_projection_accounts_for_each_real_connection_once(architecture):
    spec, plan, _ = architecture
    projected = narrative.projection(spec, plan)
    assert sorted(projected['internal']+projected['shared']+
                  [i for l in projected['links'] for i in l['edge_indices']]) == list(range(len(spec.edges)))
    links = {(l['source'],l['target']):l for l in projected['links']}
    assert links['process','extract']['both']
    assert not links['front','process']['both']
    assert len(projected['shared']) == 2


def test_corrective_attempt_recomposes_view_using_review_feedback(architecture, monkeypatch):
    spec, plan, registry = architecture
    prompts = []
    def generate(prompt, **kwargs):
        prompts.append(prompt)
        return SimpleNamespace(text=json.dumps(plan))
    planner = SimpleNamespace(generate=generate)
    monkeypatch.setattr('app.core.bedrock_llm.BedrockLLM', lambda *args: planner)
    monkeypatch.setattr(narrative, 'overview_xml', lambda *args: ('<xml/>', {}))
    monkeypatch.setattr(narrative, 'improve_rows', lambda candidate, *args: candidate)
    feedback = 'Separate the endpoint and workflow connector junctions'
    spec = replace(spec, architecture_plan={**spec.architecture_plan, 'retry_feedback': feedback})
    result = narrative.prepare(SimpleNamespace(config=None, bedrock=None, icon_registry=registry), spec)
    assert len(prompts) == 1 and feedback in prompts[0]
    assert result.nodes == spec.nodes and result.edges == spec.edges
    assert result.architecture_plan['narrative_view']


def test_member_link_projects_to_its_real_group_without_inventing_edges(architecture):
    spec, plan, _ = architecture
    plan = copy.deepcopy(plan)
    plan['links'] = [{'source':'worker', 'target':'external', 'label':'Export'}]
    checked = narrative.validate(plan, spec)
    assert checked['links'] == [{'source':'process', 'target':'external', 'label':'Export'}]
    plan['links'] = [{'source':'external', 'target':'worker', 'label':'Invented reverse'}]
    with pytest.raises(ValueError, match='actual directed'):
        narrative.validate(plan, spec)


def test_wordy_presentation_is_advisory_and_preserves_valid_architecture(architecture):
    spec,plan,_=architecture
    plan=copy.deepcopy(plan)
    plan['roles']['docs']='Private source documents for extraction'
    plan['groups'][0]['label']='Upload documents and review the extracted results'
    plan['links'][0]['label']='Submit the case for document processing'
    result=narrative.validate(plan,spec)
    assert result['roles']==plan['roles']
    assert len(result['presentation_warnings'])==3
    # Relaxing presentation never authorises a made-up component.
    plan['roles']['invented']='Short name'
    with pytest.raises(ValueError,match='known node IDs'):narrative.validate(plan,spec)


@pytest.mark.parametrize('mutation', ['missing','duplicate','global','fake_link','roles'])
def test_reject_loss_reparenting_and_invented_flow(architecture, mutation):
    spec, plan, _ = architecture
    plan = copy.deepcopy(plan)
    if mutation == 'missing':
        plan['groups'][0]['rows'].pop()
    elif mutation == 'duplicate':
        plan['groups'][0]['rows'][0].append('api')
    elif mutation == 'global':
        plan['groups'][0]['rows'][0].append('cdn')
    elif mutation == 'fake_link':
        plan['links'].append({'source':'front','target':'external','label':'Fake export'})
    else:
        del plan['roles']['docs']
    with pytest.raises(ValueError):
        narrative.validate(plan, spec)


def test_actual_xml_has_clear_routes_and_all_icons_in_correct_scopes(architecture):
    spec, plan, registry = architecture
    xml, metrics = narrative.overview_xml(spec,registry)
    assert metrics['node_overlaps'] == metrics['connector_node_intersections'] == 0
    assert metrics['connector_crossings'] == metrics['out_of_bounds'] == 0
    assert metrics['containment_violations'] == 0
    root = ET.fromstring(xml)
    for node in spec.nodes:
        assert root.find(f".//mxCell[@id='{node.id}']") is not None
    coverage = json.loads(root.find('.//mxGraphModel').get('edgeCoverage'))
    assert coverage == narrative.projection(spec,plan)
    positions, boxes, parents, _, _ = narrative.geometry(spec,plan)
    assert parents['user'] == 'root' and parents['cdn'] == 'cloud'
    assert parents['kms'] == 'region' and parents['docs'] == 'extract'
    assert parents['extract'] == 'region'


def test_do_not_flatten_physical_deployment_or_multiple_accounts(architecture):
    spec, _, _ = architecture
    assert narrative.eligible(spec)
    assert not narrative.eligible(replace(spec,nodes=(replace(spec.nodes[0],scope='vpc',subnet='private'),)+spec.nodes[1:]))
    for field in ('account','region'):
        # An unspecified placeholder plus one real owner is one deployment;
        # two explicitly different owners must never be flattened together.
        assert narrative.eligible(replace(spec,nodes=(replace(spec.nodes[0],**{field:'named'}),)+spec.nodes[1:]))
        multiple=(replace(spec.nodes[0],**{field:'first'}),replace(spec.nodes[1],**{field:'second'}))+spec.nodes[2:]
        assert not narrative.eligible(replace(spec,nodes=multiple))


def test_explicit_functional_deployment_view_preserves_scope_and_separate_exits(architecture):
    spec, plan, registry = architecture
    nodes = tuple(replace(n,scope='vpc',subnet='private',availability_zone='az_a',vpc='Application VPC')
                  if n.id=='worker' else n for n in spec.nodes)
    nodes += (Node('target2','Second integration','external',0,scope='external'),
              Node('target3','Third integration','external',0,scope='external'))
    spec = replace(spec,nodes=nodes,edges=spec.edges+(Edge('worker','target2'),Edge('worker','target3')),
        architecture_plan={**spec.architecture_plan,'functional_deployment_view':True})
    assert narrative.eligible(spec)
    xml,metrics = narrative.overview_xml(spec,registry)
    assert metrics['node_overlaps'] == metrics['connector_node_intersections'] == 0
    assert metrics['containment_violations'] == metrics['out_of_bounds'] == 0
    assert 'Private' in xml and 'Availability Zone' in xml
    assert metrics['physical_boundaries']
    cells = {c.get('id'):c for c in ET.fromstring(xml).findall('.//mxCell')}
    assert cells['worker'].get('parent') == 'vpc_0_az_0_subnet_0'
    assert cells['vpc_0_az_0_subnet_0'].get('parent') == 'vpc_0_az_0'
    assert cells['vpc_0_az_0'].get('parent') == 'vpc_0'
    functional_parent = cells['vpc_0'].get('parent')
    assert cells[functional_parent].get('parent') == 'region'
    external_parent=cells['external'].get('parent')
    assert all(cells[key].get('parent') == external_parent for key in ('external','target2','target3'))
    assert cells[external_parent].get('parent') == '1'
    assert cells[external_parent].get('value') == 'External systems'
    assert next(n for n in spec.nodes if n.id=='worker').vpc == 'Application VPC'


def test_managed_overview_uses_fixed_boundary_names_and_badges(architecture):
    spec,_,registry=architecture
    spec=replace(spec,nodes=tuple(replace(n,region='eu-west-2') if n.scope=='regional' else n for n in spec.nodes))
    xml,_=narrative.overview_xml(spec,registry)
    cells={c.get('id'):c for c in ET.fromstring(xml).findall('.//mxCell')}
    assert cells['region'].get('value')=='Region'
    assert cells['cloud'].get('value')=='AWS Cloud'
    assert all('shape=image' in cells['badge_'+k].get('style') for k in ('cloud','region'))
    assert next(n for n in spec.nodes if n.id=='worker').region=='eu-west-2'


def test_physical_boundaries_preserve_all_az_subnet_and_managed_ownership(architecture):
    from app.diagram.narrative_boundaries import geometry
    spec, _, _ = architecture
    worker = next(n for n in spec.nodes if n.id=='worker')
    nodes = tuple(n for n in spec.nodes if n.id!='worker') + tuple(
        replace(worker,id=f'w{i}',scope='az',vpc='App VPC',availability_zone=f'az_{i}',
                subnet='public' if i==0 else 'private') for i in range(3))
    nodes += (replace(worker,id='unassigned_az',scope='vpc',vpc='Other VPC',subnet='private'),)
    spec = replace(spec,nodes=nodes,edges=(),architecture_plan={**spec.architecture_plan,'functional_deployment_view':True})
    pos,boxes,parents,_,_,captions,kinds = geometry(spec)
    assert set(pos) == {n.id for n in nodes}
    assert len([k for k in kinds.values() if k=='vpc']) == 2
    assert len([k for k in kinds.values() if k=='az']) == 3
    for i in range(3):
        assert parents[f'w{i}'] == f'vpc_0_az_{i}_subnet_0'
    assert kinds[parents['w0']] == 'public' and kinds[parents['w1']] == 'private'
    assert parents['docs'] == 'region' and parents['cdn'] == 'account'
    assert parents['user'] == 'root'
    for key,rect in {**boxes,**pos}.items():
        if parents[key] in boxes:
            x,y,w,h=rect; px,py,pw,ph=boxes[parents[key]]
            assert px<=x and py<=y and x+w<=px+pw and y+h<=py+ph


def test_physical_projection_preserves_directed_path_provenance(architecture):
    from app.diagram.narrative_boundaries import projection, workload_owners
    spec, _, _ = architecture
    nodes=(Node('a','App A','service',0,scope='az',vpc='App',availability_zone='az_a',subnet='private'),
           Node('b','App B','service',0,scope='az',vpc='App',availability_zone='az_b',subnet='private'),
           Node('entry','Load balancer','service',0,scope='vpc',vpc='App'),
           Node('endpoint','S3 Gateway Endpoint','service',0,scope='vpc',vpc='App'),
           Node('s3','Media','service',0,scope='regional'))
    spec=replace(spec,nodes=nodes,edges=(Edge('entry','a'),Edge('entry','b'),
        Edge('a','endpoint','Read media'),Edge('b','endpoint','Read media'),Edge('endpoint','s3')))
    links,covered=projection(spec); owners=workload_owners(spec)
    assert len(links)==2 and covered==list(range(5))
    for item in links:
        for indices in item['paths']:
            path=[spec.edges[i] for i in indices]
            assert all(a.target==b.source for a,b in zip(path,path[1:]))
            assert item['edge'].source==owners.get(path[0].source,path[0].source)
            assert item['edge'].target==owners.get(path[-1].target,path[-1].target)


def test_logical_and_physical_applications_can_have_a_shared_data_tier(architecture):
    spec, plan, _ = architecture
    spec = replace(spec,nodes=tuple(replace(n,placement_role='data') if n.id in {'cases','audit'} else n for n in spec.nodes))
    plan = copy.deepcopy(plan)
    plan['groups'][1]['rows'] = [['worker','workflow']]
    plan['groups'].append({'id':'data','label':'Shared data tier','rows':[['cases','audit']]})
    assert narrative.validate(plan,spec)['groups'] == plan['groups']
    physical = replace(spec,architecture_plan={**spec.architecture_plan,'functional_deployment_view':True})
    assert narrative.validate(plan,physical)['groups'] == plan['groups']


def test_multiple_external_roles_get_distinct_clear_entry_lanes(architecture):
    spec, plan, registry = architecture
    extra = Node('user2','Another user','actor',0,scope='external')
    crowded = replace(spec,nodes=spec.nodes+(extra,),edges=spec.edges+(Edge('user2','api'),))
    positions,_,_,_,_ = narrative.geometry(crowded,plan)
    assert positions['user'] != positions['user2']
    _, metrics = narrative.overview_xml(crowded,registry)
    assert metrics['node_overlaps'] == metrics['connector_node_intersections'] == 0


def test_actors_and_their_external_channels_have_distinct_entry_rows(architecture):
    spec, plan, registry = architecture
    channel = Node('channel','Existing web app','external',0,scope='external')
    spec = replace(spec,nodes=spec.nodes+(channel,),
        edges=spec.edges+(Edge('user','channel'),Edge('channel','api')))
    positions,boxes,parents,_,_ = narrative.geometry(spec,plan)
    assert positions['user'][1]+positions['user'][3] < positions['channel'][1]
    assert positions['channel'][1]+positions['channel'][3] < boxes['cloud'][1]
    assert parents['channel'] == 'root'
    _,metrics = narrative.overview_xml(spec,registry)
    assert metrics['node_overlaps'] == metrics['connector_node_intersections'] == 0


def test_busy_interfaces_keep_entry_and_integration_routes_separate():
    raw = json.loads((Path(__file__).parent/'fixtures/multichannel_narrative.json').read_text(encoding='utf-8-sig'))
    spec = DiagramSpec('Multichannel support',
        tuple(Node(**n, layer=0) for n in raw['nodes']),
        tuple(Edge(**e) for e in raw['edges']), architecture_plan=raw['architecture_plan'])
    plan = spec.architecture_plan['narrative_view']
    registry = AwsIconRegistry(Path(__file__).parents[1]/'assets')
    before = copy.deepcopy(spec)
    positions,boxes,parents,width,height = narrative.geometry(spec,plan)
    cloud_bottom = boxes['cloud'][1]+boxes['cloud'][3]
    # Reply-capable customer channels stay with their users, while incoming
    # callbacks from business systems do not drag those systems into the header.
    assert positions['bsp'][1]+positions['bsp'][3] < boxes['cloud'][1]
    assert abs(positions['admins'][0]-positions['customers'][0]) >= 260
    for key in ('crm','notif','idp','mixpanel','hybris','otp'):
        assert positions[key][1] > cloud_bottom and parents[key] == 'root'
    for key in ('cloudtrail','cloudwatch','kms','secrets','sns'):
        assert parents[key] == 'region'
        assert positions[key][1]+positions[key][3] < boxes['g1'][1]
    xml,metrics = narrative.overview_xml(spec,registry)
    assert metrics['connector_crossings'] <= 3
    assert metrics['node_overlaps'] == metrics['connector_node_intersections'] == 0
    assert metrics['ambiguous_connector_pairs'] == metrics['out_of_bounds'] == 0
    assert spec == before
    projected = narrative.projection(spec,plan)
    covered = projected['internal']+projected['shared']+[i for link in projected['links'] for i in link['edge_indices']]
    assert sorted(covered) == list(range(len(spec.edges)))
    # Every selected AWS/user icon must actually embed, not silently turn into
    # an anonymous rectangle; third-party systems retain neutral external cards.
    cells = {cell.get('id'):cell for cell in ET.fromstring(xml).iter('mxCell')}
    for node in spec.nodes:
        if node.icon_key:
            assert 'shape=image' in cells[node.id].get('style','')
        elif node.scope == 'external':
            assert 'spacing=10;' in cells[node.id].get('style','')
    assert 'badge_cloud' in cells and 'badge_region' in cells


def test_local_row_search_preserves_semantics_and_does_not_worsen_quality(architecture):
    spec, _, registry = architecture
    result = narrative.improve_rows(spec,registry,budget=2)
    assert result.nodes == spec.nodes and result.edges == spec.edges
    audit = result.architecture_plan['narrative_row_search']
    assert audit['after'] <= audit['before']
    assert narrative.projection(result,result.architecture_plan['narrative_view'])['owner'] == narrative.projection(
        spec,spec.architecture_plan['narrative_view'])['owner']


def test_two_page_export_retains_original_detail_graph(architecture, monkeypatch):
    from app.diagram import hybrid, drawio_renderer
    spec, _, registry = architecture
    def forbidden_layout(*a, **k):
        raise AssertionError('Connection register must not invoke dense graph routing')
    monkeypatch.setattr(hybrid,'layout',forbidden_layout)
    monkeypatch.setattr(drawio_renderer,'render_drawio',lambda xml,**k: (b'png',xml,{}))
    _, xml, details = narrative.render(spec,SimpleNamespace(),registry)
    pages = ET.fromstring(xml).findall('diagram')
    assert [p.get('name') for p in pages] == ['Solution overview','Connection detail']
    actual = [(e.get('sourceNode'),e.get('targetNode')) for e in pages[1].findall('.//mxCell') if e.get('sourceNode')]
    assert actual == [(e.source,e.target) for e in spec.edges]
    assert {e.get('nodeId') for e in pages[1].findall('.//mxCell') if e.get('nodeId')} == {n.id for n in spec.nodes}
    assert details['overview_metrics']['nodes'] == len(spec.nodes)


def test_production_asset_uses_overview_and_preserves_spec(architecture, monkeypatch):
    spec, _, registry = architecture
    monkeypatch.setenv('ARCHITECTURE_DIAGRAM_ENGINE','hybrid_drawio')
    monkeypatch.setattr(narrative,'render',lambda *a,**k: (b'png','<mxfile/>',{'overview_metrics':{'nodes':16}}))
    service = DiagramService.__new__(DiagramService)
    service.config = SimpleNamespace()
    service.icon_registry = registry
    result = service._asset('architecture_overview','Solution Architecture',spec,{},False)
    assert result['layout_engine'] == 'narrative_drawio'
    assert result['spec'] == spec.as_dict()
    assert result['layout_metrics']['nodes'] == len(spec.nodes)


def test_review_sees_image_and_logs_failure_without_losing_it(architecture, monkeypatch):
    from app.agents import architecture_reviewer_agent as reviewer
    spec, _, _ = architecture
    monkeypatch.setattr(reviewer,'image_for_review',lambda raw: raw)
    monkeypatch.setattr(reviewer,'_audit',lambda *a: None)
    monkeypatch.setattr(reviewer,'_call',lambda *a,**k: '{"issues":[]}')
    monkeypatch.delenv('ARCHITECTURE_VISION_REVIEW_ENABLED', raising=False)
    asset = {'image_base64':'cG5n','layout_metrics':{}}
    result = narrative.review(None,asset,spec,{})
    assert result['vision_review']['image_reviewed']
    monkeypatch.setattr(reviewer,'_call',lambda *a,**k: 'broken')
    result = narrative.review(None,asset,spec,{})
    assert result['vision_review']['status'] == 'unavailable'
    assert result['image_base64'] == asset['image_base64']


def test_generation_uses_overview_review_not_incompatible_grid_repair(architecture, monkeypatch):
    from app.agents import architecture_reviewer_agent
    from app.diagram import hybrid
    from app.core import bedrock_llm
    spec, _, registry = architecture
    service = DiagramService.__new__(DiagramService)
    service.config = SimpleNamespace()
    service.icon_registry = registry
    service.bedrock = object()
    service._generate_specs = lambda *a: ([('architecture_overview','Solution Architecture',spec)],False)
    monkeypatch.setenv('ARCHITECTURE_DIAGRAM_ENGINE','hybrid_drawio')
    monkeypatch.setattr(bedrock_llm,'_save_raw_output',lambda *a: None)
    monkeypatch.setattr(narrative,'render',lambda *a,**k: (b'png','<mxfile/>',{'overview_metrics':{}}))
    monkeypatch.setattr(narrative,'review',lambda svc,asset,*a: {**asset,'vision_review':{'status':'reviewed','issues':[]}})
    def forbidden(*a,**k):
        raise AssertionError('Overview cannot be repaired by the old full-graph grid contract')
    monkeypatch.setattr(hybrid,'prepare',forbidden)
    monkeypatch.setattr(architecture_reviewer_agent,'review_architecture',forbidden)
    assets = service._generate_assets({}, {}, '')
    assert len(assets) == 1
    assert assets[0]['status'] == 'ready'
    assert assets[0]['layout_engine'] == 'narrative_drawio'
    # A cosmetic retry must retain the accepted view even when the planning
    # stage has spent its model-call allowance.
    service._generate_specs = forbidden
    retried = service._generate_assets({'_architecture_retry_spec':spec.as_dict()}, {}, '')
    assert retried[0]['layout_engine'] == 'narrative_drawio'
    assert retried[0]['image_base64']


def test_visual_findings_and_overview_fallback_are_not_silent():
    from app.diagram.reliability import publication_issues
    assert publication_issues({'image_base64':'png','layout_engine':'narrative_drawio',
        'vision_review':{'issues':[{'kind':'visual','description':'Overlap'}]}})
    assert publication_issues({'image_base64':'png','spec':{'architecture_plan':{
        'narrative_diagnostic':'Invalid grouping'}}})


def test_actor_entry_routes_around_global_service(architecture, monkeypatch):
    spec, plan, registry = architecture
    original = narrative.geometry
    def obstructed_geometry(*args):
        pos, boxes, parents, width, height = original(*args)
        # The old fixed actor entry descended on the right of the first group.
        # A global identity service can legitimately occupy that column.
        x,y,w,h = boxes['front']
        pos['iam'] = (x+w-78, 135, 120, 95)
        return pos, boxes, parents, width, height
    monkeypatch.setattr(narrative, 'geometry', obstructed_geometry)
    xml, metrics = narrative.overview_xml(spec, registry)
    assert metrics['connector_node_intersections'] == 0
    assert metrics['out_of_bounds'] == 0
    assert 'overview_link_' in xml


def test_dense_runtime_routes_to_every_dependency_without_floating_endpoints():
    raw=json.loads((Path(__file__).parent/'fixtures/dense_logical_routing.json').read_text())
    spec=DiagramSpec(raw['title'],tuple(Node(**n) for n in raw['nodes']),
        tuple(Edge(**e) for e in raw['edges']),architecture_plan=raw['architecture_plan'])
    before=copy.deepcopy(spec)
    registry=AwsIconRegistry(Path(__file__).parents[1]/'assets')
    xml,metrics=narrative.overview_xml(spec,registry)
    assert metrics['original_edges']==36
    assert metrics['node_overlaps']==metrics['connector_node_intersections']==0
    assert metrics['ambiguous_connector_pairs']==metrics['out_of_bounds']==0
    assert metrics['long_connector_count']==0
    assert spec==before
    positions,boxes,*_=narrative.geometry(spec,spec.architecture_plan['narrative_view'])
    bounds={**positions,**boxes}
    root=ET.fromstring(xml)
    assert root.find(".//mxCell[@id='card_lambda']") is not None
    assert root.find(".//mxCell[@id='card_appconfig']") is not None
    for edge in root.findall(".//mxCell[@edge='1']"):
        for attr,point_name in [('overviewSource','sourcePoint'),('overviewTarget','targetPoint')]:
            point=edge.find("mxGeometry/mxPoint[@as='"+point_name+"']")
            x,y,w,h=bounds[edge.get(attr)]
            assert x<=float(point.get('x'))<=x+w
            assert y<=float(point.get('y'))<=y+h
