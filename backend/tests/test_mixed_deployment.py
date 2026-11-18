from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree as ET
from app.diagram.service import Node,Edge,DiagramSpec
from app.diagram.aws_icons import AwsIconRegistry
from app.diagram import mixed_deployment as mixed
from app.diagram.narrative_boundaries import overview_xml


def architecture():
    def node(k,role='compute',scope='managed',**kw):return Node(k,k,'service',0,scope=scope,placement_role=role,**kw)
    nodes=[node('api','entry'),node('auth','security',icon_key='aws.service.security-identity.amazon-cognito'),node('web','data'),
           node('worker',scope='az',vpc='Private VPC',availability_zone='az_a',subnet='private'),
           node('endpoint','network','az',vpc='Private VPC',availability_zone='az_a',subnet='private'),
           node('gateway','network','vpc',vpc='Private VPC'),node('records','data'),
           node('documents','data'),node('trigger','integration'),node('workflow','integration'),node('ocr'),node('ai'),
           node('cdn','entry','global'),node('reviewer','external','external'),node('custodian','external','external'),node('export','external','external')]
    edges=[Edge(a,b,label) for a,b,label in [('reviewer','cdn','Open'),('cdn','web','Assets'),('reviewer','auth','Sign in'),
        ('reviewer','api','API'),('api','auth','Validate'),('api','worker','Invoke'),('custodian','documents','Upload'),
        ('documents','trigger','Event'),('trigger','workflow','Start'),('workflow','worker','Run'),('worker','endpoint','Private call'),
        ('endpoint','ai','Extract'),('endpoint','ocr','Results'),('worker','gateway','Store'),('gateway','records','State'),('documents','export','Export')]]
    groups=[{'id':'extract','label':'Extract documents','rows':[['documents','trigger'],['workflow','ocr'],['ai']]},
            {'id':'process','label':'Validate and store','rows':[['worker','records'],['endpoint','gateway']]},
            {'id':'review','label':'Review workbench','rows':[['api','auth'],['web']]}]
    return DiagramSpec('Mixed application',tuple(nodes),tuple(edges),architecture_plan={
        'functional_deployment_view':True,'narrative_view':{'groups':groups,'support':[],'roles':{},'links':[]}})


def test_mixed_case_preserves_scopes_and_uses_functional_columns():
    spec=architecture();assert mixed.enabled(spec)
    p,b,parents,w,h,_,kinds=mixed.geometry(spec)
    assert set(p)=={n.id for n in spec.nodes}
    assert b['review'][0]<b['process'][0]<b['extract'][0]
    assert h/w<1.2
    def chain(k):
        result=[]
        while k in parents:k=parents[k];result.append(k)
        return result
    assert kinds[parents['worker']]=='private'
    assert 'vpc_0' in chain('worker') and 'vpc_0' not in chain('records')
    assert 'vpc_0' not in chain('ocr') and 'vpc_0' not in chain('ai')


def test_story_icons_keep_mixed_boundaries_and_complete_resource_inventory():
    spec=architecture()
    spec=replace(spec,architecture_plan={**spec.architecture_plan,'story_overview':True})
    registry=AwsIconRegistry(Path(__file__).parents[1]/'assets')
    xml,metrics=overview_xml(spec,registry)
    cells={c.get('id'):c for c in ET.fromstring(xml).findall('.//mxCell')}
    assert {n.id for n in spec.nodes}<=set(cells)
    assert metrics['node_overlaps']==metrics['containment_violations']==metrics['out_of_bounds']==0
    icon=cells['icon_auth'].find('mxGeometry')
    label=cells['label_auth'].find('mxGeometry')
    assert float(icon.get('width'))==64
    assert float(label.get('y'))>float(icon.get('y'))+float(icon.get('height'))


def test_interfaces_cover_every_original_edge_and_no_fake_reverse():
    spec=architecture();links,indices=mixed.projection(spec)
    assert indices==list(range(len(spec.edges)))
    assert sorted(i for l in links for path in l['paths'] for i in path)==indices
    between=next(l for l in links if {l['edge'].source,l['edge'].target}=={'process','extract'})
    assert between['both']
    inbound=next(l for l in links if l['edge'].source=='custodian')
    assert not inbound['both']


def test_parallel_and_reverse_service_edges_share_a_wire_without_losing_evidence():
    spec=architecture()
    spec=replace(spec,edges=spec.edges+(Edge('worker','endpoint','Second call'),
                                       Edge('endpoint','worker','Reply')))
    links,indices=mixed.projection(spec)
    pair=[l for l in links if {l['edge'].source,l['edge'].target}=={'worker','endpoint'}]
    assert len(pair)==1 and pair[0]['both']
    assert len(pair[0]['paths'])==3
    assert sorted(i for l in links for path in l['paths'] for i in path)==list(range(len(spec.edges)))
    # The intermediate endpoint and its downstream dependency stay explicit.
    assert any({l['edge'].source,l['edge'].target}=={'process','extract'} for l in links)


def audience_architecture():
    spec=architecture()
    nodes=tuple(replace(n,kind='actor') if n.id=='reviewer' else n for n in spec.nodes)
    return replace(spec,nodes=nodes+(Node('admin','Admin','actor',0,scope='external'),),
        edges=spec.edges+(Edge('admin','cdn','Console'),Edge('admin','auth','Sign in'),Edge('admin','api','Admin API')))


def test_audience_bundles_only_matching_directed_destinations():
    spec=audience_architecture()
    groups=mixed.audiences(spec)
    assert list(groups.values())==[['reviewer','admin']]
    links,indices=mixed.projection(spec)
    audience=next(iter(groups))
    assert len([l for l in links if l['edge'].source==audience])==2
    assert sorted(i for l in links for path in l['paths'] for i in path)==list(range(len(spec.edges)))
    different=replace(spec,edges=spec.edges+(Edge('admin','documents','Upload'),))
    assert mixed.audiences(different)=={}
    responding=replace(spec,edges=spec.edges+(Edge('api','admin','Push'),))
    assert mixed.audiences(responding)=={}


def test_audience_keeps_actor_cards_and_routes_without_obstruction():
    spec=audience_architecture()
    positions,boxes,parents,*_=mixed.geometry(spec)
    group=next(iter(mixed.audiences(spec)))
    assert parents['reviewer']==parents['admin']==group
    assert set(positions)=={n.id for n in spec.nodes}
    registry=AwsIconRegistry(Path(__file__).parents[1]/'assets')
    xml,metrics=overview_xml(spec,registry)
    assert metrics['node_overlaps']==metrics['connector_node_intersections']==metrics['out_of_bounds']==0
    assert metrics['visible_edge_indices']==list(range(len(spec.edges)))
    assert metrics['audience_groups']=={group:['reviewer','admin']}
    from app.diagram.connection_detail import page
    detail=page(spec)
    assert len(detail.findall('.//mxCell[@sourceNode]'))==len(spec.edges)
    cells={c.get('id'):c for c in ET.fromstring(xml).findall('.//mxCell')}
    assert cells[group].get('value')=='User access'


def test_external_outputs_share_interfaces_only_for_the_same_calling_subsystems():
    spec=architecture()
    spec=replace(spec,nodes=spec.nodes+(Node('out2','Second export','external',0,scope='external'),),
                 edges=spec.edges+(Edge('documents','out2','Export second'),))
    groups=mixed.interface_groups(spec)
    key=next(k for k in groups if k.startswith('__integrations_'))
    assert set(groups[key])=={'export','out2'}
    links,indices=mixed.projection(spec)
    assert len([l for l in links if l['edge'].target==key])==1
    assert indices==list(range(len(spec.edges)))
    changed=replace(spec,edges=spec.edges+(Edge('worker','out2','Other API'),))
    assert mixed.interface_groups(changed)=={}
    changed=replace(spec,edges=spec.edges+(Edge('out2','api','Callback'),))
    assert mixed.interface_groups(changed)=={}


def test_xml_keeps_physical_membership_and_all_edge_evidence():
    spec=architecture();registry=AwsIconRegistry(Path(__file__).parents[1]/'assets')
    spec.architecture_plan['narrative_view']['groups'][1]['label']='Validate & store'
    xml,metrics=overview_xml(spec,registry)
    assert metrics['node_overlaps']==metrics['containment_violations']==metrics['out_of_bounds']==0
    assert metrics['connector_node_intersections']==0
    cells=ET.fromstring(xml).findall('.//mxCell')
    assert any(c.get('id')=='vpc_0' for c in cells)
    assert all(c.get('originalEdgePaths') for c in cells if c.get('edge'))
    assert next(c for c in cells if c.get('id')=='process').get('value')=='Validate & store'
    by_id={c.get('id'):c for c in cells}
    for key,label in {'cloud':'AWS Cloud','account':'AWS Account','region':'Region','vpc_0':'VPC',
                      'vpc_0_az_0':'Availability Zone','vpc_0_az_0_subnet_0':'Private subnet'}.items():
        assert by_id[key].get('value')==label
        assert 'shape=image' in by_id['badge_'+key].get('style')


def test_vpc_split_across_model_groups_keeps_one_physical_owner():
    spec=architecture();plan=spec.architecture_plan['narrative_view']
    plan['groups'][1]['rows'][1]=['gateway']
    plan['groups'][0]['rows'][2].append('endpoint')
    p,b,parents,*_=mixed.geometry(spec)
    owner,_,_=mixed.ownership(spec)
    assert owner['endpoint']==owner['worker']
    links,indices=mixed.projection(spec)
    assert any(l['edge'].source=='worker' and l['edge'].target=='endpoint' for l in links)


def test_global_entry_peers_do_not_overlap_above_the_same_group():
    spec=architecture()
    peer=replace(next(n for n in spec.nodes if n.id=='cdn'),id='dns')
    spec=replace(spec,nodes=spec.nodes+(peer,),edges=spec.edges+(Edge('dns','api'),))
    p,*_=mixed.geometry(spec)
    a,b=p['cdn'],p['dns']
    assert a[0]+a[2]<=b[0] or b[0]+b[2]<=a[0] or a[1]+a[3]<=b[1] or b[1]+b[3]<=a[1]


def test_shared_static_origin_does_not_displace_api_runtime_sequence():
    spec=architecture()
    spec=replace(spec,edges=tuple(e for e in spec.edges if e.source!='cdn')+(Edge('cdn','documents'),))
    _,boxes,*_=mixed.geometry(spec)
    assert boxes['review'][0]<boxes['process'][0]<boxes['extract'][0]


def test_external_export_route_avoids_shared_control_rail():
    from app.diagram.review import hits_box
    spec=architecture()
    monitor=Node('monitor','Monitoring','service',0,scope='regional',placement_role='operations')
    spec=replace(spec,nodes=spec.nodes+(monitor,))
    spec.architecture_plan['narrative_view']['support']=['monitor']
    registry=AwsIconRegistry(Path(__file__).parents[1]/'assets')
    xml,_=overview_xml(spec,registry)
    rail=mixed.geometry(spec)[1]['regional_controls']
    edge=next(c for c in ET.fromstring(xml).findall('.//mxCell') if c.get('targetNode')=='export')
    geo=edge.find('mxGeometry')
    points=[geo.find("mxPoint[@as='sourcePoint']"),*geo.findall('Array/mxPoint'),geo.find("mxPoint[@as='targetPoint']")]
    path=[(float(p.get('x')),float(p.get('y'))) for p in points]
    assert not any(hits_box(a,b,rail) for a,b in zip(path,path[1:]))
