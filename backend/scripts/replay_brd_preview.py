"""Live production preview graph from the same title/company/BRD/section inputs.

No preselected services or saved graphs. Only cloud draft persistence and HTTP UI
transport are omitted; document extraction and every preview graph node run normally.
"""
import argparse, base64, json, sys, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def main():
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8',errors='replace')
    p=argparse.ArgumentParser()
    p.add_argument('--brd',required=True);p.add_argument('--company',required=True)
    p.add_argument('--title',required=True);p.add_argument('--output',required=True)
    a=p.parse_args(); out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    from app.document.doc_reader import extract_supporting_documents_with_diagnostics
    from app.core.graph import create_fast_preview_graph
    from app.core.nodes import start_token_usage,get_token_usage
    from app.diagram.service import ASSET_KEY
    source,count=extract_supporting_documents_with_diagnostics([a.brd])
    if count!=1 or not source:raise RuntimeError('BRD extraction failed')
    state={'metadata':{'company_name':a.company,'project_title':a.title,'author_org':'Shellkode',
             'author_name':'Architecture review','selected_sow_sections':['architecture_diagram']},
        'objective':'','additional_details':'','mode':'POC','supporting_documents':[a.brd],
        'supporting_context':source,'selected_sow_sections':['architecture_diagram'],
        'errors':[],'current_step':'start','pricing_result':None,'preview_started_at':time.perf_counter()}
    (out/'request.json').write_text(json.dumps(state,indent=2),encoding='utf8')
    state['progress_callback']=lambda n,s:print(f'[LIVE PREVIEW] {n}% {s}',flush=True)
    run_id='LIVE_'+out.name;start_token_usage(run_id)
    final=create_fast_preview_graph().invoke(state)
    final.pop('progress_callback',None)
    (out/'final-state.json').write_text(json.dumps(final,indent=2,default=str),encoding='utf8')
    assets=(final.get('poc_content') or {}).get(ASSET_KEY,[])
    for i,asset in enumerate(assets):
        if asset.get('image_base64'):(out/f'diagram-{i+1}.png').write_bytes(base64.b64decode(asset['image_base64']))
        if asset.get('drawio_xml'):(out/f'diagram-{i+1}.drawio').write_text(asset['drawio_xml'],encoding='utf8')
    result={'errors':final.get('errors',[]),'assets':[{k:v for k,v in x.items() if k not in
        {'image_base64','drawio_xml','edit_url'}} for x in assets],'usage':get_token_usage(run_id)}
    (out/'audit.json').write_text(json.dumps(result,indent=2,default=str),encoding='utf8')
    print('LIVE RESULT',json.dumps({'errors':result['errors'],'assets':[
        {k:x.get(k) for k in ('status','layout_engine','layout_metrics','vision_review')} for x in assets]}),flush=True)
    if final.get('errors') or not any(x.get('image_base64') for x in assets):raise SystemExit(1)

if __name__=='__main__':main()
