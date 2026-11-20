import pytest
from app.diagram.service import DiagramSpec, Node, Edge


def graph():
    return DiagramSpec('Chat', (
        Node('handler', 'Lambda', 'service', 1, icon_key='aws.service.aws-lambda'),
        Node('nat', 'NAT Gateway', 'service', 1, icon_key='aws.service.nat-gateway'),
        Node('staging', 'S3 Knowledge Staging', 'service', 1, icon_key='aws.service.amazon-s3'),
        Node('kb', 'Bedrock Knowledge Bases', 'service', 1, icon_key='aws.service.amazon-bedrock-knowledge-bases'),
    ), (Edge('handler', 'nat', 'Outbound route'), Edge('staging', 'kb', 'Ingest articles'),
        Edge('handler', 'kb', 'Retrieve answers')))


def step(kind='egress', edge='e0'):
    return {'id': 's1', 'title': 'Enterprise calls',
            'description': 'Private connectors call enterprise APIs through outbound gateways.',
            'edge_ids': [edge], 'node_ids': ['handler', 'nat'], 'flow_kind': kind}


def test_outbound_gateway_cannot_be_called_inbound_access():
    from app.diagram.process_story import validate
    with pytest.raises(ValueError, match='outbound'):
        validate({'steps': [step('ingress')]}, graph())
    assert validate({'steps': [step()]}, graph())['steps'][0]['flow_kind'] == 'egress'


def test_ingestion_is_not_runtime_retrieval():
    from app.diagram.process_story import validate
    value = step('retrieval', 'e1'); value['node_ids'] = ['staging', 'kb']
    with pytest.raises(ValueError, match='ingestion'): validate({'steps': [value]}, graph())


def test_unknown_edge_and_service_list_prose_are_rejected():
    from app.diagram.process_story import validate
    with pytest.raises(ValueError, match='edge'): validate({'steps': [step(edge='e99')]}, graph())
    value = step(); value['description'] = 'Lambda uses NAT Gateway for invoke.'
    with pytest.raises(ValueError, match='workflow'): validate({'steps': [value]}, graph())


def test_story_budget_requires_consolidation_not_long_panel():
    from app.diagram.process_story import validate
    with pytest.raises(ValueError, match='12'):
        validate({'steps': [{**step(), 'id': f's{i}'} for i in range(13)]}, graph())


def test_reporting_service_is_not_hidden_as_shared_infrastructure():
    from app.diagram.narrative import support_ids
    spec = DiagramSpec('Analytics', (Node('bi', 'QuickSight', 'service', 1,
        icon_key='aws.service.analytics.amazon-quicksight', placement_role='operations', scope='regional'),), ())
    assert 'bi' not in support_ids(spec)


def test_story_planner_has_its_own_system_contract(monkeypatch):
    import json
    from types import SimpleNamespace
    from app.core.bedrock_llm import BedrockLLM
    from app.diagram.process_story import prepare
    diagram_llm = BedrockLLM.__new__(BedrockLLM)
    diagram_llm.system_prompt = 'Return architecture XML only'
    captured = []
    def generate(self, prompt, **kwargs):
        captured.append(self.system_prompt)
        return SimpleNamespace(text=json.dumps({'steps':[step()]}))
    monkeypatch.setattr(BedrockLLM, 'generate', generate)
    service = SimpleNamespace(llm=diagram_llm, config=SimpleNamespace(), bedrock=object())
    prepare(service, graph())
    assert captured and 'Return architecture XML only' not in captured
    assert 'workflow' in captured[0].lower()


def test_representative_story_edges_can_cover_parallel_and_intermediate_nodes():
    from app.diagram.process_story import validate
    nodes=tuple(Node(k,k,'service',i) for i,k in enumerate(['alb','a','b','route','source','unrelated']))
    spec=DiagramSpec('Representative paths',nodes,(Edge('alb','a'),Edge('alb','b'),
        Edge('a','route'),Edge('route','source')))
    story={'steps':[{'id':'s1','title':'Route customer requests',
        'description':'The load balancer routes customer requests to either application replica.',
        'node_ids':['alb','a','b'],'edge_ids':['e0'],'flow_kind':'runtime'},
        {'id':'s2','title':'Read source records',
         'description':'The application reads source records through the approved private connection.',
         'node_ids':['a','route','source'],'edge_ids':['e2'],'flow_kind':'migration'}]}
    assert validate(story,spec)==story
    story['steps'][0]['node_ids'].append('unrelated')
    with pytest.raises(ValueError,match='participate|connected'):
        validate(story,spec)
