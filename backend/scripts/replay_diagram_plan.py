"""Replay a saved model response through validation/layout without calling AWS."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.diagram.service import DiagramService, _extract_json, validate_spec, render_png
from app.diagram.aws_icons import AwsIconRegistry
from app.diagram.elk import layout
from types import SimpleNamespace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    config = SimpleNamespace(ASSETS_DIR=Path(__file__).resolve().parents[1] / 'assets')
    registry = AwsIconRegistry(config.ASSETS_DIR)
    payload = _extract_json(args.log.read_text(encoding='utf-8'))
    raw = payload.get('spec') or payload['diagrams'][0]
    # Offline diagnostic: allow only registry entries actually named by this
    # recorded response; never consult credentials or run the generation pipeline.
    candidates = registry.candidates({'aws_services': [n['label'] for n in raw['nodes']]}, '')
    service = DiagramService.__new__(DiagramService)
    service.icon_registry = registry
    spec = validate_spec(service._enrich_diagram(raw, 'architecture_overview',
                         {c.key: c for c in candidates}), 'Architecture', {c.key: c for c in candidates})
    print(f'Validated {len(spec.nodes)} nodes and {len(spec.edges)} edges')
    geometry = layout(spec, config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix('.geometry.json').write_text(json.dumps(geometry, indent=2), encoding='utf-8')
    args.output.write_bytes(render_png(spec, config, registry, layout_data=geometry))
    print(args.output)


if __name__ == '__main__':
    main()
