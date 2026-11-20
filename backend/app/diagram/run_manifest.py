"""Reproducible full-request acceptance; never confuse an available PNG with a pass."""
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

CONFIG_KEYS = ('ARCHITECTURE_PROCESS_FLOW', 'ARCHITECTURE_DIAGRAM_ENGINE',
    'ARCHITECTURE_VISION_REVIEW_ENABLED', 'BEDROCK_REGION', 'FAST_MODEL_ID',
    'ANALYSIS_MODEL_ID', 'WRITER_MODEL_ID', 'DIAGRAM_MODEL_ID',
    'DIAGRAM_REVIEW_MODEL_ID', 'REVIEW_MODEL_ID', 'EDITOR_MODEL_ID')


def capture_configuration(config):
    values = {key: config.get(key) if isinstance(config, dict) else getattr(config, key, None)
            for key in CONFIG_KEYS}
    if not isinstance(config, dict):
        import os
        for key, default in {'ARCHITECTURE_DIAGRAM_ENGINE':'hybrid','ARCHITECTURE_VISION_REVIEW_ENABLED':'true'}.items():
            values[key] = os.getenv(key, default)
    return values


def digest(value):
    return sha256(value if isinstance(value, bytes) else str(value).encode('utf8')).hexdigest()


@dataclass
class GenerationManifest:
    sources: list
    form: dict
    configuration: dict
    schema_version: int = 1

    @classmethod
    def create(cls, sources, form, configuration):
        return cls([{'path': str(Path(p).resolve()), 'filename': Path(p).name,
                     'sha256': digest(Path(p).read_bytes())} for p in sources],
                   dict(form), capture_configuration(configuration))

    def verify_sources(self):
        if not self.sources: raise ValueError('Manifest has no source documents')
        for source in self.sources:
            if digest(Path(source['path']).read_bytes()) != source['sha256']:
                raise ValueError(f"Source hash mismatch: {source['filename']}")

    def save(self, path):
        Path(path).write_text(json.dumps(asdict(self), indent=2), encoding='utf8')

    @classmethod
    def load(cls, path):
        return cls(**json.loads(Path(path).read_text(encoding='utf8')))


def assert_diagram_acceptance(asset, conceptual=False):
    assert asset and asset.get('image_base64'), 'diagram unavailable'
    assert not asset.get('used_fallback'), 'recovery diagram is not verified'
    for key in ('quality_warnings', 'validation_warnings', 'decoration_warnings', 'errors', 'warning'):
        assert not asset.get(key), f'{key}: {asset.get(key)}'
    if conceptual:
        from app.diagram.conceptual_drawio import validate
        validate(asset['plan'])
        assert asset.get('status') not in {'unavailable', 'review_required'}
        return
    assert asset.get('status') == 'ready', f"diagram status: {asset.get('status')}"
    review = asset.get('vision_review') or {}
    assert review.get('status') in {'reviewed', 'passed', 'reviewed_no_issues'} and review.get('image_reviewed'), 'image review missing'
    assert not review.get('issues') and not review.get('unresolved_architecture'), 'unresolved review findings'
    from app.diagram.reliability import retry_issues
    assert not retry_issues(asset), str(retry_issues(asset))


def assert_content_acceptance(content, selected, state=None):
    from app.core.sow_section_preferences import section_category
    sections = {('about_client' if k == 'about_company' else section_category(k) or k): v for k, v in content.items()}
    for key in selected:
        if key == 'conceptual_flow_diagram':
            assert content.get('conceptual_flow_asset'), 'conceptual diagram missing'
            assert_diagram_acceptance(content['conceptual_flow_asset'], conceptual=True)
        elif key == 'architecture_diagram':
            assets = content.get('architecture_diagram_assets') or []
            assert assets, 'architecture diagram missing'
            for item in assets: assert_diagram_acceptance(item)
            assert sections.get(key), 'architecture service table missing'
            from app.diagram.architecture_text import service_nodes
            for item in assets:
                audit = item.get('text_alignment') or {}
                expected = {n['id'] for n in service_nodes(item.get('spec') or {})}
                covered = [n for row in audit.get('row_component_ids', []) for n in row]
                assert audit.get('status') == 'aligned', 'service table not verified'
                assert set(covered) == expected and len(covered) == len(set(covered)), 'service table component coverage mismatch'
        else:
            body = sections.get(key)
            assert body and isinstance(body, str) and len(body.strip()) >= 20, f'{key}: selected section empty'
            if '|' in body:
                rows = [line for line in body.splitlines() if line.strip().startswith('|')
                        and not re.fullmatch(r'[\s|:\-]+', line)]
                if rows: assert len(rows) > 1, f'{key}: table contains only a header'
            assert not re.search(r'I (?:must decline|cannot locate|don.t have reliable information)', body), f'{key}: model refusal'
            if key == 'aws_pricing':
                assert re.search(r'AWS Pricing Calculator:\s*\[Open Link\]\(https://calculator\.aws/[^)]*\)', body), 'pricing calculator link missing'
                pricing = (state or {}).get('pricing_result') or {}
                if state is not None:
                    from app.pricing.evidence import complete_estimate
                    assert complete_estimate(pricing), 'pricing is incomplete or lacks verified pricing evidence'
                    assert pricing.get('estimate_url') and float(pricing.get('monthly_cost') or 0)>0, 'saved calculator estimate/total missing'
                    from app.pricing.ec2_inventory import selected_ec2_resources, EC2_NAME, EC2_CODE
                    required = sorted(n['id'] for n in selected_ec2_resources(state.get('validated_requirements') or {}))
                    if required:
                        coverage = (pricing.get('resource_coverage') or {}).get(EC2_NAME) or {}
                        configs = coverage.get('configurations') or []
                        covered = sorted(key for row in configs for key in row.get('resource_ids', []))
                        assert coverage.get('complete') and covered == required, 'EC2 resource coverage incomplete or duplicated'
                        entries = [e for e in pricing.get('calculator_entries', []) if e.get('service') == EC2_CODE]
                        assert sorted(e.get('instance', '') for e in entries) == sorted(c.get('instance', '') for c in configs), 'EC2 resource coverage differs from calculator configurations'
                        assert all(c.get('quantity', 0) >= len(c['resource_ids']) and 0 < c.get('monthly_hours', 0) <= 730 for c in configs), 'EC2 resource coverage has invalid quantity or runtime'
                if pricing.get('estimate_url'):
                    assert pricing['estimate_url'] in body, 'pricing estimate link differs from computed estimate'
            if key == 'timelines_deliverables' and (state or {}).get('metadata', {}).get('timeline_format') == 'gantt':
                from app.core.section_formats import has_gantt_allocation
                assert has_gantt_allocation(body), 'Gantt allocation empty'
    if 'architecture_diagram' in selected:
        assert_architecture_identity(content, state)
    if state and state.get('architecture_version'):
        versions = state.get('artifact_architecture_versions') or {}
        for key in selected:
            assert key in versions, f'{key}: architecture version missing'
            assert versions[key] == state['architecture_version'], f'{key}: stale architecture'


def assert_architecture_identity(content, state):
    from app.diagram.contracts import freeze
    state = state or {}
    version = state.get('architecture_version')
    assert isinstance(version, str) and re.fullmatch('[0-9a-f]{64}', version), 'canonical architecture version missing or invalid'
    assets = content.get('architecture_diagram_assets') or []
    assert assets, 'selected canonical architecture missing'
    for asset in assets:
        assert asset.get('architecture_version') == version, 'asset architecture version mismatch'
        assert freeze(asset.get('spec') or {})['version'] == version, 'selected spec canonical identity mismatch'
    approved = (state.get('validated_requirements') or {}).get('approved_architecture') or {}
    assert approved.get('version') == version, 'approved inventory architecture version mismatch'
    assert freeze(approved)['version'] == version, 'approved inventory canonical identity mismatch'
    if state.get('architecture_design'):
        assert freeze(state['architecture_design'])['version'] == version, 'architecture design canonical identity mismatch'
    assert (state.get('artifact_architecture_versions') or {}).get('service_table') == version, 'service table architecture version missing'


def code_fingerprint(root):
    files = sorted(p for p in Path(root).rglob('*') if p.is_file()
                   and p.suffix.lower() in {'.py', '.txt', '.md', '.json', '.yaml', '.yml'})
    return digest('\n'.join(f'{p.relative_to(root)}:{digest(p.read_bytes())}' for p in files
                             if '__pycache__' not in p.parts))


def export_section_failures(path, content, selected, metadata=None):
    """Check actual body text, not TOC presence or a second builder invocation."""
    import html
    import unicodedata
    import zipfile
    from collections import Counter
    from xml.etree import ElementTree as ET
    from app.core.sow_section_preferences import section_category, SECTION_LABELS
    metadata = metadata or {}
    ns = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
          'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
          'wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
          'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
    def normal(text):
        text = html.unescape(re.sub(r'<[^>]+>', ' ', str(text)))
        text = re.sub(r'\[([^]]+)\]\([^)]+\)', r'\1', text)
        text = unicodedata.normalize('NFKC', text).casefold()
        return ' '.join(re.findall(r'\w+', text))
    sections = {('about_client' if k == 'about_company' else section_category(k) or k):v for k,v in content.items()}
    with zipfile.ZipFile(path) as package:
        import posixpath
        relationships = ET.fromstring(package.read('word/_rels/document.xml.rels'))
        targets = {rel.get('Id'): posixpath.normpath(posixpath.join('word', rel.get('Target', ''))).lstrip('/')
                   for rel in relationships if rel.get('TargetMode') != 'External'}
        body = ET.fromstring(package.read('word/document.xml')).find('w:body', ns)
        actual = {}; current = None; tables = {}; body_paragraphs = {}; drawings = {}
        for element in body:
            # Word may split a word across runs (e.g. font/emphasis changes).
            # Preserve run adjacency and separate only actual paragraphs.
            paragraphs = [element] if element.tag == '{'+ns['w']+'}p' else element.findall('.//w:p', ns)
            text = ' '.join(''.join(t.text or '' for t in p.findall('.//w:t', ns)) for p in paragraphs)
            style = element.find('w:pPr/w:pStyle', ns)
            if style is not None and style.get('{'+ns['w']+'}val') == 'Heading1':
                current = section_category(text)
                if current is None and 'about' in text.casefold():
                    current = 'about_shellkode' if 'shellkode' in text.casefold() else 'about_client'
                if current is None:
                    current = next((k for k,v in SECTION_LABELS.items() if normal(v) in normal(text)), None)
            if current: actual.setdefault(current, []).append(text)
            if current and element.tag == '{'+ns['w']+'}tbl': tables.setdefault(current, []).append(element)
            if current and element.tag == '{'+ns['w']+'}p': body_paragraphs.setdefault(current, []).append(text)
            if current:
                for drawing in element.findall('.//w:drawing', ns):
                    extent = drawing.find('.//wp:extent', ns)
                    for blip in drawing.findall('.//a:blip', ns):
                        target = targets.get(blip.get('{'+ns['r']+'}embed'))
                        image_hash = digest(package.read(target)) if target in package.namelist() else None
                        drawings.setdefault(current, []).append({'digest': image_hash,
                            'width': int(extent.get('cx', 0))/914400 if extent is not None else 0,
                            'height': int(extent.get('cy', 0))/914400 if extent is not None else 0})
    failures = []
    import base64
    for section, assets in [('architecture_diagram', content.get('architecture_diagram_assets') or []),
                            ('conceptual_flow_diagram', [content.get('conceptual_flow_asset') or {}])]:
        if section not in selected: continue
        expected = [a for a in assets if a.get('image_base64')]
        actual_images = drawings.get(section, [])
        expected_hashes = Counter(digest(base64.b64decode(a['image_base64'])) for a in expected)
        if not expected_hashes or Counter(a['digest'] for a in actual_images) != expected_hashes:
            failures.append(f'{section}: displayed image identity or multiplicity differs from preview')
            continue
        for asset in expected:
            image_hash = digest(base64.b64decode(asset['image_base64']))
            for shown in [a for a in actual_images if a['digest'] == image_hash]:
                if min(shown['width'], shown['height']) < 1 or max(shown['width'], shown['height']) < 3:
                    failures.append(f'{section}: displayed figure physical extent is too small')
                if section == 'architecture_diagram' and asset.get('drawio_xml'):
                    from app.diagram.figure_readability import physical_type_size
                    size = physical_type_size(asset, shown['width'])
                    if size is None or size < 8:
                        failures.append(f'{section}: actual projected type is below 8 pt ({size})')
    for key in selected:
        if key not in actual:
            failures.append(f'{key}: heading/body missing from export'); continue
        source = sections.get(key)
        if key == 'conceptual_flow_diagram' or not isinstance(source,str): continue
        gantt = False
        if key == 'timelines_deliverables':
            from app.core.section_formats import _gantt_period_rows, has_gantt_allocation, sequence_gantt_markdown
            gantt = metadata.get('timeline_format') == 'gantt' or bool(_gantt_period_rows(source))
            if gantt:
                source = sequence_gantt_markdown(source)
                rows = _gantt_period_rows(source)
                if not has_gantt_allocation(source):
                    failures.append(f'{key}: Gantt allocation empty')
                elif not _word_gantt_matches(tables.get(key, []), rows, normal, ns):
                    failures.append(f'{key}: Gantt headers, row order or shaded cells differ from the schedule')
        rendered = normal(' '.join(actual[key]))
        expected_notes = Counter()
        for line in source.splitlines():
            if re.fullmatch(r'[\s|:\-]+', line) or not line.strip(): continue
            for name,value in metadata.items():
                if isinstance(value,(str,int,float)):
                    line = line.replace('{'+name.upper()+'}',str(value))
            if gantt and re.match(r'^\s*[-*•○]\s+', line):
                note = normal(line)
                if note:
                    expected_notes[note] += 1
            # Document formatting supplies numbering/bullets and can remove
            # redundant bold lead-ins; the substantive words must all remain.
            line = re.sub(r'^\s*[-*+]\s+\*\*[^*]+:\*\*\s*', '', line)
            line = re.sub(r'^\s*(?:#{1,6}\s*)?(?:\d+(?:\.\d+)*[.)]?\s+|[-*+]\s+)?', '', line)
            expected = normal(line)
            if expected and (gantt or len(expected) > 12) and expected not in rendered:
                failures.append(f'{key}: exported content differs: {expected[:120]}'); break
        if expected_notes:
            actual_notes = Counter(normal(text) for text in body_paragraphs.get(key, []))
            if any(actual_notes[note] != count for note, count in expected_notes.items()):
                failures.append(f'{key}: Gantt note paragraphs differ from the schedule')
    return failures


def _word_gantt_matches(tables, rows, normal, ns):
    if len(tables) != 1:
        return False
    fills = {'■': 'CCFFCC', '◆': '4A86E8'}
    expected = [[(normal(value), 'D9D9D9') for value in rows[0]]]
    expected.extend([
        [('', fills[value]) if i >= 2 and value in fills else (normal(value), 'FFFFFF')
         for i, value in enumerate(row)]
        for row in rows[1:]
    ])

    def cell_value(cell):
        text = ''.join(t.text or '' for t in cell.findall('.//w:t', ns))
        shade = cell.find('w:tcPr/w:shd', ns)
        fill = shade.get('{'+ns['w']+'}fill', '').upper() if shade is not None else ''
        # A marker is visible as shading alone. Raw glyphs indicate the
        # ordinary Markdown table renderer took the Gantt path's input.
        return (text if any(mark in text for mark in fills) else normal(text), fill)

    actual = [[cell_value(cell) for cell in tr.findall('w:tc', ns)] for tr in tables[0].findall('w:tr', ns)]
    return actual == expected


def exported_hyperlinks(package):
    """Resolve both valid Word URL representations, including split fragments."""
    from xml.etree import ElementTree as ET
    w = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    r = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    relationships = {item.get('Id'): item.get('Target', '')
        for item in ET.fromstring(package.read('word/_rels/document.xml.rels'))}
    links = []
    for item in ET.fromstring(package.read('word/document.xml')).iter('{'+w+'}hyperlink'):
        target = relationships.get(item.get('{'+r+'}id'), '')
        if not target: continue
        anchor = item.get('{'+w+'}anchor')
        links.append(target.split('#',1)[0]+'#'+anchor if anchor else target)
    return links


def assert_process_flow_acceptance(asset, expected):
    from math import isfinite
    from xml.etree import ElementTree as ET

    steps = (asset.get('renderer_details') or {}).get('process_flow') or []
    xml = asset.get('drawio_xml') or ''
    if expected:
        assert 1 <= len(steps) <= 12, 'enabled process flow missing or excessive'
    else:
        assert not steps, 'disabled process flow still rendered'

    document = ET.fromstring(xml)
    markers = []
    for graph in document.findall('.//root') or [document]:
        cells = graph.findall('mxCell')
        edge_ids = {c.get('id') for c in cells if c.get('edge') == '1'}
        for cell in cells:
            key = cell.get('id', '')
            if key.startswith('process_flow_marker_') or cell.get('processFlowStep'):
                markers.append(cell)
            elif cell.get('edge') == '1' or cell.get('parent') in edge_ids or key.startswith(
                ('flow_caption_', 'interface_caption_', 'edge_label_')
            ):
                assert not cell.get('value'), 'connector captions were not removed'
    overview = document.find('./diagram/mxGraphModel/root')
    panel = None if overview is None else overview.find('mxCell[@id="process_flow_panel"]')
    if not expected:
        assert panel is None and not markers, 'disabled process flow still rendered'
        return
    assert panel is not None, 'process panel absent from exported diagram'

    from app.diagram.projection import connections_from_xml
    from app.diagram.service import DiagramSpec, Edge, Node

    saved = asset.get('spec') or {}
    plan = saved.get('architecture_plan') or {}
    story = (plan.get('process_story') or {}).get('steps') or []
    assert len(steps) == len(story), 'process story/export count differs'
    assert len(markers) == len(story), 'expected one process marker per story step'
    spec = DiagramSpec(saved.get('title', ''), tuple(Node(**n) for n in saved.get('nodes', [])),
                       tuple(Edge(**e) for e in saved.get('edges', [])), architecture_plan=plan)
    connections = {c['id']: {f'e{i}' for path in c['edge_paths'] for i in path}
                   for c in connections_from_xml(xml, spec)}
    placements = set()
    for number, (planned, exported) in enumerate(zip(story, steps), 1):
        assert exported.get('id') == planned['id'] and exported.get('number') == number, 'process story/export order differs'
        assert exported.get('edge_ids') == planned['edge_ids'], 'process story/export provenance differs'
        matches = [marker for marker in markers if marker.get('processFlowStep') == str(planned['id'])]
        assert len(matches) == 1, f'expected one marker for process step {number}'
        marker = matches[0]
        assert marker in overview and marker.get('vertex') == '1' and marker.get('edge') != '1', 'process marker is not an overview vertex'
        style = dict(part.split('=', 1) for part in marker.get('style', '').split(';') if '=' in part)
        assert (marker.get('visible') != '0' and style.get('noLabel') != '1'
                and float(style.get('opacity', 100)) > 0 and float(style.get('textOpacity', 100)) > 0
                and marker.get('value') == str(number)), 'process marker must show its step number'
        connector = marker.get('processFlowConnector')
        assert connections.get(connector, set()).intersection(planned['edge_ids']), 'process marker references an unrelated connector'
        geometry = marker.find('mxGeometry')
        assert geometry is not None and all(
            isfinite(float(geometry.get(k, 0))) and float(geometry.get(k, 0)) > 0 for k in ('width', 'height')
        ), 'process marker has no visible geometry'
        parent = marker.get('parent')
        point = geometry
        if geometry.get('relative') == '1':
            assert parent == connector, 'process marker is attached to a different connector'
            point = geometry.find('mxPoint[@as="offset"]')
            assert point is not None, 'process marker offset missing'
        else:
            assert parent == '1', 'floating process marker must be on the overview layer'
        coordinates = (float(point.get('x', 0)), float(point.get('y', 0)))
        placement = (parent, *coordinates)
        assert all(map(isfinite, coordinates)) and placement not in placements, 'process markers must have distinct positions'
        placements.add(placement)


def assert_authoring_acceptance(content):
    summary = str(content.get('generation_quality_summary') or '')
    assert re.search(r'Generation quality gate:\*\* Passed(?:\n|$)', summary), 'authoring review incomplete or content flags remain'
