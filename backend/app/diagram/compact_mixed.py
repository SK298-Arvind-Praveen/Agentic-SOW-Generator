"""Balanced functional tiles with real VPC/AZ ownership for larger mixed graphs."""
import math


def enabled(spec):
    groups = spec.architecture_plan.get('narrative_view', {}).get('groups', [])
    return len(groups) >= 4 or any(sum(map(len, g['rows'])) > 6 for g in groups)


def geometry(spec, ordering=None):
    from app.diagram.mixed_deployment import ownership
    from app.diagram.narrative_boundaries import controls
    from app.diagram.tiered_deployment import subnet_order
    nodes = {n.id:n for n in spec.nodes}
    support = controls(spec)
    owner, vpcs, vpc_owner = ownership(spec)
    groups = list(spec.architecture_plan['narrative_view']['groups'])
    # Follow the application's functional order; the planner's order breaks
    # ties between dependent subsystems. No deployment is inferred from position.
    entries = {owner[n.id] for n in spec.nodes if n.id in owner and n.placement_role == 'entry'}
    distance = {k:0 for k in entries}
    for _ in groups:
        for edge in spec.edges:
            a,b = owner.get(edge.source),owner.get(edge.target)
            if a in distance and b and a != b:
                distance[b] = min(distance.get(b,99), distance[a]+1)
    groups.sort(key=lambda g:distance.get(g['id'],99))
    pos,boxes,parents,captions,kinds = {},{},{},{},{}
    tile, gutter, columns = 640,110,3
    width = 170+columns*tile+(columns-1)*gutter
    def box(key,rect,parent,label,kind):
        boxes[key],parents[key],captions[key],kinds[key] = rect,parent,label,kind
    def put(key,x,y,parent,w=250,h=104):
        pos[key],parents[key] = (x,y,w,h),parent
    # Build each tile locally first, then pack whole tiles into rows. A VPC gets
    # two columns so AZs are parallel rather than a tall stack down one edge.
    spans = {}
    for group in groups:
        gid=group['id']
        owned_vpcs=[(v,members) for v,members in vpcs.items() if vpc_owner[v] == gid]
        span=2 if owned_vpcs else 1
        spans[gid]=span
        gw=tile*span+gutter*(span-1)
        box(gid,(0,0,gw,100),'region',group['label'],'functional')
        y=52
        for v,members in owned_vpcs:
            vk=f'vpc_{list(vpcs).index(v)}';vtop=y
            box(vk,(15,y,gw-30,100),gid,v,'vpc');y+=52
            common=[n for n in members if not n.availability_zone and not n.subnet]
            common_cols=max(1,int((gw-80)/270))
            for i,n in enumerate(common):put(n.id,40+(i%common_cols)*270,y+(i//common_cols)*140,vk,235)
            if common:y+=math.ceil(len(common)/common_cols)*140+25
            scoped=[n for n in members if n not in common]
            azs=sorted({n.availability_zone for n in scoped})
            # At most two AZ columns; additional actual AZs get another row.
            az_cols=min(2,max(1,len(azs)));azw=(gw-80-(az_cols-1)*30)/az_cols
            az_row_top=y;row_bottom=y
            for ai,az in enumerate(azs):
                if ai and ai%az_cols==0:az_row_top=row_bottom+25
                ax=30+(ai%az_cols)*(azw+30);ay=az_row_top
                ak=f'{vk}_az_{ai}'
                box(ak,(ax,ay,azw,100),vk,az or 'Availability Zone','az');ay+=48
                subnets=sorted({n.subnet for n in scoped if n.availability_zone==az},key=subnet_order)
                side_by_side=(len(subnets)==2 and all(subnets) and azw>=590 and
                    all(sum(n.availability_zone==az and n.subnet==subnet for n in scoped)==1 for subnet in subnets))
                subnet_top=ay;subnet_bottom=ay
                for si,subnet in enumerate(subnets):
                    if side_by_side:ay=subnet_top
                    sx=ax+12+(si*(azw/2) if side_by_side else 0)
                    sw=azw/2-24 if side_by_side else azw-24
                    sk=f'{ak}_subnet_{si}' if subnet else ak;sy=ay
                    if subnet:
                        box(sk,(sx,ay,sw,100),ak,subnet+' subnet',
                            {0:'public',1:'private',2:'isolated'}[subnet_order(subnet)[0]])
                        ay+=52
                    members_here=[n for n in scoped if n.availability_zone==az and n.subnet==subnet]
                    cols=max(1,int((sw-24)/250));cardw=min(235,(sw-24-(cols-1)*15)/cols)
                    for i,n in enumerate(members_here):put(n.id,sx+12+(i%cols)*(cardw+15),ay+(i//cols)*135,sk,cardw)
                    ay+=math.ceil(len(members_here)/cols)*135+15
                    if subnet:boxes[sk]=(sx,sy,sw,ay-sy)
                    subnet_bottom=max(subnet_bottom,ay)
                    ay+=20
                ay=max(ay,subnet_bottom+20)
                boxes[ak]=(ax,az_row_top,azw,ay-az_row_top)
                row_bottom=max(row_bottom,ay)
            y=row_bottom+20
            boxes[vk]=(15,vtop,gw-30,y-vtop);y+=30
        # Repack the remaining managed services into rows of two (or four in a
        # wide VPC tile), outside the VPC even when they support its connectors.
        keys=[k for row in group['rows'] for k in row if k not in pos and k not in support and owner[k]==gid]
        # Anchor the busiest service before placing its direct peers. The model
        # chooses membership; incidental JSON order must not bury the runtime
        # behind its queues and force their connections across the whole tile.
        if len(keys)>2:
            degree={k:sum(e.source in keys and e.target in keys and k in (e.source,e.target)
                          for e in spec.edges) for k in keys}
            anchor=max(keys,key=lambda k:degree[k])
            keys=[anchor]+[k for k in keys if k!=anchor]
        cols=2*span;cw=(gw-60-(cols-1)*25)/cols
        for i,key in enumerate(keys):put(key,30+(i%cols)*(cw+25),y+(i//cols)*150,gid,cw)
        y+=math.ceil(len(keys)/cols)*150
        boxes[gid]=(0,0,gw,y+18)
    def actor(node):
        return node.scope=='external' and (node.kind=='actor' or '.general-icons.user' in node.icon_key)
    channel_ids={e.target for e in spec.edges if actor(nodes[e.source]) and nodes[e.target].scope=='external' and not actor(nodes[e.target])}
    # Access-only partners (for example an existing identity provider) stay
    # beside entry channels instead of acquiring a page-height footer wire.
    for n in spec.nodes:
        if n.scope!='external' or actor(n):continue
        peers={owner.get(e.target if e.source==n.id else e.source) for e in spec.edges if n.id in (e.source,e.target)}-{None}
        if peers and peers<=entries:channel_ids.add(n.id)
    cloud_top=285 if channel_ids else 155
    global_top=cloud_top+85
    region_top=global_top+140
    row_top=region_top+60;col=0;row_bottom=row_top
    for group in groups:
        gid=group['id'];span=spans[gid]
        if col+span>columns:row_top=row_bottom+100;col=0
        dx=85+col*(tile+gutter);dy=row_top
        def belongs(key):
            while key in parents and key!=gid:key=parents[key]
            return key==gid
        for collection in (boxes,pos):
            for key,(x,y,w,h) in list(collection.items()):
                if belongs(key):collection[key]=(x+dx,y+dy,w,h)
        row_bottom=max(row_bottom,dy+boxes[gid][3]);col+=span
    regional_controls=[n for n in spec.nodes if n.scope in {'managed','regional'} and n.id in support]
    bottom=row_bottom+65;control_cols=max(1,int((width-180)/260))
    if regional_controls:
        box('regional_controls',(85,bottom,width-170,60+math.ceil(len(regional_controls)/control_cols)*115),
            'region','Shared security and operations','functional')
        for i,n in enumerate(regional_controls):put(n.id,100+(i%control_cols)*260,bottom+45+(i//control_cols)*115,'regional_controls',235,90)
        bottom+=boxes['regional_controls'][3]+20
    global_nodes=[n for n in spec.nodes if n.scope=='global']
    used=set()
    for n in sorted(global_nodes,key=lambda n:(n.id in support,n.id)):
        peers=[owner[e.target] for e in spec.edges if e.source==n.id and e.target in owner]
        target=boxes[peers[0]][0]+boxes[peers[0]][2]/2-120 if peers else width-350
        slots=range(85,int(width-270),270)
        x=min((x for x in slots if x not in used),key=lambda x:abs(x-target));used.add(x)
        put(n.id,x,global_top,'account',240,90)
    box('region',(55,region_top,width-110,bottom-region_top),'account','Region','region')
    box('account',(35,cloud_top+35,width-70,bottom-cloud_top),'cloud','AWS Account','account')
    box('cloud',(20,cloud_top,width-40,bottom-cloud_top+55),'root','AWS Cloud','cloud')
    outgoing_integration={n.id for n in spec.nodes if n.scope=='external' and not actor(n) and n.id not in channel_ids
                          and any(e.target==n.id and nodes[e.source].scope!='external' for e in spec.edges)}
    rails={}
    for n in spec.nodes:
        if n.scope!='external':continue
        y=bottom+140 if n.id in outgoing_integration else (145 if n.id in channel_ids else 10)
        rails.setdefault(y,[]).append(n)
    for y,items in rails.items():
        def anchor(n):
            peers=[e.target if e.source==n.id else e.source for e in spec.edges if n.id in (e.source,e.target)]
            xs=[boxes[owner[k]][0]+boxes[owner[k]][2]/2 for k in peers if k in owner]
            return sum(xs)/len(xs) if xs else width/2
        items.sort(key=anchor)
        step=min(330,(width-200)/len(items))
        centre=sum(anchor(n) for n in items)/len(items)
        start=max(85,min(width-335-step*(len(items)-1),centre-125-step*(len(items)-1)/2))
        for i,n in enumerate(items):put(n.id,start+i*step,y,'root',250,90)
    if set(pos)!=set(nodes):raise ValueError('Compact mixed view omitted resources: '+str(set(nodes)-set(pos)))
    for key,(x,y,w,h) in {**boxes,**pos}.items():
        if parents[key] in boxes:
            px,py,pw,ph=boxes[parents[key]]
            if not(px<=x and py<=y and x+w<=px+pw and y+h<=py+ph):raise ValueError(f'{key} escapes its physical parent')
    height=max(bottom+90,max(y+h for x,y,w,h in pos.values())+45)
    return pos,boxes,parents,width,height,captions,kinds
