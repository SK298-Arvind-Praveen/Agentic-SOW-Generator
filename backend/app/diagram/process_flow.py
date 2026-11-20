"""Optional, source-graph-backed process legend for the exported architecture.

Only existing overview relationships are numbered. No new services, connections,
or architectural claims are introduced by this presentation feature.
"""
import math
import re
import html
import itertools
from xml.etree import ElementTree as ET
from types import SimpleNamespace


def enabled(config):
    value=getattr(config,'ARCHITECTURE_PROCESS_FLOW',False)
    return str(value).strip().lower() in {'true','1','yes','on'}


def remove_line_labels(xml):
    document=ET.fromstring(xml)
    for root in document.findall('./diagram/mxGraphModel/root'):
        edge_ids={c.get('id') for c in root.findall('mxCell') if c.get('edge')=='1'}
        for c in list(root):
            if c.get('edge')=='1':
                c.set('value','')
                c.set('style',c.get('style','')+'jumpStyle=arc;jumpSize=10;')
            elif c.get('parent') in edge_ids or c.get('id','').startswith(('flow_caption_','interface_caption_','edge_label_')):
                root.remove(c)
    return ET.tostring(document,encoding='unicode')


def decorate(png, xml, spec, config, render, timeout=None):
    """Presentation errors never replace an already-rendered semantic diagram."""
    details={'process_flow':[], 'decoration_warnings':[]}
    try:
        candidate=remove_line_labels(xml)
        if enabled(config):
            candidate,steps=annotate(candidate,spec)
        else:steps=[]
        for attempt in range(2):
            try:
                rendered,rendered_xml,render_details=render(candidate,timeout_seconds=timeout)
                if not rendered:raise ValueError('Decorated export returned no image')
                return rendered,rendered_xml,{**details,'process_flow':steps,'process_flow_render':render_details}
            except Exception:
                if attempt:raise
    except Exception as exc:
        details['decoration_warnings']=[f'Architecture retained; process-flow/label formatting could not complete: {type(exc).__name__}: {str(exc)[:300]}']
    return png,xml,details


def describe(edge, nodes):
    if getattr(edge,'reverse_label',None):
        source,target=nodes[edge.source].label,nodes[edge.target].label
        action,reverse=(edge.label or '').lower(),edge.reverse_label.lower()
        if re.search(r'chat|whatsapp|send message',action) and 'reply' in reverse:
            return 'Customer conversation',f'{source} passes customer messages to {target} and receives replies back.'
        if re.search(r'answer|retriev',action) and 'sync' in reverse:
            return 'Knowledge exchange',f'{source} exchanges answer requests and synchronisation updates with {target}.'
        if re.search(r'handover|agent webhook',action) and re.search(r'handover|agent webhook',reverse):
            return 'Agent handover',f'{source} and {target} exchange handover events and agent updates.'
        if re.search(r'start|resume',action) and 'extract' in reverse:
            return 'Document extraction',f'{source} starts or resumes extraction in {target} and receives the extracted records.'
        heading,forward=describe(SimpleNamespace(source=edge.source,target=edge.target,label=edge.label),nodes)
        return heading,forward.rstrip('.')+f', with a return flow for {reverse}.'
    source,target=nodes[edge.source].label,nodes[edge.target].label
    action=(edge.label or '').lower()
    if 'endpoint' in source.lower() and nodes[edge.source].placement_role=='network':
        return 'Private storage access',f'Workload traffic reaches {target} through {source} without using a public storage route.'
    if 'read objects' in action and nodes[edge.source].scope=='external':
        return 'Source file access',f'{target} reads source files from {source}.'
    if 'upload' in action and re.search(r'intake|validation',target,re.I):
        return 'Document intake',f'{source} uploads source documents to {target} for intake and validation.'
    if re.search(r'start|resume',action) and 'job' in action:
        return 'Processing workflow',f'{source} starts or resumes the processing job in {target}.'
    if 'export' in action and not re.search(r'events?',action):
        if getattr(edge,'release_checks',False):
            return 'Validated export',f'{source} exports records to {target} after the defined validation and review checks.'
        return 'Data export',f'{source} exports the processed dataset to {target}.'
    if 'open workbench' in action:
        return 'Review workbench',f'{source} opens the review workbench through {target}.'
    if re.search(r'fetch.*(?:ui|asset)',action):
        return 'Interface delivery',f'{source} retrieves interface assets from {target}.'
    if re.search(r'review actions?',action):
        return 'Record review',f'{source} sends reviewer decisions to {target} for processing.'
    if 'review session' in action:
        return 'Reviewer access',f'{source} opens a review session through {target}.'
    if re.search(r'forward|route',action):
        return 'Application access',f'{source} routes incoming application requests to {target}.'
    if re.search(r'replic',action) and re.search(r'database|rds|aurora|standby',source+' '+target,re.I):
        return 'Database replication',f'{source} replicates data to {target}.'
    if re.search(r'retrieve|sync|ingest',action):
        if re.search(r'knowledge|embedding|retrieval|\bFAQ\b',source+' '+target+' '+action,re.I):
            return 'Knowledge retrieval',f'{source} interacts with {target} for knowledge retrieval and updates.'
        return 'Data exchange',f'{source} connects to {target} to {action}.'
    if re.search(r'sso|sign.in|federat',action):
        return 'Staff authentication',f'{source} connects with {target} to authenticate staff access.'
    if re.search(r'load widget|load console|read assets',action):
        return 'Interface delivery',f'{source} loads the application interface through {target}.'
    if re.search(r'handover|agent webhook',action):
        return 'Agent handover',f'{source} exchanges handover events and updates with {target}.'
    if re.search(r'verify.*otp',action):
        return 'Customer verification',f'{source} uses {target} to verify the customer with a one-time password.'
    if re.search(r'stream events|export events',action):
        return 'Event reporting',f'{source} sends interaction events to {target} for reporting.'
    if re.search(r'view dashboard',action):
        return 'Performance reporting',f'{source} views the operational dashboards provided by {target}.'
    if 'send reply' in action:
        return 'Outbound messages',f'{source} sends replies to {target}.'
    if re.search(r'send messages?',action):
        if nodes[edge.source].kind in {'actor','user'}:
            return 'Customer conversation',f'{source} passes customer messages to {target}.'
        return 'Outbound messages',f'{source} sends messages to {target}.'
    if re.search(r'chat|whatsapp|inbound webhook',action):
        return 'Customer conversation',f'{source} passes customer messages to {target} for the conversation flow.'
    if re.search(r'order api|commerce calls',action):
        return 'Order information',f'{source} calls {target} to retrieve commerce and order information.'
    if re.search(r'full load|load.*cdc|apply changes',action):
        return 'Database migration',f'{source} transfers database records and changes to {target}.' if 'cdc' in action or 'changes' in action else f'{source} loads the source database records into {target}.'
    if re.search(r'sql|query',action):
        return 'Database access',f'{source} queries {target} for application data.'
    if re.search(r'copy|upload|put objects',action):
        if 'endpoint' in target.lower():
            return 'File transfer',f'{source} uploads files through {target}.'
        return 'File transfer',f'{source} transfers files to {target}.'
    if re.search(r'get images|object access|s3 access',action):
        return 'Storage access',f'{source} accesses stored objects through {target}.'
    if re.search(r'call|stub',action):
        return 'Dependency calls',f'{source} calls {target} for the requested operation.'
    if re.search(r'https|private|connection',action):
        heading='Private access' if 'private' in action else 'Application access'
        return heading,f'{source} sends application traffic through {target}.'
    if 'evidence' in action:
        return 'Evidence storage',f'{source} sends migration and test evidence to {target}.'
    heading=' '.join((edge.label or 'Service interaction').split()[:5]).capitalize()
    return heading,f'{source} uses {target} for {(edge.label or "the selected operation").lower()}.'


def annotate(xml, spec):
    document=ET.fromstring(xml)
    model=document.find('./diagram/mxGraphModel')
    if model is None:
        raise ValueError('Process flow requires an editable architecture overview')
    root=model.find('root')
    cells={c.get('id'):c for c in root.findall('mxCell')}
    if 'process_flow_panel' in cells:
        return xml, []
    nodes={n.id:n for n in spec.nodes}
    component_ids=set(nodes)
    plan=spec.architecture_plan.get('narrative_view') or {}
    owner={key:g['id'] for g in plan.get('groups',[]) for row in g.get('rows',[]) for key in row}
    for group in plan.get('groups',[]):
        nodes[group['id']]=SimpleNamespace(id=group['id'],label=group['label'],scope='functional',kind='group',placement_role='functional')
    labels={(l['source'],l['target']):l.get('label','') for l in plan.get('links',[])}
    design=spec.architecture_plan.get('service_design') or {}
    summary=design.get('summary','') if isinstance(design,dict) else ''
    release_checks=bool(re.search(r'(?:failing|invalid) records are blocked from release',summary,re.I))
    def rect(c):
        g=c.find('mxGeometry')
        if g is None:return (0,0,0,0)
        x,y,w,h=(float(g.get(k,0)) for k in ('x','y','width','height'))
        parent=cells.get(c.get('parent'))
        if parent is not None and parent.get('vertex')=='1':
            px,py,_,_=rect(parent);x+=px;y+=py
        return x,y,w,h
    def intersects(a,b):
        return a[0]<b[0]+b[2] and a[0]+a[2]>b[0] and a[1]<b[1]+b[3] and a[1]+a[3]>b[1]
    obstacles = []
    for key, cell in cells.items():
        if cell.get('vertex') != '1':
            continue
        if key in component_ids or key.startswith(('label_', 'icon_', 'badge_', 'heading_')):
            obstacles.append(rect(cell))
        elif cell.get('value'):
            x, y, w, h = rect(cell)
            # Boundary captions occupy the header. The rest of the container
            # is available for markers on internal connectors.
            if 'verticalAlign=top' in cell.get('style', '').split(';'):
                h = min(h, 36)
            obstacles.append((x, y, w, h))
    from app.diagram.projection import connections_from_xml
    from app.diagram.process_story import validate
    story = spec.architecture_plan.get('process_story')
    if not story:
        raise ValueError('Process story was not planned; refusing to invent workflow text while drawing')
    validate(story, spec)
    connections = connections_from_xml(xml, spec)
    edges=[]; provenance={}; ordered=[]; descriptions=[]; step_records=[]
    for connection in connections:
        c=cells[connection['id']];g=c.find('mxGeometry')
        if g is None:continue
        start=g.find("mxPoint[@as='sourcePoint']");end=g.find("mxPoint[@as='targetPoint']")
        if start is None or end is None:continue
        point=lambda p:(float(p.get('x',0)),float(p.get('y',0)))
        path=[point(start)]+[point(p) for p in g.findall('./Array/mxPoint')]+[point(end)]
        indices=sorted({i for p in connection['edge_paths'] for i in p})
        edge=SimpleNamespace(source=connection['source'],target=connection['target'],
            label=' / '.join(dict.fromkeys(spec.edges[i].label for i in indices)),reverse_label=None)
        for key in (edge.source,edge.target):
            if key not in nodes:nodes[key]=SimpleNamespace(label=key,scope='functional',kind='group')
        provenance[c.get('id')]=indices
        edges.append((c,edge,path))
    used=set()
    for step in story['steps']:
        indices={int(k[1:]) for k in step['edge_ids']}
        candidates=[row for row in edges if indices.intersection(provenance[row[0].get('id')])]
        if not candidates:
            raise ValueError('No rendered path for process step '+step['id'])
        row=min(candidates,key=lambda row:(row[0].get('id') in used,
            -len(indices.intersection(provenance[row[0].get('id')]))))
        used.add(row[0].get('id'));ordered.append(row)
        descriptions.append((step['title'],step['description']));step_records.append(step)
    width=max(30,float(model.get('pageWidth',0)),max((rect(c)[0]+rect(c)[2] for c in cells.values() if c.get('vertex')=='1'),default=0))
    height=float(model.get('pageHeight',0));panel_x=width+35;panel_w=630
    from app.diagram.figure_readability import overview_type_size, wrap_text
    text_size = max(float(model.get('minimumFontSize', 0)), overview_type_size(width, height))
    def add(key,value,box,style):
        c=ET.SubElement(root,'mxCell',id=key,value=value,vertex='1',parent='1',style=style)
        ET.SubElement(c,'mxGeometry',x=str(box[0]),y=str(box[1]),width=str(box[2]),height=str(box[3]),attrib={'as':'geometry'})
    common='whiteSpace=wrap;fontFamily=Helvetica;fontColor=#00275A;'
    # Match the AWS architecture boundary, rather than the top actor row or
    # arbitrary page origin. Distribute spare height between process entries.
    boundary=cells.get('cloud')
    panel_top=rect(boundary)[1] if boundary is not None else 20
    architecture_h=rect(boundary)[3] if boundary is not None else max(100,height-40)
    line_height = text_size*1.12
    row_heights=[max(96, (len(wrap_text(heading, panel_w-80, text_size, bold=True))
                         +len(wrap_text(sentence, panel_w-80, text_size)))*line_height+12)
                 for heading,sentence in descriptions]
    # Pack overflow into columns rather than stretching a tall sidebar far
    # below the architecture. Each column reads top-to-bottom in step order.
    columns=[];current=[];used=0
    for i,h in enumerate(row_heights):
        if current and used+h+14>architecture_h-85:
            columns.append(current);current=[];used=0
        current.append(i);used+=h+14
    if current:columns.append(current)
    # Avoid a nearly empty final column (for example 9 / 9 / 1). Balance the
    # contiguous step ranges when they still fit the same architecture height.
    count=len(columns)
    balanced=[];start=0
    for column in range(count):
        size=math.ceil((len(row_heights)-start)/(count-column))
        balanced.append(list(range(start,start+size)));start+=size
    if all(sum(row_heights[i]+14 for i in indices)<=architecture_h-85 for indices in balanced):
        columns=balanced
    column_width=panel_w
    panel_w=column_width*max(1,len(columns))
    panel_h=max(architecture_h,85+max(row_heights,default=0))
    slots={}
    for column,indices in enumerate(columns):
        gap=max(14,(panel_h-85-sum(row_heights[i] for i in indices))/max(1,len(indices)-1))
        row_y=panel_top+65
        for i in indices:
            slots[i]=(panel_x+column*column_width,row_y)
            row_y+=row_heights[i]+gap
    steps=[];y=panel_top+65
    add('process_flow_panel','',(panel_x,panel_top,panel_w,panel_h),'rounded=0;fillColor=#F5F8FC;strokeColor=#B7C9DB;')
    add('process_flow_title','Process flow',(panel_x+20,panel_top+15,panel_w-40,40),common+f'text;fontSize={max(30,text_size)};fontStyle=1;align=left;strokeColor=none;fillColor=none;')
    from app.diagram.review import hits_box
    segments = [(p, q) for _, _, route in edges for p, q in zip(route, route[1:])]
    def free(box):
        x, y, w, _ = box
        return (x >= 0 and y >= 0 and x + w <= width
                and not any(intersects(box, obstacle) for obstacle in obstacles)
                and not any(hits_box(p, q, box) for p, q in segments))

    for number,(c,edge,path) in enumerate(ordered,1):
        column_x,y=slots[number-1]
        source=nodes[edge.source].label;target=nodes[edge.target].label
        action=re.sub(r'\s+',' ',edge.label or 'Connect').strip()
        if edge.reverse_label:
            action+=' / '+re.sub(r'\s+',' ',edge.reverse_label).strip()
        heading,sentence=descriptions[number-1]
        text=(f'<div style="line-height:1.12"><b>{html.escape(heading)}</b><br/>{html.escape(sentence)}</div>')
        step={'id':step_records[number-1]['id'],'edge_ids':step_records[number-1]['edge_ids'],
              'flow_kind':step_records[number-1]['flow_kind'],'number':number,'source':edge.source,'target':edge.target,'action':action,'heading':heading,'description':sentence,
              'edge_indices':provenance[c.get('id')],
              'directions':[{'source':spec.edges[i].source,'target':spec.edges[i].target,
                             'action':spec.edges[i].label,'edge_index':i}
                            for i in provenance[c.get('id')]]}
        steps.append(step)
        circle=common+'ellipse;aspect=fixed;fillColor=#FFFFFF;strokeColor=#237BAA;strokeWidth=2;fontSize=18;fontStyle=1;'
        add(f'process_flow_key_{number}',str(number),(column_x+18,y+7,30,30),circle)
        row_h=row_heights[number-1]
        add(f'process_flow_text_{number}',text,(column_x+60,y,column_width-80,row_h),common+f'text;html=1;fontSize={text_size};spacing=0;align=left;verticalAlign=top;strokeColor=none;fillColor=none;')
        placed=None
        for a,b in sorted(zip(path,path[1:]),key=lambda pair:-math.dist(*pair)):
            for fraction in (.5, .25, .75, .375, .625, .125, .875):
                px=a[0]+(b[0]-a[0])*fraction;py=a[1]+(b[1]-a[1])*fraction
                for dx,dy in ((0,-25),(0,25),(-25,0),(25,0)):
                    box=(px+dx-15,py+dy-15,30,30)
                    if free(box):
                        placed=box;break
                if placed:break
            if placed:break
        edge_id = c.get('id')
        marker = ET.SubElement(root, 'mxCell', id=f'process_flow_marker_{number}', value=str(number),
                               vertex='1', style=circle, processFlowStep=step['id'],
                               processFlowConnector=edge_id, connectable='0')
        if placed:
            marker.set('parent', '1')
            ET.SubElement(marker, 'mxGeometry', x=str(placed[0]), y=str(placed[1]),
                          width='30', height='30', attrib={'as': 'geometry'})
        else:
            # Edge-relative x=0 anchors each child to the route midpoint.
            # Search perpendicular placements first, keeping earlier keys clear.
            pairs = [(a, b, math.dist(a, b)) for a, b in zip(path, path[1:])]
            remaining = sum(length for _, _, length in pairs) / 2
            for a, b, length in pairs:
                if remaining <= length:
                    fraction = remaining / length if length else 0
                    break
                remaining -= length
            px, py = (a[i] + (b[i] - a[i]) * fraction for i in range(2))
            offsets = ((1, 0), (-1, 0), (0, 1), (0, -1))
            if abs(a[0] - b[0]) > abs(a[1] - b[1]):
                offsets = offsets[2:] + offsets[:2]
            # On a crowded page the column below the diagram remains available.
            # Clamp its x so a marker always fits within the overview width.
            centre_x = min(max(px, 15), width - 15)
            for distance in itertools.count(35, 40):
                for dx, dy in offsets:
                    box = (centre_x + distance * dx - 15, py + distance * dy - 15, 30, 30)
                    if free(box):
                        placed = box
                        break
                if placed:
                    break
            marker.set('parent', edge_id)
            geo = ET.SubElement(marker, 'mxGeometry', relative='1', width='30', height='30',
                                attrib={'as': 'geometry'})
            ET.SubElement(geo, 'mxPoint', x=str(placed[0] - px), y=str(placed[1] - py),
                          attrib={'as': 'offset'})
            height = max(height, placed[1] + placed[3] + 25)
        obstacles.append(placed)
    model.set('pageWidth',str(math.ceil(panel_x+panel_w+25)))
    model.set('pageHeight',str(math.ceil(max(height,panel_top+panel_h+25))))
    return ET.tostring(document,encoding='unicode'),steps
