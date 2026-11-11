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


def test_interfaces_cover_every_original_edge_and_no_fake_reverse():
    spec=architecture();links,indices=mixed.projection(spec)
    assert indices==list(range(len(spec.edges)))
    assert sorted(i for l in links for path in l['paths'] for i in path)==indices
    between=next(l for l in links if {l['edge'].source,l['edge'].target}=={'process','extract'})
    assert between['both']
    inbound=next(l for l in links if l['edge'].source=='custodian')
    assert not inbound['both']


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
