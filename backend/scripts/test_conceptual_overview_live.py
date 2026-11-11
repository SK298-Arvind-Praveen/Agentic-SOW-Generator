import sys,json,base64,argparse,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core.config import Config
from app.diagram.service import DiagramService
from app.diagram.conceptual_drawio import generate
parser=argparse.ArgumentParser();parser.add_argument('--case',choices=['kingfisher','itsm'],default='kingfisher');parser.add_argument('--round',default='1');parser.add_argument('--revise',type=Path);args=parser.parse_args()
root=Path(__file__).resolve().parents[1];config=Config();service=DiagramService(config)
if args.case=='kingfisher':
 data=json.loads((root/'output/llm-debug/20261104T103720_138940Z_0028_Architecture_Inputs.txt').read_text(encoding='utf8'))
 requirements=data['requirements'];source=requirements.get('architecture_source_context','')
else:
 with zipfile.ZipFile(Path.home()/'Downloads/Agentic_AI_ITSM_BRD.docx') as archive:
  tree=ET.fromstring(archive.read('word/document.xml'));ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
  source='\n'.join(''.join(t.text or '' for t in p.findall('.//w:t',ns)) for p in tree.findall('.//w:p',ns))
 requirements={'project_overview':'Agentic AI for internal IT service management using Freshdesk and Jira'}
previous=json.loads(args.revise.read_text(encoding='utf8'))['plan'] if args.revise else None
feedback=("Keep every component ID, zone ID, zone membership, edge and layer_link unchanged. "
          "Revise ONLY visible wording. Title: Kingfisher Catalogue: AWS Migration POC. "
          "Rename the support panel to Controls and support. Replace Delta reconcile with Keep all writes. "
          "Use AWS DMS as the Database replication qualifier. Rename Migration ledger to Migration log "
          "with qualifier Record checks. Leave the rest unchanged. Do not introduce extra details.") if previous else None
asset=generate(service.llm,config,requirements,source,{},previous_plan=previous,review_feedback=feedback)
if previous:
 assert [[c['id'] for c in g['components']] for g in asset['plan']['zones']+asset['plan']['bands']]==[[c['id'] for c in g['components']] for g in previous['zones']+previous['bands']]
 assert asset['plan']['edges']==previous['edges']
 assert asset['plan']['layer_links']==previous['layer_links']
out=root/'output/conceptual-overview-tests'/f'{args.case}-{args.round}';out.mkdir(parents=True,exist_ok=True)
(out/'diagram.png').write_bytes(base64.b64decode(asset.pop('image_base64')))
(out/'diagram.drawio').write_text(asset.pop('drawio_xml'),encoding='utf8');asset.pop('edit_url',None)
plan=asset['plan'];groups=plan['zones']+plan.get('bands',[]);components=[c for g in groups for c in g['components']]
visible=[plan.get('title','')]+[g['label'] for g in groups]+[c[k] for c in components for k in ('label','technology')]+[e['label'] for e in plan.get('layer_links',[])]
asset['assessment']={'visible_words':sum(len(s.split()) for s in visible),'layers':len(plan['zones']),'support_panels':len(plan.get('bands',[])),'components':len(components),'max_label_words':max(len(c['label'].split()) for c in components),'visible_links':len(plan.get('layer_links',[]))}
(out/'audit.json').write_text(json.dumps(asset,indent=2),encoding='utf8');print('SAVED',out,asset['assessment'],flush=True)
