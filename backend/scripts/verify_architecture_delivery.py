"""Check generated diagram survives preview storage and the real DOCX builder."""
import argparse
import base64
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    from app.core.config import Config
    from app.diagram.service import ASSET_KEY
    from app.preview.preview_handler import store_preview_data, get_preview_data, delete_preview_data
    from app.document.document_builder import DocumentBuilder
    p = argparse.ArgumentParser()
    p.add_argument('--run', required=True)
    args = p.parse_args()
    directory = Path(args.run).resolve()
    asset = json.loads((directory/'audit.json').read_text())
    pixels = (directory/'diagram.png').read_bytes()
    assert pixels.startswith(b'\x89PNG'), 'Generation did not produce a PNG'
    review = asset.get('vision_review') or {}
    assert asset.get('status') == 'ready' or (asset.get('status') is None
        and review.get('image_reviewed') and not review.get('issues')
        and not review.get('unresolved_architecture')), asset.get('quality_warnings')
    assert not asset.get('used_fallback'), 'A generic fallback is not a successful test'
    asset['image_base64'] = base64.b64encode(pixels).decode()
    asset['drawio_xml'] = (directory/'diagram.drawio').read_text(encoding='utf8')
    content = {ASSET_KEY:[asset], 'architecture_diagram':'The architecture diagram shows the proposed solution.',
               'toc_structure':'1. Solution Architecture'}
    metadata = {'company_name':'Diagram regression', 'project_title':asset.get('title','Architecture verification')}
    preview_id = 'LOCAL_DELIVERY_TEST'
    store_preview_data(preview_id, content, metadata, 'POC')
    try:
        preview = json.loads(json.dumps(get_preview_data(preview_id)))
        assert preview['content'][ASSET_KEY][0]['image_base64'] == asset['image_base64']
        config = Config()
        config.OUTPUT_DIR = directory
        config.PRECOMPUTE_DOCUMENT_FIELDS = False
        path = DocumentBuilder(config).build_document(preview['content'],metadata,'POC')
        assert path and path.exists(), 'Document build failed'
        with zipfile.ZipFile(path) as archive:
            embedded = [name for name in archive.namelist() if name.startswith('word/media/')
                        and archive.read(name) == pixels]
            assert embedded, 'The generated diagram was omitted from the DOCX'
        result = {'preview_image':True,'docx_image':True,'document':str(path),
                  'review':asset.get('vision_review'), 'warnings':asset.get('quality_warnings',[])}
        (directory/'delivery-check.json').write_text(json.dumps(result,indent=2),encoding='utf8')
        print('DELIVERY PASS',path)
    finally:
        delete_preview_data(preview_id)


if __name__ == '__main__':
    main()
