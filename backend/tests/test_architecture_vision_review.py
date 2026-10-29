import base64
from dataclasses import replace
import io
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest

from app.agents import architecture_reviewer_agent as reviewer
from app.diagram.service import DiagramService, validate_spec, _layout
from app.diagram.aws_icons import AwsIconRegistry


@pytest.fixture
def scene(monkeypatch):
    monkeypatch.setenv('ARCHITECTURE_DIAGRAM_ENGINE', 'builtin')
    monkeypatch.setenv('ARCHITECTURE_VISION_REVIEW_ENABLED', 'true')
    service = DiagramService.__new__(DiagramService)
    service.config = SimpleNamespace(ASSETS_DIR=Path(__file__).parents[1] / 'assets')
    service.icon_registry = AwsIconRegistry(service.config.ASSETS_DIR)
    spec = validate_spec({'title': 'Support', 'nodes': [
        {'id': 'user', 'label': 'Customer', 'kind': 'actor', 'layer': 0, 'scope': 'external'},
        {'id': 'app', 'label': 'Application', 'kind': 'application', 'layer': 1}],
        'edges': [{'source': 'user', 'target': 'app', 'label': 'Request'}]}, 'Support', {})
    asset = service._asset('architecture_overview', 'Solution Architecture', spec, {}, False)
    return service, spec, asset


def review(scene):
    service, spec, asset = scene
    return reviewer.review_architecture(service, asset, spec, {}, {'project_title': 'Support'},
                                        'The Application uses managed compute services.')


def test_review_receives_image_and_repairs_once(scene, monkeypatch, tmp_path):
    calls = []
    def model(service, prompt, deadline, image=None, planner=False, **kwargs):
        calls.append(planner)
        assert image.startswith(b'\x89PNG')
        assert 'architecture_plan' in prompt and 'design_evidence' in prompt
        return json.dumps({'issues': [{'kind': 'visual', 'node_ids': ['app'], 'problem': 'Tight spacing'}],
                           'layout_patch': {'spacing_scale': 1.15}})
    monkeypatch.setattr(reviewer, '_call', model)
    monkeypatch.setenv('ARCHITECTURE_REVIEW_OUTPUT_DIR', str(tmp_path))
    result = review(scene)
    assert calls == [False]
    assert result['vision_review']['repair_passes'] == 1
    assert not result['vision_review']['candidate_visually_rechecked']
    assert result['spec']['nodes'] == scene[2]['spec']['nodes']
    assert result['spec']['edges'] == scene[2]['spec']['edges']
    assert result['spec']['spacing_scale'] == 1.15
    logs = list(tmp_path.glob('*/review.json'))
    assert len(logs) == 1
    assert logs[0].with_name('before.png').exists()
    assert logs[0].with_name('candidate.png').exists()
    assert json.loads(logs[0].read_text())['status'] == 'repaired_not_visually_rechecked'


@pytest.mark.parametrize('response', ['broken JSON'])
def test_malformed_review_preserves_image(scene, monkeypatch, response):
    monkeypatch.setattr(reviewer, '_call', lambda *a, **k: response)
    result = review(scene)
    assert result['image_base64'] == scene[2]['image_base64']
    assert result['vision_review']['status'] == 'review_unavailable'


def test_timeout_preserves_image(scene, monkeypatch):
    def timeout(*args, **kwargs):
        raise TimeoutError('review deadline')
    monkeypatch.setattr(reviewer, '_call', timeout)
    assert review(scene)['image_base64'] == scene[2]['image_base64']


def test_layout_issue_alias_does_not_discard_review(scene, monkeypatch):
    monkeypatch.setattr(reviewer, '_call', lambda *a, **k: json.dumps({
        'issues':[{'kind':'layout','node_ids':['app'],'problem':'Long connection'}],
        'layout_patch':{}}))
    result = review(scene)
    assert result['vision_review']['image_reviewed']
    assert result['vision_review']['issues'][0]['kind'] == 'visual'


@pytest.mark.parametrize('patch', [{'node_order': ['app']}, {'edge_order': []},
                                  {'spacing_scale': 5}, {'spacing_scale': float('nan')},
                                  {'scope': 'vpc'}, {'node_order': ['app', 'app']}])
def test_layout_rejects_loss_or_semantic_mutation(scene, patch):
    with pytest.raises(ValueError):
        reviewer.layout_patch(scene[1], patch)


def test_architecture_findings_require_planner_and_exact_evidence(scene, monkeypatch):
    calls = []
    def model(service, prompt, deadline, image=None, planner=False, **kwargs):
        calls.append(planner)
        if not planner:
            return json.dumps({'issues': [{'kind': 'architecture', 'node_ids': ['app'],
                                          'problem': 'Check compute containment'}], 'layout_patch': {}})
        assert image is None
        return json.dumps({'placements': [{'node_id': 'app', 'scope': 'managed', 'placement_role': 'compute',
                         'evidence_quote': 'The Application uses managed compute services.'}], 'unresolved': []})
    monkeypatch.setattr(reviewer, '_call', model)
    result = review(scene)
    assert calls == [False, True]
    assert result['vision_review']['image_reviewed']
    assert len(result['spec']['nodes']) == 2


def test_placement_cannot_invent_source_or_change_ownership(scene):
    for key, quote in [('app', 'Invented source statement'), ('user', 'The user is an external customer.')]:
        with pytest.raises(ValueError):
            reviewer.placement_patch(scene[1], [{'node_id': key, 'scope': 'vpc',
                'placement_role': 'compute', 'evidence_quote': quote}], 'The user is an external customer.')


def test_geometry_regression_rejected(scene, monkeypatch):
    monkeypatch.setattr(reviewer, '_call', lambda *a, **k: json.dumps(
        {'issues': [], 'layout_patch': {'spacing_scale': 1.2}}))
    monkeypatch.setattr(reviewer, 'measurements', lambda spec: {
        'node_overlaps': int(spec.spacing_scale > 1), 'connector_node_intersections': 0,
        'connector_crossings': 0, 'out_of_bounds': 0})
    result = review(scene)
    assert result['image_base64'] == scene[2]['image_base64']
    assert result['vision_review']['status'] == 'repair_rejected_geometry_regression'


def test_disabled_review_makes_no_calls(scene, monkeypatch):
    monkeypatch.setenv('ARCHITECTURE_VISION_REVIEW_ENABLED', 'false')
    monkeypatch.setattr(reviewer, '_call', lambda *a, **k: pytest.fail('disabled'))
    assert review(scene)['vision_review']['status'] == 'disabled'


def test_image_is_bounded_and_valid():
    buffer = io.BytesIO()
    Image.new('RGB', (9000, 300), 'white').save(buffer, 'PNG')
    data = reviewer.image_for_review(buffer.getvalue())
    assert len(data) < 3_500_000
    with Image.open(io.BytesIO(data)) as image:
        assert max(image.size) <= 2400


def test_review_call_has_short_timeout_no_retries_and_image(monkeypatch):
    config = SimpleNamespace(BEDROCK_REGION='us-east-1', FAST_MODEL_ID='haiku',
                             DIAGRAM_REVIEW_MODEL_ID='vision', DIAGRAM_MODEL_ID='planner')
    closed = []
    def factory(*args, **kwargs):
        sdk = kwargs['config']
        assert sdk.read_timeout <= 22
        assert sdk.connect_timeout == 2
        assert sdk.retries['total_max_attempts'] == 1
        return SimpleNamespace(close=lambda: closed.append(True))
    def generate(self, prompt, **kwargs):
        assert kwargs['image_bytes'] == b'PNG bytes'
        assert kwargs['model_id'] == 'vision'
        assert kwargs['retry_on_truncation'] is False
        assert kwargs.get('fallback_model_id') is None
        return SimpleNamespace(text='{}')
    monkeypatch.setattr(reviewer.boto3, 'client', factory)
    monkeypatch.setattr(reviewer.BedrockLLM, 'generate', generate)
    reviewer._call(SimpleNamespace(config=config), 'review', reviewer.time.monotonic()+60, b'PNG bytes')
    assert closed == [True]


def test_expired_budget_never_starts_a_call(monkeypatch):
    monkeypatch.setattr(reviewer.boto3, 'client', lambda *a, **k: pytest.fail('deadline expired'))
    with pytest.raises(TimeoutError):
        reviewer._call(None, 'review', reviewer.time.monotonic()-1)


def test_repair_renderer_failure_retains_working_image(scene, monkeypatch):
    monkeypatch.setattr(reviewer, '_call', lambda *a, **k: '{"issues":[],"layout_patch":{"spacing_scale":1.1}}')
    monkeypatch.setattr(scene[0], '_asset', lambda *a, **k: {**scene[2], 'layout_engine': 'failed-kit-fallback'})
    result = review(scene)
    assert result['image_base64'] == scene[2]['image_base64']
    assert result['vision_review']['status'] == 'repair_rejected_renderer_failure'


def test_rendered_kit_image_is_sent_to_reviewer(scene, monkeypatch):
    from app.diagram import arch_kit
    service, spec, asset = scene
    service.bedrock = object()
    monkeypatch.setenv('ARCHITECTURE_DIAGRAM_ENGINE', 'aws_arch_kit')
    monkeypatch.setattr(service, '_generate_specs', lambda *a: ([('architecture_overview', 'Solution Architecture', spec)], False))
    png = base64.b64decode(asset['image_base64'])
    monkeypatch.setattr(arch_kit, 'render_arch_kit', lambda *a, **k: png)
    calls = []
    def model(*a, **kwargs):
        calls.append(kwargs if kwargs else a)
        return '{"issues":[],"layout_patch":{}}'
    monkeypatch.setattr(reviewer, '_call', model)
    result = service.generate_assets({}, {}, 'Managed support application')
    assert len(calls) == 1
    # Missing cosmetic geometry metrics must not discard a valid rendered plan.
    assert result[0]['status'] == 'ready'
    assert result[0]['image_base64'] == asset['image_base64']


def test_incomplete_order_keeps_nodes_and_still_calls_planner(scene, monkeypatch, tmp_path):
    calls = []
    def model(*args, planner=False, **kwargs):
        calls.append(planner)
        if planner:
            return json.dumps({'placements': [], 'unresolved': ['Duplicate is not established']})
        return json.dumps({'issues': [{'kind': 'architecture', 'node_ids': ['app'],
                                      'problem': 'Suspected duplicate'}],
                           'layout_patch': {'node_order': ['app'], 'spacing_scale': 1.15}})
    monkeypatch.setattr(reviewer, '_call', model)
    monkeypatch.setenv('ARCHITECTURE_REVIEW_OUTPUT_DIR', str(tmp_path))
    result = review(scene)
    assert calls == [False, True]
    assert result['vision_review']['status'] == 'repaired_not_visually_rechecked'
    assert result['spec']['nodes'] == scene[2]['spec']['nodes']
    assert result['spec']['edges'] == scene[2]['spec']['edges']
    assert result['spec']['spacing_scale'] == 1.15
    decision = result['vision_review']['layout_decisions'][0]
    assert decision['status'] == 'normalized'
    assert decision['preserved_entries'] == ['user']


@pytest.mark.parametrize('bad', [None, ['app', 'app'], ['unknown'], [{}]])
def test_bad_order_does_not_discard_spacing(scene, bad):
    revised, decisions = reviewer.safe_layout_patch(scene[1], {'node_order': bad, 'spacing_scale': 1.2})
    assert revised.nodes == scene[1].nodes
    assert revised.spacing_scale == 1.2
    assert decisions[0]['status'] == 'rejected'
    assert decisions[1]['status'] == 'accepted'


def test_unsupported_semantic_edit_is_logged_not_review_failure(scene, monkeypatch):
    monkeypatch.setattr(reviewer, '_call', lambda *a, **k: json.dumps(
        {'issues': [], 'layout_patch': {'nodes': []}}))
    result = review(scene)
    assert result['image_base64'] == scene[2]['image_base64']
    assert result['vision_review']['image_reviewed']
    assert result['vision_review']['status'] != 'review_unavailable'
    assert result['vision_review']['layout_decisions'][0]['status'] == 'rejected'


def test_bad_placement_keeps_valid_placement_and_layout(scene):
    evidence = 'The Application uses managed compute services.'
    spec = replace(scene[1], spacing_scale=1.15)
    revised, decisions = reviewer.safe_placement_patch(spec, [
        {'node_id': 'user', 'scope': 'vpc', 'placement_role': 'compute', 'evidence_quote': evidence},
        {'node_id': 'app', 'scope': 'managed', 'placement_role': 'compute', 'evidence_quote': evidence},
    ], evidence)
    assert decisions[0]['status'] == 'rejected'
    assert decisions[1]['status'] == 'accepted'
    assert revised.nodes[0] == spec.nodes[0]
    assert revised.nodes[1].scope == 'managed'
    assert revised.spacing_scale == 1.15


def test_render_failure_is_not_mislabeled_as_bedrock_failure(scene, monkeypatch):
    monkeypatch.setattr(reviewer, '_call', lambda *a, **k: json.dumps(
        {'issues': [], 'layout_patch': {'spacing_scale': 1.2}}))
    def failed(*args, **kwargs):
        raise RuntimeError('Renderer failed')
    monkeypatch.setattr(scene[0], '_asset', failed)
    result = review(scene)
    assert result['vision_review']['image_reviewed']
    assert result['vision_review']['status'] == 'repair_failed'
    assert result['image_base64'] == scene[2]['image_base64']


@pytest.mark.parametrize('accepted', [True, False])
@pytest.mark.parametrize('engine', ['hybrid', 'hybrid_drawio'])
def test_hybrid_correction_is_rechecked_and_failed_candidate_not_delivered(scene, monkeypatch, tmp_path, accepted, engine):
    service, spec, original = scene
    metrics = reviewer.measurements(spec)
    original = {**original, 'layout_engine':engine, 'layout_metrics':metrics}
    image = Image.new('RGB',(100,100),'white')
    encoded = io.BytesIO()
    image.save(encoded,'PNG')
    candidate = {**original,'image_base64':base64.b64encode(encoded.getvalue()).decode()}
    monkeypatch.setattr(service,'_asset',lambda *a,**kw:candidate)
    calls = []
    def model(*args, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return json.dumps({'issues':[{'kind':'visual','node_ids':['app'],'problem':'Crowded'}],
                               'composition_patch':{'grids':{}, 'external_sides':{'user':'top'}}})
        return json.dumps({'acceptable':accepted,'problems':[] if accepted else ['False junction']})
    monkeypatch.setattr(reviewer,'_call',model)
    monkeypatch.setenv('ARCHITECTURE_REVIEW_OUTPUT_DIR',str(tmp_path))
    result = reviewer.review_architecture(service,original,spec,{}, {},'')
    assert len(calls) == 2
    assert all(call['planner'] for call in calls)
    assert result['vision_review']['candidate_visually_rechecked']
    assert result['vision_review']['repair_passes'] == int(accepted)
    assert result['image_base64'] == (candidate if accepted else original)['image_base64']
    assert result['vision_review']['status'] == ('repaired_visually_checked' if accepted else 'repair_rejected_visual_check')
