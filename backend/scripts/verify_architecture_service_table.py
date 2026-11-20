"""Live regression: accepted BRD design -> production diagram -> table -> DOCX.

Preserves the approved component graph so this presentation change cannot redesign
an already agreed solution. Model visual review and service-role generation are live.
"""
import argparse
import base64
import copy
import hashlib
from html import unescape
import json
from pathlib import Path
import sys
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    from app.core.config import Config
    from app.diagram.service import DiagramService, ASSET_KEY
    from app.diagram.architecture_text import synchronize, service_nodes, flow_order
    from app.core.sow_presentation import presentation_issues
    from app.document.document_builder import DocumentBuilder
    from docx import Document
    p=argparse.ArgumentParser()
    p.add_argument('--inputs',required=True)
    p.add_argument('--audit',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--runs',type=int,default=2)
    args=p.parse_args()
    source=json.loads(Path(args.inputs).read_text(encoding='utf-8-sig'))
    prior=json.loads(Path(args.audit).read_text(encoding='utf-8-sig'))
    baseline=prior['spec']
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
    config=Config();config.PRECOMPUTE_DOCUMENT_FIELDS=False
    service=DiagramService(config)
    results=[]
    try:
        for run in range(1,args.runs+1):
            folder=out/f'run-{run}';folder.mkdir(exist_ok=True)
            requirements=copy.deepcopy(source['requirements'])
            requirements['_architecture_retry_spec']=copy.deepcopy(baseline)
            requirements.pop('_architecture_retry_feedback',None)
            print(f'LIVE RUN {run}: diagram',flush=True)
            assets=service.generate_assets(requirements,source['metadata'],source.get('narrative',''))
            asset=assets[0]
            pixels=base64.b64decode(asset['image_base64'])
            (folder/'diagram.png').write_bytes(pixels)
            (folder/'diagram.drawio').write_text(asset['drawio_xml'],encoding='utf-8')
            content={'architecture_diagram':source.get('narrative',''), ASSET_KEY:assets,
                     'toc_structure':'1. Solution Architecture'}
            # This is the same synchronizer used by initial generation and regeneration.
            synchronize(service.llm,content,assets,requirements)
            table=content['architecture_diagram']
            (folder/'service-table.md').write_text(table,encoding='utf-8')
            (folder/'audit.json').write_text(json.dumps({k:v for k,v in asset.items() if k not in
                {'image_base64','drawio_xml','edit_url'}},indent=2),encoding='utf-8')
            assert asset.get('text_alignment',{}).get('status')=='aligned', asset.get('text_alignment')
            assert not presentation_issues(table,'architecture_diagram')
            alignment = asset['text_alignment']
            covered = [node_id for group in alignment['row_component_ids'] for node_id in group]
            assert sorted(covered)==sorted(n['id'] for n in service_nodes(asset['spec']))
            assert len(alignment['row_component_ids'])==alignment['row_count']
            assert asset['spec']['nodes']==baseline['nodes'], 'Node semantics changed'
            assert asset['spec']['edges']==baseline['edges'], 'Connections changed'
            config.OUTPUT_DIR=folder
            metadata={**source['metadata'],'selected_sow_sections':['architecture_diagram']}
            path=DocumentBuilder(config).build_document(content,metadata,'POC')
            document=Document(path)
            tables=[t for t in document.tables if t.cell(0,0).text=='Service name']
            assert len(tables)==1 and len(tables[0].rows)==alignment['row_count']+1
            expected=[[unescape(c.strip()) for c in line.strip('|').split('|')]
                      for line in table.splitlines()[2:]]
            assert [[c.text for c in row.cells] for row in tables[0].rows[1:]] == expected
            with zipfile.ZipFile(path) as z:
                assert any(z.read(n)==pixels for n in z.namelist() if n.startswith('word/media/'))
            row={'run':run,'diagram_status':asset.get('status'),'used_fallback':asset.get('used_fallback'),
                 'table_audit':asset['text_alignment'],'document':str(path),
                 'flow_order':flow_order(asset['spec']),'diagram_sha256':hashlib.sha256(pixels).hexdigest(),
                 'metrics':asset.get('layout_metrics'),'warnings':asset.get('validation_warnings',[])}
            results.append(row)
            (out/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
            print('TABLE/EXPORT PASS',json.dumps(row),flush=True)
        assert all(r['diagram_status']=='ready' and not r['used_fallback'] for r in results), \
            'Tables exported, but at least one diagram still needs review; inspect results.json'
    finally:
        service.bedrock.close()


if __name__=='__main__':
    main()
