from copy import deepcopy
import pytest


def test_context_preserves_all_evidence_and_excludes_calculator_payload():
    from app.diagram.context import architecture_context
    source = 'evidence ' * 30000
    result = architecture_context({'architecture_source_context': source,
        'functional_requirements': ['chat'], 'aws_pricing_result': {'large': 'private transport'},
        'service_design': {'services': ['Lambda']}, 'region': 'eu-west-2'}, {'pricing_region': 'ap-south-1'})
    assert result['source'] == source
    assert 'aws_pricing_result' not in result['requirements']
    assert result['selected_region'] == 'ap-south-1'
    assert sum(c['end'] - c['start'] for c in result['evidence_chunks']) == len(source)


def test_frozen_version_excludes_presentation_but_includes_ownership_and_edges():
    from app.diagram.contracts import freeze
    spec = {'nodes': [{'id': 'a', 'account': 'customer'}, {'id': 'b', 'account': 'supplier'}],
            'edges': [{'source': 'a', 'target': 'b', 'label': 'Read'}], 'architecture_plan': {}}
    original = freeze(spec)
    changed = deepcopy(spec); changed['architecture_plan']['process_story'] = {'steps': []}
    assert freeze(changed)['version'] == original['version']
    changed['nodes'][0]['account'] = 'supplier'
    assert freeze(changed)['version'] != original['version']
    assert original['operations'][0]['operation_type'] == 'unknown'


def test_dependencies_cannot_silently_pass_after_semantic_change():
    from app.diagram.contracts import stale_artifacts
    assert stale_artifacts('new', {'scope_of_work': 'old', 'aws_pricing': 'old', 'service_table': 'new'}) == ['scope_of_work', 'aws_pricing']


def test_every_graph_puts_canonical_architecture_before_dependent_authoring():
    from app.core.graph import create_preview_graph, create_fast_preview_graph, create_graph
    for build in (create_preview_graph, create_fast_preview_graph, create_graph):
        graph = build().get_graph()
        edges = {(e.source, e.target) for e in graph.edges}
        assert ('solution_design', 'architecture') in edges
        assert ('architecture', 'scope_architecture') in edges
        assert ('solution_design', 'scope_architecture') not in edges


def test_accepted_services_replace_stale_suggestions_without_promoting_them():
    from types import SimpleNamespace
    from app.diagram.contracts import bind_requirements
    registry = SimpleNamespace(by_key={'aws.service.lambda': {'label': 'AWS Lambda'}})
    result = bind_requirements({'aws_services': ['Amazon EC2'], 'confirmed_aws_services': ['Amazon EC2']},
        {'nodes': [{'id': 'app', 'scope': 'managed', 'icon_key': 'aws.service.lambda'}], 'edges': []}, registry)
    assert result['aws_services'] == ['AWS Lambda']
    assert result['confirmed_aws_services'] == []
    assert result['approved_architecture']['nodes'][0]['id'] == 'app'


def test_equal_versions_cannot_change_positional_edge_meaning():
    from app.diagram.contracts import freeze
    graph = {'nodes':[{'id':k} for k in 'abc'], 'edges':[
        {'source':'a','target':'b'}, {'source':'b','target':'c'}]}
    first = freeze(graph)
    second = freeze({**graph, 'edges':list(reversed(graph['edges']))})
    assert first['version'] != second['version'] or first['operations'] == second['operations']


def test_typed_operation_survives_planning_normalization_and_freeze():
    from app.diagram.service import DiagramService, validate_spec
    from app.diagram.contracts import freeze
    nodes=[{'id':'caller','label':'App','kind':'service','layer':0},
           {'id':'data','label':'Records','kind':'service','layer':1}]
    edge={'source':'caller','target':'data','label':'Read records','operation_type':'read',
          'initiator':'caller','data_direction':'target_to_source','evidence_refs':['c1']}
    edges=DiagramService._simplify_architecture_edges(nodes,[edge])
    spec=validate_spec({'nodes':nodes,'edges':edges},'Read')
    operation=freeze(spec)['operations'][0]
    assert operation['data_direction']=='target_to_source'
    assert operation['initiator']=='caller' and operation['evidence_refs']==('c1',)


def test_operation_initiator_can_be_upstream_of_network_hop():
    import pytest
    from app.diagram.service import validate_spec
    nodes=[{'id':key,'label':key,'kind':'service','layer':i} for i,key in enumerate(['caller','endpoint','data'])]
    edges=[{'source':'caller','target':'endpoint'},
           {'source':'endpoint','target':'data','operation_type':'read',
            'initiator':'caller','data_direction':'target_to_source'}]
    spec=validate_spec({'nodes':nodes,'edges':edges},'Read through endpoint')
    assert spec.edges[1].initiator=='caller'
    edges[1]['initiator']='nonexistent'
    with pytest.raises(ValueError,match='initiator'):
        validate_spec({'nodes':nodes,'edges':edges},'Unknown initiator')
