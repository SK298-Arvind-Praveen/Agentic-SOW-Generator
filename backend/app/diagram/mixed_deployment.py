"""Functional columns with real network islands for mixed managed/VPC workloads.

Service membership and network ownership come from the selected graph. A VPC
must not force all regional services into a single peripheral inventory column.
"""
import math
import time
from collections import Counter


def enabled(spec):
    from app.diagram.tiered_deployment import enabled as tiered
    groups=spec.architecture_plan.get('narrative_view',{}).get('groups',[])
    grouped={k for g in groups for row in g['rows'] for k in row}
    # A stale/incomplete narrative cannot own new network resources. The
    # general physical layout still renders those resources without omission.
    if not groups or any(n.id not in grouped for n in spec.nodes if n.scope in {'vpc','az'}):return False
    return (not tiered(spec) and any(n.scope in {'vpc','az'} for n in spec.nodes)
            and sum(n.scope in {'regional','managed'} and n.placement_role not in {'security','operations'}
                    for n in spec.nodes)>=3)


def ownership(spec):
    owner={k:g['id'] for g in spec.architecture_plan['narrative_view']['groups'] for row in g['rows'] for k in row}
    vpcs={}
    for n in spec.nodes:
        if n.scope in {'vpc','az'}:vpcs.setdefault(n.vpc or 'VPC',[]).append(n)
    vpc_owner={v:Counter(owner.get(n.id) for n in members if n.placement_role!='network').most_common(1)[0][0]
               if any(n.placement_role!='network' for n in members) else owner[members[0].id]
               for v,members in vpcs.items()}
    for v,members in vpcs.items():
        for n in members:owner[n.id]=vpc_owner[v]
    return owner,vpcs,vpc_owner


def audiences(spec):
    """Group only human actors with identical directed overview destinations.

    This is a presentation boundary, not an authentication or processing hop.
    Individual actors and every original service-level edge remain available.
    """
    from app.diagram.narrative_boundaries import controls
    owner, _, _ = ownership(spec)
    support = controls(spec)
    candidates = [n.id for n in spec.nodes if n.scope == 'external' and
                  (n.kind == 'actor' or '.general-icons.user' in n.icon_key)]
    buckets = {}
    for key in candidates:
        # Incoming responses can carry role-specific semantics: keep those
        # actors separate rather than treating an audience as a two-way peer.
        if any(e.target == key for e in spec.edges):
            continue
        targets = frozenset(owner.get(e.target, e.target) for e in spec.edges
                            if e.source == key and e.target not in support)
        if len(targets) >= 2:
            buckets.setdefault(targets, []).append(key)
    groups = {}
    occupied = {n.id for n in spec.nodes} | set(owner.values())
    for members in buckets.values():
        if len(members) < 2:
            continue
        key = '__audience_' + str(len(groups))
        while key in occupied:
            key += '_'
        groups[key] = members
        occupied.add(key)
    return groups


def interface_groups(spec):
    groups = audiences(spec)
    owner, _, _ = ownership(spec)
    buckets = {}
    for node in spec.nodes:
        if node.scope != 'external' or node.kind == 'actor' or '.general-icons.user' in node.icon_key:
            continue
        if any(e.source == node.id for e in spec.edges):
            continue
        sources = frozenset(owner.get(e.source, e.source) for e in spec.edges if e.target == node.id)
        if sources:
            buckets.setdefault(sources, []).append(node.id)
    occupied = {n.id for n in spec.nodes} | set(owner.values()) | set(groups)
    for members in buckets.values():
        if len(members) < 2:continue
        key = '__integrations_' + str(len(groups))
        while key in occupied:key += '_'
        groups[key] = members
        occupied.add(key)
    return groups


def audience_geometry(spec, data):
    groups = interface_groups(spec)
    if not groups:
        return data
    pos, boxes, parents, width, height, captions, kinds = data
    # Reserve a heading above the actor cards, retaining their individual icons.
    for collection in (pos, boxes):
        for key, (x, y, w, h) in list(collection.items()):
            collection[key] = (x, y + 40, w, h)
    rails = {}
    for node in spec.nodes:
        if node.scope == 'external' and parents[node.id] == 'root':
            rails.setdefault(pos[node.id][1], []).append(node.id)
    for members_on_rail in rails.values():
        ordered = [k for members in groups.values() for k in members if k in members_on_rail]
        ordered += [k for k in sorted(members_on_rail,key=lambda k:pos[k][0]) if k not in ordered]
        for key, rect in zip(ordered, sorted(pos[k] for k in members_on_rail)):
            pos[key] = rect
    for key, members in groups.items():
        left = min(pos[k][0] for k in members) - 12
        top = min(pos[k][1] for k in members) - 32
        right = max(pos[k][0] + pos[k][2] for k in members) + 12
        bottom = max(pos[k][1] + pos[k][3] for k in members) + 12
        boxes[key] = (left, top, right-left, bottom-top)
        parents[key], captions[key], kinds[key] = 'root', ('User access' if key.startswith('__audience_') else 'External systems'), 'functional'
        for member in members:
            parents[member] = key
    return pos, boxes, parents, width, height + 40, captions, kinds


def projection(spec):
    from app.diagram.narrative_boundaries import controls
    from app.diagram.service import Edge
    owner,_,_=ownership(spec);support=controls(spec);pairs={};links=[]
    actor_owner = {k:g for g, members in interface_groups(spec).items() for k in members}
    owner.update(actor_owner)
    local_pairs = {}
    labels={(l['source'],l['target']):l['label'] for l in spec.architecture_plan['narrative_view'].get('links',[])}
    for i,e in enumerate(spec.edges):
        if e.source in support or e.target in support:continue
        a,b=owner.get(e.source,e.source),owner.get(e.target,e.target)
        if a==b:local_pairs.setdefault((e.source,e.target),[]).append(i)
        else:pairs.setdefault((a,b),[]).append(i)
    # One connector per service pair; use two arrowheads only when the graph
    # actually contains both directions. Never remove an intermediate service.
    local_done = set()
    for (a,b), indices in local_pairs.items():
        if (a,b) in local_done:continue
        reverse = local_pairs.get((b,a),[]) if a != b else []
        local_done.update({(a,b),(b,a)})
        texts = list(dict.fromkeys(spec.edges[i].label for i in indices+reverse if spec.edges[i].label))
        links.append({'edge':Edge(a,b,' / '.join(texts)), 'paths':[[i] for i in indices+reverse],
                      'both':bool(reverse)})
    done=set()
    for (a,b),indices in pairs.items():
        if (a,b) in done:continue
        reverse=pairs.get((b,a),[]);done.update({(a,b),(b,a)})
        label=labels.get((a,b)) or labels.get((b,a)) or spec.edges[indices[0]].label
        if a in actor_owner.values():
            label='Web access' if any(n.id==b and 'cloudfront' in n.icon_key for n in spec.nodes) else 'App access'
        if b.startswith('__integrations_'):
            label='External calls'
        links.append({'edge':Edge(a,b,label),'paths':[[i] for i in indices+reverse],
                      'both':bool(reverse),'interface':True})
    return links,sorted(i for l in links for path in l['paths'] for i in path)


def routes(view,positions,boxes,parents,width,height,deadline,captions,links):
    """Local service connections plus truthful functional interfaces.

    Group arrows end on the functional boundary. No control or network node is
    presented as a made-up processing hop; exact edge IDs accompany each arrow.
    """
    from dataclasses import replace
    from app.diagram.review import local_routes,geometry_report
    iconic=bool(view.architecture_plan.get('story_overview'))
    group_ids={g['id'] for g in view.architecture_plan['narrative_view']['groups']} | {k for k in boxes if k.startswith(('__audience_','__integrations_'))}
    indices=[i for i,l in enumerate(links) if not l.get('interface')]
    peers=[i for i in range(len(view.edges)) if i not in indices]
    result=[None]*len(view.edges)
    from app.diagram.compact_mixed import enabled as compact
    if compact(view):
        # Internal connectors cannot escape their functional tile to find a
        # cheaper page-wide detour. Smaller routing grids also avoid timeouts.
        for group in view.architecture_plan['narrative_view']['groups']:
            gid=group['id'];gx,gy,gw,gh=boxes[gid]
            def belongs(key):
                while key in parents and key!=gid:key=parents[key]
                return key==gid
            p={k:(x-gx,y-gy,w,h) for k,(x,y,w,h) in positions.items() if belongs(k)}
            b={k:(x-gx,y-gy,w,h) for k,(x,y,w,h) in boxes.items() if belongs(k)}
            par={k:('root' if k==gid else parents[k]) for k in {*p,*b}}
            selected=[i for i in indices if view.edges[i].source in p and view.edges[i].target in p]
            if not selected:continue
            subset=replace(view,edges=tuple(view.edges[i] for i in selected))
            paths=local_routes(subset,p,b,par,gw,gh,deadline,captions,iconic,True,24,True)
            def local_score(candidate):
                m=geometry_report(subset,p,candidate)
                return (m['ambiguous_connector_pairs'],m['connector_crossings'],
                        m['connector_length_normalized'],m['connector_bends'])
            best=local_score(paths)
            orders=[list(reversed(range(len(selected)))),sorted(range(len(selected)),key=lambda i:
                abs(p[subset.edges[i].source][0]-p[subset.edges[i].target][0])+abs(p[subset.edges[i].source][1]-p[subset.edges[i].target][1]))]
            for order in orders:
                if time.monotonic()>deadline-2:break
                try:
                    trial=local_routes(replace(subset,edges=tuple(subset.edges[i] for i in order)),p,b,par,
                                       gw,gh,deadline,captions,iconic,True,24,True)
                    restored=[None]*len(selected)
                    for i,path in zip(order,trial):restored[i]=path
                    score=local_score(restored)
                    if score<best:paths,best=restored,score
                except (ValueError,TimeoutError):pass
            for i,path in zip(selected,paths):result[i]=[(x+gx,y+gy) for x,y in path]
        indices=[]
    for selected,p,b,par in [
        (indices,positions,boxes,parents),
        (peers,{**{k:v for k,v in positions.items() if parents.get(k)=='regional_controls' or not any(k in row for g in view.architecture_plan['narrative_view']['groups'] for row in g['rows'])},
                **{k:boxes[k] for k in group_ids},
                **({'regional_controls':boxes['regional_controls']} if 'regional_controls' in boxes and not compact(view) else {})},
         {**{k:v for k,v in boxes.items() if k in {'cloud','account','region'}},
          **({'control_heading':(*boxes['regional_controls'][:2],400,38)}
             if compact(view) and 'regional_controls' in boxes else {})},parents)]:
        if not selected:continue
        subset=replace(view,edges=tuple(view.edges[i] for i in selected))
        sides={}
        if compact(view) and selected is peers:
            for edge in subset.edges:
                a,z=p[edge.source],p[edge.target]
                if edge.source in group_ids and parents.get(edge.target)=='root':
                    if z[1]>boxes['cloud'][1]+boxes['cloud'][3]:
                        sides[(edge.source,edge.target)]={edge.source:{'bottom'},edge.target:{'top'}}
                    elif z[1]<boxes['cloud'][1]:
                        sides[(edge.source,edge.target)]={edge.source:{'top'},edge.target:{'bottom'}}
                elif parents.get(edge.source)=='root' and a[1]+a[3]<z[1]:
                    sides[(edge.source,edge.target)]={edge.source:{'bottom'},edge.target:{'top'}}
        crossing_penalty=350 if compact(view) else 180
        def route(candidate):
            return local_routes(candidate,p,b,par,width,height,deadline,captions,iconic,True,24,True,terminal_sides=sides,
                                crossing_penalty=crossing_penalty)
        try:paths=route(subset)
        except (ValueError,TimeoutError):
            if not sides:raise
            sides={};paths=route(subset)
        if len(selected)>1 and (selected is indices or compact(view)):
            def score(candidate):
                if compact(view) and selected is peers:
                    combined=list(result)
                    for i,path in zip(selected,candidate):combined[i]=path
                    m=geometry_report(view,positions,combined)
                else:m=geometry_report(subset,p,candidate)
                return (m['connector_node_intersections'],m['ambiguous_connector_pairs'],
                        m['connector_crossings']*8+m['connector_length_normalized']*18+
                        m['connector_bends']*2+m['long_connector_count']*30)
            best=score(paths)
            def span(i):
                e=subset.edges[i];a,z=p[e.source],p[e.target]
                return abs(a[0]-z[0])+abs(a[1]-z[1])
            for order in (list(reversed(range(len(selected)))),sorted(range(len(selected)),key=span,reverse=True),
                          sorted(range(len(selected)),key=span)):
                if time.monotonic()>deadline-2:break
                try:
                    candidate=route(replace(subset,edges=tuple(subset.edges[i] for i in order)))
                except (ValueError,TimeoutError):
                    continue  # Optional improvement cannot discard valid routes.
                restored=[None]*len(selected)
                for i,path in zip(order,candidate):restored[i]=path
                candidate_score=score(restored)
                if candidate_score<best:paths,best=restored,candidate_score
            if sides and compact(view):
                # Entry-side preferences are cosmetic. Compare unrestricted
                # routes too; forcing a port must not create a page-wide loop.
                sides={}
                for order in (list(range(len(selected))),list(reversed(range(len(selected)))),
                              sorted(range(len(selected)),key=span)):
                    if time.monotonic()>deadline-2:break
                    try:
                        trial=route(replace(subset,edges=tuple(subset.edges[i] for i in order)))
                        restored=[None]*len(selected)
                        for i,path in zip(order,trial):restored[i]=path
                        trial_score=score(restored)
                        if trial_score<best:paths,best=restored,trial_score
                    except (ValueError,TimeoutError):continue
            if compact(view) and selected is peers:
                for crossing_penalty in (180,700):
                    for order in (list(range(len(selected))),list(reversed(range(len(selected)))),sorted(range(len(selected)),key=span)):
                        if time.monotonic()>deadline-2:break
                        try:
                            trial=route(replace(subset,edges=tuple(subset.edges[i] for i in order)))
                            restored=[None]*len(selected)
                            for i,path in zip(order,trial):restored[i]=path
                            trial_score=score(restored)
                            if trial_score<best:paths,best=restored,trial_score
                        except (ValueError,TimeoutError):continue
        for i,path in zip(selected,paths):result[i]=path
    return result


def geometry(spec, ordering=None):
    return audience_geometry(spec, _geometry(spec, ordering))


def _geometry(spec, ordering=None):
    from app.diagram import compact_mixed
    if compact_mixed.enabled(spec):
        return compact_mixed.geometry(spec, ordering)
    from app.diagram.narrative_boundaries import controls
    from app.diagram.tiered_deployment import subnet_order
    support=controls(spec);nodes={n.id:n for n in spec.nodes}
    plan=spec.architecture_plan['narrative_view'];groups=list(plan['groups'])
    owner,vpcs,vpc_owner=ownership(spec)
    # Start at actual entry services, then follow their dependencies. Other data
    # suppliers keep a separate entry lane above their owning subsystem.
    entries={owner[n.id] for n in spec.nodes if n.id in owner and n.placement_role=='entry'}
    # A static origin can share its S3 service with document storage. It must
    # not pull extraction ahead of the application's API -> runtime path.
    if not entries:
        entries={owner[e.target] for e in spec.edges if nodes[e.source].scope=='global'
                 and e.target in owner and e.source not in support}
    distance={k:0 for k in entries}
    for _ in groups:
        for e in spec.edges:
            a,b=owner.get(e.source),owner.get(e.target)
            if a in distance and b and a!=b:distance[b]=min(distance.get(b,99),distance[a]+1)
    groups.sort(key=lambda g:distance.get(g['id'],99))
    width=160+len(groups)*640+(len(groups)-1)*110
    pos,boxes,parents,captions,kinds={},{},{},{},{}
    def box(k,r,parent,label,kind):
        boxes[k]=r;parents[k]=parent;captions[k]=label;kinds[k]=kind
    def put(k,x,y,parent,w=250,h=104):pos[k]=(x,y,w,h);parents[k]=parent
    box('cloud',(20,140,width-40,100),'root','AWS Cloud','cloud')
    box('account',(35,180,width-70,100),'cloud',next((n.account for n in spec.nodes if n.account and n.scope!='external'),'AWS Account'),'account')
    global_nodes=[n for n in spec.nodes if n.scope=='global' and n.id not in support]
    columns={g['id']:85+i*750 for i,g in enumerate(groups)}
    global_slots=list(range(100,int(width-300),280));occupied=set();last_global_y=235
    for i,n in enumerate(global_nodes):
        target=next((owner[e.target] for e in spec.edges if e.source==n.id and e.target in owner),groups[0]['id'])
        gy=235+(i//len(global_slots))*115
        gx=min((sx for sx in global_slots if (sx,gy) not in occupied),key=lambda sx:abs(sx-columns[target]-195))
        occupied.add((gx,gy));last_global_y=max(last_global_y,gy)
        put(n.id,gx,gy,'account',250,90)
    top=max(385,last_global_y+150)
    box('region',(55,top,width-110,100),'account',next((n.region for n in spec.nodes if n.region and n.scope not in {'global','external'}),'Region'),'region')
    group_top=top+65;bottom=group_top
    for g in groups:
        gid=g['id'];x=columns[gid];y=group_top+52
        box(gid,(x,group_top,640,100),'region',g['label'],'functional')
        for vi,(v,members) in enumerate(vpcs.items()):
            if vpc_owner[v]!=gid:continue
            vk=f'vpc_{vi}';vtop=y
            box(vk,(x+15,y,610,100),gid,v,'vpc');y+=48
            scoped=[n for n in members if n.availability_zone or n.subnet]
            for ai,az in enumerate(sorted({n.availability_zone for n in scoped})):
                ak=f'{vk}_az_{ai}';atop=y
                label=az.replace('az_','AZ ').replace('az-','AZ ')
                if label.startswith('AZ '):label=label.upper()
                box(ak,(x+28,y,584,100),vk,label or 'AZ not specified','az');y+=42
                for si,subnet in enumerate(sorted({n.subnet for n in scoped if n.availability_zone==az},key=subnet_order)):
                    sk=f'{ak}_subnet_{si}' if subnet else ak;sy=y
                    if subnet:
                        box(sk,(x+40,y,560,100),ak,subnet.replace('_',' ').title()+' subnet',
                            {0:'public',1:'private',2:'isolated'}[subnet_order(subnet)[0]]);y+=44
                    members_here=[n for n in scoped if n.availability_zone==az and n.subnet==subnet]
                    members_here.sort(key=lambda n:(n.placement_role=='network',n.id))
                    for j,n in enumerate(members_here):put(n.id,x+60+(j%2)*270,y+(j//2)*140,sk,230)
                    y+=math.ceil(len(members_here)/2)*140+12
                    if subnet:boxes[sk]=(x+40,sy,560,y-sy)
                    y+=20
                boxes[ak]=(x+28,atop,584,y-atop);y+=25
            common=[n for n in members if n not in scoped]
            for j,n in enumerate(common):put(n.id,x+60+(j%2)*270,y+(j//2)*140,vk,230)
            y+=math.ceil(len(common)/2)*140+18
            boxes[vk]=(x+15,vtop,610,y-vtop);y+=40
        # Keep the model's functional rows; eliminate only nodes already placed
        # inside their real VPC, never the VPC itself or its dependencies.
        for row in g['rows']:
            row=[k for k in row if k not in pos and k not in support and owner[k]==gid]
            if not row:continue
            for c,k in enumerate(row):
                if len(row)==1:
                    # Align a regional dependency with its local caller. This
                    # keeps endpoint -> workflow and endpoint -> data routes
                    # in separate lanes instead of crossing at an arrowhead.
                    sources=[pos[e.source] for e in spec.edges if e.target==k and e.source in pos
                             and owner.get(e.source)==gid]
                    if sources:
                        centre=sum(r[0]+r[2]/2 for r in sources)/len(sources)
                        c=min((0,1),key=lambda col:abs(x+165+col*290-centre))
                put(k,x+35+c*290,y,gid,260)
            y+=155
        boxes[gid]=(x,group_top,640,y-group_top+12);bottom=max(bottom,y+12)
    # Columns need not have equal heights; blank space should not imply a tier.
    regional_controls=[n for n in spec.nodes if n.scope in {'regional','managed'} and n.id in support]
    sy=bottom+65;cols=max(1,int((width-180)/270))
    if regional_controls:
        for i,n in enumerate(regional_controls):put(n.id,100+(i%cols)*270,sy+45+(i//cols)*115,'regional_controls',245,90)
        end=sy+55+math.ceil(len(regional_controls)/cols)*115
        rail_width=min(width-170,min(cols,len(regional_controls))*270+30)
        box('regional_controls',(85,sy,rail_width,end-sy),'region','Shared security and operations','functional')
    else:end=sy
    boxes['region']=(55,top,width-110,end-top+20)
    globals_=[n for n in spec.nodes if n.scope=='global' and n.id in support]
    gy=end+65
    for i,n in enumerate(globals_):put(n.id,100+(i%cols)*270,gy+(i//cols)*110,'account',245,90)
    bottom=gy+math.ceil(len(globals_)/cols)*110
    for k,extra in [('account',20),('cloud',40)]:
        x,y,w,_=boxes[k];boxes[k]=(x,y,w,bottom-y+extra)
    used={};out_bottom=bottom+80
    for n in sorted((n for n in spec.nodes if n.scope=='external'),key=lambda n:n.id):
        outgoing=[e.target for e in spec.edges if e.source==n.id]
        targets=outgoing or [e.source for e in spec.edges if e.target==n.id]
        peer=next((k for k in targets if k in pos),None)
        x=(pos[peer][0] if peer else 100)
        y=15 if outgoing else bottom+85
        candidates=sorted(range(90,int(width-290),280),key=lambda t:abs(t-x))
        x=next(t for t in candidates if t not in used.setdefault(y,set()));used[y].add(x)
        put(n.id,x,y,'root',250,90);out_bottom=max(out_bottom,y+110)
    if set(pos)!=set(nodes):raise ValueError('Mixed layout omitted resources: '+str(set(nodes)-set(pos)))
    for k,(x,y,w,h) in {**boxes,**pos}.items():
        if parents[k] in boxes:
            px,py,pw,ph=boxes[parents[k]]
            if not(px<=x and py<=y and x+w<=px+pw and y+h<=py+ph):raise ValueError(f'{k} escapes its physical parent')
    return pos,boxes,parents,width,out_bottom+35,captions,kinds
