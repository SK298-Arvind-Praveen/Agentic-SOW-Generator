"""Optional AWS architecture kit adapter; no additional model invocation."""
import base64
import io
import json
import os
from pathlib import Path, PureWindowsPath
import subprocess
import time

from PIL import Image


def worker_command():
    worker = Path(__file__).with_name('arch_kit_worker.py')
    distro = os.getenv('AWS_ARCH_KIT_WSL_DISTRO', '').strip()
    if distro:
        python = os.getenv('AWS_ARCH_KIT_WSL_PYTHON', '').strip()
        if not python.startswith('/'):
            raise RuntimeError('Set AWS_ARCH_KIT_WSL_PYTHON to the kit environment Python path')
        path = PureWindowsPath(worker)
        if not path.drive or len(path.drive) != 2:
            raise RuntimeError('WSL mode requires the backend on a local Windows drive')
        linux_worker = '/mnt/' + path.drive[0].lower() + '/' + '/'.join(path.parts[1:])
        return ['wsl.exe', '-d', distro, '--exec', 'env', '-i',
                'PATH=' + python.rsplit('/', 1)[0] + ':/usr/bin:/bin', python, linux_worker]
    python = os.getenv('AWS_ARCH_KIT_PYTHON', '').strip()
    if not python:
        raise RuntimeError('Set AWS_ARCH_KIT_PYTHON or AWS_ARCH_KIT_WSL_DISTRO for the optional renderer')
    return [python, str(worker)]


def render_arch_kit(spec, registry, timeout_seconds=None):
    from app.diagram.service import _layout
    from app.diagram.review import routes
    started = time.monotonic()
    timeout = max(15, min(180, int(os.getenv('AWS_ARCH_KIT_TIMEOUT_SECONDS', '90'))))
    worker_timeout = timeout + 20
    if timeout_seconds is not None:
        worker_timeout = max(1, min(worker_timeout, int(timeout_seconds)))
        timeout = max(1, worker_timeout - 2)
    positions, boxes, _, height = _layout(spec)
    groups = {group.id: group.label for group in spec.groups}
    payload = {'height': height, 'timeout': timeout, 'nodes': [],
               'groups': [{'label': groups.get(key, key.replace('_', ' ').title()), 'box': box} for key, box in boxes.items()],
               'edges': [{'points': points, 'label': edge.label} for edge, points in zip(spec.edges, routes(spec, positions))]}
    for node in spec.nodes:
        item = {'label': node.label, 'box': positions[node.id]}
        icon = registry.png(node.icon_key, 128) if node.icon_key else None
        if icon is not None:
            buffer = io.BytesIO()
            icon.save(buffer, format='PNG')
            item['icon'] = base64.b64encode(buffer.getvalue()).decode('ascii')
        payload['nodes'].append(item)
    environment = {key: value for key, value in os.environ.items() if key.upper() in {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'COMSPEC'}}
    print(f'[DIAGRAM][ARCH-KIT] Starting; nodes={len(spec.nodes)}; edges={len(spec.edges)}; timeout={timeout}s', flush=True)
    result = subprocess.run(worker_command(), input=json.dumps(payload), text=True, encoding='utf-8',
                            capture_output=True, timeout=worker_timeout, env=environment,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    try:
        response = json.loads(result.stdout)
    except ValueError as exc:
        raise RuntimeError('Architecture kit returned an invalid worker response') from exc
    if result.returncode or response.get('error'):
        raise RuntimeError(response.get('error', 'Architecture kit worker failed'))
    png = base64.b64decode(response['image_base64'], validate=True)
    if not 100 < len(png) < 20_000_000:
        raise RuntimeError('Architecture kit returned an invalid image size')
    with Image.open(io.BytesIO(png)) as image:
        if image.format != 'PNG' or min(image.size) < 50 or image.width * image.height > 40_000_000:
            raise RuntimeError('Architecture kit returned invalid PNG dimensions')
        image.verify()
    print(f'[DIAGRAM][ARCH-KIT] Complete; png_bytes={len(png)}; elapsed={time.monotonic()-started:.1f}s', flush=True)
    return png
