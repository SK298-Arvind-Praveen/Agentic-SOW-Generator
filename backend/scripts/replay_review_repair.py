"""Replay a recorded failed review through production repair and live re-review.

The first result is explicitly recorded evidence, not a new model review. All
subsequent work uses the unmodified production renderer and Bedrock reviewer.
"""
import argparse
import base64
import copy
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    from app.core.config import Config
    from app.diagram.service import DiagramService
    parser=argparse.ArgumentParser()
    for name in ('failed-audit','failed-image','failed-drawio','inputs','output'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    recorded=json.loads(Path(args.failed_audit).read_text(encoding='utf-8'))
    seed=recorded['assets'][0] if 'assets' in recorded else recorded
    seed['image_base64']=base64.b64encode(Path(args.failed_image).read_bytes()).decode()
    seed['drawio_xml']=Path(args.failed_drawio).read_text(encoding='utf-8')
    inputs=json.loads(Path(args.inputs).read_text(encoding='utf-8'))
    service=DiagramService(Config());original=service._generate_assets_once
    initial=True
    def recorded_then_live(*a,**kw):
        nonlocal initial
        if initial:
            initial=False
            print('REPLAY: first review is the recorded failing result',flush=True)
            return [copy.deepcopy(seed)]
        return original(*a,**kw)
    service._generate_assets_once=recorded_then_live
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    try:
        asset=service.generate_assets(inputs['requirements'],inputs['metadata'],inputs['narrative'])[0]
        (out/'diagram.png').write_bytes(base64.b64decode(asset['image_base64']))
        (out/'diagram.drawio').write_text(asset['drawio_xml'],encoding='utf-8')
        (out/'audit.json').write_text(json.dumps({k:v for k,v in asset.items()
            if k not in {'image_base64','drawio_xml','edit_url'}},indent=2),encoding='utf-8')
        print('RESULT',asset.get('status'),asset.get('layout_metrics'),flush=True)
        print('REVIEW',asset.get('vision_review'),flush=True)
    finally:
        service.bedrock.close()


if __name__=='__main__':main()
