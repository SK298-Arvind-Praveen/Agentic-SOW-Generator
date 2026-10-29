"""Offline rendering QA for reference boundary styles; illustrative, not a client design."""
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
    root = Path(__file__).resolve().parents[1]
    registry = AwsIconRegistry(root / 'assets')

    def icon(label):
        return next((key for key, entry in registry.by_key.items()
                     if entry['label'] == label), '')

    spec = DiagramSpec('Reference styling QA - illustrative private workload', (
        Node('hub', 'Approved downloads', 'external', 3, scope='external'),
        Node('worker', 'EC2 worker', 'service', 1, scope='vpc',
             icon_key=icon('Amazon EC2'), availability_zone='az_a', subnet='private'),
        Node('nat', 'NAT gateway', 'service', 2, scope='vpc',
             icon_key=icon('Amazon VPC NAT Gateway'), availability_zone='az_a', subnet='public'),
        Node('igw', 'Internet gateway', 'service', 2, scope='vpc', icon_key=icon('Amazon VPC Internet Gateway')),
        Node('s3', 'Amazon S3', 'data', 2, scope='managed',
             icon_key=icon('Amazon Simple Storage Service')),
        Node('model', 'Amazon Bedrock', 'service', 2, scope='managed',
             icon_key=icon('Amazon Bedrock')),
    ), (Edge('worker', 's3', 'Read/write'), Edge('worker', 'model', 'Inference'),
        Edge('worker', 'nat', 'HTTPS egress'), Edge('nat', 'igw'), Edge('igw', 'hub')))
    service = DiagramService.__new__(DiagramService)
    service.config = SimpleNamespace(ASSETS_DIR=root / 'assets')
    service.icon_registry = registry
    os.environ['ARCHITECTURE_DIAGRAM_ENGINE'] = 'elk'
    asset = service._asset('architecture_overview', 'Solution Architecture', spec, {}, False)
    if asset['layout_engine'] != 'elk':
        raise RuntimeError(asset['renderer_fallback'])
    folder = root / 'output/reference-style-smoke'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'architecture.png').write_bytes(base64.b64decode(asset['image_base64']))
    (folder / 'architecture.drawio').write_text(asset['drawio_xml'], encoding='utf-8')
    (folder / 'metrics.json').write_text(json.dumps(asset['layout_metrics'], indent=2), encoding='utf-8')
    print(json.dumps({'image': str(folder / 'architecture.png'), 'metrics': asset['layout_metrics']}))


if __name__ == '__main__':
    main()
