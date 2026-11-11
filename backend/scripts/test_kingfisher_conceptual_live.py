import sys,json,base64
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core.config import Config
from app.diagram.service import DiagramService
from app.diagram.conceptual_drawio import generate
root=Path(__file__).resolve().parents[1];config=Config();service=DiagramService(config)
data=json.loads((root/'output/llm-debug/20261104T103720_138940Z_0028_Architecture_Inputs.txt').read_text(encoding='utf8'))
asset=generate(service.llm,config,data['requirements'],data['requirements'].get('architecture_source_context',''),{})
out=root/'output/kingfisher-conceptual';out.mkdir(exist_ok=True)
(out/'kingfisher-live.png').write_bytes(base64.b64decode(asset.pop('image_base64')))
(out/'kingfisher-live.drawio').write_text(asset.pop('drawio_xml'),encoding='utf8')
asset.pop('edit_url',None);(out/'live-audit.json').write_text(json.dumps(asset,indent=2),encoding='utf8')
print('SAVED',out)
