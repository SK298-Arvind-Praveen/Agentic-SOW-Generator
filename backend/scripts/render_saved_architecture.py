"""Local visual regression render from a saved architecture, no model calls."""
import argparse
import base64
import json
from dataclasses import replace
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    from app.core.config import Config
    from app.diagram.service import DiagramService, DiagramSpec, Node, Edge, Group
    from app.diagram.aws_icons import AwsIconRegistry
    parser = argparse.ArgumentParser()
    parser.add_argument('--audit', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = json.loads(Path(args.audit).read_text(encoding='utf-8'))
    raw = (report['assets'][0] if 'assets' in report else report)['spec']
    spec = DiagramSpec(raw['title'], tuple(Node(**n) for n in raw['nodes']), tuple(Edge(**e) for e in raw['edges']),
        groups=tuple(Group(**g) for g in raw.get('groups', [])), architecture_plan=raw['architecture_plan'])
    if not spec.architecture_plan.get('narrative_view'):
        spec = replace(spec, architecture_plan={**spec.architecture_plan,
            'deployment_overview': spec.architecture_plan.get('deployment_overview') or {'enabled': True}})
    service = DiagramService.__new__(DiagramService)
    service.config = Config()
    service.icon_registry = AwsIconRegistry(service.config.ASSETS_DIR)
    asset = service._asset('architecture_overview', 'Solution Architecture', spec, {}, False)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    (out/'diagram.png').write_bytes(base64.b64decode(asset['image_base64']))
    (out/'diagram.drawio').write_text(asset['drawio_xml'], encoding='utf-8')
    (out/'audit.json').write_text(json.dumps({k:v for k,v in asset.items() if k not in
        {'image_base64','drawio_xml','edit_url'}}, indent=2), encoding='utf-8')
    print('RESULT', asset['layout_engine'], asset['layout_metrics'])


if __name__ == '__main__':
    main()
