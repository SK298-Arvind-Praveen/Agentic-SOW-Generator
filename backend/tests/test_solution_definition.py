from types import SimpleNamespace

from app.core.solution_definition import attach_traceability, bind_solution
from app.core.authoring_context import authoring_facts
from app.diagram.workflow_placement import nearby_rows
from app.diagram.knowledge import select_patterns, semantic_directory


def test_semantic_selection_does_not_need_trigger_phrase():
    req = {'objective': 'A coordinator delegates to experts and revises actions from their findings.',
           'service_design': {'reference_pattern_ids': ['agent-runtime']}}
    assert select_patterns(req, 1)[0]['id'] == 'agent-runtime'
    assert any(c['id'] == 'agent-runtime' for c in semantic_directory())


def test_agent_runtime_has_real_icon_and_framework_is_not_a_service():
    from pathlib import Path
    from app.diagram.aws_icons import AwsIconRegistry
    registry = AwsIconRegistry(Path(__file__).parents[1] / 'assets')
    assert registry.named_service('Amazon Bedrock AgentCore Runtime').key.endswith('amazon-bedrock-agentcore')
    assert registry.named_service('Strands Agents') is None


def test_ledger_preserves_release_and_verifies_source_without_inventing_quotes():
    source = 'Release two adds publisher integration. Retain logs for twelve months.'
    design = {'requirement_ledger': [
        {'requirement': 'Publisher integration', 'source_quote': 'Release two adds publisher integration.',
         'disposition': 'included', 'release': 'two'},
        {'requirement': 'Invented', 'source_quote': 'This was never said', 'disposition': 'excluded'}]}
    checked = attach_traceability(design, source)
    first, second = checked['requirement_ledger']
    assert first['source_verified'] and first['release'] == 'two'
    assert source[first['source_ref']['start']:first['source_ref']['end']] == first['source_quote']
    assert not second['source_verified'] and 'source_ref' not in second
    assert checked['traceability_issues']
    assert 'source_verified' not in design['requirement_ledger'][0]


def test_shared_contract_survives_authoring_and_version_changes_with_scope():
    d = {'services': [{'name': 'Amazon Bedrock AgentCore'}],
         'requirement_ledger': [{'disposition': 'included', 'release': 'two'}]}
    first = bind_solution({}, d)
    assert authoring_facts(first)['solution_definition']['contract'] == 'service_design'
    d['requirement_ledger'][0]['disposition'] = 'deferred'
    assert bind_solution({}, d)['solution_definition']['version'] != first['solution_definition']['version']
    assert first['service_design']['requirement_ledger'][0]['disposition'] == 'included'


def test_shared_definition_does_not_invalidate_service_design_cache():
    from app.diagram.service_design import fingerprint
    req = {'objective': 'Review incoming documents'}
    before = fingerprint(req, req['objective'])
    bound = bind_solution(req, {'summary': 'Review', 'services': []})
    assert fingerprint(bound, req['objective']) == before


def test_placement_brings_chain_nearby_without_changing_nodes_or_rows():
    rows = [['a', 'c'], ['d', 'b']]
    edges = [SimpleNamespace(source=a, target=b) for a,b in [('a','b'),('b','c'),('c','d')]]
    result = nearby_rows(rows, edges)
    assert sorted(k for r in result for k in r) == ['a','b','c','d']
    assert [len(r) for r in result] == [2,2]
    def distance(value):
        pos = {k:(x,y) for y,r in enumerate(value) for x,k in enumerate(r)}
        return sum(abs(pos[e.source][0]-pos[e.target][0])+abs(pos[e.source][1]-pos[e.target][1]) for e in edges)
    assert distance(result) <= distance(rows)
