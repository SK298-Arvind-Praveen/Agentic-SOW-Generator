"""Replay a saved validated asset, optionally making a live visual review only."""
import argparse
import base64
import json
from pathlib import Path
import sys
from dataclasses import replace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core.config import Config
from app.diagram.service import DiagramService, DiagramSpec, Node, Edge, Group

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('asset',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--review',action='store_true')
    parser.add_argument('--inspect-candidates',action='store_true')
    args=parser.parse_args()
    previous=json.loads(args.asset.read_text(encoding='utf-8'))
    raw=previous['spec']
    spec=DiagramSpec(raw['title'],tuple(Node(**n) for n in raw['nodes']),
        tuple(Edge(**e) for e in raw['edges']),groups=tuple(Group(**g) for g in raw.get('groups',[])),
        architecture_plan=raw.get('architecture_plan',{}))
    spec=replace(spec,nodes=tuple(replace(n,subtitle='') for n in spec.nodes))
    service=DiagramService(Config())
    asset=service._asset('architecture_overview','Solution Architecture',spec,{},previous['used_fallback'])
    if args.review:
        from app.agents.architecture_reviewer_agent import review_architecture
        asset=review_architecture(service,asset,spec,{}, {},'')
    args.output.mkdir(parents=True,exist_ok=True)
    if args.inspect_candidates:
        import time
        from app.diagram.hybrid import compose, topology_composition
        from app.diagram.service import render_png
        geometry=compose(spec,service.config,topology_composition(spec,service.config),time.monotonic()+10)
        (args.output/'reference.png').write_bytes(render_png(spec,service.config,service.icon_registry,geometry))
        (args.output/'reference-layout.json').write_text(json.dumps(geometry,indent=2),encoding='utf-8')
    (args.output/'diagram.png').write_bytes(base64.b64decode(asset['image_base64']))
    (args.output/'diagram.drawio').write_text(asset['drawio_xml'],encoding='utf-8')
    (args.output/'asset.json').write_text(json.dumps({k:v for k,v in asset.items()
        if k not in {'image_base64','drawio_xml','edit_url'}},indent=2),encoding='utf-8')
    print(args.output)

if __name__=='__main__':
    main()
