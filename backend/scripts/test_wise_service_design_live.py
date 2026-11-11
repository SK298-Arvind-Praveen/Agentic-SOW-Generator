"""Replay Wise through the shared service planner and real architecture renderer."""
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import Config
from app.diagram.service import DiagramService
from app.diagram.service_design import ensure_service_design


def main():
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / 'output/llm-debug/20261105T054810_418848Z_0024_Architecture_Inputs.txt').read_text(encoding='utf-8'))
    service = DiagramService(Config())
    req = data['requirements']
    out = root / 'output/wise-service-design'
    out.mkdir(parents=True, exist_ok=True)
    if '--reuse-design' in sys.argv:
        req['service_design'] = json.loads((out / 'service-design.json').read_text(encoding='utf-8'))
    design = ensure_service_design(service.llm, req, data['metadata'], req['architecture_source_context'])
    (out / 'service-design.json').write_text(json.dumps(design, indent=2), encoding='utf-8')
    assert design['status'] == 'ready', design
    req['service_design'] = design
    assets = service.generate_assets(req, data['metadata'], data['narrative'])
    asset = assets[0]
    (out / 'diagram.png').write_bytes(base64.b64decode(asset['image_base64']))
    (out / 'diagram.drawio').write_text(asset['drawio_xml'], encoding='utf-8')
    (out / 'audit.json').write_text(json.dumps({k: v for k, v in asset.items()
        if k not in {'image_base64', 'drawio_xml', 'edit_url'}}, indent=2), encoding='utf-8')
    assert not asset['used_fallback'], 'Unexpected generic architecture fallback'
    print('SELECTED:', ', '.join(s['name'] for s in design['services']))
    print('SAVED', out)


if __name__ == '__main__':
    main()
