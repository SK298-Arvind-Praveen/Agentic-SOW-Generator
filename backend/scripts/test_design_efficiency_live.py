"""Replay saved source through the actual preview graph, without UI or mocks."""
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding='utf-8'))
    requirements = data['requirements']
    source = requirements.get('architecture_source_context')
    if not source:
        raise ValueError('Saved input has no original source; do not test generated prose as BRD')
    from app.core.graph import create_fast_preview_graph
    from app.core.nodes import start_token_usage, get_token_usage, unbind_token_usage
    args.output.mkdir(parents=True, exist_ok=True)
    run = 'EFFICIENCY_' + str(time.time_ns())
    token = start_token_usage(run)
    started = time.perf_counter()
    state = dict(metadata=data['metadata'], objective=requirements.get('_generation_guidance', ''),
                 supporting_context=source, mode='POC',
                 selected_sow_sections=data['metadata'].get('selected_sow_sections'),
                 current_step='start', errors=[], preview_started_at=started)
    try:
        result = create_fast_preview_graph().invoke(state)
        (args.output / 'result.json').write_text(json.dumps(result, default=str, ensure_ascii=False), encoding='utf-8')
        if result.get('errors'):
            raise RuntimeError(str(result['errors']))
        design = result['validated_requirements']['service_design']
        assert design['status'] == 'ready', design.get('error')
        print('LIVE COMPLETE', design['status'], 'requirements', len(design.get('requirement_ledger', [])))
    finally:
        (args.output / 'timing.json').write_text(json.dumps({
            'elapsed_seconds':time.perf_counter()-started, 'usage':get_token_usage(run)}, indent=2), encoding='utf-8')
        unbind_token_usage(token)

if __name__ == '__main__':
    main()
