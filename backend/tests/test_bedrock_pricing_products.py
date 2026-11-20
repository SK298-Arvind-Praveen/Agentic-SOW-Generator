import io
from copy import deepcopy
import json
from types import SimpleNamespace

from app.pricing.renderer import render_aws_pricing_section
from app.pricing.service import AwsPricingService


BEDROCK = 'Amazon Bedrock'
KB = 'Amazon Bedrock Knowledge Bases'
GUARDRAILS = 'Amazon Bedrock Guardrails'
REGION = 'ap-south-1'
SOURCE = 'About 50k conversations per month. Use Guardrails content filtering and PII masking.'


def _field(field, options=None):
    if options:
        return {'id': field, 'type': 'dropdown', 'options': [{'id': key, 'label': label} for key, label in options.items()]}
    return {'id': field, 'type': 'numericInput'}


def _config(config):
    return {'config': config, 'sizing': [{'input': 'Monthly workload', 'value': 'Estimated request or embedding input', 'status': 'Approximated'}]}


class _Calculator:
    def __init__(self):
        self.entries = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def call(self, tool, args):
        if tool == 'get_service_fields':
            assert args['service'] == 'amazon'
            return {'fields': [
                _field('location', {'ir': 'In-Region'}), _field('tierIR', {'standard': 'On Demand - Standard'}),
                _field('modelSelection', {'nova': 'Nova Lite', 'titan': 'Titan Text Embeddings V2'}),
                _field('selectedModel', {'mirror': 'Nova Lite'}), _field('selectedModel_od', {'2': 'Nova Lite'}),
                _field('selectedEmbeddingModel', {'titan': 'Titan Text Embeddings V2'}),
                _field('avgRequestsPerMin'), _field('hoursPerDayAtThisRate'), _field('avgInputTokensPerRequest'),
                _field('avgOutputTokensPerRequest'), _field('documentsPerMonth'), _field('averageTokensPerDocument'),
                _field('imageInput', {'0': 'No', '1': 'Yes'}), _field('withPromptCaching', {'0': 'No', '1': 'Yes'}),
            ]}
        assert tool == 'build_estimate'
        self.entries = json.loads(args['services'])
        return {'sharable_url': 'https://calculator.aws/#/estimate?id=estimate1'}


class _Llm:
    def __init__(self, *, omit_sensitive=False):
        self.calls = []
        self.omit_sensitive = omit_sensitive

    def generate(self, prompt, *, call_name, **kwargs):
        self.calls.append(call_name)
        inference = {'location': 'ir', 'tierIR': 'standard', 'modelSelection': 'nova',
                     'selectedModel': 'mirror', 'selectedModel_od': '2', 'avgRequestsPerMin': 8,
                     'hoursPerDayAtThisRate': 16, 'avgInputTokensPerRequest': 2000, 'avgOutputTokensPerRequest': 200}
        embedding = {'selectedEmbeddingModel': 'titan', 'documentsPerMonth': 800, 'averageTokensPerDocument': 100}
        if call_name == f'AWS Pricing Estimated Fields - {BEDROCK}':
            payload = _config({**inference, **embedding} if self.calls.count(call_name) == 1 else inference)
        elif call_name == f'AWS Pricing Estimated Fields - {KB}':
            payload = _config({**embedding, 'location': 'ir', 'tierIR': 'standard', 'modelSelection': 'titan'})
        elif call_name == 'AWS Pricing Bedrock Guardrails Usage':
            payload = {'policies': [
                {'policy': 'Content', 'monthly_calls': 50000, 'characters_per_input': 1010,
                 'characters_per_output': 150, 'reason': 'One input and one output per guarded conversation'},
                {'policy': 'SensitiveInfo', 'monthly_calls': 50000, 'characters_per_input': 300,
                 'characters_per_output': 150, 'reason': 'PII masking scans messages and responses'},
            ]}
            if self.omit_sensitive:
                payload['policies'].pop()
        elif call_name == f'AWS Pricing Estimated Fields - {GUARDRAILS}':
            payload = _config(inference)
        else:
            payload = {'services': [], 'volume_metrics': []}
        return SimpleNamespace(text=json.dumps(payload))


def _pricebook(*, sensitive=True):
    prices = {'Content': '0.00015', **({'SensitiveInfo': '0.00010'} if sensitive else {})}
    return {'version': '20261111013037', 'publicationDate': '2026-11-11T01:30:37Z',
            'products': {f'{key}-SKU': {'attributes': {'regionCode': REGION, 'operation': 'ApplyGuardrail',
                                                        'servicecode': 'AmazonBedrock', 'policyType': key}}
                         for key in prices},
            'terms': {'OnDemand': {f'{key}-SKU': {'term': {'priceDimensions': {
                'rate': {'unit': 'TextUnit', 'beginRange': '0', 'endRange': 'Inf', 'rateCode': f'{key}-SKU.rate',
                         'pricePerUnit': {'USD': value}},
            }}} for key, value in prices.items()}}}


def _generate(tmp_path, *, omit_sensitive=False, bedrock_cost=100, kb_purpose='Use an existing OpenSearch vector store'):
    client, llm = _Calculator(), _Llm(omit_sensitive=omit_sensitive)
    service = AwsPricingService(SimpleNamespace(OUTPUT_DIR=tmp_path), llm, lambda: client)
    service._read_cost = lambda url: {'monthlyCost': 100, 'monthlyByService': {'Amazon Bedrock': bedrock_cost}}
    result = service.generate({'aws_services': [BEDROCK, KB, GUARDRAILS, 'Amazon OpenSearch Service'],
        'confirmed_aws_services': [BEDROCK, KB, GUARDRAILS],
        'service_design': {'services': [{'name': KB, 'purpose': kb_purpose},
                                        {'name': GUARDRAILS, 'purpose': 'Content filtering and PII masking'}]},
    }, {'pricing_region': REGION}, SOURCE)
    return result, client.entries, llm.calls


def test_bedrock_workloads_are_priced_by_distinct_dimensions(tmp_path, monkeypatch):
    monkeypatch.setattr('urllib.request.urlopen', lambda url, **kwargs: io.BytesIO(json.dumps(_pricebook()).encode()))
    result, entries, calls = _generate(tmp_path)
    assert [entry['instance'] for entry in entries] == [BEDROCK, KB]
    assert 'selectedEmbeddingModel' not in entries[0]['config']
    assert entries[0]['config']['withPromptCaching'] == '0'
    assert entries[0]['config']['imageInput'] == '0'
    assert 'avgRequestsPerMin' not in entries[1]['config']
    assert calls.count(f'AWS Pricing Estimated Fields - {BEDROCK}') == 2
    assert result['status'] == 'hybrid_priced'
    assert result['calculator_monthly_cost'] == 100
    assert result['monthly_cost'] == 132.5
    supplement, = result['official_rate_components']
    assert supplement['pricebook_version'] == '20261111013037'
    assert {line['policy']: line['monthly_text_units'] for line in supplement['dimensions']} == {'Content': 150000, 'SensitiveInfo': 100000}
    markdown = render_aws_pricing_section(result)
    assert '32.50' in markdown and '132.50' in markdown and 'AWS public price list' in markdown


def test_unavailable_guardrails_rate_keeps_calculator_result_partial(tmp_path, monkeypatch):
    monkeypatch.setattr('urllib.request.urlopen', lambda url, **kwargs: io.BytesIO(json.dumps(_pricebook(sensitive=False)).encode()))
    result, entries, _ = _generate(tmp_path)
    assert all(entry['instance'] != GUARDRAILS for entry in entries)
    assert result['status'] == 'partial_priced'
    assert result['monthly_cost'] is None and result['calculator_monthly_cost'] == 100
    assert any(item['field'] == GUARDRAILS for item in result['missing_inputs'])


def test_estimated_guardrails_must_cover_explicitly_selected_policies(tmp_path, monkeypatch):
    monkeypatch.setattr('urllib.request.urlopen', lambda url, **kwargs: io.BytesIO(json.dumps(_pricebook()).encode()))
    result, _, calls = _generate(tmp_path, omit_sensitive=True)
    assert calls.count('AWS Pricing Bedrock Guardrails Usage') == 2
    assert result['status'] == 'partial_priced'
    assert any('Missing selected Guardrails policies: SensitiveInfo' in m['reason'] for m in result['missing_inputs'])


def test_explicit_alternate_embedding_model_is_not_silently_replaced(tmp_path, monkeypatch):
    monkeypatch.setattr('urllib.request.urlopen', lambda url, **kwargs: io.BytesIO(json.dumps(_pricebook()).encode()))
    result, entries, _ = _generate(tmp_path, kb_purpose='Use Cohere Embed 3 with an OpenSearch vector store')
    assert all(entry['instance'] != KB for entry in entries)
    assert result['status'] == 'partial_priced'
    assert any(item['field'] == KB for item in result['missing_inputs'])


def test_calculator_nonzero_total_cannot_hide_zero_bedrock_line(tmp_path, monkeypatch):
    monkeypatch.setattr('urllib.request.urlopen', lambda url, **kwargs: io.BytesIO(json.dumps(_pricebook()).encode()))
    result, _, _ = _generate(tmp_path, bedrock_cost=0)
    assert result['status'] == 'partial_priced'
    assert result['monthly_cost'] is None
    assert any(item['field'] == BEDROCK for item in result['missing_inputs'])


def test_architecture_pricing_refresh_accepts_only_verified_complete_hybrid(tmp_path, monkeypatch):
    from app.preview.architecture_regeneration import complete_pricing_refresh

    monkeypatch.setattr('urllib.request.urlopen', lambda url, **kwargs: io.BytesIO(json.dumps(_pricebook()).encode()))
    result, _, _ = _generate(tmp_path)
    assert complete_pricing_refresh(result, {}, require_calculator=True)
    bad = deepcopy(result)
    bad['official_rate_components'][0]['dimensions'][0]['monthly_text_units'] -= 1
    assert not complete_pricing_refresh(bad, {}, require_calculator=True)
    assert not complete_pricing_refresh({**result, 'monthly_cost': 132}, {}, require_calculator=True)
    assert not complete_pricing_refresh({**result, 'official_rate_components': []}, {}, require_calculator=True)


def test_pricing_volume_restores_monthly_conversations_when_planner_omits_them():
    source = ('About 50k conversations per month across two bots. '
              'Legacy channel has 32 inbound voice agents and 8 WhatsApp agents. '
              'Licence pricing alternatives are 30, 50, 75 agents. RTO is 30 minutes.')
    plan = {'volume_metrics': [
        {'metric': 'inbound_voice_agents', 'value': '32 agents', 'evidence_quote': '32 inbound voice agents'},
        {'metric': 'whatsapp_agents', 'value': '8 agents', 'evidence_quote': '8 WhatsApp agents'},
        {'metric': 'agent_count_pricing_slabs', 'value': '30, 50, 75 agents', 'evidence_quote': '30, 50, 75 agents'},
        {'metric': 'RTO', 'value': '30 minutes', 'evidence_quote': 'RTO is 30 minutes'},
    ]}
    metrics = AwsPricingService._validated_volume_metrics(plan, source)
    assert [(item['metric'], item['value']) for item in metrics] == [
        ('Monthly conversation volume', '50k conversations/month'), ('whatsapp_agents', '8 agents'),
    ]
