"""Render an inspectable sheet of the exact boundary SVGs used by the app."""
import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.diagram.aws_icons import AwsIconRegistry
from app.diagram.boundary_style import boundary_header, BOUNDARY_HEADER_VERSION

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);args=p.parse_args()
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    registry=AwsIconRegistry(Path(__file__).resolve().parents[1]/'assets')
    kinds=['cloud','account','region','vpc','az','public','private','isolated']
    parts=['<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1000" height="420"><rect width="1000" height="420" fill="white"/>']
    inventory=[]
    for i,kind in enumerate(kinds):
        label,uri=boundary_header(kind,registry)
        if not uri:raise ValueError('Missing boundary badge: '+kind)
        x=30+(i%4)*250;y=20+(i//4)*200
        parts.append(f'<rect x="{x}" y="{y}" width="220" height="175" rx="8" fill="#F8FAFC" stroke="#CBD5E1"/>')
        parts.append(f'<image x="{x+70}" y="{y+20}" width="80" height="80" xlink:href="{uri}"/>')
        parts.append(f'<text x="{x+110}" y="{y+132}" text-anchor="middle" font-family="Arial" font-size="19" fill="#12325A">{html.escape(label)}</text>')
        source='Custom AZ badge' if kind=='az' else 'Bundled AWS icon'
        parts.append(f'<text x="{x+110}" y="{y+156}" text-anchor="middle" font-family="Arial" font-size="13" fill="#64748B">{source}</text>')
        inventory.append({'kind':kind,'label':label,'source':source,'available':True})
    svg=out/'boundary-icons.svg';svg.write_text(''.join(parts)+'</svg>',encoding='utf8')
    from resvg_py import svg_to_bytes
    (out/'boundary-icons.png').write_bytes(svg_to_bytes(svg_path=str(svg),width=1000,height=420))
    (out/'inventory.json').write_text(json.dumps({'version':BOUNDARY_HEADER_VERSION,'icons':inventory},indent=2),encoding='utf8')
    print('Rendered',out/'boundary-icons.png')

if __name__=='__main__':main()
