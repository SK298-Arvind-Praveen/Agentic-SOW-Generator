from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET

from app.diagram.service import DiagramSpec,Node,Edge,DiagramService
from app.diagram.aws_icons import AwsIconRegistry
from app.diagram import tiered_deployment as tiers
from app.diagram.narrative_boundaries import projection,geometry,overview_xml


def spec():
    nodes=[Node('entry','ALB','service',0,scope='vpc',vpc='App',placement_role='entry')]
    for az in ('a','b'):
        for name,subnet,role in [('nat','public','network'),('app','private','compute'),('db','isolated','data')]:
            nodes.append(Node(name+az,name,'service',0,scope='az',vpc='App',availability_zone=az,
                              subnet=subnet,placement_role=role))
    nodes += [Node('user','Customer','actor',0,scope='external'),Node('sink','HTTPS destination','external',0,scope='external')]
    edges=[Edge('user','entry','HTTPS'),Edge('entry','appa','Requests'),Edge('entry','appb','Requests'),
           Edge('appa','dba','SQL'),Edge('appb','dba','SQL'),Edge('dba','dbb','Sync replication'),
           Edge('appa','nata','Egress'),Edge('appb','natb','Egress'),Edge('appa','sink','Send events')]
    return DiagramSpec('Any tiered application',tuple(nodes),tuple(edges),architecture_plan={
        'functional_deployment_view':True,'narrative_view':{'groups':[],'roles':{}}})


def test_physical_tiers_follow_request_order_and_keep_true_owners():
    value=spec();p,b,parents,w,h,labels,kinds=geometry(value)
    assert tiers.enabled(value)
    for az in ('a','b'):
        assert p['nat'+az][1]<p['app'+az][1]<p['db'+az][1]
        assert kinds[parents['nat'+az]]=='public'
        assert kinds[parents['app'+az]]=='private'
        assert kinds[parents['db'+az]]=='isolated'
    assert p['appa'][1]==p['appb'][1] and p['dba'][1]==p['dbb'][1]
    assert parents['sink']=='root' and p['sink'][0]>b['cloud'][0]+b['cloud'][2]
    assert not any('workloads' in k for k in b)


def test_request_database_replication_and_egress_edges_never_disappear_into_one_group():
    value=spec();links,indices=projection(value)
    assert [item['edge'] for item in links]==list(value.edges)
    assert indices==list(range(len(value.edges)))
    assert all(item['paths']==[[i]] for i,item in enumerate(links))


def test_story_projection_uses_representative_replica_edges_without_deleting_graph():
    value=spec();original=value.edges
    value=replace(value,architecture_plan={**value.architecture_plan,'story_overview':True})
    links,indices=projection(value)
    assert value.edges==original
    assert all(link['edge']==original[link['paths'][0][0]] for link in links)
    assert any(e.source=='dba' and e.target=='dbb' for e in (l['edge'] for l in links))
    assert len({e.target for e in (l['edge'] for l in links) if e.source=='entry'})==2


def test_no_extra_subnets_or_standby_are_invented_for_a_shared_database():
    value=spec()
    nodes=tuple(n for n in value.nodes if n.id not in {'dba','dbb'})+(
        Node('db','RDS Multi-AZ','service',0,scope='vpc',vpc='App',placement_role='data'),)
    value=replace(value,nodes=nodes,edges=())
    p,b,parents,*_=geometry(value)
    assert parents['db']=='vpc_0'
    assert set(p)=={n.id for n in nodes}
    assert not any('isolated' in k for k in b)


def test_regional_dependencies_stay_outside_vpc():
    value=spec()
    value=replace(value,nodes=value.nodes+(Node('s3','Reports','service',0,scope='regional',placement_role='data'),),
                  edges=value.edges+(Edge('appa','s3','Write reports'),))
    p,b,parents,w,h,*_=geometry(value)
    assert parents['s3']=='region'
    for key,(x,y,bw,bh) in {**b,**p}.items():
        if parents[key] in b:
            px,py,pw,ph=b[parents[key]]
            assert px<=x and py<=y and x+bw<=px+pw and y+bh<=py+ph


def test_tiered_xml_preserves_resource_edges_and_has_no_node_collisions():
    registry=AwsIconRegistry(Path(__file__).parents[1]/'assets')
    value=spec();xml,metrics=overview_xml(value,registry)
    assert metrics['node_overlaps']==metrics['containment_violations']==metrics['out_of_bounds']==0
    cells=ET.fromstring(xml).findall('.//mxCell')
    pairs={(c.get('sourceNode'),c.get('targetNode')) for c in cells if c.get('edge')}
    assert {('appa','dba'),('appb','dba'),('dba','dbb')}<=pairs


def test_specific_alb_icon_is_not_replaced_by_generic_internet_word():
    registry=AwsIconRegistry(Path(__file__).parents[1]/'assets')
    candidate=registry.candidate('Application Load Balancer','proposed','ingress')
    svc=DiagramService.__new__(DiagramService);svc.icon_registry=registry;svc.config=SimpleNamespace()
    for label in ('Internet ALB','Internet-facing ALB','Public ALB','Internal ALB'):
        value=svc._enrich_diagram({'nodes':[{'id':'alb','label':label,'kind':'service',
            'icon_key':candidate.key,'scope':'vpc'}],'edges':[]},'architecture_overview',{candidate.key:candidate})
        assert value['nodes'][0]['icon_key']==candidate.key


def test_dependency_validation_ignores_explicit_omissions_but_keeps_real_requirements():
    from app.diagram.service_design import unlisted_dependencies
    omitted={'services':[],'capabilities':[{'implementation':'AWS Backup is not added. S3 and CloudFront are not deployed.'}],
             'workflows':[]}
    assert unlisted_dependencies(omitted)==[]
    omitted['capabilities'].append({'implementation':'Use Amazon S3 to store reports.'})
    assert any('Storage' in n or 'S3' in n for n in unlisted_dependencies(omitted))


def test_migration_ingress_alignment_keeps_external_cards_apart():
    value=spec()
    value=replace(value,nodes=value.nodes+(
        Node('dms','DMS','service',0,scope='az',vpc='App',availability_zone='a',subnet='private',placement_role='integration'),
        Node('source','Source database','external',0,scope='external'),
        Node('ops','Operations','actor',0,scope='external'),
        Node('repo','Repository','external',0,scope='external'),
    ),edges=value.edges+(Edge('source','dms'),Edge('dms','dba')))
    positions,*_=geometry(value)
    top=[positions[n.id] for n in value.nodes if n.scope=='external' and positions[n.id][1]==15]
    for i,(x,y,w,h) in enumerate(top):
        for xx,yy,ww,hh in top[i+1:]:
            assert x+w<=xx or xx+ww<=x
    assert positions['user'][0]==positions['entry'][0]
