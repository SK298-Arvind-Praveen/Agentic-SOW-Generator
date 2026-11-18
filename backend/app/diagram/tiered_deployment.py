"""Presentation of real deployment nodes, preserving runtime and replica edges.

No project names, service additions or invented placement. Tier order is semantic;
the selected graph remains the authority for resource ownership and connections.
"""
import math
import re


def enabled(spec):
    scoped=[n for n in spec.nodes if n.scope in {'vpc','az'}]
    return (len({n.availability_zone for n in scoped if n.availability_zone})>=2
            and any(n.placement_role=='compute' for n in scoped)
            and any(n.placement_role=='data' for n in scoped))


def subnet_order(name):
    name=name.lower()
    if 'public' in name:return (0,name)
    if any(t in name for t in ('isolated','database','data','db')):return (2,name)
    return (1,name)


def geometry(spec, ordering=None):
    from app.diagram.narrative_boundaries import controls
    ordering=ordering or {}; support=controls(spec)
    rank={key:(i,r,c) for i,g in enumerate(spec.architecture_plan['narrative_view']['groups'])
          for r,row in enumerate(g['rows']) for c,key in enumerate(row)}
    order=lambda n:(ordering.get(n.id,0),rank.get(n.id,(99,0,0)),n.id)
    scoped=[n for n in spec.nodes if n.scope in {'vpc','az'}]
    node_map={n.id:n for n in spec.nodes}
    migration_ids={n.id for n in spec.nodes if 'database-migration' in n.icon_key
                   or re.search(r'\bDMS\b',n.label)}
    migration=bool(migration_ids)
    runtime_ids={e.target for e in spec.edges if node_map[e.source].placement_role=='entry'}
    migration_source_ids={e.source for e in spec.edges if e.target in migration_ids
                          and node_map[e.source].scope=='external'}
    migration_helpers=migration_ids | {e.target for e in spec.edges
        if e.source in migration_source_ids
        and node_map[e.target].scope in {'vpc','az'} and e.target not in runtime_ids
        and node_map[e.target].placement_role in {'compute','integration'}}
    if migration and runtime_ids:
        # Test/import/migration hosts are secondary to load-balancer targets,
        # regardless of their names or whether they read from or receive data
        # from the source. Keep the direct application-to-database lane clear.
        migration_helpers.update(n.id for n in scoped if n.id not in runtime_ids
            and n.placement_role in {'compute','integration'} and n.id not in support)
    vpcs=sorted({n.vpc or 'VPC' for n in scoped})
    zones={v:sorted({n.availability_zone for n in scoped if (n.vpc or 'VPC')==v and n.availability_zone}) for v in vpcs}
    if migration:
        zones={v:sorted(azs,key=lambda az:(not any(n.id in migration_helpers and
            n.availability_zone==az and (n.vpc or 'VPC')==v for n in scoped),az))
            for v,azs in zones.items()}
    repair=bool(spec.architecture_plan.get('routing_repair'))
    shared_endpoints={n.id for n in scoped if n.scope=='vpc' and 'endpoint' in n.icon_key
        and len({node_map[e.source].availability_zone for e in spec.edges if e.target==n.id
                 and node_map[e.source].availability_zone})>=2}
    zone_step=705 if migration else 740 if repair and shared_endpoints else 520 if repair else 430
    zone_width=565 if migration else 405
    core=max(1180,max(len(zones[v])+int(any(n.subnet and not n.availability_zone and (n.vpc or 'VPC')==v for n in scoped)) for v in vpcs)*zone_step+(340 if migration else 300))
    # Reserve distinct vertical tracks between VPC egress and regional auth/data.
    # A narrow gutter makes the auth drop look attached to the outbound gateway.
    regional_gutter=60 if repair else 0
    width=core+510+regional_gutter
    pos,boxes,parents,captions,kinds={},{},{},{},{}
    def box(key,rect,parent,label,kind):
        boxes[key]=rect;parents[key]=parent;captions[key]=label;kinds[key]=kind
    def place(n,x,y,parent,w=250,h=100):pos[n.id]=(x,y,w,h);parents[n.id]=parent
    def row(nodes,x,y,parent,cols,step=280,h=100):
        for i,n in enumerate(sorted(nodes,key=order)):place(n,x+(i%cols)*step,y+(i//cols)*(h+28),parent,min(250,step-20),h)
        return y+math.ceil(len(nodes)/cols)*(h+28)
    box('cloud',(25,140,width-50,100),'root','AWS Cloud','cloud')
    box('account',(40,180,width-80,100),'cloud',next((n.account for n in spec.nodes if n.account and n.scope!='external'),'AWS Account'),'account')
    globals_=sorted([n for n in spec.nodes if n.scope=='global'],key=lambda n:(n.id in support,order(n)))
    cols=max(1,int((width-200)/280))
    for i,n in enumerate(globals_):place(n,165+(i%cols)*280,230+(i//cols)*116,'account',250,88)
    y=230+math.ceil(len(globals_)/cols)*116+25
    top=y
    box('region',(60,top,width-120,100),'account',next((n.region for n in spec.nodes if n.region and n.scope not in {'global','external'}),'Region'),'region')
    y+=55
    for vi,vpc in enumerate(vpcs):
        key=f'vpc_{vi}';vtop=y
        members=[n for n in scoped if (n.vpc or 'VPC')==vpc]
        box(key,(85,y,core,100),'region',vpc,'vpc')
        common=[n for n in members if not n.availability_zone and not n.subnet]
        entry=[n for n in common if n.placement_role=='entry']
        network=[n for n in common if n.placement_role=='network']
        top_network=[n for n in network if 'internet-gateway' in n.icon_key]
        network=[n for n in network if n not in top_network]
        data=[n for n in common if n not in entry+network+top_network and n.id not in support]
        # Stable request-first order; network egress must not displace ingress.
        for i,n in enumerate(sorted(entry,key=order)+sorted(top_network,key=order)):
            ex=110+(len(zones[vpc])-1)*zone_step/2+(300 if migration else 50)
            x=(ex if migration else 165)+i*300
            if repair and not migration:
                x=(110+(len(zones[vpc])-1)*zone_step/2+65) if n in entry else core-175
            place(n,x,y+60,key)
        y+=60+(128 if entry+top_network else 0)+40
        # Every AZ uses the same tier heights, so a reader can compare replicas.
        az_names=zones[vpc]
        if any(n.subnet and not n.availability_zone for n in members):az_names=az_names+['']
        tiers=sorted({n.subnet for n in members if n.availability_zone or n.subnet},key=subnet_order)
        def row_count(subnet,az):
            entries=[n for n in members if n.subnet==subnet and n.availability_zone==az]
            if not migration:return len(entries)
            return max(sum(n.id in migration_helpers for n in entries),
                       sum(n.id not in migration_helpers for n in entries))
        tier_heights={s:max([row_count(s,az) for az in az_names]+[0])*120+(100 if migration else 80 if repair else 50) for s in tiers}
        tier_gap=100 if migration else 75
        az_top=y
        az_height=48+sum(tier_heights.values())+max(0,len(tiers)-1)*tier_gap+25
        for ai,az in enumerate(az_names):
            ax=110+ai*zone_step;ak=f'{key}_az_{ai}'
            label=re.sub(r'^az[_ -]*','AZ ',az,flags=re.I) if az else 'AZ not specified'
            box(ak,(ax,az_top,zone_width,az_height),key,label,'az' if az else 'functional')
            sy=az_top+48
            for si,subnet in enumerate(tiers):
                entries=[n for n in members if n.availability_zone==az and n.subnet==subnet]
                if entries:
                    sk=f'{ak}_subnet_{si}' if subnet else ak
                    if subnet:
                        tier=subnet_order(subnet)[0];kind=('public' if tier==0 else 'isolated' if tier==2 else 'private')
                        label=subnet.replace('_',' ').title()
                        if 'subnet' not in label.lower():label+=' subnet'
                        box(sk,(ax+12,sy,zone_width-24,tier_heights[subnet]),ak,label,kind)
                    # A clear left corridor keeps ingress from passing through NAT.
                    lane_counts={True:0,False:0}
                    for ni,n in enumerate(sorted(entries,key=order)):
                        if migration:
                            helper=n.id in migration_helpers
                            # Top ports need room below the boundary header;
                            # otherwise the router cannot enter an app from above.
                            mirrored=bool(spec.architecture_plan.get('story_overview') and ai==len(az_names)-1 and ai>0)
                            offset=(300 if helper else 40) if mirrored else (40 if helper else 300)
                            place(n,ax+offset,sy+88+lane_counts[helper]*120,sk,235)
                            lane_counts[helper]+=1
                            continue
                        is_nat='nat-gateway' in n.icon_key
                        place(n,ax+(153 if is_nat else 50),sy+(78 if repair else 48)+ni*120,sk,215 if is_nat else 280)
                sy+=tier_heights[subnet]+tier_gap
        y=az_top+az_height+55
        y=row(data,150,y,key,max(1,int((core-100)/280)))
        # Private endpoints sit beside their callers, not below the database.
        ny=az_top+48
        for n in sorted(network,key=order):
            if repair and not migration and n.id in shared_endpoints and len(zones[vpc])==2:
                callers=[e.source for e in spec.edges if e.target==n.id and e.source in pos]
                peers=[pos[source][1] for source in callers]
                endpoint_y=min(peers)
                if callers and all(node_map[source].subnet in tiers[:-1] for source in callers):
                    # Put exports in the gap after the app tier, with a clear
                    # horizontal path to storage outside the application boxes.
                    endpoint_y=max(boxes[parents[source]][1]+boxes[parents[source]][3]
                                   for source in callers)+tier_gap/2-50
                place(n,110+zone_width+(zone_step-zone_width-235)/2,endpoint_y,key,235,100)
                continue
            peers=[pos[e.source][1]+pos[e.source][3]+30 for e in spec.edges if e.target==n.id and e.source in pos]
            ny=max(ny,min(peers) if peers else ny)
            place(n,core-175,ny,key,235,100);ny+=135
        y=max(y,ny)+20
        y=row([n for n in common if n.id in support],150,y,key,max(1,int((core-100)/280)),h=88)+20
        boxes[key]=(85,vtop,core,y-vtop)
        y+=50
    regional=[n for n in spec.nodes if n.scope in {'regional','managed'} and n.id not in support]
    # Runtime dependencies follow the owning workload rather than alphabetical order.
    ry=top+65
    for n in sorted(regional,key=order):
        peers=[pos[e.source][1] for e in spec.edges if e.target==n.id and e.source in pos and e.source not in support]
        desired=min(peers) if peers else ry
        ry=max(ry,desired);place(n,core+155+regional_gutter,ry,'region',280,112);ry+=155
    bottom=max(y,ry)+20
    shared=[n for n in spec.nodes if n.scope in {'regional','managed'} and n.id in support]
    if shared:
        btop=bottom;bottom=row(shared,105,bottom+50,'regional_controls',max(1,int((width-190)/245)),step=245,h=80)+15
        box('regional_controls',(90,btop,width-180,bottom-btop),'region','Shared security and operations','functional')
    x,yy,w,_=boxes['region'];boxes['region']=(x,yy,w,bottom-yy+20)
    for k,extra in [('account',40),('cloud',60)]:
        x,yy,w,_=boxes[k];boxes[k]=(x,yy,w,bottom-yy+extra)
    external=[n for n in spec.nodes if n.scope=='external']
    outputs=[n for n in external if not any(e.source==n.id for e in spec.edges) and
             n.kind not in {'actor','user'} and not re.search(r'operator|admin|staff',n.label,re.I)]
    inputs=[n for n in external if n not in outputs]
    # Put active users over ingress; unconnected support actors follow them.
    inputs.sort(key=lambda n:(not any(e.source==n.id and e.target not in support for e in spec.edges),order(n)))
    for i,n in enumerate(inputs):place(n,165+(i%max(1,int((width-160)/280)))*280,15,'root',250,90)
    oy=top+300
    for n in sorted(outputs,key=order):
        peers=[pos[e.source][1] for e in spec.edges if e.target==n.id and e.source in pos]
        oy=max(oy,min(peers) if peers else oy)
        place(n,width+25,oy,'root',260,100);oy+=145
    height=max(bottom+110,oy+30 if outputs else 0)
    if outputs:width+=315
    if migration:
        # Keep source migration traffic beside its target lane, outside AWS.
        # Human/test requests still enter from above the load balancer.
        left_sources={n.id for n in inputs if any(e.source==n.id and e.target in migration_helpers for e in spec.edges)}
        if left_sources:
            shift=320
            pos={k:(x+shift,yy,w,h) for k,(x,yy,w,h) in pos.items()}
            boxes={k:(x+shift,yy,w,h) for k,(x,yy,w,h) in boxes.items()}
            width+=shift
        else:shift=0
        side_slots={'left':[],'right':[]}
        for n in inputs:
            targets=[node_map[e.target] for e in spec.edges if e.source==n.id]
            helpers=[t for t in targets if t.id in migration_helpers]
            transfers=[t for t in targets if t.placement_role=='integration' and t.scope in {'regional','managed'}]
            entry_targets=[t for t in targets if t.placement_role=='entry']
            if helpers or transfers:
                side='left' if helpers else 'right'; target=(helpers or transfers)[0]
                if spec.architecture_plan.get('story_overview') and target.id in migration_ids:
                    target_zones=zones.get(target.vpc or 'VPC',[])
                    side='right' if target_zones and target.availability_zone==target_zones[-1] else 'left'
                yy=pos[target.id][1]
                while any(abs(yy-other)<130 for other in side_slots[side]):yy+=130
                side_slots[side].append(yy)
                place(n,25 if side=='left' else boxes['cloud'][0]+boxes['cloud'][2]+55,yy,'root',250,90)
            elif entry_targets:
                place(n,pos[entry_targets[0].id][0],15,'root',250,90)
        # DNS sits directly above ingress. Pack global controls into the remaining
        # slots rather than letting them displace the primary request path.
        gateways=[n for n in globals_ if n.id not in support and any(
            e.source==n.id and node_map[e.target].placement_role=='entry' for e in spec.edges)]
        # Keep the ingress column clear through account-wide controls. Otherwise
        # an unrelated IAM/Budgets icon forces a needless dogleg above the ALB.
        occupied=[(pos[n.id][0],230,250,88) for n in scoped
                  if n.placement_role=='entry'] if spec.architecture_plan.get('story_overview') else []
        for n in gateways:
            target=next(node_map[e.target] for e in spec.edges if e.source==n.id and node_map[e.target].placement_role=='entry')
            x,yy,w,h=pos[n.id];pos[n.id]=(pos[target.id][0],yy,w,h);occupied.append(pos[n.id])
        for n in (n for n in globals_ if n not in gateways):
            x,yy,w,h=pos[n.id]
            for trial in range(165+shift,int(boxes['account'][0]+boxes['account'][2]-w-20),280):
                if all(abs(trial-r[0])>=270 or yy!=r[1] for r in occupied):
                    pos[n.id]=(trial,yy,w,h);occupied.append(pos[n.id]);break
        # Aligning the test client above ingress can collide with another actor
        # left in its old slot. Repack the remaining input cards afterwards.
        anchored = {n.id for n in inputs if any(e.source==n.id and
                    node_map[e.target].placement_role=='entry' for e in spec.edges)}
        occupied = [pos[k] for k in anchored]
        for n in (n for n in inputs if n.id not in anchored and pos[n.id][1]==15):
            x,yy,w,h=pos[n.id]
            while any(x < ox+ow+25 and x+w+25 > ox for ox,oy,ow,oh in occupied):
                x=max(ox+ow+25 for ox,oy,ow,oh in occupied if x < ox+ow+25 and x+w+25 > ox)
            pos[n.id]=(x,yy,w,h);occupied.append(pos[n.id])
        width=max(width,max(x+w for x,yy,w,h in pos.values())+35)
        height=max(height,max(yy+h for x,yy,w,h in pos.values())+35)
    if set(pos)!={n.id for n in spec.nodes}:raise ValueError('Tier layout omitted resources')
    for key,(x,yy,w,h) in {**boxes,**pos}.items():
        if parents[key] in boxes:
            px,py,pw,ph=boxes[parents[key]]
            if not (px<=x and py<=yy and x+w<=px+pw and yy+h<=py+ph):raise ValueError(f'{key} escapes parent')
    return pos,boxes,parents,width,height,captions,kinds
