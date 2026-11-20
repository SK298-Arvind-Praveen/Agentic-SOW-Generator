from types import SimpleNamespace


def test_generic_recovery_retries_planning_instead_of_promoting_fallback():
    from app.diagram.repair_controller import repair_request
    result = repair_request({'used_fallback': True, 'retained_planned_spec': False,
        'spec': {'title': 'Fallback', 'nodes': [], 'edges': [], 'architecture_plan': {}},
        'rejected_spec': {'title': 'Rejected real graph'}, 'validation_warnings': ['Invalid plan']})
    assert result['replan'] and result['stage'] == 'graph'


def test_replica_projection_preserves_selected_story_edge_provenance():
    from app.diagram.service import DiagramSpec, Node, Edge
    from app.diagram.story_overview import projection
    from app.diagram.projection import select_links
    from app.diagram.process_story import validate
    nodes = tuple(Node(k, 'App AZ '+zone.upper(), 'service', 1,
        icon_key='aws.service.aws-lambda', scope='az', availability_zone='az_'+zone,
        placement_role='compute') for k, zone in [('a','a'),('b','b')]) + (
        Node('x', 'Enterprise API', 'service', 2, scope='external'),)
    story = {'steps': [{'id': 's1', 'title': 'Enterprise access',
        'description': 'Application workers call the enterprise API for order information.',
        'node_ids': ['a','x'], 'edge_ids': ['e0'], 'flow_kind': 'egress'}]}
    spec = DiagramSpec('Replicas', nodes, (Edge('a','x','Call API'), Edge('b','x','Call API')),
        architecture_plan={'process_story': story})
    validate(story, spec)
    links, _ = projection(spec, set())
    retained = select_links(spec, links)
    assert len(retained) == 1
    assert {i for path in retained[0]['paths'] for i in path} == {0,1}


def test_pricing_uses_frozen_inventory_not_previous_service_design():
    from app.diagram.contracts import bind_requirements
    from app.pricing.service import AwsPricingService
    registry = SimpleNamespace(by_key={'aws.service.lambda': {'label': 'AWS Lambda'},
                                     'aws.resource.nat': {'label': 'AWS NAT Gateway'}})
    requirements = {'service_design': {'status':'ready', 'services':[
        {'name':'AWS Lambda', 'status':'proposed', 'purpose':'App'}]}}
    graph = {'nodes': [{'id':'app','icon_key':'aws.service.lambda','scope':'az'},
                       {'id':'nat','icon_key':'aws.resource.nat','scope':'az'}], 'edges':[]}
    bound = bind_requirements(requirements, graph, registry)
    assert set(AwsPricingService._candidate_services(bound, {})) == {'AWS Lambda','AWS NAT Gateway'}


def test_existing_aws_platform_can_remain_client_owned_external():
    from app.diagram.service import DiagramSpec, Node
    from app.diagram.service_design import validate_diagram_coverage
    key='aws.service.analytics.amazon-redshift'
    registry=SimpleNamespace(named_service=lambda name:SimpleNamespace(key=key), by_key={key:{}})
    spec=DiagramSpec('Existing warehouse',(Node('warehouse','Amazon Redshift','service',1,
        scope='external',icon_key=key),),(), architecture_plan={'service_mapping':[{'service_id':'s1','node_ids':['warehouse']}]})
    design={'status':'ready','services':[{'id':'s1','name':'Amazon Redshift','status':'confirmed',
        'purpose':'Existing client warehouse accepting exported records'}]}
    assert validate_diagram_coverage(spec,design,registry).nodes[0].scope=='external'
    import pytest
    design['services'][0].update(status='proposed',purpose='New warehouse for this solution')
    with pytest.raises(ValueError,match='unrelated'):
        validate_diagram_coverage(spec,design,registry)


def test_website_region_overrides_source_and_placeholder_without_replanning():
    from app.diagram.service import DiagramSpec, Node
    from app.diagram.deployment_checks import validate
    spec=DiagramSpec('Region',(Node('app','Lambda','service',1,scope='managed',region='Region'),),())
    updated=validate(spec,{'architecture_source_context':'Deploy in the UK region eu-west-2.'},'ap-south-1')
    assert updated.nodes[0].region=='ap-south-1'
    assert spec.nodes[0].region=='Region'


def test_detail_only_step_is_rejected_before_attempting_panel_render():
    from app.diagram.service import DiagramSpec, Node, Edge
    from app.diagram.process_story import validate
    import pytest
    spec=DiagramSpec('Config',(Node('a','App','service',1),Node('k','Secrets','service',1)),(Edge('a','k'),))
    story={'steps':[{'id':'s1','title':'Read secrets','description':'The application reads its private credentials before making calls.',
        'node_ids':['a','k'],'edge_ids':['e0'],'flow_kind':'runtime'}]}
    with pytest.raises(ValueError,match='no visible overview path'):
        validate(story,spec,set())


def test_mixed_story_replans_hidden_control_only_step():
    import json
    from unittest.mock import Mock
    from app.diagram.service import DiagramSpec, Node, Edge
    from app.diagram.process_story import prepare
    from app.diagram.narrative_boundaries import projection
    story = {'steps':[{'id':'s1','title':'Read certificate',
        'description':'The application reads its certificate before serving secure requests.',
        'node_ids':['app','acm'],'edge_ids':['e0'],'flow_kind':'runtime'}]}
    spec=DiagramSpec('Mixed',(
        Node('app','Application','service',1,scope='az',placement_role='compute'),
        Node('acm','Certificate Manager','service',1,scope='regional',placement_role='security'),
        *(Node(k,k,'service',2,scope='managed') for k in ['api','data','report'])),
        (Edge('app','acm'),Edge('api','app')),
        architecture_plan={'functional_deployment_view':True,'process_story':story,
            'narrative_view':{'groups':[{'id':'work','rows':[['app']]},
                                      {'id':'services','rows':[['api','data','report']]}]}})
    assert 0 not in {i for link in projection(spec)[0] for path in link['paths'] for i in path}
    revised={'steps':[{'id':'s1','title':'Handle requests',
        'description':'The API invokes the application to handle customer requests.',
        'node_ids':['api','app'],'edge_ids':['e1'],'flow_kind':'runtime'}]}
    model=Mock();model.generate.return_value=SimpleNamespace(text=json.dumps(revised))
    result=prepare(SimpleNamespace(llm=model),spec)
    assert result.architecture_plan['process_story']==revised
    assert model.generate.call_count==1
