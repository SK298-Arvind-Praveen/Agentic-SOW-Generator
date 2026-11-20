"""Balanced functional tiles with real VPC/AZ ownership for larger mixed graphs."""
import math


def enabled(spec):
    groups = spec.architecture_plan.get('narrative_view', {}).get('groups', [])
    return len(groups) >= 4 or any(sum(map(len, g['rows'])) > 6 for g in groups)


def geometry(spec, ordering=None):
    from app.diagram.mixed_deployment import ownership, interface_groups
    from app.diagram.narrative_boundaries import controls
    from app.diagram.tiered_deployment import subnet_order
    nodes = {n.id:n for n in spec.nodes}
    support = controls(spec)
    owner, vpcs, vpc_owner = ownership(spec)
    from app.diagram.projection import selected_edge_indices
    selected=selected_edge_indices(spec)
    story_edges=[e for i,e in enumerate(spec.edges) if selected is None or i in selected]
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
            common_ids={n.id for n in common}
            # Place connected runtime peers together before unconnected plumbing.
            # Stable sorting retains planner order for equally connected cards.
            common.sort(key=lambda n:-sum(n.id in (e.source,e.target)
                and e.source in common_ids and e.target in common_ids for e in story_edges))
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
        # Keep real side ports outside neighbouring icon/label obstacles after
        # iconic rendering scales this layout. Caption-bottom ports are not exits.
        cols=2*span;gap=48;cw=(gw-80-(cols-1)*gap)/cols
        for i,key in enumerate(keys):put(key,40+(i%cols)*(cw+gap),y+(i//cols)*150,gid,cw)
        y+=math.ceil(len(keys)/cols)*150
        boxes[gid]=(0,0,gw,y+18)
        physical=[k for k in boxes if parents.get(k)==gid and kinds[k]=='vpc']
        managed=[k for k in pos if parents.get(k)==gid]
        if physical and managed:
            # Regional peers stay immediately above the VPC, rather than below
            # its complete subnet stack. Ownership is unchanged.
            first=min(boxes[k][1] for k in physical)
            mtop=min(pos[k][1] for k in managed)
            delta=max(pos[k][1]+150 for k in managed)-mtop
            def physical_child(key):
                while key in parents and key not in physical:key=parents[key]
                return key in physical
            for collection in (pos,boxes):
                for key,(x,yy,w,h) in list(collection.items()):
                    if physical_child(key):collection[key]=(x,yy+delta,w,h)
            for key in managed:
                x,yy,w,h=pos[key];pos[key]=(x,first+yy-mtop,w,h)
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
    column_bottom=[region_top+60]*columns
    for group in groups:
        gid=group['id'];span=spans[gid]
        col=min(range(columns-span+1),key=lambda c:(max(column_bottom[c:c+span]),c))
        row_top=max(column_bottom[col:col+span])
        dx=85+col*(tile+gutter);dy=row_top
        def belongs(key):
            while key in parents and key!=gid:key=parents[key]
            return key==gid
        for collection in (boxes,pos):
            for key,(x,y,w,h) in list(collection.items()):
                if belongs(key):collection[key]=(x+dx,y+dy,w,h)
        for c in range(col,col+span):column_bottom[c]=dy+boxes[gid][3]+100
    row_bottom=max(column_bottom)-100
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
    actors={n.id for n in spec.nodes if actor(n)}
    direct_channels={e.target for e in spec.edges if e.source in actors}
    def connected_groups(key):
        return list(dict.fromkeys(owner[e.target if e.source==key else e.source]
            for e in spec.edges if key in (e.source,e.target)
            and (e.target if e.source==key else e.source) in owner))
    movable=[n.id for n in spec.nodes if n.scope=='external' and n.id not in actors|direct_channels
             and connected_groups(n.id)]
    membership={key:tuple(members) for members in interface_groups(spec).values() for key in members}
    def units(keys):
        available=set(keys)
        return list(dict.fromkeys(tuple(k for k in membership.get(key,(key,)) if k in available) for key in keys))
    # Multi-subsystem integrations get their desired slot before single-group
    # peers; pushing a callback system down would create a page-height return.
    side_units=units(movable)
    side_units.sort(key=lambda unit:-len({g for key in unit for g in connected_groups(key)}))
    if movable:
        pos={k:(x+350,y,w,h) for k,(x,y,w,h) in pos.items()}
        boxes={k:(x+350,y,w,h) for k,(x,y,w,h) in boxes.items()}
        width+=700
        used={'left':[],'right':[]}
        for unit in side_units:
            key=unit[0]
            peers={e.target if e.source==key else e.source for e in spec.edges if key in (e.source,e.target)}
            groups_here=connected_groups(key)
            access=[g for g in groups_here if any(k in peers and nodes[k].placement_role=='entry'
                    and owner.get(k)==g for k in nodes)]
            gx,gy,gw,gh=boxes[(access or groups_here)[0]]
            side='left' if gx+gw/2<boxes['region'][0]+boxes['region'][2]/2 else 'right'
            block_height=(len(unit)-1)*150+100
            desired=max(boxes['cloud'][1]+50,gy+gh/2-block_height/2)
            candidates=[desired]+[q for a,z in used[side] for q in (a-block_height-60,z+60)]
            available=[yy for yy in candidates if yy>=boxes['cloud'][1]+50
                and all(yy+block_height+45<=a or z+45<=yy for a,z in used[side])]
            yy=min(available,key=lambda yy:(abs(yy-desired),yy))
            used[side].append((yy,yy+block_height))
            x=25 if side=='left' else boxes['cloud'][0]+boxes['cloud'][2]+55
            for i,key in enumerate(unit):
                pos[key]=(x,yy+i*150,pos[key][2],pos[key][3])
    # Partners behind an existing external API are downstream systems, not
    # entry channels. Keep their group off the user rail, with wrapped slots.
    leaves=[n.id for n in spec.nodes if n.scope=='external' and n.id not in actors
        and not any(e.source==n.id for e in spec.edges)
        and any(e.target==n.id and nodes[e.source].scope=='external' and e.source not in actors for e in spec.edges)]
    placed_leaves=set()
    for unit in units(leaves):
        peers=[e.source for e in spec.edges if e.target in unit and nodes[e.source].scope=='external'
               and e.source not in actors and e.source not in leaves]
        if not peers: continue
        peer=pos[peers[0]]
        if not (peer[0]+peer[2]<=boxes['cloud'][0] or peer[0]>=boxes['cloud'][0]+boxes['cloud'][2]):
            continue
        x=peer[0]; yy=peer[1]+peer[3]+60
        for key in unit:
            w,h=pos[key][2:]
            occupied=[r for k,r in pos.items() if k not in unit and nodes[k].scope=='external']
            while any(x<ox+ow+20 and x+w+20>ox and yy<oy+oh+30 and yy+h+30>oy
                      for ox,oy,ow,oh in occupied):
                yy=max(oy+oh+45 for ox,oy,ow,oh in occupied
                       if x<ox+ow+20 and x+w+20>ox and yy<oy+oh+30 and yy+h+30>oy)
            pos[key]=(x,yy,w,h); yy+=h+60; placed_leaves.add(key)
    leaves=[k for k in leaves if k not in placed_leaves]
    footer_y=max(boxes['cloud'][1]+boxes['cloud'][3],
        max((y+h for k,(x,y,w,h) in pos.items() if k not in leaves),default=0))+110
    footer_cols=max(1,int((boxes['cloud'][2]-120)/330))
    column=0;row_bottom=footer_y
    for unit in units(leaves):
        span=min(len(unit),footer_cols)
        if column+span>footer_cols:
            column=0;footer_y=row_bottom+80
        for i,key in enumerate(unit):
            x=boxes['cloud'][0]+80+(column+i%span)*330
            pos[key]=(x,footer_y+(i//span)*150,pos[key][2],pos[key][3])
        row_bottom=max(row_bottom,footer_y+math.ceil(len(unit)/span)*150)
        column+=span
    if set(pos)!=set(nodes):raise ValueError('Compact mixed view omitted resources: '+str(set(nodes)-set(pos)))
    for key,(x,y,w,h) in {**boxes,**pos}.items():
        if parents[key] in boxes:
            px,py,pw,ph=boxes[parents[key]]
            if not(px<=x and py<=y and x+w<=px+pw and y+h<=py+ph):raise ValueError(f'{key} escapes its physical parent')
    height=max(bottom+90,max(y+h for x,y,w,h in pos.values())+45)
    return pos,boxes,parents,width,height,captions,kinds
