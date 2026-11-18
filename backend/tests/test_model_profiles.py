import pytest
from app.core.model_profiles import MODEL_PROFILES, resolve_model
from app.core.config import Config
from app.core.bedrock_llm import BedrockLLM, model_for_task


@pytest.mark.parametrize('alias', ['opus-5.5', 'gpt-6-astra'])
@pytest.mark.parametrize('task', ['fast', 'analysis', 'writer', 'diagram', 'diagram_review', 'review', 'editor', 'fallback'])
def test_every_component_can_select_new_profile_independently(monkeypatch, alias, task):
    from app.core.bedrock_llm import TASK_MODEL_ATTRIBUTES
    for key in TASK_MODEL_ATTRIBUTES:
        monkeypatch.setenv('BEDROCK_' + TASK_MODEL_ATTRIBUTES[key], 'unchanged-' + key)
    monkeypatch.setenv('BEDROCK_' + TASK_MODEL_ATTRIBUTES[task], alias)
    cfg = Config()
    for key in TASK_MODEL_ATTRIBUTES:
        assert model_for_task(cfg, key) == (MODEL_PROFILES[alias]['id'] if key == task else 'unchanged-' + key)
    assert {'opus-5.5', 'gpt-6-astra'} <= {m['key'] for m in cfg.get_bedrock_config()['available_models']}


def test_review_follows_resolved_diagram_selection_unless_overridden(monkeypatch):
    monkeypatch.setenv('BEDROCK_DIAGRAM_MODEL_ID', 'opus-5.5')
    monkeypatch.delenv('BEDROCK_DIAGRAM_REVIEW_MODEL_ID', raising=False)
    cfg = Config()
    assert cfg.DIAGRAM_REVIEW_MODEL_ID == cfg.DIAGRAM_MODEL_ID == resolve_model('opus-5.5')
    monkeypatch.setenv('BEDROCK_DIAGRAM_REVIEW_MODEL_ID', 'gpt-6-astra')
    assert Config().DIAGRAM_REVIEW_MODEL_ID == resolve_model('gpt-6-astra')


@pytest.mark.parametrize('alias,fields', [
    ('opus-5.5', {'thinking': {'type': 'adaptive'}}), ('gpt-6-astra', {})])
def test_provider_fields_and_images_use_selected_profile(alias, fields):
    class Client:
        def converse(self, **request):
            self.request = request
            return {'output': {'message': {'content': [{'text': 'OK'}]}}, 'stopReason': 'end_turn'}
    client = Client()
    BedrockLLM(Config(), client).generate('Check', model_id=alias, image_bytes=b'png', retry_on_truncation=False)
    assert client.request['modelId'] == resolve_model(alias)
    assert client.request.get('additionalModelRequestFields', {}) == fields
    assert 'temperature' not in client.request['inferenceConfig']
    assert any('image' in block for block in client.request['messages'][0]['content'])


def test_full_arns_remain_supported():
    for profile in MODEL_PROFILES.values():
        assert resolve_model(profile['id']) == profile['id']
    assert resolve_model('custom.model-id') == 'custom.model-id'
