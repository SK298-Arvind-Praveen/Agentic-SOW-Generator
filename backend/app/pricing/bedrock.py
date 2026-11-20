"""Map Bedrock workloads to calculator products and public rate dimensions."""

from decimal import Decimal, InvalidOperation
import json
import re
from urllib import request


GUARDRAIL_RATE_METHOD = 'aws_price_list_bedrock_guardrails_v1'
GUARDRAIL_POLICIES = {'Content', 'Topic', 'SensitiveInfo', 'ContextualGrounding', 'WordPolicy', 'SensitiveInfoFree'}
FREE_GUARDRAIL_POLICIES = {'WordPolicy', 'SensitiveInfoFree'}
_REQUIRED_TEXT_POLICIES = {
    'Content': r'content filter|prompt[ -]attack',
    'Topic': r'denied[ -]topic|topic filter',
    'SensitiveInfo': r'\bpii (?:mask|redact)|sensitive information filter',
    'ContextualGrounding': r'contextual grounding|grounding check',
}
_EMBEDDING_FIELDS = re.compile(r'^(selectedEmbeddingModel|documentsPerMonth|averageTokensPerDocument|imageInput_emb|avgImagesPerRequest_emb|avgImageLengthInPixels_emb|avgImageWidthInPixels_emb)')
_EMBEDDING_STANDARD = {'selectedEmbeddingModel', 'documentsPerMonth', 'averageTokensPerDocument'}
_SHARED_FIELDS = {'location', 'tierIR', 'modelSelection'}


def bedrock_workload(name):
    name = str(name).casefold()
    if not re.search(r'\bbedrock\b', name):
        return None
    if re.search(r'\bguardrails?\b', name):
        return 'guardrails'
    if re.search(r'\bknowledge bas(?:e|es)\b', name):
        return 'knowledge_base'
    return 'inference'


def bedrock_calculator_fields(fields, workload, separate_kb):
    """Scope the live provider contract to the selected Bedrock workload."""
    if not isinstance(fields, dict) or not workload:
        return fields
    rows = fields.get('fields', [])
    if workload == 'knowledge_base':
        rows = [row for row in rows if row['id'] in _SHARED_FIELDS | _EMBEDDING_STANDARD]
        rows = [{**row, 'options': [o for o in row.get('options', []) if 'titan text embeddings v2' in o['label'].casefold()]}
                if row['id'] in {'modelSelection', 'selectedEmbeddingModel'} else row for row in rows]
    elif separate_kb:
        rows = [row for row in rows if not _EMBEDDING_FIELDS.match(row['id'])]
        rows = [{**row, 'options': [o for o in row.get('options', []) if 'embed' not in o['label'].casefold()]}
                if row['id'].startswith('modelSelection') else row for row in rows]
    return {**fields, 'fields': rows}


def unsupported_embedding_basis(text):
    """Keep a Titan fallback from pricing a differently specified KB model."""
    text = re.sub(r'[_.-]+', ' ', text)
    return bool(re.search(r'\b(?:cohere embed|(?:nova|titan) multimodal embeddings?|'
                          r'titan text embeddings v1|titan embed text v1)\b', text, re.I))


def _numeric(value):
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Expected a finite numeric quantity') from exc
    if not amount.is_finite():
        raise ValueError('Expected a finite numeric quantity')
    return amount


def validate_bedrock_calculator(config, contracts, workload, separate_kb):
    if workload == 'knowledge_base':
        if not (_SHARED_FIELDS | _EMBEDDING_STANDARD).issubset(config) or config['location'] != 'ir' or config['tierIR'] != 'standard':
            raise ValueError('Knowledge Bases needs in-region, standard embedding model and document/token quantities')
        if not all(_numeric(config[key]) > 0 for key in ('documentsPerMonth', 'averageTokensPerDocument')):
            raise ValueError('Knowledge Bases requires positive embedding usage quantities')
        for key in ('modelSelection', 'selectedEmbeddingModel'):
            if not any(o['id'] == config[key] and 'titan text embeddings v2' in o['label'].casefold()
                       for o in contracts.get(key, {}).get('options', [])):
                raise ValueError('Knowledge Bases must select the live Titan Text Embeddings V2 model in both selectors')
        return
    if workload != 'inference':
        return

    if config.get('tierIR') == 'standard' and config.get('location') in {'ir', 'geo'}:
        suffix = 'geoStan' if config['location'] == 'geo' else ''
        selectors = [base + suffix for base in ('modelSelection', 'selectedModel', 'selectedModel_od')]
        if separate_kb or config.get(selectors[1]) is not None:
            labels = [next((str(o['label']).casefold() for o in contracts.get(key, {}).get('options', [])
                            if str(o['id']) == str(config.get(key))), None) for key in selectors]
            if not labels[0] or len(set(labels)) != 1:
                raise ValueError('Use the same inference model in the three active live model selectors')
            usage = [base + suffix for base in ('avgRequestsPerMin', 'hoursPerDayAtThisRate', 'avgInputTokensPerRequest', 'avgOutputTokensPerRequest')]
            if any(key not in config or _numeric(config[key]) <= 0 for key in usage):
                raise ValueError('Standard Bedrock inference requires positive active request, duration, and token fields')
            for base in ('imageInput', 'withPromptCaching'):
                key = base + suffix
                # The native form relies on explicit switches to activate the price calculation.
                if key in contracts and any(str(o['id']) == '0' for o in contracts[key].get('options', [])):
                    config.setdefault(key, '0')


def guardrail_offer_url(region):
    if not isinstance(region, str) or not re.fullmatch(r'[a-z]{2}(?:-gov)?-[a-z]+-\d', region):
        raise ValueError('Expected a valid AWS region for Guardrails pricing')
    return f'https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonBedrock/current/{region}/index.json'


def _pricebook_rate(offer, region, policy):
    matches = []
    for sku, product in offer.get('products', {}).items():
        attrs = product.get('attributes', {})
        if any(attrs.get(key) != expected for key, expected in {
            'servicecode': 'AmazonBedrock', 'regionCode': region, 'operation': 'ApplyGuardrail', 'policyType': policy,
        }.items()):
            continue
        for term in offer.get('terms', {}).get('OnDemand', {}).get(sku, {}).values():
            for rate in term.get('priceDimensions', {}).values():
                if (rate.get('unit'), rate.get('beginRange'), rate.get('endRange')) == ('TextUnit', '0', 'Inf'):
                    amount = _numeric(rate.get('pricePerUnit', {}).get('USD'))
                    code = str(rate.get('rateCode') or '')
                    expected_rate = amount == 0 if policy in FREE_GUARDRAIL_POLICIES else amount > 0
                    if expected_rate and code.startswith(f'{sku}.'):
                        matches.append((sku, code, amount))
    if len(matches) != 1:
        raise ValueError(f'AWS price list has no unique On-Demand TextUnit rate for {policy} in {region}')
    return matches[0]


def _positive_int(value, *, allow_zero=False):
    amount = _numeric(value)
    if amount != amount.to_integral_value() or amount < (0 if allow_zero else 1):
        raise ValueError('Expected a whole usage quantity in the allowed range')
    return int(amount)


def _usage_dimensions(mapped):
    policies = mapped.get('policies')
    if not isinstance(policies, list) or not policies:
        raise ValueError('Guardrails requires per-policy text usage')
    rows = {}
    for item in policies:
        policy = item.get('policy') if isinstance(item, dict) else None
        if policy not in GUARDRAIL_POLICIES or policy in rows:
            raise ValueError(f'Unsupported or repeated Guardrails policy {policy}')
        calls = _positive_int(item.get('monthly_calls'))
        in_chars = _positive_int(item.get('characters_per_input'), allow_zero=True)
        out_chars = _positive_int(item.get('characters_per_output'), allow_zero=True)
        if policy == 'ContextualGrounding':
            context_chars = _positive_int(item.get('characters_per_grounding_source'))
            units = (in_chars + out_chars + context_chars + 999) // 1000
        else:
            units = (in_chars + 999) // 1000 + (out_chars + 999) // 1000
        reason = str(item.get('reason') or '').strip()
        if not units or not reason:
            raise ValueError(f'{policy} requires billable text units and a sizing reason')
        rows[policy] = {'monthly_text_units': calls * units, 'monthly_calls': calls, 'reason': reason,
                        'characters_per_input': in_chars, 'characters_per_output': out_chars}
        if policy == 'ContextualGrounding':
            rows[policy]['characters_per_grounding_source'] = context_chars
    return rows


def prepare_guardrails(owner, service, region):
    """Size guarded text only. Unit prices come directly from the AWS offer."""
    from .service import _json_object

    name = service['service_name']
    selected = service.get('_bedrock_selected_design') or ''
    required_policies = {policy for policy, pattern in _REQUIRED_TEXT_POLICIES.items() if re.search(pattern, selected, re.I)}
    try:
        url = guardrail_offer_url(region)
        with request.urlopen(url, timeout=20) as response:
            offer = json.load(response)
        version, published = offer.get('version'), offer.get('publicationDate')
        if not version or not published:
            raise ValueError('AWS price list did not identify its version and publication date')
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        return [{'field': name, 'basis': 'AWS public price list', 'reason': str(exc)}]

    prompt = '''Size the text usage of the selected Amazon Bedrock Guardrails deployment for one month.
Use the provided business volumes, percentage of traffic guarded, guardrail policies and design.
Include each selected text policy once. Choices: Content (includes prompt attacks), Topic (denied topics),
SensitiveInfo (paid PII filters), ContextualGrounding, WordPolicy, SensitiveInfoFree (regex only).
Do not charge content filtering twice for prompt attacks. ContextualGrounding applies only to answers checked
against grounding context. Do not add voice or images to a text-only workload. Estimate missing usage and
explain the role of the projected calls. Do not return dollars, rates, token volumes, or Bedrock model IDs.
Return JSON {"policies":[{"policy":"Content","monthly_calls":number,"characters_per_input":number,
"characters_per_output":number,"characters_per_grounding_source":number,"reason":"brief rationale"}]}.
Use characters_per_grounding_source only for ContextualGrounding.
''' + json.dumps({'source': service.get('_sizing_context'), 'facts': service.get('usage_facts'),
                   'monthly_volumes': service.get('_pricing_volume_metrics'),
                   'required_policies': sorted(required_policies)}, default=str)
    for attempt in range(2):
        try:
            answer = owner.llm.generate(prompt, task='analysis', max_tokens=3500, temperature=0,
                                        call_name='AWS Pricing Bedrock Guardrails Usage')
            usage = _usage_dimensions(_json_object(answer.text))
            if missing := required_policies - usage.keys():
                raise ValueError('Missing selected Guardrails policies: ' + ', '.join(sorted(missing)))
            break
        except Exception as exc:
            if attempt:
                return [{'field': name, 'basis': 'Guardrails usage sizing', 'reason': str(exc)}]
            prompt += f'\nCorrective attempt: {exc}'

    dimensions = []
    try:
        for policy, sizing in usage.items():
            sku, code, amount = _pricebook_rate(offer, region, policy)
            dimensions.append({'policy': policy, **sizing, 'sku': sku, 'rate_code': code,
                               'usd_per_text_unit': format(amount, 'f'),
                               'monthly_cost': format(amount * sizing['monthly_text_units'], 'f')})
    except (TypeError, ValueError, AttributeError) as exc:
        return [{'field': name, 'basis': 'AWS public price list', 'reason': str(exc)}]
    monthly = sum(Decimal(row['monthly_cost']) for row in dimensions).quantize(Decimal('0.01'))
    service['_official_rate_component'] = {
        'service': name, 'region': region, 'method': GUARDRAIL_RATE_METHOD,
        'pricebook_url': url, 'pricebook_version': str(version), 'pricebook_publication_date': published,
        'dimensions': dimensions, 'monthly_cost': float(monthly),
    }
    service['_sizing_details'] = [{
        'service': name, 'input': f"{row['policy']} text usage", 'value': f"{row['monthly_text_units']:,} text units/month",
        'reason': row['reason'], 'status': 'Approximated',
    } for row in dimensions]
    return []
