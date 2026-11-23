import json
from types import SimpleNamespace
import pytest


def test_prompt_blocks_preserve_text_and_cache_stable_prefix(monkeypatch):
    from app.core.generation_efficiency import prompt_blocks
    monkeypatch.setenv('BEDROCK_PROMPT_CACHE_ENABLED', 'true')
    prefix = 'fact ' * 4500
    prompt = prefix + '\nREFINEMENT PRESERVATION CONTRACT\nsection A'
    blocks, system = prompt_blocks('sonnet-5.5', prompt, '')
    assert ''.join(b.get('text', '') for b in blocks) == prompt
    assert blocks[1]['cachePoint']['type'] == 'default'
    assert blocks[0]['text'] == prefix + '\n'
    assert not system


def test_only_exact_system_prefix_removed(monkeypatch):
    from app.core.generation_efficiency import prompt_blocks
    monkeypatch.setenv('BEDROCK_PROMPT_CACHE_ENABLED', 'true')
    blocks, system = prompt_blocks('sonnet-5.5', 'RULES\nunique data', 'RULES')
    assert ''.join(b.get('text', '') for b in blocks) == '\nunique data'
    assert system[0]['text'] == 'RULES'
    blocks, _ = prompt_blocks('sonnet-5.5', 'data RULES data', 'RULES')
    assert blocks[0]['text'] == 'data RULES data'


def test_unknown_model_and_disable_have_no_cache(monkeypatch):
    from app.core.generation_efficiency import prompt_blocks
    for model in ('unknown-profile', 'gpt-6-astra'):
        blocks, _ = prompt_blocks(model, 'word ' * 5000, '')
        assert not any('cachePoint' in b for b in blocks)
    monkeypatch.setenv('BEDROCK_PROMPT_CACHE_ENABLED', 'false')
    blocks, _ = prompt_blocks('sonnet-5.5', 'word ' * 5000, '')
    assert len(blocks) == 1


def test_validated_cache_isolation_copy_and_expiry():
    from app.core.generation_efficiency import StageCache
    clock = [0]
    cache = StageCache(ttl=10, capacity=2, clock=lambda: clock[0])
    cache.put('run-a', 'key', {'ok': []})
    hit = cache.get('run-a', 'key'); hit['ok'].append(1)
    assert cache.get('run-a', 'key') == {'ok': []}
    assert cache.get('run-b', 'key') is None
    clock[0] = 11
    assert cache.get('run-a', 'key') is None


def test_retry_does_not_accumulate_obsolete_candidates():
    from app.diagram.reliability import structured_retry
    prompts = []
    def call(p):
        prompts.append(p)
        return json.dumps({'candidate': len(prompts)})
    def validate(v):
        if v['candidate'] < 3: raise ValueError('correct candidate')
        return v
    assert structured_retry(call, 'original contract', validate)['candidate'] == 3
    assert '"candidate": 1' not in prompts[2]
    assert '"candidate": 2' in prompts[2]


def test_structured_reuse_revalidates_and_invalidates(monkeypatch):
    from app.core import generation_efficiency as g
    from app.diagram.reliability import structured_retry
    monkeypatch.setattr(g, 'run_id', lambda: 'cache-test')
    g.clear('cache-test')
    calls, checks = [], []
    def call(p):
        calls.append(p)
        return '{"ok": true}'
    def validate(v):
        checks.append(v)
        return v
    for _ in range(2): structured_retry(call, 'source', validate, cache_key='model-v1')
    assert len(calls) == 1 and len(checks) == 2
    structured_retry(call, 'changed source', validate, cache_key='model-v1')
    structured_retry(call, 'source', validate, cache_key='model-v2')
    assert len(calls) == 3
    def reject(v): raise ValueError('new validator rejects')
    with pytest.raises(ValueError):
        structured_retry(call, 'source', reject, cache_key='model-v1', attempts=1)
    assert len(calls) == 4


def test_failed_validation_not_cached(monkeypatch):
    from app.core import generation_efficiency as g
    from app.diagram.reliability import structured_retry
    monkeypatch.setattr(g, 'run_id', lambda: 'failure-test')
    g.clear('failure-test')
    calls = []
    def call(p):
        calls.append(p)
        return '{"ok": false}'
    def reject(v): raise ValueError('invalid')
    for _ in range(2):
        with pytest.raises(ValueError): structured_retry(call, 'source', reject, cache_key='key', attempts=1)
    assert len(calls) == 2


def test_converse_cache_usage_and_failures_are_recorded(monkeypatch):
    from app.core import generation_efficiency as g
    from app.core.bedrock_llm import BedrockLLM
    monkeypatch.setattr(g, 'run_id', lambda: 'metrics-test')
    g.clear('metrics-test')
    requests = []
    class Client:
        def converse(self, **request):
            requests.append(request)
            return {'output': {'message': {'content': [{'text': 'complete'}]}},
                    'usage': {'inputTokens': 10, 'outputTokens': 2,
                              'cacheReadInputTokens': 1000, 'cacheWriteInputTokens': 20}}
    llm = BedrockLLM(SimpleNamespace(WRITER_MODEL_ID='sonnet-5.5'), Client())
    llm.generate('word ' * 600, call_name='section')
    assert any('cachePoint' in b for b in requests[0]['messages'][0]['content'])
    row = g.metrics('metrics-test')[0]
    assert row['calls'] == 1 and row['cache_read_input_tokens'] == 1000
    assert row['cache_write_input_tokens'] == 20 and row['output_tokens'] == 2
    def fail(**kwargs): raise RuntimeError('network unavailable')
    llm.client.converse = fail
    with pytest.raises(RuntimeError): llm.generate('word', call_name='section')
    row = g.metrics('metrics-test')[0]
    assert row['failures'] == 1 and row['calls'] == 2


def test_section_reuse_keeps_model_and_source_changes_fresh(monkeypatch):
    from app.core import generation_efficiency as g
    from app.core.bedrock_llm import BedrockLLM
    from app.agents.poc_writer_agent import POCWriterAgent
    monkeypatch.setattr(g, 'run_id', lambda: 'writer-cache')
    g.clear('writer-cache')
    writer = POCWriterAgent.__new__(POCWriterAgent)
    writer.config = SimpleNamespace(WRITER_MODEL_ID='sonnet-5.5', FAST_MODEL_ID='haiku')
    writer.llm = BedrockLLM(writer.config, object())
    writer._section_category = lambda s: 'business_benefits'
    writer._section_key = lambda *a: 'business_benefits'
    writer._build_individual_prompt = lambda s, r, m, source, **kw: source
    writer._section_token_budget = lambda s: 1000
    writer._replace_placeholders = lambda name, *a: name
    writer._clean_content = lambda content, name: content
    writer._authoring_issues = lambda *a: []
    calls = []
    def generate(*a, **kw):
        calls.append(a)
        return '- Improve inspection accuracy.'
    writer._call_bedrock = generate
    section = SimpleNamespace(name='Business Benefits', content='contract', metadata={})
    for _ in range(2): writer._generate_section(section, {}, {}, 'source A', [])
    assert len(calls) == 1
    writer._generate_section(section, {}, {}, 'source B', [])
    writer.config.FAST_MODEL_ID = 'new-model'
    writer._generate_section(section, {}, {}, 'source B', [])
    assert len(calls) == 3


def test_stage_key_configuration_and_disable(monkeypatch):
    from app.core import generation_efficiency as g
    from app.core.bedrock_llm import BedrockLLM
    monkeypatch.setattr(g, 'run_id', lambda: 'key-test')
    config = SimpleNamespace(DIAGRAM_MODEL_ID='sonnet-5.5', BEDROCK_REGION='us-east-1')
    llm = BedrockLLM(config, object())
    original = g.stage_key(llm, 'design')
    llm.system_prompt = 'changed schema'
    assert original != g.stage_key(llm, 'design')
    config.BEDROCK_REGION = 'us-west-2'
    assert original != g.stage_key(llm, 'design')
    monkeypatch.setenv('SOW_STAGE_CACHE_ENABLED', 'false')
    assert g.stage_key(llm, 'design') is None
