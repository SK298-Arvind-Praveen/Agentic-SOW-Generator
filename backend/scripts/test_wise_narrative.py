import argparse
import base64
import json
from pathlib import Path
import sys
from dataclasses import replace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core.config import Config
from app.diagram.service import DiagramService, DiagramSpec, Node, Edge, Group
from app.diagram.narrative import prepare, render, validate

parser=argparse.ArgumentParser()
parser.add_argument('--live-plan',action='store_true')
parser.add_argument('--review',action='store_true')
parser.add_argument('--output',default='output/wise-narrative')
args=parser.parse_args()
raw=json.loads(Path('output/wise-service-design/audit.json').read_text(encoding='utf8'))['spec']
spec=DiagramSpec(raw['title'],tuple(Node(**n) for n in raw['nodes']),tuple(Edge(**e) for e in raw['edges']),
                 groups=tuple(Group(**g) for g in raw.get('groups',[])),architecture_plan=raw['architecture_plan'])
service=DiagramService(Config())
out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
if args.live_plan:
    spec=prepare(service,spec)
    plan=spec.architecture_plan['narrative_view']
else:
    plan=json.loads((out/'plan.json').read_text(encoding='utf8'))
    validate(plan,spec)
    spec=replace(spec,architecture_plan={**spec.architecture_plan,'narrative_view':plan})
(out/'plan.json').write_text(json.dumps(plan,indent=2),encoding='utf8')
asset=service._asset('architecture_overview','Solution Architecture',spec,{'project_title':'Wise document verification'},False)
if args.review:
    from app.diagram.narrative import review
    asset=review(service,asset,spec,{'project_title':'Wise document verification'})
png=base64.b64decode(asset['image_base64'])
xml=asset['drawio_xml']
metrics=asset['renderer_details']
(out/'diagram.png').write_bytes(png)
(out/'diagram.drawio').write_text(xml,encoding='utf8')
(out/'audit.json').write_text(json.dumps({k:v for k,v in asset.items() if k not in {'image_base64','drawio_xml','edit_url'}},indent=2),encoding='utf8')
print('SAVED',out)
