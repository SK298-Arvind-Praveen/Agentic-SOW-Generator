"""Replay a captured composition through the production renderer without model calls."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Config
from app.diagram.service import DiagramService, DiagramSpec, Node, Edge, Group, _extract_json
from app.diagram.aws_icons import AwsIconRegistry
from app.diagram import narrative

p = argparse.ArgumentParser()
p.add_argument('--audit', required=True)
p.add_argument('--plan', required=True)
p.add_argument('--output', required=True)
args = p.parse_args()
report = json.loads(Path(args.audit).read_text(encoding='utf8'))
raw = report['assets'][0]['spec']
raw['architecture_plan'].pop('narrative_diagnostic', None)
raw['architecture_plan']['narrative_view'] = _extract_json(Path(args.plan).read_text(encoding='utf8'))
spec = DiagramSpec(raw['title'], tuple(Node(**n) for n in raw['nodes']), tuple(Edge(**e) for e in raw['edges']),
    groups=tuple(Group(**g) for g in raw.get('groups', [])), architecture_plan=raw['architecture_plan'])
config = Config()
registry = AwsIconRegistry(config.ASSETS_DIR)
spec = narrative.improve_rows(spec, registry)
png, xml, details = narrative.render(spec, config, registry)
out = Path(args.output)
out.mkdir(parents=True, exist_ok=True)
(out/'diagram.png').write_bytes(png)
(out/'diagram.drawio').write_text(xml, encoding='utf8')
(out/'audit.json').write_text(json.dumps(details, indent=2), encoding='utf8')
print(json.dumps(details.get('overview_metrics'), indent=2))
