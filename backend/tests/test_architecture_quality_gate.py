from app.diagram.service import DiagramService


def test_exhausted_diagram_keeps_recovery_image_and_explicit_reason(monkeypatch):
    service = DiagramService.__new__(DiagramService)
    rejected = dict(image_base64='bad', drawio_xml='<xml/>', edit_url='url',
                    used_fallback=True, spec={'nodes':[{'id':'unapproved'}]}, validation_warnings=['Planner failed'])
    monkeypatch.setattr(service, '_generate_assets', lambda *args: [rejected])
    result = service.generate_assets({}, {}, '')[0]
    assert result['status'] == 'review_required'
    assert result['image_base64'] == 'bad'
    assert result['drawio_xml'] == '<xml/>' and result['edit_url'] == 'url'
    assert 'Planner failed' in result['quality_warnings']
    assert result['spec']['nodes'] == [{'id':'unapproved'}]
    assert result['used_fallback']  # Consumers must not promote this to approved design.
    assert 'Planner failed' in result['diagnostic']


def test_reviewed_clean_image_is_preserved(monkeypatch):
    service = DiagramService.__new__(DiagramService)
    clean = dict(image_base64='pixels', drawio_xml='<xml/>', used_fallback=False,
                 status='ready', vision_review={'status':'reviewed', 'issues':[]})
    monkeypatch.setattr(service, '_generate_assets', lambda *args: [clean])
    assert service.generate_assets({}, {}, '')[0] == clean


def test_crossing_repair_exhaustion_cannot_erase_a_reviewed_real_image(monkeypatch):
    service=DiagramService.__new__(DiagramService)
    asset=dict(image_base64='pixels',drawio_xml='<xml/>',used_fallback=False,
        layout_engine='narrative_drawio',spec={'nodes':[{'id':'real'}]},retry_exhausted=True,
        layout_metrics={'connector_crossings':6,'edges':18,'node_overlaps':0,'out_of_bounds':0,'containment_violations':0},
        vision_review={'status':'reviewed','issues':[],'unresolved_architecture':False})
    monkeypatch.setattr(service,'_generate_assets',lambda *args:[asset])
    result=service.generate_assets({}, {}, '')[0]
    assert result['status']=='review_required'
    assert result['image_base64']=='pixels' and result['drawio_xml']=='<xml/>'
    assert result['spec']['nodes']==[{'id':'real'}]
    assert 'crossings' in ' '.join(result['quality_warnings'])
    assert 'needs review' in result['review_warning']


def test_review_transport_outage_does_not_erase_valid_image(monkeypatch):
    service = DiagramService.__new__(DiagramService)
    asset = dict(image_base64='pixels',drawio_xml='<xml/>',used_fallback=False,
        vision_review={'status':'unavailable','issues':[],'error':'Connection closed'},
        spec={'architecture_plan':{'service_design':{'status':'ready'}}})
    monkeypatch.setattr(service,'_generate_assets',lambda *args:[asset])
    result = service.generate_assets({}, {}, '')[0]
    assert result['image_base64'] == 'pixels'
    assert result['status'] == 'review_required'
    assert result['review_warning']


def test_review_outage_cannot_hide_known_architecture_failure(monkeypatch):
    service = DiagramService.__new__(DiagramService)
    asset = dict(image_base64='pixels',drawio_xml='<xml/>',used_fallback=False,
        vision_review={'status':'unavailable','unresolved_architecture':True,'issues':[]})
    monkeypatch.setattr(service,'_generate_assets',lambda *args:[asset])
    result = service.generate_assets({}, {}, '')[0]
    assert result['image_base64'] == 'pixels'
    assert 'Unresolved architecture findings' in result['quality_warnings']
    assert result['status'] == 'review_required'


def test_cosmetic_review_preserves_real_diagram_with_warning(monkeypatch):
    service = DiagramService.__new__(DiagramService)
    asset = dict(image_base64='pixels',drawio_xml='<xml/>',used_fallback=False,
        layout_engine='narrative_drawio',vision_review={'status':'reviewed',
        'issues':[{'kind':'visual','description':'Caption spacing'}]},
        validation_warnings=['Overview image review found visual issues; see diagram diagnostics'])
    monkeypatch.setattr(service,'_generate_assets',lambda *args:[asset])
    result = service.generate_assets({}, {}, '')[0]
    assert result['image_base64'] == 'pixels'
    assert 'needs review' in result['review_warning']
    assert 'Caption spacing' in result['quality_warnings']
    assert result['quality_warnings']


def test_cosmetic_warning_does_not_override_structural_overlap(monkeypatch):
    service = DiagramService.__new__(DiagramService)
    asset = dict(image_base64='pixels',drawio_xml='<xml/>',used_fallback=False,
        layout_metrics={'node_overlaps':1},vision_review={'status':'reviewed',
        'issues':[{'kind':'visual','description':'Caption spacing'}]})
    monkeypatch.setattr(service,'_generate_assets',lambda *args:[asset])
    result = service.generate_assets({}, {}, '')[0]
    assert result['image_base64'] == 'pixels'
    assert 'node_overlaps=1' in result['quality_warnings']


def test_failed_service_selection_cannot_start_diagram_planning(monkeypatch):
    import pytest
    from app.diagram.reliability import pipeline_attempt
    service = DiagramService.__new__(DiagramService)
    service.llm = object()
    monkeypatch.setattr('app.diagram.service_design.ensure_service_design',
        lambda *args: {'status':'needs_review','error':'Response ended prematurely'})
    token = pipeline_attempt.set(1)
    try:
        with pytest.raises(ValueError,match='Service selection was not accepted'):
            service._generate_specs({}, {}, '')
    finally:
        pipeline_attempt.reset(token)
