import sys
from pathlib import Path
sys.path.insert(0,str(Path('backend/venv/Lib/site-packages').resolve()))
sys.path.insert(0,str(Path('backend').resolve()))
import base64,io,json
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from docx import Document
from app.diagram import conceptual_drawio
from app.document.document_builder import DocumentBuilder
plan={'zones':[{'label':k,'kind':k,'components':[{'id':str(i),'label':label,'technology':'','responsibility':'','evidence':'project request'}]} for i,(k,label) in enumerate([('channels','Receive request'),('application','Process request'),('outputs','Return result')])],'bands':[],'edges':[],'workflow':[{'component':str(i),'label':label} for i,label in enumerate(['Receive request','Process request','Return result'])]}
config=SimpleNamespace(ASSETS_DIR=Path('backend/assets'))
llm=SimpleNamespace(generate=lambda *a,**k:SimpleNamespace(text=json.dumps(plan)))
with patch.object(conceptual_drawio,'render_drawio',side_effect=RuntimeError('Desktop unavailable')):
    asset=conceptual_drawio.generate(llm,config,{},'project request',{})
Image.open(io.BytesIO(base64.b64decode(asset['image_base64']))).verify()
asset['following_sections']=['architecture_diagram']
builder=DocumentBuilder(config)
sections={'toc_structure':'1. Business Benefits\n2. Solution Architecture','conceptual_flow_asset':asset}
builder._parse_toc_entries(sections)
assert builder.toc_entries==['1. Business Benefits','2. Conceptual Flow Diagram','3. Solution Architecture'],builder.toc_entries
builder.doc=Document();builder.section_builder=object()
builder._build_section('Conceptual Flow Diagram',sections,{},1)
assert len(builder.doc.inline_shapes)==1
output=Path('backend/output/conceptual-recovery-verification.docx');builder.doc.save(output)
assert len(Document(output).inline_shapes)==1
print('PASS: draw.io failure recovery, valid PNG, section ordering, DOCX embedding and reopening')
