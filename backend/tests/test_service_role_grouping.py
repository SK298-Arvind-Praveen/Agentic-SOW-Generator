from app.diagram.architecture_text import _table_rows


def test_identical_roles_group_across_zones_with_different_wiring():
    spec = {'nodes': [
        {'id': 'a', 'label': 'ECS Fargate Tasks — AZ A', 'availability_zone': 'a', 'scope': 'az'},
        {'id': 'b', 'label': 'ECS Fargate Tasks — AZ B', 'availability_zone': 'b', 'scope': 'az'},
        {'id': 'db', 'label': 'Database', 'scope': 'regional'}],
        'edges': [{'source': 'a', 'target': 'db'}]}
    rows = [{'node_id': 'a', 'role': 'Runs the booking web and API application.'},
            {'node_id': 'b', 'role': 'Runs the booking web and API application.'},
            {'node_id': 'db', 'role': 'Stores booking records.'}]
    table = _table_rows(spec, rows)
    assert len(table) == 2
    grouped = next(r for r in table if len(r['node_ids']) == 2)
    assert grouped['name'] == 'ECS Fargate Tasks — AZ A & AZ B'
    assert set(grouped['node_ids']) == {'a', 'b'}
    rows[1]['role'] = 'Runs background report exports.'
    assert len(_table_rows(spec, rows)) == 3
