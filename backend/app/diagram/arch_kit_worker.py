"""Isolated stdio MCP worker. Receives validated geometry, never model-written Python."""
import asyncio
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import textwrap


def compile_diagram(payload, directory):
    """Compile only constants and known drawing operations into the kit's DSL."""
    height = payload['height']
    def position(x, y):
        return f'{x / 100:.3f},{(height - y) / 100:.3f}!'
    lines = [
        'with Diagram("Solution Architecture", show=False, outformat="png", '
        'graph_attr={"layout":"neato","overlap":"true","splines":"false","dpi":"150",'
        '"pad":"0.4","bgcolor":"white","outputorder":"edgesfirst"}, '
        'node_attr={"fontname":"Arial","fontsize":"11"}):'
    ]
    for i, group in enumerate(payload['groups']):
        x, y, w, h = group['box']
        lines.append(f'    g{i} = Node({group["label"]!r}, image="", shape="box", '
                     f'pos={position(x+w/2,y+h/2)!r}, width={str(w/100)!r}, '
                     f'height={str(h/100)!r}, fixedsize="true", labelloc="t", '
                     'color="#94A3B8", style="rounded", penwidth="1.2")')
    for i, node in enumerate(payload['nodes']):
        x, y, w, h = node['box']
        label = '\n'.join(textwrap.wrap(node['label'], 25))
        icon = node.get('icon')
        if icon:
            icon_path = directory / f'icon_{i}.png'
            icon_path.write_bytes(base64.b64decode(icon, validate=True))
            # Graphviz resolves relative image paths beside its output file.
            output_directory = directory / 'generated-diagrams'
            output_directory.mkdir(exist_ok=True)
            (output_directory / icon_path.name).write_bytes(icon_path.read_bytes())
            lines.append(f'    n{i} = Node("", shape="none", image={icon_path.name!r}, '
                         f'pos={position(x+w/2,y+35)!r}, width="0.65", height="0.65", '
                         'fixedsize="true", imagescale="true")')
            lines.append(f'    t{i} = Node({label!r}, image="", labelloc="c", shape="plaintext", '
                         f'pos={position(x+w/2,y+85)!r}, width={str(w/100)!r}, height="0.4")')
        else:
            lines.append(f'    n{i} = Node({label!r}, image="", labelloc="c", shape="box", '
                         f'pos={position(x+w/2,y+h/2)!r}, width={str(w/100)!r}, '
                         f'height={str(h/100)!r}, fixedsize="true", style="rounded,filled", '
                         'fillcolor="#F1F5F9", color="#64748B")')
    for i, edge in enumerate(payload['edges']):
        points = edge['points']
        for j, (x, y) in enumerate(points):
            lines.append(f'    p{i}_{j} = Node("", image="", shape="point", width="0.001", '
                         f'height="0.001", style="invis", pos={position(x,y)!r})')
        for j in range(len(points)-1):
            arrow = 'normal' if j == len(points)-2 else 'none'
            lines.append(f'    p{i}_{j} >> Edge(color="#64748B", penwidth="1.3", '
                         f'arrowhead={arrow!r}) >> p{i}_{j+1}')
        if edge.get('label') and len(points) > 1:
            a, b = max(zip(points, points[1:]), key=lambda pair: abs(pair[0][0]-pair[1][0])+abs(pair[0][1]-pair[1][1]))
            label = '\n'.join(textwrap.wrap(edge['label'], 25))
            lines.append(f'    e{i} = Node({label!r}, image="", labelloc="c", shape="plaintext", fontsize="8", '
                         f'pos={position((a[0]+b[0])/2,(a[1]+b[1])/2-10)!r})')
    return '\n'.join(lines)


async def render(payload, directory):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    executable = Path(sys.executable).parent / ('awslabs.aws-diagram-mcp-server.exe' if os.name == 'nt' else 'awslabs.aws-diagram-mcp-server')
    # Do not give the drawing subprocess credentials or access to default AWS profiles.
    environment = {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP') if key in os.environ}
    environment.update(HOME=str(directory), USERPROFILE=str(directory),
                       AWS_CONFIG_FILE=str(directory/'no-config'), AWS_SHARED_CREDENTIALS_FILE=str(directory/'no-credentials'),
                       AWS_EC2_METADATA_DISABLED='true', FASTMCP_LOG_LEVEL='ERROR')
    params = StdioServerParameters(command=str(executable), env=environment)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool('generate_diagram', {
                'code': compile_diagram(payload, directory), 'filename': 'architecture',
                'workspace_dir': str(directory), 'timeout': payload['timeout'],
            })
            if result.isError:
                raise RuntimeError('MCP tool reported an error')
            responses = []
            for block in result.content:
                if getattr(block, 'text', None):
                    try:
                        responses.append(json.loads(block.text))
                    except ValueError:
                        pass
            response = next((item for item in responses if isinstance(item, dict) and item.get('status') == 'success'), None)
            if not response:
                raise RuntimeError('MCP did not return a successful diagram result: ' + str(responses)[:600])
            path = Path(response['path']).resolve()
            if not path.is_relative_to(directory.resolve()) or path.suffix.lower() != '.png':
                raise RuntimeError('MCP returned an unexpected output path')
            if not path.is_file() or not 100 < path.stat().st_size < 20_000_000:
                raise RuntimeError('MCP returned an empty or oversized image')
            return base64.b64encode(path.read_bytes()).decode('ascii')


def main():
    payload = json.loads(sys.stdin.read(8_000_000))
    with tempfile.TemporaryDirectory(prefix='sow-arch-kit-') as scratch:
        previous = Path.cwd()
        try:
            os.chdir(scratch)
            result = asyncio.run(asyncio.wait_for(render(payload, Path(scratch)), timeout=payload['timeout']+10))
        finally:
            os.chdir(previous)
    print(json.dumps({'image_base64': result}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        def details(error):
            children = getattr(error, 'exceptions', ())
            return '; '.join(details(child) for child in children) if children else str(error)
        print(json.dumps({'error': details(exc)[:1000]}))
        sys.exit(1)
