"""Import reviewed PNGs: python scripts/build_curated_architecture_library.py <zip>.

The hand-reviewed manifest pins the exact file list and hashes. No automatic
classification, model calls, extraction of documents or execution of ZIP content.
"""
import argparse
import hashlib
import html
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

from PIL import Image


def reviewed_assets(archive, manifest):
    """Validate the whole import before publishing; never extract ZIP paths."""
    prefix = 'Sample arch diagrams/'
    expected = {prefix + ref['source_file'] for ref in manifest['references']}
    if len(expected) != len(manifest['references']):
        raise ValueError('Duplicate reviewed source file')
    assets = []
    with ZipFile(archive) as bundle:
        files = [item for item in bundle.infolist() if not item.is_dir()]
        if {item.filename for item in files} != expected or len(files) != len(expected):
            raise ValueError('Archive differs from reviewed image list')
        for ref in manifest['references']:
            item = bundle.getinfo(prefix + ref['source_file'])
            if item.file_size > 3_500_000:
                raise ValueError('Reference exceeds image budget')
            content = bundle.read(item)
            if hashlib.sha256(content).hexdigest() != ref['sha256']:
                raise ValueError(f"Reference changed; re-review {ref['source_file']}")
            with Image.open(BytesIO(content)) as im:
                if im.format != 'PNG':
                    raise ValueError('Expected PNG')
                dimensions = list(im.size)
                im.verify()
            assets.append((ref, content, dimensions))
    return assets


def build(archive):
    library = Path(__file__).resolve().parents[1] / 'knowledge/architecture'
    manifest = json.loads((library / 'curated-import.json').read_text(encoding='utf-8'))
    assets = reviewed_assets(archive, manifest)
    cards, gallery = [], []
    for ref, content, dimensions in assets:
        relative = Path('references/upload-20261014') / ref['category'] / (ref['id'] + '.png')
        destination = (library / relative).resolve()
        if not destination.is_relative_to((library / 'references/upload-20261014').resolve()):
            raise ValueError('Invalid asset destination')
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        card = {key: value for key, value in ref.items() if key != 'sha256'}
        card.update(source_type='user_reference', source_url='local:' + relative.as_posix(),
                    image_path=relative.as_posix(), image_sha256=ref['sha256'],
                    source_archive=manifest['archive'],
                    reviewed_on=manifest['reviewed_on'], review_type='visual_user_reference',
                    historical=False, visual_enabled=ref.get('visual_enabled', True),
                    use_when=ref['title'], anchors=[ref['view'], ref['category'], ref['title']],
                    deployment_checks=['Apply shared containment rules; references are advisory.'],
                    visual_conventions='aws-reference-light-v1', image_dimensions=dimensions)
        cards.append(card)
        status = 'Image + guidance' if card['visual_enabled'] else 'Guidance only: source containment errors'
        gallery.append('<section><h2>' + html.escape(ref['title']) + '</h2><p>' +
                       html.escape(f"{ref['category']} | {ref['view']} | {ref['stage']} | {status}") +
                       '</p><img loading="lazy" src="' + relative.as_posix() + '"><p><b>Flow:</b> ' +
                       html.escape(ref['flow']) + '</p><p><b>Reuse:</b> ' + html.escape(ref['layout']) +
                       '</p><p><b>Cautions:</b> ' + html.escape(ref['avoid']) +
                       '</p><p>Source: ' + html.escape(ref['source_file']) +
                       '</p><small>SHA-256: ' + ref['sha256'] + '</small></section>')
    (library / 'user-patterns.json').write_text(json.dumps({
        'schema_version': 1, 'library_version': manifest['library_version'],
        'source_archive': manifest['archive'], 'patterns': cards,
        'excluded': manifest['excluded']}, ensure_ascii=False, indent=2), encoding='utf-8')
    (library / 'catalog.html').write_text('<!doctype html><meta charset="utf-8"><title>Architecture reference catalogue</title>'
        '<style>body{font:16px sans-serif;max-width:1100px;margin:40px auto;color:#232f3e}section{border-top:1px solid #ddd;padding:24px 0}'
        'img{max-width:100%;background:white}p{line-height:1.5}small{overflow-wrap:anywhere}</style><h1>Reviewed architecture references</h1>'
        '<p>10 diagrams from Sample arch diagrams.zip: 6 Data, 4 GenAI. No Cloud-only sample supplied. '
        'Inspected individually; advisory patterns, not certified designs. Previous SOW-document imports are superseded.</p>' +
        ''.join(gallery), encoding='utf-8')
    print(f'Built {len(cards)} reference cards and local catalogue; no AWS calls.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    build(parser.parse_args().archive)
