"""Replay conceptual generation with the selected architecture, not just the BRD."""
import argparse
import base64
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    from app.core.config import Config
    from app.diagram.service import DiagramService
    from app.diagram.conceptual_drawio import generate
    parser=argparse.ArgumentParser()
    parser.add_argument('--inputs',required=True)
    parser.add_argument('--architecture-audit',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    raw=json.loads(Path(args.inputs).read_text(encoding='utf-8-sig'))
    audit=json.loads(Path(args.architecture_audit).read_text(encoding='utf-8-sig'))
    spec=(audit['assets'][0] if 'assets' in audit else audit)['spec']
    req=raw['requirements']
    req['_conceptual_selected_architecture']={'nodes':spec['nodes'],
        'service_design':spec['architecture_plan'].get('service_design',{})}
    service=DiagramService(Config())
    try:
        asset=generate(service.llm,service.config,req,req.get('architecture_source_context',''),{})
        out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
        (out/'diagram.png').write_bytes(base64.b64decode(asset.pop('image_base64')))
        (out/'diagram.drawio').write_text(asset.pop('drawio_xml'),encoding='utf-8')
        asset.pop('edit_url',None)
        (out/'audit.json').write_text(json.dumps(asset,indent=2),encoding='utf-8')
        print('RESULT',asset['overview_metrics'])
    finally:
        service.bedrock.close()


if __name__=='__main__': main()
