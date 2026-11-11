import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core.config import Config
from app.diagram.conceptual_drawio import validate,render_layered,xml_for
config=Config();root=Path(__file__).resolve().parents[1];out=root/'output/kingfisher-conceptual';out.mkdir(exist_ok=True)
for file in sorted((root/'output/llm-debug').glob('20261104T104*Plan.txt')):
 plan=json.loads(file.read_text(encoding='utf8').strip().removeprefix('```json').removesuffix('```'))
 validate(plan)
 print(file.name,'VALID',len(plan['zones']),'layers',sum(len(g['components']) for g in plan['zones']+plan.get('bands',[])),'components',len(plan['edges']),'relationships')
(out/'kingfisher-layered.png').write_bytes(render_layered(plan,config))
(out/'kingfisher-layered.drawio').write_text(xml_for(plan,config),encoding='utf8')
(out/'plan.json').write_text(json.dumps(plan,indent=2),encoding='utf8')
