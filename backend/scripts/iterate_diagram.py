"""Reproduce the diagram stage from captured inputs without saving a SOW.

--live explicitly permits Bedrock calls. Without it, replay the supplied response.
Inputs and results stay local; no DynamoDB or S3 writes are performed.
"""
import argparse
import base64
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import Config
from app.core.authoring_context import boundary_summary
from app.diagram.service import DiagramService, _extract_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, help='Exact Architecture Inputs snapshot from a pipeline run')
    parser.add_argument('--requirements', type=Path)
    parser.add_argument('--scope', type=Path)
    parser.add_argument('--narrative', type=Path)
    parser.add_argument('--company')
    parser.add_argument('--project')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--response', type=Path)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--review-replay', action='store_true',
                        help='Explicitly enable Bedrock vision review of a saved planner response')
    parser.add_argument('--layout-variant', choices=['auto','lanes'], default='auto',
                        help='Diagnostic render; auto uses the production layout selection')
    args = parser.parse_args()
    if not args.live and not args.response:
        parser.error('Use --response for offline replay or --live for Bedrock')
    if args.inputs:
        inputs = json.loads(args.inputs.read_text(encoding='utf-8'))
        requirements, metadata, narrative = (inputs[k] for k in ('requirements', 'metadata', 'narrative'))
    else:
        if not all((args.requirements, args.scope, args.narrative, args.company, args.project)):
            parser.error('Supply --inputs OR requirements, scope, narrative, company and project')
        requirements = _extract_json(args.requirements.read_text(encoding='utf-8'))
        requirements['scope_boundaries'] = boundary_summary(_extract_json(args.scope.read_text(encoding='utf-8')))
        metadata = {'company_name': args.company, 'project_title': args.project}
        narrative = args.narrative.read_text(encoding='utf-8')
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'inputs.json').write_text(json.dumps(dict(requirements=requirements,
        metadata=metadata, narrative=narrative), indent=2), encoding='utf-8')
    service = DiagramService(Config())
    from app.diagram import elk
    production_layout = elk.layout
    def diagnostic_layout(spec, config, *positional, **kw):
        if args.layout_variant == 'lanes':
            kw.update(_optimize=False, _flow_direction='LANES', _compound=True, _iconic=True)
        data = production_layout(spec, config, *positional, **kw)
        (args.output / 'layout.json').write_text(json.dumps(data,indent=2), encoding='utf-8')
        return data
    elk.layout = diagnostic_layout
    if not args.live:
        from types import SimpleNamespace
        service.llm = SimpleNamespace(generate=lambda *a, **kw:
            SimpleNamespace(text=args.response.read_text(encoding='utf-8')))
        if not args.review_replay:
            del service.bedrock  # No vision call in offline mode.
    assets = service.generate_assets(requirements, metadata, narrative)
    for index, asset in enumerate(assets):
        (args.output / f'diagram-{index}.png').write_bytes(base64.b64decode(asset['image_base64']))
        (args.output / f'diagram-{index}.drawio').write_text(asset['drawio_xml'], encoding='utf-8')
        (args.output / f'diagram-{index}.json').write_text(json.dumps(
            {k:v for k,v in asset.items() if k not in {'image_base64', 'drawio_xml', 'edit_url'}}, indent=2), encoding='utf-8')
        print(f"RESULT: fallback={asset['used_fallback']}, nodes={len(asset['spec']['nodes'])}, "
              f"metrics={asset.get('layout_metrics')}", flush=True)


if __name__ == '__main__':
    main()
