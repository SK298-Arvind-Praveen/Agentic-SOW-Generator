"""Re-render a local architecture review plan without calling AWS or an LLM."""
import argparse
import base64
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.diagram.aws_icons import AwsIconRegistry
from app.diagram.service import DiagramService, validate_spec


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('audit')
    parser.add_argument('output')
    args = parser.parse_args()
    report = json.loads(Path(args.audit).read_text(encoding='utf-8'))
    raw = report['original_spec']
    service = DiagramService.__new__(DiagramService)
    service.config = SimpleNamespace(ASSETS_DIR=Path(__file__).resolve().parents[1] / 'assets')
    service.icon_registry = AwsIconRegistry(service.config.ASSETS_DIR)
    candidates = service.icon_registry.candidates({'aws_services': [n['label'] for n in raw['nodes']]}, '')
    allowed = {c.key: c for c in candidates}
    # Correct icons from existing component labels; do not invent components.
    spec = validate_spec(service._enrich_diagram(raw, 'architecture_overview', allowed), raw['title'], allowed)
    asset = service._asset('architecture_overview', 'Solution Architecture', spec, {}, False)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(base64.b64decode(asset['image_base64']))
    print(json.dumps({'engine': asset['layout_engine'], 'metrics': asset['layout_metrics'], 'output': str(output)}))


if __name__ == '__main__':
    main()
