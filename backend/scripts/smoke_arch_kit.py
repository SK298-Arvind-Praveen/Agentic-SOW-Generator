"""Offline optional-renderer check: run from backend, no AWS calls."""
from pathlib import Path
from dataclasses import replace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.diagram.arch_kit import render_arch_kit
from app.diagram.aws_icons import AwsIconRegistry
from app.diagram.service import validate_spec


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    registry = AwsIconRegistry(root / 'assets')
    bedrock = next(key for key, value in registry.by_key.items() if value['label'] == 'Amazon Bedrock')
    spec = validate_spec({
        'title': 'Offline renderer test',
        'nodes': [
            {'id': 'user', 'label': 'Customer', 'kind': 'actor', 'layer': 0},
            {'id': 'app', 'label': 'Support Application', 'kind': 'application', 'layer': 1},
            {'id': 'model', 'label': 'Amazon Bedrock', 'kind': 'ai', 'layer': 2},
        ],
        'edges': [{'source': 'user', 'target': 'app', 'label': 'Request'},
                  {'source': 'app', 'target': 'model', 'label': 'Inference'}],
    }, 'Offline renderer test', {})
    # Explicit known catalog icon for this offline fixture (no model selection).
    spec = replace(spec, nodes=spec.nodes[:-1] + (replace(spec.nodes[-1], icon_key=bedrock),))
    output = root / 'output' / 'arch_kit_smoke.png'
    output.parent.mkdir(exist_ok=True)
    output.write_bytes(render_arch_kit(spec, registry))
    print(output)
