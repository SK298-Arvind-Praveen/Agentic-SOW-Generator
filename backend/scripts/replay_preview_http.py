"""Live multipart/status API regression using Flask's in-process HTTP client.

Uses the application's existing TESTING identity and isolates cloud draft/archive
persistence. Upload parsing, source extraction, async worker, graph, model calls,
renderer and status response are the real localhost application code.
"""
import argparse
import base64
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf8',errors='replace')
    p=argparse.ArgumentParser()
    p.add_argument('--brd',required=True);p.add_argument('--company',required=True)
    p.add_argument('--title',required=True);p.add_argument('--output',required=True)
    args=p.parse_args();out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    from app.core import server
    from app.diagram.service import ASSET_KEY
    server.app.config['TESTING']=True
    # Do not create pretend-user cloud drafts. Neither callback participates in
    # requirements, model prompts, diagram layout or the returned preview content.
    def complete(preview_id,*a,**kw):
        with server.preview_lock:
            server.preview_storage[preview_id].update(status='ready',progress=100,auto_draft_enabled=False)
        return {'success':True}
    server._save_preview_as_draft=complete
    server._schedule_preview_auto_draft=lambda *a,**kw:None
    client=server.app.test_client()
    form={'mode':'POC','company_name':args.company,'project_name':args.title,
          'author_name':'Architecture regression','additional_details':'',
          'selected_sow_sections':json.dumps(['architecture_diagram']),
          'supporting_doc_count':'1','fast_mode':'true'}
    (out/'request.json').write_text(json.dumps(form,indent=2),encoding='utf8')
    with open(args.brd,'rb') as brd:
        response=client.post('/api/preview',data={**form,'supporting_docs':(brd,Path(args.brd).name)},content_type='multipart/form-data')
    accepted=response.get_json()
    (out/'accepted.json').write_text(json.dumps(accepted,indent=2),encoding='utf8')
    if response.status_code!=202:raise RuntimeError(f'Upload failed: {accepted}')
    preview_id=accepted['preview_id'];previous=None;deadline=time.monotonic()+2400
    while time.monotonic()<deadline:
        response=client.get('/api/preview/status/'+preview_id)
        state=response.get_json()
        marker=(state.get('status'),state.get('progress'),state.get('current_step'))
        if marker!=previous:print('[HTTP PREVIEW]',marker,flush=True);previous=marker
        if state.get('has_error'):raise RuntimeError(state.get('error'))
        if state.get('is_complete'):break
        time.sleep(2)
    else:raise TimeoutError('Live HTTP preview did not complete')
    (out/'response.json').write_text(json.dumps(state,indent=2,default=str),encoding='utf8')
    with server.preview_lock:
        final=server.preview_storage[preview_id]['final_state']
    (out/'final-state.json').write_text(json.dumps(final,indent=2,default=str),encoding='utf8')
    assets=state.get('content',{}).get(ASSET_KEY,[])
    for i,asset in enumerate(assets):
        if asset.get('image_base64'):(out/f'diagram-{i+1}.png').write_bytes(base64.b64decode(asset['image_base64']))
        if asset.get('drawio_xml'):(out/f'diagram-{i+1}.drawio').write_text(asset['drawio_xml'],encoding='utf8')
    audit={'preview_id':preview_id,'source_diagnostics':state.get('source_diagnostics'),
           'status':state.get('status'),'errors':final.get('errors',[]),'assets':[
               {k:v for k,v in a.items() if k not in {'image_base64','drawio_xml','edit_url'}} for a in assets]}
    (out/'audit.json').write_text(json.dumps(audit,indent=2,default=str),encoding='utf8')
    print('HTTP RESULT',json.dumps({'status':audit['status'],'assets':[
        {k:a.get(k) for k in ('status','layout_engine','layout_metrics','text_alignment','quality_warnings')} for a in assets]}),flush=True)
    if not assets or not all(a.get('image_base64') and not a.get('used_fallback') for a in assets):raise SystemExit(1)


if __name__=='__main__':main()
