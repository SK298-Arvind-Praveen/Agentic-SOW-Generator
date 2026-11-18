"""Physical ownership with a narrative ordering, using only the selected graph.

AZs are parallel failure domains. Ingress, workloads, shared data and regional
dependencies form the reading path; controls do not create a second wiring mesh.
"""
from dataclasses import replace
import html
import json
import math
import itertools
import re
import time
from xml.etree import ElementTree as ET


def enabled(spec):
    return bool(spec.architecture_plan.get('functional_deployment_view') and
                any(n.scope in {'vpc', 'az'} for n in spec.nodes))


def controls(spec):
    from app.diagram.narrative import support_ids
    result = support_ids(spec) | {n.id for n in spec.nodes if n.scope != 'external' and
            (n.placement_role in {'security', 'operations'} or 'auto-scaling' in n.icon_key
             or 'elastic-container-registry' in n.icon_key)
            and 'cognito' not in n.icon_key}
    # Audit sinks belong with their control producer, not in the customer path.
    for n in spec.nodes:
        peers={e.source if e.target==n.id else e.target for e in spec.edges if n.id in (e.source,e.target)}
        if n.scope in {'regional','managed'} and peers and peers<=result and re.search(r'audit|trail|logs',n.label,re.I):result.add(n.id)
    return result


def workload_owners(spec):
    from app.diagram.tiered_deployment import enabled as tiered
    from app.diagram.mixed_deployment import enabled as mixed
    if tiered(spec) or mixed(spec):return {}
    vpcs=sorted({n.vpc or 'VPC' for n in spec.nodes if n.scope in {'vpc','az'}})
    return {n.id:f'vpc_{vpcs.index(n.vpc or "VPC")}_workloads' for n in spec.nodes
            if n.scope in {'vpc','az'} and (n.availability_zone or n.subnet)}


def projection(spec):
    """Collapse network access hops, never processing steps or invented edges."""
    from app.diagram.service import Edge
    support = controls(spec)
    from app.diagram.tiered_deployment import enabled as tiered
    from app.diagram.mixed_deployment import enabled as mixed
    if mixed(spec):
        from app.diagram.mixed_deployment import projection as mixed_projection
        return mixed_projection(spec)
    if tiered(spec):
        if spec.architecture_plan.get('story_overview'):
            from app.diagram.story_overview import projection as story_projection
            return story_projection(spec,support)
        indices=[i for i,e in enumerate(spec.edges) if e.source not in support and e.target not in support]
        return [{'edge':spec.edges[i],'paths':[[i]]} for i in indices],indices
    endpoints = {n.id for n in spec.nodes if 'endpoint' in (n.icon_key+' '+n.label).lower()
                 and n.scope in {'vpc', 'az'}}
    outgoing = {}
    for i,e in enumerate(spec.edges): outgoing.setdefault(e.source, []).append((i,e))
    links, covered = {}, set()
    for i,e in enumerate(spec.edges):
        if e.source in support | endpoints or e.target in support: continue
        pending = [(e.target, [i], {e.source}, e.label)]
        while pending:
            target, path, seen, label = pending.pop()
            if target in seen or target in support: continue
            if target in endpoints:
                for j,next_edge in outgoing.get(target, []):
                    pending.append((next_edge.target,path+[j],seen|{target},label or next_edge.label))
            else:
                key=(e.source,target)
                links.setdefault(key, {'edge':Edge(e.source,target,label), 'paths':[]})['paths'].append(path)
                covered.update(path)
    owners=workload_owners(spec)
    grouped={}
    for link in links.values():
        e=link['edge']; a,b=owners.get(e.source,e.source),owners.get(e.target,e.target)
        if a==b: continue
        item=grouped.setdefault((a,b),{'edge':Edge(a,b,e.label),'paths':[]})
        item['paths'].extend(link['paths'])
        if e.label and e.label not in item['edge'].label.split(' / '):
            item['edge']=Edge(a,b,item['edge'].label+' / '+e.label)
    return list(grouped.values()), sorted(covered)


def geometry(spec, ordering=None):
    from app.diagram import tiered_deployment, mixed_deployment
    if tiered_deployment.enabled(spec):return tiered_deployment.geometry(spec,ordering)
    if mixed_deployment.enabled(spec):return mixed_deployment.geometry(spec,ordering)
    plan = spec.architecture_plan['narrative_view']
    rank = {key: (i, r, c) for i, g in enumerate(plan['groups'])
            for r, row in enumerate(g['rows']) for c, key in enumerate(row)}
    ordering = ordering or {}
    order = lambda n: (ordering.get(n.id, 0), rank.get(n.id, (99, 0, 0)), n.id)
    support = controls(spec)
    vpcs = sorted({n.vpc or 'VPC' for n in spec.nodes if n.scope in {'vpc', 'az'}})
    azs = {v: sorted({n.availability_zone for n in spec.nodes
                     if n.scope in {'vpc', 'az'} and (n.vpc or 'VPC') == v and n.availability_zone}) for v in vpcs}
    slots = [len(azs[v])+int(any(n.subnet and not n.availability_zone and (n.vpc or 'VPC')==v
                               for n in spec.nodes if n.scope in {'vpc','az'})) for v in vpcs]
    vpc_width = max(880, max(slots, default=1)*300 + 360)
    width = vpc_width + 480
    pos, boxes, parents, captions, styles = {}, {}, {}, {}, {}
    def box(key, rect, parent, caption, kind):
        boxes[key], parents[key], captions[key], styles[key] = rect, parent, caption, kind
    def row(items, x, y, cols, parent, step=190, small=False):
        for i, n in enumerate(sorted(items, key=order)):
            pos[n.id] = (x+(i % cols)*step, y+(i//cols)*(115 if small else 165), 150, 95 if small else 130)
            parents[n.id] = parent
        return y + math.ceil(len(items)/cols)*(115 if small else 165)
    box('cloud', (25, 135, width-50, 100), 'root', 'AWS Cloud', 'cloud')
    box('account', (40, 170, width-80, 100), 'cloud',
        next((n.account for n in spec.nodes if n.scope != 'external' and n.account), 'AWS Account'), 'account')
    globals_ = [n for n in spec.nodes if n.scope == 'global']
    for n in globals_:
        if n.id not in support: ordering[n.id] = -10
    global_bottom = row(globals_, 75, 210, max(1, int((width-160)/190)), 'account', small=True)
    top = global_bottom + 45
    region = next((n.region for n in spec.nodes if n.scope not in {'external', 'global'} and n.region), 'Region')
    box('region', (60, top, width-120, 100), 'account', region, 'region')
    vtop = top+55
    for vi, vpc in enumerate(vpcs):
        vk = f'vpc_{vi}'
        members = [n for n in spec.nodes if n.scope in {'vpc', 'az'} and (n.vpc or 'VPC') == vpc]
        box(vk, (80, vtop, vpc_width, 100), 'region', vpc, 'vpc')
        common = [n for n in members if not n.availability_zone and not n.subnet]
        endpoints = [n for n in common if 'endpoint' in (n.icon_key+' '+n.label).lower() and n.id not in support]
        data = [n for n in common if n.placement_role == 'data' and n not in endpoints and n.id not in support]
        ingress = [n for n in common if n not in endpoints+data and n.id not in support]
        y = row(ingress, 115, vtop+55, max(1, int((vpc_width-80)/230)), vk, step=230)+100
        az_bottom = y
        scopes = [(az, [n for n in members if n.availability_zone == az]) for az in azs[vpc]]
        unzoned = [n for n in members if n.subnet and not n.availability_zone]
        if unzoned:
            scopes.append(('', unzoned))
        for ai, (az, nodes) in enumerate(scopes):
            ax = 110+ai*300
            ak = f'{vk}_az_{ai}' if az else vk
            label = re.sub(r'^az[_ -]*', 'AZ ', az, flags=re.I).upper() if az else ''
            if az:
                box(ak, (ax, y, 280, 100), vk, label, 'az')
            sy = y + (42 if az else 0)
            for si, subnet in enumerate(sorted({n.subnet for n in nodes},key=tiered_deployment.subnet_order)):
                entries = [n for n in nodes if n.subnet == subnet]
                sk = f'{ak}_subnet_{si}' if subnet else ak
                if subnet:
                    box(sk, (ax+12, sy, 256, 100), ak, subnet.replace('_', ' ').title()+' subnet',
                        'public' if 'public' in subnet.lower() else 'private')
                bottom = row(entries, ax+60, sy+(42 if subnet else 12), 1, sk)
                if subnet:
                    x0,y0,w0,_ = boxes[sk]; boxes[sk] = (x0,y0,w0,bottom-sy+12)
                sy = bottom+28
            if az:
                x0,y0,w0,_ = boxes[ak]; boxes[ak] = (x0,y0,w0,sy-y)
            az_bottom = max(az_bottom, sy)
        if scopes:
            wk=vk+'_workloads'
            box(wk,(100,y-40,len(scopes)*300-10,az_bottom-y+52),vk,'Workloads','functional')
            for ai,(az,_) in enumerate(scopes):
                if az: parents[f'{vk}_az_{ai}']=wk
                else:
                    for key in boxes:
                        if key.startswith(vk+'_subnet_'): parents[key]=wk
        data_bottom = row(data, 80+vpc_width-190, y+60, 1, vk)
        y = max(az_bottom, data_bottom)+35
        y = row(endpoints+[n for n in common if n.id in support], 115, y+15,
                max(1, int((vpc_width-100)/190)), vk, small=True)
        x0,y0,w0,_ = boxes[vk]; boxes[vk] = (x0,y0,w0,y-vtop+25)
        vtop = y+70
    regional = [n for n in spec.nodes if n.scope in {'regional', 'managed'} and n.id not in support]
    # Dependencies remain next to, but outside, the VPC that calls them.
    rbottom = row(regional, vpc_width+165, top+115, 1, 'region')
    bottom = max(vtop, rbottom)+20
    shared = [n for n in spec.nodes if n.scope in {'regional', 'managed'} and n.id in support]
    controls_top = bottom
    bottom = row(shared,105,bottom+50,max(1,int((width-200)/190)),
                 'regional_controls' if shared else 'region',small=True)+20
    if shared:
        box('regional_controls',(90,controls_top,width-180,bottom-controls_top),'region',
            'Shared security and operations','functional')
    for key in ('region', 'account', 'cloud'):
        x,y,w,_ = boxes[key]; boxes[key] = (x,y,w,bottom-y+({'region':0,'account':20,'cloud':40}[key]))
    external = [n for n in spec.nodes if n.scope == 'external']
    incoming, outgoing = [], []
    for n in sorted(external, key=order):
        (outgoing if not any(e.source == n.id for e in spec.edges) else incoming).append(n)
    # Spread input actors over their actual first-hop targets, reserving unique slots.
    occupied = []
    for n in incoming:
        peer = next((pos[e.target] for e in spec.edges if e.source == n.id and e.target in pos), (100,0,150,95))
        desired = peer[0]
        x = min((x for x in range(80, int(width-180), 180) if x not in occupied), key=lambda x: abs(x-desired))
        occupied.append(x); pos[n.id] = (x, 10, 150, 100); parents[n.id] = 'root'
    end = row(outgoing, 100, bottom+75, max(1, int((width-160)/190)), 'root', small=True)
    height = max(bottom+100, end+30)
    if set(pos) != {n.id for n in spec.nodes}:
        raise ValueError('Physical narrative omitted resources: '+str({n.id for n in spec.nodes}-set(pos)))
    for key, (x,y,w,h) in {**boxes, **pos}.items():
        p = parents[key]
        if p in boxes:
            px,py,pw,ph = boxes[p]
            if not (px <= x and py <= y and x+w <= px+pw and y+h <= py+ph):
                raise ValueError(f'{key} escapes its {p} boundary')
    return pos, boxes, parents, width, height, captions, styles


def overview_xml(spec, registry):
    from app.diagram.review import local_routes, geometry_report
    from app.diagram.boundary_style import boundary_header, BOUNDARY_HEADER_VERSION
    pos, boxes, parents, width, height, captions, kinds = geometry(spec)
    iconic=bool(spec.architecture_plan.get('story_overview'))
    if iconic:
        pos={k:(x*.75,y,w*.75,max(100,h)) for k,(x,y,w,h) in pos.items()}
        boxes={k:(x*.75,y,w*.75,h+(20 if k=='regional_controls' else 0)) for k,(x,y,w,h) in boxes.items()}
        width=math.ceil(width*.75)
    captions={k:boundary_header(kinds[k])[0] or v for k,v in captions.items()}
    support = controls(spec)
    links, indices = projection(spec)
    visible = tuple(link['edge'] for link in links)
    view = replace(spec, edges=visible)
    owners=workload_owners(spec)
    from app.diagram.tiered_deployment import enabled as tiered_enabled
    from app.diagram.mixed_deployment import enabled as mixed_enabled
    tiered=tiered_enabled(spec) or mixed_enabled(spec)
    mixed=mixed_enabled(spec)
    def route_geometry(p,b,par):
        if tiered:return p,b,par
        rp={k:v for k,v in p.items() if k not in owners}
        rp.update({key:b[key] for key in set(owners.values())})
        rb={k:v for k,v in b.items() if k not in set(owners.values()) and '_az_' not in k and '_subnet_' not in k}
        return rp,rb,{k:v for k,v in par.items() if k in rp or k in rb}
    routing_pos,routing_boxes,routing_parents=route_geometry(pos,boxes,parents)
    if mixed:
        routing_pos={**routing_pos,**{g['id']:boxes[g['id']] for g in spec.architecture_plan['narrative_view']['groups']}}
        routing_pos.update({k:v for k,v in boxes.items() if k.startswith(('__audience_','__integrations_'))})
    deadline = time.monotonic()+(90 if tiered else 35)
    repair=bool(spec.architecture_plan.get('routing_repair')) and tiered_enabled(spec) and not iconic
    if mixed:
        from app.diagram.mixed_deployment import routes as mixed_routes
        paths=mixed_routes(view,pos,boxes,parents,width,height,deadline,captions,links)
    elif repair:
        from app.diagram.routing_repair import routes as repair_routes
        paths=repair_routes(view,pos,boxes,parents,width,height,deadline,captions)
    else:
        paths = local_routes(view,routing_pos,routing_boxes,routing_parents,width,height,deadline,captions,iconic or not tiered,True,16 if iconic else 32,tiered)
    def score(p, positions=None):
        positions=positions or pos;m=geometry_report(view,positions,p)
        story_cost=0
        if tiered:
            nm={n.id:n for n in spec.nodes}
            for e,path in zip(visible,p):
                a,b=nm.get(e.source),nm.get(e.target)
                if not a or not b:continue
                # Protect the vertical application -> writer story from being
                # displaced by secondary export/notification wiring.
                if (a.placement_role=='compute' and b.placement_role=='data'
                        and a.availability_zone and a.availability_zone==b.availability_zone):
                    ax,ay,aw,ah=positions[a.id];bx,by,bw,bh=positions[b.id]
                    if by>ay+ah:
                        story_cost+=80*(path[0][1]!=ay+ah)+80*(path[-1][1]!=by)
        # Never trade a page-long detour for one fewer crossing. Cosmetic scores
        # choose a better layout; they are not acceptance gates.
        return (m['connector_node_intersections'],m['ambiguous_connector_pairs'],
                m['connector_crossings']*8+m['connector_length_normalized']*18+m['connector_bends']*2+m['long_connector_count']*30+story_cost)
    # Search only sibling orderings. Ownership and graph edges never change.
    buckets = {}
    for n in spec.nodes:
        if n.id not in support and n.scope != 'external':
            # Swap ingress peers in their own row, not an entire VPC inventory.
            # Keep vertical application/migration order within each AZ intact.
            row_key = 'regional' if n.scope in {'regional','managed'} else pos[n.id][1]
            buckets.setdefault((parents[n.id],row_key), []).append(n.id)
    swaps = [] if mixed or repair or iconic else [keys for keys in buckets.values() if 2 <= len(keys) <= 3]
    best_score = score(paths)
    for choices in itertools.islice(itertools.product(*[list(itertools.permutations(k)) for k in swaps]), 48):
        if mixed or repair or iconic or time.monotonic()>deadline-2: break
        ordering = {key:i for group in choices for i,key in enumerate(group)}
        candidate_geometry = geometry(spec,ordering)
        cp,cb,cpar,cw,ch,cc,cs = candidate_geometry
        cc={k:boundary_header(cs[k])[0] or v for k,v in cc.items()}
        candidate_geometry=cp,cb,cpar,cw,ch,cc,cs
        try:
            rp,rb,rpar=route_geometry(cp,cb,cpar)
            trial = local_routes(view,rp,rb,rpar,cw,ch,deadline,cc,not tiered,True,32,tiered)
            report = geometry_report(view,cp,trial)
            trial_score = score(trial,cp)
            if trial_score < best_score:
                pos,boxes,parents,width,height,captions,kinds = candidate_geometry
                routing_pos,routing_boxes,routing_parents=rp,rb,rpar
                paths,best_score = trial,trial_score
        except (ValueError,TimeoutError):
            continue
    node_map={n.id:n for n in spec.nodes}
    def runtime_priority(i):
        e=visible[i];a,b=node_map.get(e.source),node_map.get(e.target)
        if not a or not b:return 3
        if a.placement_role=='compute' and b.placement_role=='data' and b.scope in {'vpc','az'}:return 0
        if a.placement_role==b.placement_role=='data':return 1
        if a.placement_role=='entry' and b.placement_role=='compute':return 2
        return 3
    for order in [sorted(range(len(visible)),key=runtime_priority),list(reversed(range(len(visible)))), sorted(range(len(visible)),key=lambda i:
                  abs(routing_pos[visible[i].source][0]-routing_pos[visible[i].target][0])+abs(routing_pos[visible[i].source][1]-routing_pos[visible[i].target][1]))]:
        if mixed or repair or iconic or time.monotonic()>deadline:
            break
        try:
            candidate = local_routes(replace(view,edges=tuple(visible[i] for i in order)),routing_pos,routing_boxes,routing_parents,width,height,deadline,captions,not tiered,True,32,tiered)
            restored = [None]*len(order)
            for i,p in zip(order,candidate): restored[i] = p
            if score(restored)<score(paths): paths = restored
        except (ValueError,TimeoutError):
            pass
    metrics = {**geometry_report(view,pos,paths), 'nodes':len(spec.nodes), 'containment_violations':0,
               'out_of_bounds':sum(x<0 or y<0 or x>width or y>height for path in paths for x,y in path),
               'physical_boundaries':True, 'original_edges':len(spec.edges),
               'visible_edge_indices':indices, 'shared_associations':len(spec.edges)-len(indices)}
    if mixed:
        from app.diagram.mixed_deployment import audiences, interface_groups
        metrics['audience_groups'] = audiences(spec)
        metrics['interface_groups'] = interface_groups(spec)
        metrics['overview_connectors'] = len(links)
        metrics['aggregated_connections'] = len(indices) - len(links)
    if metrics['node_overlaps']:
        raise ValueError('Physical narrative has obstructed routes: '+json.dumps(metrics))
    file = ET.Element('mxfile',host='app.diagrams.net')
    page = ET.SubElement(file,'diagram',id='overview',name='Solution overview')
    model = ET.SubElement(page,'mxGraphModel',page='1',pageWidth=str(width),pageHeight=str(height),
                          renderedMembership=json.dumps(parents),edgeCoverage=json.dumps(indices))
    if mixed:
        model.set('audienceGroups', json.dumps(metrics['audience_groups']))
        model.set('interfaceGroups', json.dumps(metrics['interface_groups']))
    root = ET.SubElement(model,'root'); ET.SubElement(root,'mxCell',id='0'); ET.SubElement(root,'mxCell',id='1',parent='0')
    def cell(key,value,rect,style,parent='1'):
        x,y,w,h = rect
        if parent in boxes: x-=boxes[parent][0]; y-=boxes[parent][1]
        c=ET.SubElement(root,'mxCell',id=key,value=value,style=style,vertex='1',parent=parent)
        ET.SubElement(c,'mxGeometry',x=str(x),y=str(y),width=str(w),height=str(h),attrib={'as':'geometry'})
        return c
    palette={'cloud':('#232F3E','#FFFFFF',0), 'account':('#E7157B','#FFFFFF',0),
             'region':('#00A4A6','#FFFFFF',1), 'vpc':('#8C4FFF','#FAF7FF',0),
             'az':('#147EBA','#FFFFFF',1), 'private':('#00A4A6','#E6F6F7',0),
             'public':('#7AA116','#F2F6E8',0), 'isolated':('#456B93','#F0F5FB',0), 'functional':('#94A3B8','#FAF7FF',1)}
    def depth(key):
        return 0 if parents[key]=='root' else 1+depth(parents[key])
    for key in sorted(boxes,key=depth):
        rect=boxes[key]
        color,fill,dash=palette[kinds[key]]
        _,badge=boundary_header(kinds[key],registry)
        # ElementTree escapes the XML attribute; these are plain-text labels,
        # so HTML-escaping as well would display literal '&amp;' in draw.io.
        cell(key,captions[key],rect,
             f'rounded=0;whiteSpace=wrap;fillColor={fill};strokeColor={color};dashed={dash};strokeWidth=1.5;'
             f'fontColor={"#12325A" if kinds[key]=="functional" else color};fontSize=16;fontStyle=1;align=left;verticalAlign=top;spacing=10;spacingLeft={44 if badge else 10};',
             parents[key] if parents[key]!='root' else '1')
        if badge:
            x,y,_,_=rect
            cell('badge_'+key,'',(x+4,y+4,30,30),
                 'shape=image;imageAspect=1;image='+badge.replace(';base64,',',')+';',key)
    roles=spec.architecture_plan['narrative_view']['roles']
    for n in spec.nodes:
        x,y,w,h=pos[n.id]; parent=parents[n.id] if parents[n.id]!='root' else '1'
        small=h<=100; size=64 if iconic else 42 if small else 58
        name=re.sub(r'^(Amazon|AWS)\s+','',n.label)
        uri=registry.svg_data_uri(n.icon_key) if n.icon_key else None
        if tiered and not iconic:
            cell(n.id,'',(x,y,w,h),'rounded=1;arcSize=8;fillColor=#FFFFFF;strokeColor=#CBD5E1;',parent)
            if uri:cell('icon_'+n.id,'',(x+12,y+18,44,44),'shape=image;imageAspect=1;image='+uri.replace(';base64,',',')+';',parent)
            role=roles.get(n.id,'')
            label='<b>'+html.escape(name)+'</b>'
            if role:label+='<br/><font color="#64748B" style="font-size:'+str(14 if len(role.split())>4 else 16)+'px">'+html.escape(role)+'</font>'
            cell('label_'+n.id,label,(x+(66 if uri else 12),y+8,w-(76 if uri else 24),h-16),
                 'text;html=1;whiteSpace=wrap;align=left;verticalAlign=middle;fontSize=17;fillColor=none;strokeColor=none;',parent)
            continue
        cell(n.id,'',(x,y,w,h),'fillColor=none;strokeColor=none;' if uri else
             'rounded=1;fillColor=#F8FAFC;strokeColor=#64748B;',parent)
        if uri:
            cell('icon_'+n.id,'',(x+(w-size)/2,y,size,size),'shape=image;imageAspect=1;image='+uri.replace(';base64,',',')+';',parent)
        label='<b>'+html.escape(name)+'</b>'
        role=roles.get(n.id,'')
        if role and not small and not iconic: label+='<br/><font color="#64748B">'+html.escape(role)+'</font>'
        cell('label_'+n.id,label,(x-8,y+size+5,w+16,h-size-5) if uri else (x+5,y+8,w-10,h-16),
             'text;html=1;whiteSpace=wrap;align=center;verticalAlign='+('top' if uri else 'middle')+
             ';fontSize=15;fontFamily=Helvetica;fillColor=none;strokeColor=none;',parent)
    caption_boxes = []
    def caption_rect(path, label):
        from app.diagram.review import hits_box
        w,h = min(96 if mixed else 105,len(label)*6.5+8), max(28, math.ceil(len(label)/14)*17)
        obstacles = list(pos.values()) + caption_boxes
        for x,y,bw,bh in boxes.values():
            obstacles.extend([(x,y,bw,35),(x-3,y,6,bh),(x+bw-3,y,6,bh),(x,y+bh-3,bw,6)])
        def overlaps(a,b):
            return a[0]<b[0]+b[2] and a[0]+a[2]>b[0] and a[1]<b[1]+b[3] and a[1]+a[3]>b[1]
        def distance(rect, route):
            cx,cy=rect[0]+rect[2]/2,rect[1]+rect[3]/2
            return min(math.hypot(cx-max(min(cx,max(a[0],b[0])),min(a[0],b[0])),
                                  cy-max(min(cy,max(a[1],b[1])),min(a[1],b[1])))
                       for a,b in zip(route,route[1:]))
        for p,q in sorted(zip(path,path[1:]),key=lambda pair:-abs(pair[0][0]-pair[1][0])-abs(pair[0][1]-pair[1][1])):
            for fraction in (.5,.3,.7,.15,.85):
                x,y = p[0]+fraction*(q[0]-p[0]),p[1]+fraction*(q[1]-p[1])
                # Put the caption on its own segment with an opaque backing.
                # Floating beside dense parallel wires gives the label to the
                # wrong relationship, even when no rectangles overlap.
                if abs(p[0]-q[0])+abs(p[1]-q[1]) < (w+20 if p[1]==q[1] else h+20):continue
                options = [(x-w/2,y-h/2,w,h)]
                for rect in options:
                    if rect[0]<5 or rect[1]<5 or rect[0]+w>width-5 or rect[1]+h>height-5: continue
                    if any(overlaps(rect,other) for other in obstacles): continue
                    if any(hits_box(a,b,(rect[0]-4,rect[1]-4,w+8,h+8)) for route in paths
                           if route is not path for a,b in zip(route,route[1:])): continue
                    # A clear rectangle can still sit nearer the wrong wire.
                    # Omit that caption instead of attributing the operation
                    # to a neighbouring database/endpoint connection.
                    if any(distance(rect,route)+1<distance(rect,path) for route in paths if route is not path): continue
                    caption_boxes.append(rect)
                    return rect
        return None
    pending_captions=[]
    for i,(e,path) in enumerate(zip(visible,paths)):
        colour='#526A7B';dash=''
        if tiered:
            nodes={n.id:n for n in spec.nodes};a,b=nodes.get(e.source),nodes.get(e.target)
            if a and b and a.placement_role==b.placement_role=='data' and re.search(r'replic|sync|standby',e.label+' '+b.label,re.I):
                colour='#008C95';dash='dashed=1;'
            elif a and b and any(t in a.icon_key+' '+b.icon_key for t in ('nat-gateway','internet-gateway')):
                colour='#B7791F';dash='dashed=1;'
            elif a and b and a.placement_role in {'compute','entry'} and b.placement_role in {'compute','data'}:
                colour='#235C91'
        c=ET.SubElement(root,'mxCell',id='flow_'+str(i),edge='1',parent='1',
            sourceNode=e.source,targetNode=e.target,value='',
            originalEdgePaths=json.dumps(links[i]['paths']),
            style='edgeStyle=none;rounded=0;endArrow=block;endFill=1;strokeColor='+colour+';strokeWidth=1.5;'+dash+('startArrow=block;startFill=1;' if links[i].get('both') else ''))
        geo=ET.SubElement(c,'mxGeometry',relative='1',attrib={'as':'geometry'})
        for p,key in [(path[0],'sourcePoint'),(path[-1],'targetPoint')]:
            ET.SubElement(geo,'mxPoint',x=str(p[0]),y=str(p[1]),attrib={'as':key})
        arr=ET.SubElement(geo,'Array',attrib={'as':'points'})
        for x,y in path[1:-1]: ET.SubElement(arr,'mxPoint',x=str(x),y=str(y))
        caption = caption_rect(path,e.label) if e.label else None
        if caption:
            pending_captions.append((i,e.label,caption))
    for i,label,caption in pending_captions:
            cell('flow_caption_'+str(i),label,caption,
                 'text;whiteSpace=wrap;align=center;verticalAlign=middle;fontSize=13;'
                 'fontColor=#526A7B;fillColor=#FFFFFF;strokeColor=none;')
    metrics['visible_flow_captions'] = len(caption_boxes)
    metrics['boundary_header_version'] = BOUNDARY_HEADER_VERSION
    metrics['boundary_badges'] = sum(c.get('id','').startswith('badge_') for c in root.findall('mxCell'))
    return ET.tostring(file,encoding='unicode'),metrics
