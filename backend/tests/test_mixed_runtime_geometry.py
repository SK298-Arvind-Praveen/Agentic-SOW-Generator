from dataclasses import replace

from app.diagram.compact_mixed import geometry
from app.diagram.service import DiagramSpec, Node, Edge


def application():
    def n(key,role='data',scope='managed',**kw):
        return Node(key,key,'actor' if role=='actor' else 'service',0,scope=scope,placement_role=role,**kw)
    nodes=[n('api','entry'),n('auth','entry'),n('web'),n('queue','integration'),n('timer','integration'),n('state'),
        n('worker','compute','vpc',vpc='App'),n('search','data','vpc',vpc='App'),
        n('igw','network','vpc',vpc='App'),n('endpoint','network','vpc',vpc='App'),
        n('object_endpoint','network','vpc',vpc='App'),n('model_endpoint','network','vpc',vpc='App'),
        n('n1','network','az',vpc='App',availability_zone='a',subnet='public'),
        n('n2','network','az',vpc='App',availability_zone='b',subnet='public'),
        n('model','compute'),n('knowledge'),n('archive'),n('user','actor','external'),
        n('channel','external','external'),n('source','external','external'),n('crm','external','external'),
        n('enterprise_api','external','external'),n('leaf1','external','external'),n('leaf2','external','external')]
    edges=tuple(Edge(a,b) for a,b in [('user','channel'),('channel','api'),('api','worker'),('timer','worker'),
        ('state','worker'),('worker','endpoint'),('worker','model'),('model','archive'),('source','archive'),
        ('crm','api'),('worker','crm'),('worker','enterprise_api'),('enterprise_api','leaf1'),('enterprise_api','leaf2')])
    groups=[{'id':key,'label':key,'rows':[members]} for key,members in [
        ('access',['api','auth','web']),('runtime',['queue','timer','state','worker','search','igw','endpoint','object_endpoint','model_endpoint','n1','n2']),
        ('answers',['model','knowledge']),('history',['archive'])]]
    return DiagramSpec('Mixed runtime',tuple(nodes),edges,architecture_plan={
        'functional_deployment_view':True,'story_overview':True,
        'process_story':{'steps':[{'edge_ids':[f'e{i}' for i in range(len(edges))]}]},
        'narrative_view':{'groups':groups,'roles':{},'support':[],'links':[]}})


def test_managed_runtime_peers_stay_near_compute_and_outside_vpc():
    spec=application();before=spec.as_dict()
    p,b,parents,*_=geometry(spec)
    for key in ('queue','timer','state'):
        assert parents[key]=='runtime'
        assert p[key][1]+p[key][3]<b['vpc_0'][1]
    assert parents['worker']=='vpc_0'
    assert abs(p['worker'][0]-p['endpoint'][0])<=300
    assert spec.as_dict()==before


def test_small_subsystems_fill_space_beside_the_large_network_tile():
    p,b,*_=geometry(application())
    assert b['answers'][1]<b['runtime'][1]+b['runtime'][3]
    assert b['history'][1]<b['runtime'][1]+b['runtime'][3]
    assert b['answers'][0]==b['access'][0]==b['history'][0]


def test_external_sources_and_callbacks_follow_their_owning_subsystems():
    p,b,parents,*_=geometry(application())
    assert p['user'][1]+p['user'][3]<p['channel'][1]<b['cloud'][1]
    assert p['source'][1]>=b['history'][1]
    assert abs(p['crm'][1]-b['access'][1])<b['access'][3]
    for key in ('leaf1','leaf2'):
        assert p[key][1]>b['cloud'][1], 'Downstream partners must not occupy the ingress rail'
    assert parents['source']==parents['crm']=='root'


def test_wrapped_external_groups_never_enclose_unrelated_partners():
    from itertools import combinations
    from app.diagram.mixed_deployment import geometry as mixed_geometry, interface_groups
    spec=application()
    extra=tuple(Node(key,key,'service',0,scope='external',placement_role='external')
        for key in ('leaf3','leaf4','leaf5','leaf6','leaf7','hub2','other1','other2'))
    edges=spec.edges+tuple(Edge('enterprise_api',f'leaf{i}') for i in range(3,8))
    edges+=(Edge('worker','hub2'),Edge('hub2','other1'),Edge('hub2','other2'))
    spec=replace(spec,nodes=spec.nodes+extra,edges=edges,architecture_plan={**spec.architecture_plan,
        'process_story':{'steps':[{'edge_ids':[f'e{i}' for i in range(len(edges))]}]}})
    before=spec.as_dict();p,b,parents,*_=mixed_geometry(spec)
    groups=interface_groups(spec)
    for key,members in groups.items():
        assert all(parents[member]==key for member in members)
    for a,c in combinations(groups,2):
        x,y,w,h=b[a];xx,yy,ww,hh=b[c]
        assert x+w<=xx or xx+ww<=x or y+h<=yy or yy+hh<=y
    assert spec.as_dict()==before


def test_side_interface_group_cannot_trap_an_unrelated_external_source():
    import copy
    from app.diagram.mixed_deployment import geometry as mixed_geometry, interface_groups
    spec=application();plan=copy.deepcopy(spec.architecture_plan)
    peers=tuple(Node('partner'+str(i),'Partner '+str(i),'external',0,scope='external') for i in range(4))
    extra=tuple(Node('answer'+str(i),'Answer '+str(i),'service',0,scope='managed',placement_role='data') for i in range(6))
    plan['narrative_view']['groups'][2]['rows'][0].extend(n.id for n in extra)
    edges=spec.edges+tuple(Edge('worker',n.id) for n in peers)
    plan['process_story']={'steps':[{'edge_ids':[f'e{i}' for i in range(len(edges))]}]}
    value=replace(spec,nodes=spec.nodes+peers+extra,edges=edges,architecture_plan=plan)
    p,b,parents,*_=mixed_geometry(value)
    for key,members in interface_groups(value).items():
        x,y,w,h=b[key]
        for n in value.nodes:
            if n.scope!='external' or n.id in members:continue
            xx,yy,ww,hh=p[n.id]
            assert x+w<=xx or xx+ww<=x or y+h<=yy or yy+hh<=y, (key,n.id)


def test_side_integration_blocks_keep_allocated_slots_at_shared_heights():
    from app.diagram.mixed_deployment import geometry as mixed_geometry, interface_groups

    internals = tuple(Node(key, key, 'service', 0, scope='regional') for key in ('a', 'b', 'c'))
    internals += (Node('d', 'Compute', 'service', 0, scope='vpc', vpc='App', placement_role='compute'),)
    sinks = tuple(Node(key, key, 'service', 0, scope='external')
                  for key in ('right1', 'right2', 'right3', 'right4', 'left1', 'left2'))
    edges = tuple(Edge('c' if n.id.startswith('right') else 'a', n.id) for n in sinks)
    groups = [{'id': f'group_{n.id}', 'label': n.label, 'rows': [[n.id]]} for n in internals]
    spec = DiagramSpec('Side blocks', internals + sinks, edges, architecture_plan={
        'narrative_view': {'groups': groups, 'links': []}})

    base, *_ = geometry(spec)
    positions, boxes, parents, *_ = mixed_geometry(spec)
    for group, members in interface_groups(spec).items():
        x, y, width, height = boxes[group]
        for key in members:
            px, py, pw, ph = base[key]
            assert positions[key] == (px, py + 40, pw, ph)
            assert parents[key] == group
        for key in ['cloud'] + [n.id for n in spec.nodes if n.id not in members]:
            px, py, pw, ph = boxes[key] if key == 'cloud' else positions[key]
            assert x + width <= px or px + pw <= x or y + height <= py or py + ph <= y
