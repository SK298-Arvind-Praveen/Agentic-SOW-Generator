"""Official local draw.io MCP processing followed by Desktop PNG export.

No hosted rendering, shell commands, model-generated code or silent substitution
of the Pillow renderer. The exact MCP-processed XML accompanies the PNG.
"""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from xml.etree import ElementTree as ET

from PIL import Image


def desktop_binary():
    configured = os.getenv('DRAWIO_DESKTOP_BINARY', '').strip()
    candidates = [configured] if configured else [
        shutil.which('drawio'), shutil.which('draw.io'),
        r'C:\Program Files\draw.io\draw.io.exe',
        str(Path(os.getenv('LOCALAPPDATA', '')) / 'Programs/draw.io/draw.io.exe'),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise RuntimeError('Install draw.io Desktop or set DRAWIO_DESKTOP_BINARY to its executable')


def _run(command, *, timeout, environment, input_text=None):
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, encoding='utf-8',
                               errors='replace', env=environment,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try:
        stdout, stderr = process.communicate(input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        # Kill only the worker/exporter we created, including its child process.
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           capture_output=True, timeout=10,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        process.kill()
        process.communicate(timeout=5)
        raise TimeoutError('Local draw.io operation exceeded its time budget') from None
    if process.returncode:
        # Output may contain source XML or customer text: keep errors generic.
        raise RuntimeError(f'Local draw.io process failed (exit {process.returncode})')
    return stdout


def _cells(xml):
    if len(xml) > 20_000_000 or '<!DOCTYPE' in xml.upper() or '<!ENTITY' in xml.upper():
        raise ValueError('Invalid draw.io XML')
    root = ET.fromstring(xml)
    result = {}
    pages = root.findall('diagram') or [root]
    for page_index, page in enumerate(pages):
        for cell in page.findall('.//mxCell'):
            cell_id = cell.get('id')
            key = (page_index, cell_id)
            if not cell_id or key in result:
                raise ValueError('Invalid draw.io cell identifiers')
            result[key] = cell
            # Only bundled icon data, never a remote resource or local file.
            style = cell.get('style', '')
            if 'image=' in style and not style.split('image=', 1)[1].startswith('data:image/'):
                raise ValueError('External images are not permitted in local diagram export')
    if not result:
        raise ValueError('Empty draw.io XML')
    return result


def validate_processed_xml(original, processed):
    before, after = _cells(original), _cells(processed)
    pages = lambda xml: [(p.get('id'), p.get('name')) for p in ET.fromstring(xml).findall('diagram')]
    if pages(original) != pages(processed):
        raise ValueError('Draw.io MCP changed diagram pages')
    if before.keys() != after.keys():
        raise ValueError('Draw.io MCP changed diagram membership')
    for key, cell in before.items():
        other = after[key]
        for attr in ('source', 'target', 'parent', 'vertex', 'edge', 'value', 'overviewSource', 'overviewTarget'):
            if cell.get(attr) != other.get(attr):
                raise ValueError(f'Draw.io MCP changed the fixed architecture or labels ({key}, {attr})')
        # MCP may normalise style ordering / add label background defaults.
        # Service images, direction and routing semantics must remain identical.
        style = lambda c: dict(part.split('=',1) for part in c.get('style','').split(';') if '=' in part)
        a_style, b_style = style(cell), style(other)
        for attr in ('image', 'startArrow', 'endArrow', 'edgeStyle', 'shape'):
            if a_style.get(attr) != b_style.get(attr):
                raise ValueError(f'Draw.io MCP changed fixed diagram style ({key}, {attr})')
        # No optional routing/layout pass: preserve the checked hybrid geometry.
        a, b = cell.find('mxGeometry'), other.find('mxGeometry')
        if a is not None and (b is None or ET.tostring(a) != ET.tostring(b)):
            raise ValueError('Draw.io MCP changed checked layout geometry')


def render_drawio(xml, timeout_seconds=None):
    executable = desktop_binary()
    node = os.getenv('DRAWIO_NODE_BINARY') or shutil.which('node')
    worker = Path(__file__).resolve().parents[3] / 'tools/drawio-renderer/worker.mjs'
    if not node or not (worker.parent / 'node_modules/@drawio/mcp/src/index.js').is_file():
        raise RuntimeError('Install local MCP dependencies: npm ci --prefix tools/drawio-renderer --ignore-scripts')
    _cells(xml)
    from app.diagram.budgets import seconds
    budget = min(600, max(1, float(timeout_seconds if timeout_seconds is not None else seconds('render'))))
    deadline = time.monotonic() + budget
    environment = {k: v for k, v in os.environ.items() if k.upper() in {
        'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'COMSPEC', 'USERPROFILE',
        'LOCALAPPDATA', 'APPDATA', 'HOME', 'DISPLAY', 'XAUTHORITY',
    }}
    environment['DRAWIO_DISABLE_UPDATE'] = 'true'
    print('[DIAGRAM][DRAWIO] Starting local MCP + Desktop export', flush=True)
    for attempt in range(2):
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('Draw.io processing deadline exhausted')
        # Cold local MCP startup gets a fair share of the render budget. Retry
        # the same checked XML once; never replan or substitute a diagram here.
        stage_budget=min(90,remaining)
        try:
            raw = _run([node, str(worker)], timeout=stage_budget, environment=environment,
                       input_text=json.dumps({'xml': xml, 'timeout_ms': int(max(1,stage_budget-5)*1000)}))
            break
        except (TimeoutError,RuntimeError) as exc:
            if attempt or deadline-time.monotonic()<10:raise
            print(f'[DIAGRAM][DRAWIO] MCP attempt=1; retrying same XML after {type(exc).__name__}',flush=True)
    response = json.loads(raw)
    processed = response['xml']
    validate_processed_xml(xml, processed)
    with tempfile.TemporaryDirectory(prefix='sow-drawio-') as directory:
        folder = Path(directory)
        source, target = folder / 'architecture.drawio', folder / 'architecture.png'
        source.write_text(processed, encoding='utf-8')
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Draw.io export deadline exhausted')
        _run([executable, '--user-data-dir=' + str(folder / 'profile'), '--disable-update',
              '--export', '--format', 'png', '--page-index', '1', '--scale', '1.5', '--border', '16',
              '--output', str(target), str(source)], timeout=remaining, environment=environment)
        if not target.is_file() or not 100 < target.stat().st_size < 20_000_000:
            raise RuntimeError('draw.io Desktop did not export a valid nonempty PNG')
        png = target.read_bytes()
        with Image.open(io.BytesIO(png)) as image:
            if image.format != 'PNG' or min(image.size) < 50 or image.width * image.height > 40_000_000:
                raise RuntimeError('Invalid draw.io PNG dimensions')
            image.verify()
    print(f'[DIAGRAM][DRAWIO] MCP={response.get("mcp_version")}; png_bytes={len(png)}; '
          f'elapsed={budget-(deadline-time.monotonic()):.1f}s', flush=True)
    return png, processed, {'mcp_version': response.get('mcp_version'), 'renderer': 'draw.io Desktop'}
