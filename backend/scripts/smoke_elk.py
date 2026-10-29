"""Offline ELK render using a saved architecture plan; no Bedrock/API calls.

Run from backend: python scripts/smoke_elk.py [path/to/review.json]
"""
import base64
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.diagram.service import DiagramService, DiagramSpec, Node, Edge, Group
from app.diagram.aws_icons import AwsIconRegistry


def main():
    root = Path(__file__).resolve().parents[1]
    if len(sys.argv) > 1:
        report = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
        raw = report.get('selected_spec') or report.get('original_spec') or report
        spec = DiagramSpec(raw['title'], tuple(Node(**n) for n in raw['nodes']),
                           tuple(Edge(**e) for e in raw['edges']),
                           groups=tuple(Group(**g) for g in raw.get('groups', [])))
    else:
        spec = DiagramSpec('Offline ELK architecture test', (
            Node('user', 'Customer', 'actor', 0, scope='external'),
            Node('app', 'Application', 'application', 1, scope='vpc'),
            Node('model', 'Amazon Bedrock', 'service', 2, scope='managed'),
        ), (Edge('user', 'app', 'HTTPS'), Edge('app', 'model', 'Inference')))
    service = DiagramService.__new__(DiagramService)
    service.config = SimpleNamespace(ASSETS_DIR=root / 'assets')
    service.icon_registry = AwsIconRegistry(root / 'assets')
    os.environ['ARCHITECTURE_DIAGRAM_ENGINE'] = 'elk'
    asset = service._asset('architecture_overview', 'Solution Architecture', spec, {}, False)
    if asset['layout_engine'] != 'elk':
        raise RuntimeError(asset['renderer_fallback'])
    folder = root / 'output' / 'elk-smoke'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'architecture.png').write_bytes(base64.b64decode(asset['image_base64']))
    (folder / 'architecture.drawio').write_text(asset['drawio_xml'], encoding='utf-8')
    (folder / 'metrics.json').write_text(json.dumps(asset['layout_metrics'], indent=2), encoding='utf-8')
    print(folder / 'architecture.png')


if __name__ == '__main__':
    main()
