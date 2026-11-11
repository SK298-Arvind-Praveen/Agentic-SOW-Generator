"""Replay a saved architecture with fresh grouping and actual image review."""
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
    from app.diagram.narrative import prepare, review
    parser = argparse.ArgumentParser()
    parser.add_argument('--audit',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--reuse-plan',action='store_true')
    args = parser.parse_args()
    report = json.loads(Path(args.audit).read_text(encoding='utf8'))
    raw = (report['assets'][0] if 'assets' in report else report)['spec']
    spec = DiagramSpec(raw['title'],tuple(Node(**n) for n in raw['nodes']),tuple(Edge(**e) for e in raw['edges']),
        groups=tuple(Group(**g) for g in raw.get('groups',[])),architecture_plan=raw['architecture_plan'])
    out = Path(args.output)
    out.mkdir(parents=True,exist_ok=True)
    if not args.reuse_plan:
        spec = replace(spec,architecture_plan={k:v for k,v in spec.architecture_plan.items() if k!='narrative_view'})
    if any(n.scope in {'vpc','az'} for n in spec.nodes):
        spec = replace(spec,architecture_plan={**spec.architecture_plan,'functional_deployment_view':True})
    # Apply the same aggregate placement rule as the production graph normalizer.
    import re
    spec = replace(spec, nodes=tuple(replace(n, availability_zone='') if 'rds' in n.icon_key
        and re.search(r'Multi[ -]AZ', n.label, re.I) and not re.search(r'primary|writer|standby|replica', n.label, re.I)
        else n for n in spec.nodes))
    service = DiagramService(Config())
    try:
        spec = prepare(service,spec)
        (out/'plan-audit.json').write_text(json.dumps({'spec':spec.as_dict()},indent=2),encoding='utf8')
        if not spec.architecture_plan.get('narrative_view'):
            raise RuntimeError(spec.architecture_plan.get('narrative_diagnostic','No overview'))
        asset = service._asset('architecture_overview','Solution Architecture',spec,{'project_title':spec.title},False)
        asset = review(service,asset,spec,{'project_title':spec.title})
        (out/'diagram.png').write_bytes(base64.b64decode(asset['image_base64']))
        (out/'diagram.drawio').write_text(asset['drawio_xml'],encoding='utf8')
        (out/'audit.json').write_text(json.dumps({k:v for k,v in asset.items() if k not in
            {'image_base64','drawio_xml','edit_url'}},indent=2),encoding='utf8')
        print('SAVED',out,json.dumps(asset['vision_review'], ensure_ascii=True))
    finally:
        service.bedrock.close()


if __name__=='__main__':
    main()
