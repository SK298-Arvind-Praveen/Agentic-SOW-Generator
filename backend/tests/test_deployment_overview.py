from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import pytest
from app.diagram.service import Node, Edge, DiagramSpec, DiagramService, expand_security_icons
from app.diagram.aws_icons import AwsIconRegistry
from app.diagram.deployment import projection
from app.diagram.deployment_checks import validate
from app.diagram.reliability import structured_retry, pipeline_attempt


def test_projection_preserves_ownership_and_all_connections():
    nodes = (Node('app', 'App', 'service', 0, scope='vpc', account='A', region='eu-west-2',
                  vpc='Private VPC', subnet='private', availability_zone='A'),
             Node('db', 'Database', 'service', 1, scope='vpc', account='B', region='eu-west-1'),
             Node('logs', 'Logs', 'service', 2, scope='regional', placement_role='operations'))
    spec = DiagramSpec('Multiple owners', nodes, (Edge('app','db'), Edge('app','logs')))
    projected, coverage = projection(spec)
    assert projected.nodes == spec.nodes
    assert projected.edges == (spec.edges[0],)
    assert sorted(coverage['visible_edge_indices']+coverage['shared_control_edge_indices']) == [0,1]
    assert coverage['shared_control_edge_indices'] == [1]
    assert spec.edges == (Edge('app','db'), Edge('app','logs'))


def test_service_identity_is_not_replaced_by_generic_alias():
    registry = AwsIconRegistry(Path(__file__).parents[1]/'assets')
    assert registry.named_service('AWS DMS').key == 'aws.service.databases.aws-database-migration-service'
    identity = registry.named_service('AWS IAM Identity Center')
    assert identity.key.endswith('aws-iam-identity-center')
    node = Node('identity', 'AWS IAM Identity Center', 'service', 0, scope='regional', icon_key=identity.key)
    spec = DiagramSpec('Auth', (node,), ())
    assert expand_security_icons(spec, registry).nodes == spec.nodes


def test_control_named_storage_retains_storage_identity():
    registry = AwsIconRegistry(Path(__file__).parents[1]/'assets')
    node = Node('logs', 'S3 CloudTrail Logs', 'service', 1, scope='regional',
                icon_key=registry.named_service('Amazon S3').key, placement_role='data')
    spec = DiagramSpec('Audit', (node,), ())
    assert expand_security_icons(spec, registry).nodes == (node,)


def test_explicit_deployment_constraints_cannot_disappear():
    spec = DiagramSpec('App', (Node('a','EC2','service',0,scope='vpc',placement_role='compute'),), ())
    requirements = {'architecture_source_context':'Two AZs in eu-west-2 behind an internal ALB.'}
    with pytest.raises(ValueError, match='two AZs'):
        validate(spec, requirements)
    assert validate(spec, {}) == spec  # Never invent constraints for another BRD.


@pytest.mark.parametrize('failure', ['render', 'visual', 'fallback', 'review'])
def test_pipeline_retries_once_and_carries_feedback(failure, monkeypatch):
    service = DiagramService.__new__(DiagramService)
    service.config = SimpleNamespace()
    calls = []
    def generate(req, meta, narrative):
        calls.append(narrative)
        if len(calls) == 1:
            if failure == 'render':
                raise TimeoutError('Export timed out')
            return [{'image_base64':'png', 'used_fallback':failure=='fallback',
                     'layout_engine':'deployment_drawio', 'vision_review':
                     {'status':'unavailable' if failure=='review' else 'reviewed',
                      'issues':[{'kind':'visual','description':'Crossing'}] if failure=='visual' else []}}]
        return [{'image_base64':'png','vision_review':{'status':'reviewed','issues':[]}}]
    monkeypatch.setattr(service, '_generate_assets_once', generate)
    monkeypatch.setattr('app.diagram.service.local_fallback_asset', lambda *a: {
        'image_base64':'fallback','used_fallback':True,'validation_warnings':['Export timed out']})
    result = service._generate_assets({}, {}, 'Original context')[0]
    assert len(calls) == 2
    assert 'Corrective attempt' in calls[1]
    assert len(result['pipeline_attempts']) == 2
    assert not result['retry_exhausted']
    assert pipeline_attempt.get() == 0


def test_persistent_failure_stops_after_third_attempt(monkeypatch):
    service = DiagramService.__new__(DiagramService)
    calls = []
    def generate(*args):
        calls.append(1)
        return [{'image_base64':'png','used_fallback':True}]
    monkeypatch.setattr(service,'_generate_assets_once',generate)
    result = service._generate_assets({}, {}, '')[0]
    assert len(calls) == 3 and result['retry_exhausted']
    assert result['image_base64']  # Preserve useful output after failed retry.


def test_pipeline_cancellation_is_not_retried(monkeypatch):
    from app.preview.cancellation import GenerationCancelled
    service = DiagramService.__new__(DiagramService)
    calls = []
    def generate(*args):
        calls.append(1)
        raise GenerationCancelled()
    monkeypatch.setattr(service,'_generate_assets_once',generate)
    with pytest.raises(GenerationCancelled):
        service._generate_assets({}, {}, '')
    assert len(calls) == 1 and pipeline_attempt.get() == 0


def test_nested_json_stage_gets_only_one_corrective_retry():
    calls = []
    token = pipeline_attempt.set(1)
    try:
        with pytest.raises(ValueError):
            structured_retry(lambda p: calls.append(p) or '{}', '', lambda v: v['required'], attempts=3)
    finally:
        pipeline_attempt.reset(token)
    assert len(calls) == 2


def test_budgets_are_longer_but_bounded_and_configurable(monkeypatch):
    from app.diagram.budgets import seconds
    assert seconds('model') >= 180 and seconds('review') >= 240
    monkeypatch.setenv('ARCHITECTURE_RENDER_TIMEOUT_SECONDS','300')
    assert seconds('render') == 300
    monkeypatch.setenv('ARCHITECTURE_RENDER_TIMEOUT_SECONDS','999999')
    assert seconds('render') == 600
    monkeypatch.setenv('ARCHITECTURE_RENDER_TIMEOUT_SECONDS','invalid')
    assert seconds('render') == 300


def test_failed_export_retries_same_valid_plan_once(monkeypatch):
    service = DiagramService.__new__(DiagramService)
    service.config = SimpleNamespace()
    service.icon_registry = AwsIconRegistry(Path(__file__).parents[1]/'assets')
    spec = DiagramSpec('Application', (Node('app','Application','service',0),), ())
    monkeypatch.setenv('ARCHITECTURE_DIAGRAM_ENGINE','builtin')
    monkeypatch.setattr('app.core.bedrock_llm._save_raw_output',lambda *a: None)
    monkeypatch.setattr(service,'_generate_specs',lambda *a: ([('architecture_overview','Solution Architecture',spec)],False))
    attempts = []
    def render(kind, placement, actual, *args):
        attempts.append(actual)
        if len(attempts) == 1:
            raise TimeoutError('Desktop export timed out')
        return {'image_base64':'png','spec':actual.as_dict()}
    monkeypatch.setattr(service,'_asset',render)
    result = service._generate_assets({}, {}, '')[0]
    assert len(attempts)==2 and attempts[0]==attempts[1]
    assert attempts[0].nodes==spec.nodes and attempts[0].edges==spec.edges
    assert attempts[0].architecture_plan['story_overview'] is True
    assert result['status'] == 'ready'
    assert result['render_attempts'][0]['error'] == 'Desktop export timed out'
    assert len(result['pipeline_attempts']) == 1
def test_geographic_and_independent_facility_requirements_are_not_lost():
    import pytest
    from dataclasses import replace
    from app.diagram.deployment_checks import validate
    from app.diagram.service import DiagramSpec, Node
    source = {'architecture_source_context':'Run across two independent hosting facilities in the UK region.'}
    node = Node('app_a','Application','service',1,scope='az',placement_role='compute',
                availability_zone='az_a',region='Region')
    spec = DiagramSpec('Booking',(node,),())
    with pytest.raises(ValueError,match='UK-region'):
        validate(spec,source)
    ready = replace(spec,nodes=(replace(node,region='eu-west-2'),
        replace(node,id='app_b',region='eu-west-2',availability_zone='az_b')))
    assert validate(ready,source) == ready




def test_third_attempt_can_recover_after_two_visual_failures(monkeypatch):
    service=DiagramService.__new__(DiagramService)
    calls=[]
    def generate(*args):
        calls.append(1)
        return [{'image_base64':'png','vision_review':{'status':'reviewed',
            'issues':[] if len(calls)==3 else [{'kind':'visual','description':'Crossings'}]}}]
    monkeypatch.setattr(service,'_generate_assets_once',generate)
    asset=service._generate_assets({}, {}, '')[0]
    assert len(calls)==3 and not asset['retry_exhausted']
    assert asset['vision_review']['issues']==[]
