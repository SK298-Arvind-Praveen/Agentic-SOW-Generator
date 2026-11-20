from copy import deepcopy


def test_wrong_prose_repairs_story_without_replanning_graph():
    from app.diagram.repair_controller import repair_request
    asset = {'spec': {'nodes': [{'id': 'a'}], 'edges': [], 'architecture_plan': {
        'process_story': {'steps': []}, 'narrative_view': {'groups': []}}},
        'vision_review': {'issues': [{'stage': 'story', 'kind': 'architecture',
            'description': 'NAT outbound traffic described as incoming requests'}]}}
    before = deepcopy(asset)
    result = repair_request(asset)
    assert result['stage'] == 'story' and not result['replan']
    assert result['spec']['nodes'] == asset['spec']['nodes']
    assert result['spec']['architecture_plan']['story_feedback']
    assert asset == before


def test_real_missing_service_requires_semantic_correction():
    from app.diagram.repair_controller import repair_request
    result = repair_request({'spec': {'nodes': [], 'edges': [], 'architecture_plan': {}},
        'vision_review': {'issues': [{'stage': 'graph', 'description': 'Required OCR missing',
            'node_ids': ['intake'], 'evidence': 'Approved extraction workflow has no OCR service',
            'repair_instruction': 'Restore the approved OCR step after intake'}]}})
    assert result['replan']


def test_geometry_repair_preserves_story_and_semantics():
    from app.diagram.repair_controller import repair_request
    asset = {'spec': {'nodes': [{'id': 'a'}], 'edges': [], 'architecture_plan': {'process_story': {'steps': []}}},
        'vision_review': {'issues': [{'stage': 'layout', 'description': 'Detached port'}]}}
    result = repair_request(asset)
    assert result['stage'] == 'layout' and not result['replan']
    assert result['spec']['architecture_plan']['process_story'] == {'steps': []}
    assert result['spec']['architecture_plan']['routing_repair'] == 1


def test_story_and_review_allowances_do_not_exhaust_semantic_corrections():
    from app.diagram.repair_controller import call_budget
    assert call_budget('Architecture Process Story', 3) == ('Architecture Process Story/candidate-3', 2)
    assert call_budget('Architecture Plan Correction', 3) == ('Architecture Plan Correction', 3)


def test_outer_retry_passes_story_feedback_with_identical_graph():
    from app.diagram.service import DiagramService
    from app.diagram.contracts import freeze
    spec = {'nodes': [{'id': 'a'}, {'id': 'b'}],
            'edges': [{'source': 'a', 'target': 'b', 'label': 'Outbound route'}],
            'architecture_plan': {'process_story': {'steps': []}}}
    service = DiagramService.__new__(DiagramService)
    calls = []
    def render(requirements, metadata, narrative):
        calls.append(requirements)
        if len(calls) == 1:
            return [{'image_base64': 'png', 'spec': spec, 'layout_engine': 'narrative_drawio',
                'vision_review': {'status': 'reviewed', 'issues': [{'stage': 'story',
                    'kind': 'architecture', 'description': 'Gateway is described as inbound'}]}}]
        assert freeze(requirements['_architecture_retry_spec'])['version'] == freeze(spec)['version']
        assert requirements['_architecture_retry_spec']['architecture_plan']['story_feedback']
        return [{'image_base64': 'corrected', 'spec': spec, 'vision_review': {'status': 'reviewed', 'issues': []}}]
    service._generate_assets_once = render
    result = service._generate_assets_bounded({}, {}, '')
    assert len(calls) == 2 and result[0]['image_base64'] == 'corrected'
    assert result[0]['pipeline_attempts'][0]['repair_stage'] == 'story'


def test_presentation_retry_count_is_bounded_when_provider_stays_unavailable():
    from app.diagram.service import DiagramService
    service = DiagramService.__new__(DiagramService); calls = []
    def fail(requirements, metadata, narrative):
        calls.append(requirements)
        return [{'image_base64': 'retained', 'spec': {'nodes': [], 'edges': [], 'architecture_plan': {}},
            'vision_review': {'status': 'unavailable', 'error': 'review timeout'}}]
    service._generate_assets_once = fail
    result = service._generate_assets_bounded({}, {}, '')
    assert len(calls) == 3
    assert result[0]['image_base64'] == 'retained' and result[0]['retry_exhausted']
    assert result[0]['quality_warnings']
def test_saved_strategy_record_advances_to_second_visual_repair_without_replanning():
    from app.diagram.repair_controller import repair_request
    asset = {'spec': {'nodes': [{'id': 'a'}], 'edges': [], 'architecture_plan': {
        'routing_repair': {'version': 1, 'strategy': 'separate_runtime_and_egress'}}},
        'vision_review': {'issues': [{'stage': 'layout', 'description': 'Crossing remains'}]}}
    before = deepcopy(asset)
    result = repair_request(asset)
    assert not result['replan'] and result['spec']['architecture_plan']['routing_repair'] == 2
    assert result['spec']['nodes'] == asset['spec']['nodes'] and asset == before

