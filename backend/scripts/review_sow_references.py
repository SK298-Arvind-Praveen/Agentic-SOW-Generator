"""Read DOCX body blocks in order for authoring comparisons (no cloud calls)."""
import json
import re
import sys
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

def inspect(path):
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read('word/document.xml'))
    blocks = []
    for element in root.find('w:body', NS):
        if element.tag.endswith('}tbl'):
            rows = []
            for row in element.findall('w:tr', NS):
                rows.append(' | '.join(' '.join(t.text or '' for t in c.findall('.//w:t', NS)) for c in row.findall('w:tc', NS)))
            blocks.append('[TABLE]\n' + '\n'.join(rows))
        else:
            text = ''.join(t.text or '' for t in element.findall('.//w:t', NS))
            style = element.find('w:pPr/w:pStyle', NS)
            if text.strip():
                blocks.append(f'[{style.get("{" + NS["w"] + "}val") if style is not None else "p"}] {text}')
    return {'file': str(path), 'words': sum(len(re.findall(r'\b\w+\b', b)) for b in blocks), 'tables': sum(b.startswith('[TABLE]') for b in blocks), 'blocks': blocks}

if __name__ == '__main__':
    result = inspect(Path(sys.argv[1]))
    if len(sys.argv) > 2:
        result['blocks'] = result['blocks'][int(sys.argv[2]):int(sys.argv[3])]
    print(json.dumps(result, ensure_ascii=True, indent=2))
