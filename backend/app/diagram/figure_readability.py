"""Physical figure sizing derived from the actual reviewed XML and PNG."""
import base64
import io
import math
import re
from xml.etree import ElementTree as ET

from PIL import Image

A3 = (16.54, 11.69)
MIN_TYPE_PT = 8


def overview_font_sizes(xml):
    root = ET.fromstring(xml).find('./diagram/mxGraphModel/root')
    if root is None: return []
    sizes = []
    for cell in root.findall('mxCell'):
        if not cell.get('value') or cell.get('edge') == '1': continue
        # The diagram's integer references are markers, not sustained text.
        if cell.get('id', '').startswith(('process_flow_marker_', 'process_flow_key_')): continue
        style = cell.get('style', '')
        match = re.search(r'(?:^|;)fontSize=([\d.]+)', style)
        if match: sizes.append(float(match[1]))
        sizes.extend(float(n) for n in re.findall(r'font-size:\s*([\d.]+)px', cell.get('value', '')))
    return sizes


def physical_type_size(asset, width_inches):
    if not asset.get('drawio_xml'): return None
    sizes = overview_font_sizes(asset['drawio_xml'])
    if not sizes: return None
    with Image.open(io.BytesIO(base64.b64decode(asset['image_base64']))) as image:
        pixels = image.width
    renderer = asset.get('renderer_details') or {}
    scale = renderer.get('export_scale') or (renderer.get('process_flow_render') or {}).get('export_scale') or 1.5
    return min(sizes) * float(scale) * 72 * width_inches / pixels


def fit_figure(asset, page_width, page_height, heading=True):
    """Choose the smallest supported page that preserves eight-point figure text."""
    with Image.open(io.BytesIO(base64.b64decode(asset['image_base64']))) as image:
        aspect = image.width / image.height
    def fit(size):
        pw, ph = size
        width = min(pw - 1, (ph - 1 - (.65 if heading else .2)) * aspect)
        return {'page_width': pw, 'page_height': ph, 'width': width, 'height': width/aspect}
    original = (max(page_width, page_height), min(page_width, page_height)) if aspect >= 1.15 else (min(page_width, page_height), max(page_width, page_height))
    result = fit(original)
    projected = physical_type_size(asset, result['width'])
    if projected is not None and projected < MIN_TYPE_PT:
        result = max((fit(A3), fit(tuple(reversed(A3)))), key=lambda row: row['width'])
    result['minimum_type_pt'] = physical_type_size(asset, result['width'])
    return result


def overview_type_size(width, height, panel=True):
    # Include the same bounded process panel and Word heading allowance used by
    # the final exporter. This changes type before image review, never in Word.
    width += 690 if panel else 0
    return max(25, math.ceil(max(width/15.54, height/10.04)*MIN_TYPE_PT/72) + 1)


def display_name(node):
    name = re.sub(r'^(?:Amazon|AWS)\s+', '', node.label)
    if name.endswith(' EC2'): name = 'EC2 ' + name[:-4]
    aliases = {
        'Identity and Access Management': 'IAM', 'Key Management Service': 'KMS',
        'Simple Notification Service': 'SNS', 'Simple Queue Service': 'SQS',
        'Bedrock Knowledge Bases': 'Knowledge Bases', 'Bedrock Knowledge Base': 'Knowledge Base',
        'EventBridge Scheduler': 'Scheduler', 'Elastic Load Balancing Application Load Balancer': 'ALB',
        'Application Load Balancer': 'ALB', 'Certificate Manager': 'ACM',
        'RDS Multi-AZ Primary': 'RDS primary', 'RDS Multi-AZ Standby': 'RDS standby',
    }
    return aliases.get(name, name)


def _font(size, bold=False):
    from PIL import ImageFont
    from pathlib import Path
    paths = [Path('C:/Windows/Fonts/arialbd.ttf' if bold else 'C:/Windows/Fonts/arial.ttf'),
             Path(__file__).resolve().parents[2]/'assets/fonts'/('DMSans-Bold.ttf' if bold else 'DMSans-Regular.ttf')]
    font = None
    for path in paths:
        try: font = ImageFont.truetype(str(path), size=round(size)); break
        except OSError: pass
    return font or ImageFont.load_default(size=round(size))


def wrap_text(text, width, size, bold=False):
    """Measured wrapping without dropping words or manufacturing shorter prose."""
    font = _font(size, bold)
    lines = []; line = ''
    for word in text.split():
        if font.getlength(word) > width:
            if line: lines.append(line); line = ''
            chunks = re.findall(r'[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|[^A-Za-z]+', word)
            for chunk in chunks:
                if font.getlength(chunk) > width:
                    for char in chunk:
                        if line and font.getlength(line+char) > width:
                            lines.append(line); line = ''
                        line += char
                elif line and font.getlength(line+chunk) > width:
                    lines.append(line); line = chunk
                else: line += chunk
            continue
        candidate = (line+' '+word).strip()
        if line and font.getlength(candidate) > width:
            lines.append(line); line = word
        else: line = candidate
    if line: lines.append(line)
    return lines or ['']


def boundary_header_sizes(boxes, captions, size, badge_keys=()):
    """Measure the same bold type, badge slot and padding used in the XML."""
    result = {}; font = _font(size, True)
    for key, (_, _, width, _) in boxes.items():
        left = 44 if key in badge_keys else 8
        lines = wrap_text(captions.get(key, key), max(1, width-left-16), size, True)
        result[key] = (min(width, left+16+max(font.getlength(line) for line in lines)),
                       max(38 if key in badge_keys else 0, math.ceil(len(lines)*size*1.2+16)))
    return result


def caption_geometry(spec, positions, boxes, parents, captions, width, height):
    """Reserve rendered line heights and header clearance before routing wires.

    Monotone row insertions keep parallel lanes aligned and expand every enclosing
    boundary; individual services never move out of their physical ownership.
    """
    base_positions, base_boxes, base_height = positions, boxes, height
    size = overview_type_size(width, height)
    for _ in range(4):
        labels = {n.id: wrap_text(display_name(n), base_positions[n.id][2]-4, size, bold=True) for n in spec.nodes}
        positions = {k:(x,y,w,max(h,math.ceil(73+len(labels[k])*size*1.2)))
                     for k,(x,y,w,h) in base_positions.items()}
        boxes = dict(base_boxes); height = base_height
        def insert_row(cut, delta):
            nonlocal positions, boxes, height
            positions = {k:(x,y+delta if y>=cut else y,w,h) for k,(x,y,w,h) in positions.items()}
            boxes = {k:(x,y+delta if y>=cut else y,w,h+delta if y<cut<=y+h else h)
                     for k,(x,y,w,h) in boxes.items()}
            height += delta
        for _pass in range(100):
            adjustment = None
            for key,(x,y,w,h) in boxes.items():
                header = max(40, len(wrap_text(captions[key], max(60,w-56), size, bold=True))*size*1.2+16)
                children = [rect[1] for child,rect in {**boxes,**positions}.items() if parents.get(child)==key]
                if children and min(children) < y+header:
                    adjustment = (min(children), math.ceil(y+header-min(children))); break
            if adjustment is None:
                ordered = sorted(positions.items(), key=lambda pair:pair[1][1])
                for i,(_,a) in enumerate(ordered):
                    for _,b in ordered[i+1:]:
                        if a[1] >= b[1] or a[0]+a[2] <= b[0] or b[0]+b[2] <= a[0]: continue
                        if b[1] < a[1]+a[3]+14:
                            adjustment = (b[1], math.ceil(a[1]+a[3]+14-b[1])); break
                    if adjustment: break
            if adjustment is None:
                # Root-level actors and outside systems sit above sibling AWS
                # boundaries. Their captions require the same clearance as a
                # following service, even though the boundary is not a node.
                for key,(x,y,w,h) in positions.items():
                    for boundary,(bx,by,bw,_) in boxes.items():
                        if (parents.get(key) == parents.get(boundary) and y < by
                                and x+w > bx and bx+bw > x and y+h+14 > by):
                            adjustment = (by, math.ceil(y+h+14-by)); break
                    if adjustment: break
            if adjustment is None:
                for key,(_,y,_,h) in positions.items():
                    parent = parents.get(key)
                    if parent in boxes:
                        _,py,_,ph = boxes[parent]
                        if y+h+8 > py+ph:
                            adjustment = (py+ph, math.ceil(y+h+8-py-ph)); break
            if adjustment is None: break
            insert_row(*adjustment)
        else:
            raise ValueError('Readable caption clearance could not fit the fixed deployment')
        required = overview_type_size(width, height)
        if required <= size: return positions, boxes, height, size, labels
        size = required
    raise ValueError('Readable caption layout exceeds the bounded figure page')
