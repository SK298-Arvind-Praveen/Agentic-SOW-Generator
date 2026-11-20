import copy
import json
from html import unescape
from types import SimpleNamespace
from pathlib import Path

import pytest
from docx import Document

from app.diagram.architecture_text import flow_order, render_table, synchronize, write


@pytest.mark.parametrize('conflict', [False, True])
def test_captured_same_launch_template_replicas_allow_representative_ancillary_edges(conflict):
    from app.diagram.architecture_text import _table_rows, service_nodes
    spec=json.loads((Path(__file__).parent/'fixtures/kingfisher_table_representative_edges.json').read_text())
    original=copy.deepcopy(spec)
    roles=spec['architecture_plan']['narrative_view']['roles']
    rows=[{'node_id':n['id'], 'role': ('Runs the catalogue application and queries the shared database.'
          if n['id'] in {'ec2_a','ec2_b'} else roles.get(n['id'],n['label']))} for n in service_nodes(spec)]
    if conflict:
        next(e for e in spec['edges'] if e['source']=='ec2_b' and e['target']=='rds_primary').update(
            operation_type='write', data_direction='source_to_target')
        next(e for e in spec['edges'] if e['source']=='ec2_a' and e['target']=='rds_primary').update(
            operation_type='read', data_direction='target_to_source')
    table=_table_rows(spec,rows)
    app_rows=[r for r in table if set(r['node_ids']) & {'ec2_a','ec2_b'}]
    assert len(app_rows)==(2 if conflict else 1)
    assert {k for r in table for k in r['node_ids']} == {r['node_id'] for r in rows}
    if not conflict: assert spec == original


def replica_asset():
    nodes = []
    roles = {}
    for prefix, label, subnet, planned in [
        ('conn', 'AWS Lambda', 'private', 'Connector'),
        ('nat', 'NAT Gateway', 'public', 'Egress'),
    ]:
        for zone in ('a', 'b'):
            node_id = f'{prefix}_{zone}'
            nodes.append({
                'id': node_id, 'label': label, 'kind': 'service', 'scope': 'az',
                'account': 'AWS Account', 'region': 'ap-south-1', 'vpc': 'Connector VPC',
                'availability_zone': f'az_{zone}', 'subnet': subnet,
            })
            roles[node_id] = f'{planned} AZ-{zone.upper()}'
    return {'spec': {
        'nodes': nodes,
        'edges': [{'source': f'conn_{zone}', 'target': f'nat_{zone}', 'label': 'Outbound route'}
                  for zone in ('a', 'b')],
        'architecture_plan': {'narrative_view': {'roles': roles}},
    }}


def replica_rows(spec):
    roles = {
        f'conn_{zone}': f'Connector Lambda in AZ {zone.upper()} private subnet calling Hybris order APIs and enterprise OTP APIs.'
        for zone in ('a', 'b')
    }
    roles.update({
        f'nat_{zone}': f'Provides outbound-only egress for AZ {zone.upper()} connector calls toward the Internet Gateway.'
        for zone in ('a', 'b')
    })
    return [{'node_id': node_id, 'role': roles[node_id]} for node_id in flow_order(spec)]


def table_cells(text):
    return [[unescape(cell.strip()) for cell in line.strip('|').split('|')]
            for line in text.splitlines()[2:]]


def test_equivalent_az_roles_have_one_display_row_and_complete_instance_coverage():
    asset = replica_asset()
    original = copy.deepcopy(asset['spec'])
    response = json.dumps({'rows': replica_rows(asset['spec'])})
    llm = SimpleNamespace(generate=lambda *args, **kwargs: SimpleNamespace(text=response))

    text, audit = write(llm, asset)

    assert table_cells(text) == [
        ['AWS Lambda — AZ A & AZ B',
         'Connector Lambda across private subnets calling Hybris order APIs and enterprise OTP APIs.'],
        ['NAT Gateway — AZ A & AZ B',
         'Provides outbound-only egress for connector calls toward the Internet Gateway.'],
    ]
    assert audit['status'] == 'aligned' and audit['attempts'] == 1
    assert audit['row_count'] == 2
    assert audit['component_ids'] == ['conn_a', 'conn_b', 'nat_a', 'nat_b']
    assert audit['row_component_ids'] == [['conn_a', 'conn_b'], ['nat_a', 'nat_b']]
    assert asset['spec'] == original


@pytest.mark.parametrize(('field', 'value'), [
    ('account', 'Other account'), ('region', 'eu-west-1'), ('vpc', 'Other VPC'),
    ('subnet', 'public'), ('deployment_role', 'standby'),
    ('subtitle', 'Processes refund requests'), ('availability_zone', 'az_a'),
])
def test_same_service_does_not_merge_different_purpose_or_deployment(field, value):
    asset = replica_asset()
    asset['spec']['nodes'][1][field] = value
    rows = replica_rows(asset['spec'])

    cells = table_cells(render_table(asset['spec'], rows))

    # The distinct connector context also distinguishes the NAT's incoming flow.
    assert len(cells) == 4
    assert sum(name.startswith('AWS Lambda') for name, _ in cells) == 2


@pytest.mark.parametrize('distinct_by', ['generated_role', 'planned_role'])
def test_writer_and_standby_remain_separate_even_with_same_service(distinct_by):
    asset = replica_asset()
    spec = asset['spec']
    spec['nodes'] = spec['nodes'][:2]
    spec['edges'] = []
    for node in spec['nodes']:
        node['label'] = 'Amazon RDS'
    rows = [{'node_id': 'conn_a', 'role': 'Stores current order records'},
            {'node_id': 'conn_b', 'role': 'Stores current order records'}]
    if distinct_by == 'generated_role':
        rows[0]['role'] = 'Writer stores current order records'
        rows[1]['role'] = 'Standby replicates current order records'
    else:
        spec['architecture_plan']['narrative_view']['roles'] = {
            'conn_a': 'Primary writer AZ-A', 'conn_b': 'Standby replica AZ-B'}

    assert len(table_cells(render_table(spec, rows))) == 2


def test_distinct_s3_data_sets_and_unzoned_workloads_remain_separate():
    spec = {'nodes': [
        {'id': 'assets', 'label': 'Amazon S3', 'subtitle': 'Web assets', 'scope': 'regional'},
        {'id': 'evidence', 'label': 'Amazon S3', 'subtitle': 'Audit evidence', 'scope': 'regional'},
        {'id': 'worker1', 'label': 'AWS Lambda', 'scope': 'regional'},
        {'id': 'worker2', 'label': 'AWS Lambda', 'scope': 'regional'},
    ]}
    rows = [{'node_id': node['id'], 'role': 'Handles project data'} for node in spec['nodes']]

    cells = table_cells(render_table(spec, rows))

    assert len(cells) == 4
    assert [row[0] for row in cells[:2]] == ['Amazon S3 — Web assets', 'Amazon S3 — Audit evidence']


def test_different_downstream_data_targets_prevent_generic_role_merging():
    asset = replica_asset()
    spec = asset['spec']
    spec['nodes'].extend([
        {'id': 'assets', 'label': 'Amazon S3', 'subtitle': 'Web assets', 'scope': 'regional'},
        {'id': 'evidence', 'label': 'Amazon S3', 'subtitle': 'Audit evidence', 'scope': 'regional'},
    ])
    spec['edges'].extend([
        {'source': 'conn_a', 'target': 'assets', 'label': 'Reads objects'},
        {'source': 'conn_b', 'target': 'evidence', 'label': 'Reads objects'},
    ])
    roles = {row['node_id']: row['role'] for row in replica_rows(replica_asset()['spec'])}
    roles.update(assets='Stores project objects', evidence='Stores project objects')
    rows = [{'node_id': node_id, 'role': roles[node_id]} for node_id in flow_order(spec)]

    cells = table_cells(render_table(spec, rows))

    assert sum(name.startswith('AWS Lambda') for name, _ in cells) == 2
    assert sum(name.startswith('NAT Gateway') for name, _ in cells) == 2


@pytest.mark.parametrize('difference', ['endpoint', 'label', 'direction'])
def test_different_external_inputs_prevent_identical_role_merging(difference):
    asset = replica_asset()
    spec = asset['spec']
    spec['nodes'].extend([
        {'id': 'orders', 'label': 'Orders API', 'scope': 'external'},
        {'id': 'refunds', 'label': 'Refunds API', 'scope': 'external'},
    ])
    spec['edges'].extend([
        {'source': 'orders', 'target': 'conn_a', 'label': 'Sends updates'},
        {'source': 'refunds', 'target': 'conn_b', 'label': 'Sends updates'},
    ])
    if difference == 'label':
        spec['edges'][-1].update(source='orders', label='Sends refunds')
    elif difference == 'direction':
        spec['edges'][-1].update(source='conn_b', target='orders')

    cells = table_cells(render_table(spec, replica_rows(spec)))

    assert sum(name.startswith('AWS Lambda') for name, _ in cells) == 2
    assert sum(name.startswith('NAT Gateway') for name, _ in cells) == 2


def test_downstream_distinction_propagates_back_through_replica_candidates():
    asset = replica_asset()
    spec = asset['spec']
    spec['nodes'].extend([
        {'id': 'public_api', 'label': 'Public API', 'scope': 'external'},
        {'id': 'private_api', 'label': 'Private API', 'scope': 'external'},
    ])
    spec['edges'].extend([
        {'source': 'nat_a', 'target': 'public_api', 'label': 'Outbound egress'},
        {'source': 'nat_b', 'target': 'private_api', 'label': 'Outbound egress'},
    ])
    original = copy.deepcopy(spec)
    response = json.dumps({'rows': replica_rows(spec)})
    llm = SimpleNamespace(generate=lambda *args, **kwargs: SimpleNamespace(text=response))

    text, audit = write(llm, asset)

    cells = table_cells(text)
    assert sum(name.startswith('AWS Lambda') for name, _ in cells) == 2
    assert sum(name.startswith('NAT Gateway') for name, _ in cells) == 2
    assert audit['row_component_ids'] == [['conn_a'], ['conn_b'], ['nat_a'], ['nat_b']]
    assert audit['component_ids'] == ['conn_a', 'conn_b', 'nat_a', 'nat_b']
    assert asset['spec'] == original


def test_missing_replica_still_retries_before_grouped_rendering():
    asset = replica_asset()
    complete = replica_rows(asset['spec'])
    drafts = iter([{'rows': [row for row in complete if row['node_id'] != 'conn_b']},
                   {'rows': complete}])
    llm = SimpleNamespace(generate=lambda *args, **kwargs: SimpleNamespace(text=json.dumps(next(drafts))))

    text, audit = write(llm, asset)

    assert audit['attempts'] == 2
    assert audit['row_count'] == 2
    assert len(table_cells(text)) == 2
    assert 'conn_b' in audit['component_ids']


def test_planned_role_recovery_groups_replicas_and_keeps_coverage():
    asset = replica_asset()
    original = copy.deepcopy(asset['spec'])
    llm = SimpleNamespace(generate=lambda *args, **kwargs: SimpleNamespace(text='invalid JSON'))
    content = {'architecture_diagram': 'Old table'}

    synchronize(llm, content, [asset])

    assert len(table_cells(content['architecture_diagram'])) == 2
    assert asset['text_alignment']['row_count'] == 2
    assert asset['text_alignment']['row_component_ids'] == [['conn_a', 'conn_b'], ['nat_a', 'nat_b']]
    assert asset['text_alignment']['status'] == 'needs_review'
    assert asset['spec'] == original


def test_unknown_recovery_roles_do_not_assert_replica_equivalence():
    asset = replica_asset()
    asset['spec'].pop('architecture_plan')
    llm = SimpleNamespace(generate=lambda *args, **kwargs: SimpleNamespace(text='invalid JSON'))
    content = {'architecture_diagram': 'Old table'}

    synchronize(llm, content, [asset])

    assert len(table_cells(content['architecture_diagram'])) == 4
    assert asset['text_alignment']['row_count'] == 4


def test_full_zone_names_are_preserved_and_neutral_role_has_no_dangling_preposition():
    asset = replica_asset()
    spec = asset['spec']
    spec['nodes'] = spec['nodes'][2:]
    spec['edges'] = []
    spec.pop('architecture_plan')
    spec['nodes'][0]['availability_zone'] = 'ap-south-1a'
    spec['nodes'][1]['availability_zone'] = 'ap-south-1b'
    rows = [
        {'node_id': 'nat_a', 'role': 'Provides outbound egress for ap-south-1a.'},
        {'node_id': 'nat_b', 'role': 'Provides outbound egress for ap-south-1b.'},
    ]

    assert table_cells(render_table(spec, rows)) == [[
        'NAT Gateway — ap-south-1a & ap-south-1b',
        'Provides outbound egress for each AZ.',
    ]]


def test_grouped_table_survives_word_export_with_preview_text_preserved():
    from app.document.document_builder import DocumentBuilder, SectionBuilder

    asset = replica_asset()
    text = render_table(asset['spec'], replica_rows(asset['spec']))
    doc = Document()
    builder = DocumentBuilder(SimpleNamespace())
    builder.doc = doc
    builder._configure_styles()

    SectionBuilder(doc, SimpleNamespace()).parse_content(text)

    table = doc.tables[0]
    assert len(table.rows) == 3
    assert [[cell.text for cell in row.cells] for row in table.rows[1:]] == table_cells(text)

