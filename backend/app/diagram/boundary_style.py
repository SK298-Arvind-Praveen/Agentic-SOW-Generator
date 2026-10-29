"""Shared PNG/draw.io boundary styling using bundled AWS group glyphs.

Palette is the reviewed reference house style, not a universal AWS mandate.
Region/AZ dashed outlines describe containment, not asynchronous execution.
"""


def boundary_style(key):
    if key.startswith('__flowlane_'):
        return {'kind':'functional', 'colour':'#8795A8', 'fill':'#FFFFFF', 'dashed':True, 'icon_key':''}
    if key.startswith('__shared_controls'):
        return {'kind':'functional', 'colour':'#8795A8', 'fill':'#FFFFFF', 'dashed':True, 'icon_key':''}
    kind = ('public-subnet' if key.endswith('_public') else
            'private-subnet' if key.endswith(('_private', '_isolated')) else
            'availability-zone' if '__elk_az_' in key else
            'aws-cloud' if key == '__aws_cloud' else
            'aws-account' if key.startswith('__aws_account') else
            'region' if key.startswith('__region') else
            'virtual-private-cloud-vpc' if key.startswith('__vpc') else 'functional')
    colour, fill, dashed = {
        'aws-cloud': ('#232F3E', '#FFFFFF', False),
        'aws-account': ('#E7157B', '#FFFFFF', False),
        'region': ('#00A4A6', '#FFFFFF', True),
        'virtual-private-cloud-vpc': ('#8C4FFF', '#FFFFFF', False),
        'availability-zone': ('#147EBA', '#FFFFFF', True),
        'public-subnet': ('#7AA116', '#F2F6E8', False),
        'private-subnet': ('#00A4A6', '#E6F6F7', False),
        'functional': ('#8795A8', '#FFFFFF', True),
    }[kind]
    icon = 'aws.group.boundaries.' + kind if kind not in {'availability-zone', 'functional'} else ''
    return {'kind': kind, 'colour': colour, 'fill': fill, 'dashed': dashed, 'icon_key': icon}


def draw_boundary(draw, box, style):
    x, y, w, h = box
    draw.rectangle((x, y, x+w, y+h), fill=style['fill'])
    if not style['dashed']:
        draw.rectangle((x, y, x+w, y+h), outline=style['colour'], width=2)
        return
    for start in range(0, int(w)+1, 12):
        end = min(start+6, w)
        draw.line((x+start, y, x+end, y), fill=style['colour'], width=2)
        draw.line((x+start, y+h, x+end, y+h), fill=style['colour'], width=2)
    for start in range(0, int(h)+1, 12):
        end = min(start+6, h)
        draw.line((x, y+start, x, y+end), fill=style['colour'], width=2)
        draw.line((x+w, y+start, x+w, y+end), fill=style['colour'], width=2)
