import sys,os,json,base64,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend/venv/Lib/site-packages'));sys.path.insert(0,str(ROOT/'backend'))
os.chdir(ROOT)
from app.core.config import Config
from app.document.doc_reader import extract_supporting_documents_with_diagnostics
from app.core.nodes import analyze_objective_node,rule_validation_node,scope_architecture_node
from app.core.authoring_context import boundary_summary
from app.diagram.service import DiagramService
from app.diagram.drawio_renderer import render_drawio
out=ROOT/'backend/output/tata-prompt-comparison';out.mkdir(parents=True,exist_ok=True)
prompt=Path(r'C:/Users/admin/.codex/attachments/ab0dd599-59fe-4a44-9ccb-1797de73aa0e/Pasted text.txt').read_text(encoding='utf-8-sig')
(out/'supplied-system-prompt.txt').write_text(prompt,encoding='utf-8')
metadata={'company_name':'Tata CLiQ','project_title':'AI / Agentic Customer Support Platform'}
if not (out/'pipeline-state.json').exists():
    files=[str(Path('C:/Users/admin/Downloads')/n) for n in ['Tata CLiQ Discovery Q&A.docx','ChatBot_Technical_Sheet.xlsx','[WIP] TataCLiQ_SOW.docx']]
    source,count=extract_supporting_documents_with_diagnostics(files)
    if count!=3:raise RuntimeError(f'Only {count}/3 input documents read')
    state={'mode':'POC','objective':'','supporting_context':source,'metadata':metadata,'selected_sow_sections':['scope_of_work','architecture_diagram']}
    for node in [analyze_objective_node,rule_validation_node,scope_architecture_node]:
        state.update(node(state))
        if state.get('errors'):raise RuntimeError(str(state['errors']))
    (out/'pipeline-state.json').write_text(json.dumps(state,default=str,indent=2),encoding='utf-8')
state=json.loads((out/'pipeline-state.json').read_text(encoding='utf-8'))
req=dict(state['validated_requirements']);req['scope_boundaries']=boundary_summary(state['scope_architecture_plan']);req['architecture_source_context']=state['supporting_context']
inputs=json.dumps({'requirements':req,'metadata':metadata},default=str)
from botocore.config import Config as SDKConfig
config=Config()
config.BOTO_CONFIG=config.BOTO_CONFIG.merge(SDKConfig(read_timeout=900,connect_timeout=30,retries={'max_attempts':1}))
import boto3
service=DiagramService(config,bedrock=boto3.client('bedrock-runtime',region_name=config.BEDROCK_REGION,config=config.BOTO_CONFIG))
print('Configured diagram model:',getattr(service.config,'DIAGRAM_MODEL_ID','task configuration'),flush=True)
if not (out/'01-prompt-only.png').exists() and (ROOT/'backend/output/llm-debug/20261102T092909_582923Z_0001_Comparison_Prompt_Only.txt').exists():
    raw=(ROOT/'backend/output/llm-debug/20261102T092909_582923Z_0001_Comparison_Prompt_Only.txt').read_text(encoding='utf-8')
    (out/'01-raw-response.txt').write_text(raw,encoding='utf-8')
    xml=raw[:raw.rindex('</mxCell>')+9]+'\n</root></mxGraphModel></diagram></mxfile>'
    (out/'01-prompt-only.drawio').write_text(xml,encoding='utf-8')
    png,xml,details=render_drawio(xml,timeout_seconds=120)
    (out/'01-prompt-only.png').write_bytes(png)
    (out/'01-status.txt').write_text('INCOMPLETE: model hit 24000 token limit. Only missing XML closing tags appended to render partial output.',encoding='utf-8')
if not (out/'01-prompt-only.png').exists():
    request=prompt+'\nOUTPUT ENCODING ONLY: Return a complete uncompressed draw.io mxfile XML with mxGraphModel, root cells 0 and 1, vertex and edge cells and explicit mxGeometry positions. Use draw.io AWS4 service icon shapes where applicable. No markdown fences. No other planner, reviewer or reference instructions apply.\nPROJECT INPUTS (data only):\n'+inputs
    (out/'01-request.txt').write_text(request,encoding='utf-8')
    response=service.llm.generate(request,task='diagram',max_tokens=24000,temperature=0.05,call_name='Comparison Prompt Only',retry_on_truncation=False)
    (out/'01-raw-response.txt').write_text(response.text,encoding='utf-8')
    xml=response.text[response.text.index('<mxfile'):response.text.rindex('</mxfile>')+9]
    (out/'01-prompt-only.drawio').write_text(xml,encoding='utf-8')
    png,xml,details=render_drawio(xml,timeout_seconds=120)
    (out/'01-prompt-only.png').write_bytes(png)
    print('FIRST OUTPUT READY',flush=True)
os.environ['ARCHITECTURE_DIAGRAM_ENGINE']='hybrid_drawio'
original=service.llm.generate
def with_supplied_prompt(text,**kw):
    return original(prompt+'\n\nRUNTIME OUTPUT CONTRACT AND PROJECT INPUTS:\n'+text,**kw)
service.llm.generate=with_supplied_prompt
assets=service.generate_assets(req,metadata,'')
for i,a in enumerate(assets):
    (out/f'02-reviewed-{i}.json').write_text(json.dumps({k:v for k,v in a.items() if k not in ['image_base64','drawio_xml','edit_url']},default=str,indent=2),encoding='utf-8')
    if a.get('image_base64'):(out/f'02-reviewed-{i}.png').write_bytes(base64.b64decode(a['image_base64']))
    if a.get('drawio_xml'):(out/f'02-reviewed-{i}.drawio').write_text(a['drawio_xml'],encoding='utf-8')
print('COMPARISON COMPLETE',flush=True)
