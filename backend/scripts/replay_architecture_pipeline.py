"""Run the production architecture pipeline from an approved input snapshot."""
import argparse
import base64
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from app.core.config import Config
    from app.diagram.service import DiagramService
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--reuse-design', help='Reuse a source-fingerprint-validated service design, still generate a fresh graph')
    args = parser.parse_args()
    raw = json.loads(Path(args.inputs).read_text(encoding='utf-8-sig'))
    if args.reuse_design:
        prior = json.loads(Path(args.reuse_design).read_text(encoding='utf-8-sig'))
        raw['requirements']['service_design'] = prior['spec']['architecture_plan']['service_design']
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    service = DiagramService(Config())
    try:
        assets = service.generate_assets(raw['requirements'], raw['metadata'], raw['narrative'])
        asset = assets[0]
        (out/'diagram.png').write_bytes(base64.b64decode(asset['image_base64']))
        (out/'diagram.drawio').write_text(asset['drawio_xml'], encoding='utf-8')
        (out/'audit.json').write_text(json.dumps({k:v for k,v in asset.items()
            if k not in {'image_base64','drawio_xml','edit_url'}}, indent=2), encoding='utf-8')
        print('RESULT', asset.get('status'), asset.get('layout_engine'), asset.get('layout_metrics'))
        print('WARNINGS', asset.get('validation_warnings'))
    finally:
        service.bedrock.close()


if __name__ == '__main__':
    main()
