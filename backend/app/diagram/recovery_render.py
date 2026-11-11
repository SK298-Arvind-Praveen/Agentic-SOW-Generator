"""Last-resort local picture of the actual graph, independent of icons/draw.io.

This is explicitly unverified recovery output, never a successful quality result.
It keeps all nodes and directed edges without making up a replacement architecture.
"""
import io
import math
import textwrap
from xml.etree import ElementTree as ET


def render(spec):
    from PIL import Image, ImageDraw, ImageFont
    columns = min(4, max(1, math.ceil(math.sqrt(len(spec.nodes)))))
    rows = max(1, math.ceil(len(spec.nodes) / columns))
    width, height = columns * 330 + 60, rows * 190 + 150
    canvas = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=18)
    draw.text((30, 22), 'Recovery diagram - needs review', fill='#92400E', font=font)
    draw.text((30, 52), 'Original components and connections; automated layout checks failed.', fill='#475569', font=font)
    root = ET.Element('mxfile')
    page = ET.SubElement(root, 'diagram', name='Recovery diagram')
    model = ET.SubElement(page, 'mxGraphModel', pageWidth=str(width), pageHeight=str(height))
    cells = ET.SubElement(model, 'root')
    ET.SubElement(cells, 'mxCell', id='0')
    ET.SubElement(cells, 'mxCell', id='1', parent='0')
    positions = {n.id:(30 + (i % columns)*330, 105 + (i // columns)*190) for i,n in enumerate(spec.nodes)}
    for i, edge in enumerate(spec.edges):
        if edge.source not in positions or edge.target not in positions:
            continue
        x,y = positions[edge.source]; tx,ty = positions[edge.target]
        a,b = (x+280,y+60),(tx,ty+60)
        draw.line([a,b], fill='#94A3B8', width=2)
        dx,dy=b[0]-a[0],b[1]-a[1]; length=max(1,math.hypot(dx,dy))
        ux,uy=dx/length,dy/length
        draw.polygon([b,(b[0]-ux*11-uy*5,b[1]-uy*11+ux*5),
                      (b[0]-ux*11+uy*5,b[1]-uy*11-ux*5)],fill='#64748B')
        c=ET.SubElement(cells,'mxCell',id='edge_'+str(i),edge='1',parent='1',
            source=edge.source,target=edge.target,style='edgeStyle=orthogonalEdgeStyle;endArrow=block;')
        ET.SubElement(c,'mxGeometry',relative='1',attrib={'as':'geometry'})
    for n in spec.nodes:
        x,y=positions[n.id]
        scope=' / '.join(filter(None,[n.scope,n.vpc,n.availability_zone,n.subnet]))
        label='\n'.join(textwrap.wrap(n.label,26))
        draw.rounded_rectangle((x,y,x+280,y+125),radius=10,fill='#F8FAFC',outline='#64748B',width=2)
        draw.multiline_text((x+12,y+12),label,fill='#0F172A',font=font,spacing=4)
        draw.text((x+12,y+100),textwrap.shorten(scope,36,placeholder='...'),fill='#475569',font=font)
        c=ET.SubElement(cells,'mxCell',id=n.id,value=n.label+'\n'+scope,vertex='1',parent='1',
            style='rounded=1;whiteSpace=wrap;fillColor=#F8FAFC;fontSize=16;')
        ET.SubElement(c,'mxGeometry',x=str(x),y=str(y),width='280',height='125',attrib={'as':'geometry'})
    output=io.BytesIO();canvas.save(output,format='PNG')
    return output.getvalue(),ET.tostring(root,encoding='unicode')
