"""Replay the exact recorded graph through the production overview renderer."""
import argparse,base64,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core.config import Config
from app.diagram.service import DiagramService,DiagramSpec,Node,Edge,Group

p=argparse.ArgumentParser();p.add_argument('--audit',required=True);p.add_argument('--output',required=True);p.add_argument('--review',action='store_true');p.add_argument('--inputs');a=p.parse_args()
raw=json.loads(Path(a.audit).read_text(encoding='utf8'));raw=raw.get('assets',[raw])[0]['spec']
plan=raw['architecture_plan'];plan['story_overview']=True
spec=DiagramSpec(raw['title'],tuple(Node(**n) for n in raw['nodes']),tuple(Edge(**e) for e in raw['edges']),
    groups=tuple(Group(**g) for g in raw.get('groups',[])),architecture_plan=plan)
s=DiagramService(Config());out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
try:
    if a.inputs:
        from app.preview.architecture_regeneration import regenerate
        from app.diagram.service import ASSET_KEY
        inputs=json.loads(Path(a.inputs).read_text(encoding='utf8'))
        content={'architecture_diagram':inputs['narrative'],ASSET_KEY:[{'spec':raw}]}
        state={'validated_requirements':inputs['requirements'],
            'supporting_context':inputs['requirements'].get('architecture_source_context') or json.dumps(inputs['requirements'])}
        result=regenerate({'content':content,'metadata':inputs['metadata'],'final_state':state},
            'Reduce crossings, use straight arrows and full-size icons with labels below. Keep the same architecture.',s.config,print)
        asset=result['content'][ASSET_KEY][0]
        assert asset['spec']['nodes']==raw['nodes'] and asset['spec']['edges']==raw['edges']
        assert result['content']['architecture_diagram']==content['architecture_diagram']
    else:
        asset=s._asset('architecture_overview','Solution Architecture',spec,{'project_title':spec.title},False)
    if a.review and not a.inputs:
        from app.diagram.narrative import review
        asset=review(s,asset,spec,{'project_title':spec.title})
    (out/'diagram.png').write_bytes(base64.b64decode(asset['image_base64']))
    (out/'diagram.drawio').write_text(asset['drawio_xml'],encoding='utf8')
    (out/'audit.json').write_text(json.dumps({k:v for k,v in asset.items() if k not in {'image_base64','drawio_xml','edit_url'}},indent=2),encoding='utf8')
    print(json.dumps({'metrics':asset['layout_metrics'],'review':asset.get('vision_review')},default=str),flush=True)
finally:s.bedrock.close()
