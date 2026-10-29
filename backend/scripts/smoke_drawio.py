"""Local-only export fixture: tests nested public/private shading, not a customer design."""
import base64
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.diagram.aws_icons import AwsIconRegistry
from app.diagram.service import DiagramService, DiagramSpec, Node, Edge


def main():
    os.environ['ARCHITECTURE_DIAGRAM_ENGINE'] = 'hybrid_drawio'
    service = DiagramService.__new__(DiagramService)
    service.config = SimpleNamespace(ASSETS_DIR=Path(__file__).resolve().parents[1] / 'assets')
    service.icon_registry = AwsIconRegistry(service.config.ASSETS_DIR)
    def node(key, name, layer, **kwargs):
        match = service.icon_registry.match(name)
        return Node(key, name, 'service', layer, icon_key=match['key'] if match else '', **kwargs)
    spec = DiagramSpec('Local export fixture', (
        Node('user', 'Users', 'external', 0, scope='external'),
        node('alb', 'Application Load Balancer', 1, scope='vpc', subnet='public', availability_zone='A'),
        node('worker', 'AWS Lambda', 2, scope='vpc', subnet='private', availability_zone='A'),
        node('data', 'Amazon RDS', 3, scope='vpc', subnet='private', availability_zone='A'),
        node('logs', 'Amazon CloudWatch', 3, scope='managed', placement_role='operations'),
    ), (Edge('user','alb'), Edge('alb','worker'), Edge('worker','data')))
    asset = service._asset('architecture_overview','Solution Architecture',spec,{},False)
    folder = Path(__file__).resolve().parents[1] / 'output/drawio-local-test/nested'
    folder.mkdir(parents=True, exist_ok=True)
    (folder/'diagram.png').write_bytes(base64.b64decode(asset['image_base64']))
    (folder/'diagram.drawio').write_text(asset['drawio_xml'], encoding='utf-8')
    (folder/'asset.json').write_text(json.dumps({k:v for k,v in asset.items()
        if k not in {'image_base64','drawio_xml','edit_url'}}, indent=2), encoding='utf-8')
    print(folder)


if __name__ == '__main__':
    main()
