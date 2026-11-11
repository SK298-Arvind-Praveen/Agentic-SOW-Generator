import json
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree as ET

from app.diagram.service import DiagramSpec, Node, Edge, Group
from app.diagram.aws_icons import AwsIconRegistry
from app.diagram.narrative_boundaries import geometry, overview_xml, projection


def migration_spec():
    raw=json.loads((Path(__file__).parent/'fixtures/private_migration_graph.json').read_text())
    return DiagramSpec(raw['title'],tuple(Node(**n) for n in raw['nodes']),
        tuple(Edge(**e) for e in raw['edges']),groups=tuple(Group(**g) for g in raw.get('groups',[])),
        architecture_plan=raw['architecture_plan'])


def test_migration_sources_and_helpers_do_not_interrupt_runtime_path():
    spec=migration_spec()
    pos,boxes,parents,width,height,labels,kinds=geometry(spec)
    assert pos['source-db'][0]+pos['source-db'][2] < boxes['cloud'][0]
    assert pos['source-media'][0] > boxes['cloud'][0]+boxes['cloud'][2]
    assert pos['clients'][1] < boxes['cloud'][1]
    assert parents['dms'] == parents['ec2a'] == parents['runner']
    assert pos['dms'][0]+pos['dms'][2] < pos['ec2a'][0]
    assert pos['ec2a'][0] == pos['rds-primary'][0]
    assert pos['ec2b'][0] == pos['rds-standby'][0]
    assert kinds[parents['ec2a']]=='private'
    assert kinds[parents['rds-primary']]=='isolated'
    assert pos['ec2a'][1]-boxes[parents['ec2a']][1] >= 80
    assert boxes[parents['ec2b']][0]-(boxes[parents['ec2a']][0]+boxes[parents['ec2a']][2]) >= 100
    assert parents['s3-media']=='region'
    assert set(pos)=={n.id for n in spec.nodes}
    links,indices=projection(spec)
    assert {('source-db','dms'),('dms','rds-primary'),('rds-primary','rds-standby'),
            ('ec2b','rds-primary')} <= {(l['edge'].source,l['edge'].target) for l in links}


def test_dense_migration_graph_renders_with_clear_runtime_and_replication_links():
    spec=migration_spec()
    xml,metrics=overview_xml(spec,AwsIconRegistry(Path(__file__).parents[1]/'assets'))
    assert metrics['node_overlaps']==metrics['connector_node_intersections']==0
    assert metrics['out_of_bounds']==metrics['containment_violations']==0
    assert metrics['ambiguous_connector_pairs']==0
    assert metrics['connector_crossings'] <= 8  # Previous layout had 15.
    assert metrics['original_edges']==len(spec.edges)
    assert metrics['nodes']==len(spec.nodes)
    assert 'badge_' in xml
    cells=ET.fromstring(xml).findall('.//mxCell')
    by_id={c.get('id'):c for c in cells}
    for caption in (c for c in cells if c.get('id','').startswith('flow_caption_')):
        edge=by_id[caption.get('id').replace('flow_caption_','flow_')]
        geo=caption.find('mxGeometry')
        centre=(float(geo.get('x'))+float(geo.get('width'))/2,
                float(geo.get('y'))+float(geo.get('height'))/2)
        eg=edge.find('mxGeometry')
        points=[eg.find("mxPoint[@as='sourcePoint']"),*eg.findall('Array/mxPoint'),eg.find("mxPoint[@as='targetPoint']")]
        points=[(float(p.get('x')),float(p.get('y'))) for p in points]
        assert any(min(a[0],b[0])<=centre[0]<=max(a[0],b[0]) and
                   min(a[1],b[1])<=centre[1]<=max(a[1],b[1]) for a,b in zip(points,points[1:]))
        assert cells.index(caption)>max(i for i,c in enumerate(cells) if c.get('edge')=='1')


def test_secondary_test_host_and_alternate_migration_az_keep_clear_lanes():
    spec=migration_spec()
    # The model can describe a test host as a caller instead of a recipient of
    # source data. Its position must not depend on that incidental edge direction.
    spec=replace(spec,edges=tuple(e for e in spec.edges if (e.source,e.target)!=('source-db','runner'))+
        (Edge('runner','alb','Load tests'),))
    p,*_=geometry(spec)
    assert p['runner'][0]+p['runner'][2] < p['ec2a'][0]
    # Zone IDs do not dictate migration-lane order or change actual ownership.
    spec=replace(spec,nodes=tuple(replace(n,availability_zone='az_b') if n.id in {'dms','runner'} else n
        for n in spec.nodes))
    p,b,parents,*_=geometry(spec)
    assert p['dms'][0] < p['ec2a'][0]
    assert parents['dms'] == parents['ec2b']
    assert parents['dms'] != parents['ec2a']
