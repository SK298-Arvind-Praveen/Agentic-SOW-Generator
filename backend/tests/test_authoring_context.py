from app.core.authoring_context import authoring_facts, boundary_summary
from app.diagram.service import DiagramSpec, Node, Edge, _aws_architecture_layout


def test_authoring_facts_removes_duplicate_sources_without_dropping_domain_facts():
    result = authoring_facts({'_original_objective': 'raw BRD', 'supporting_context': 'raw BRD',
                             'concurrent_users': 500, 'requirements': ['Retain human approval'],
                             'data_characteristics': {'retention': '12 months'}})
    assert 'raw BRD' not in str(result)
    assert result['concurrent_users'] == 500
    assert result['requirements'] == ['Retain human approval']
    assert result['data_characteristics']['retention'] == '12 months'


def test_boundary_summary_omits_module_expansion_but_keeps_decisions():
    plan = {'deliverables':[{'name':'Build','purpose':'Working tool','modules':['Details']}],
            'open_boundaries':['Support term']}
    assert 'modules' not in str(boundary_summary(plan))
    assert boundary_summary(plan)['open_boundaries'] == ['Support term']


def test_serverless_layout_has_no_empty_vpc_and_keeps_channels_external():
    spec = DiagramSpec('Test', (
        Node('web','Web','channel',0,scope='external',placement_role='entry'),
        Node('lambda','Lambda','service',1,scope='regional',placement_role='compute'),
        Node('s3','S3','data',2,scope='managed',placement_role='data'),
    ), (Edge('web','lambda'),Edge('lambda','s3')))
    positions, boxes, width, height = _aws_architecture_layout(spec)
    assert '__vpc' not in boxes and '__workload' not in boxes
    assert positions['web'][1] + positions['web'][3] < boxes['__aws_account'][1]
    assert all(x >= 0 and y >= 0 and x+w <= width and y+h <= height for x,y,w,h in positions.values())
