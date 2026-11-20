"""Evidence checks for publishing a complete AWS estimate."""

from decimal import Decimal, InvalidOperation
import math
import re

from .bedrock import FREE_GUARDRAIL_POLICIES, GUARDRAIL_POLICIES, GUARDRAIL_RATE_METHOD, bedrock_workload, guardrail_offer_url


_SAVED_ESTIMATE = re.compile(r'https://calculator\.aws/(?:#?/)?estimate\?id=[A-Za-z0-9_-]+')
_CENTS = Decimal('0.01')


def _decimal(value):
    parsed = Decimal(str(value))
    if not parsed.is_finite():
        raise ValueError('Non-finite pricing evidence')
    return parsed


def _verified_component(component, region):
    if (component['method'] != GUARDRAIL_RATE_METHOD or bedrock_workload(component['service']) != 'guardrails'
            or component['region'] != region or component['pricebook_url'] != guardrail_offer_url(region)
            or not re.fullmatch(r'\d{14}', str(component['pricebook_version']))
            or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', component['pricebook_publication_date'])):
        raise ValueError('Incomplete AWS regional Guardrails rate provenance')
    lines = component['dimensions']
    if not isinstance(lines, list) or not lines:
        raise ValueError('Missing verified Guardrails pricing dimensions')
    policies = set()
    subtotal = Decimal(0)
    for line in lines:
        policy, sku, code = line['policy'], line['sku'], line['rate_code']
        units, unit_price = _decimal(line['monthly_text_units']), _decimal(line['usd_per_text_unit'])
        matching_rate = unit_price == 0 if policy in FREE_GUARDRAIL_POLICIES else unit_price > 0
        if (policy not in GUARDRAIL_POLICIES or policy in policies or not sku or not code.startswith(f'{sku}.')
                or units <= 0 or units != units.to_integral_value() or not matching_rate
                or units * unit_price != _decimal(line['monthly_cost'])):
            raise ValueError('Invalid Guardrails unit-cost evidence')
        policies.add(policy)
        subtotal += units * unit_price
    rounded = subtotal.quantize(_CENTS)
    if rounded != _decimal(component['monthly_cost']):
        raise ValueError('Guardrails component subtotal does not match its rates and units')
    return rounded


def complete_estimate(result, *, require_calculator=True):
    """Check native estimates and fully covered, source-verified supplements."""
    try:
        total = float(result.get('monthly_cost'))
        if (not math.isfinite(total) or total <= 0 or result.get('missing_inputs') or result.get('fallback_estimate')
                or any(not row.get('complete') for row in (result.get('resource_coverage') or {}).values())):
            return False
        components = result.get('official_rate_components') or []
        status = result.get('status')
        if status == 'priced':
            return not components and (not require_calculator or bool(_SAVED_ESTIMATE.fullmatch(str(result.get('estimate_url') or ''))))
        if status != 'hybrid_priced' or not _SAVED_ESTIMATE.fullmatch(str(result.get('estimate_url') or '')):
            return False
        if len(components) != 1 or result.get('currency') != 'USD':
            return False
        native = _decimal(result['calculator_monthly_cost'])
        supplement = _verified_component(components[0], result['region'])
        priced = result['calculator_priced_services']
        no_charge = len(result.get('no_direct_charge_services') or [])
        services = result.get('services') or []
        return (native > 0 and isinstance(priced, int) and priced == len(services)
                and not any(bedrock_workload(row.get('service')) == 'guardrails' for row in services)
                and result['calculator_planned_services'] == priced + no_charge + len(components)
                and _decimal(result['monthly_cost']) == (native + supplement).quantize(_CENTS))
    except (InvalidOperation, KeyError, TypeError, ValueError, AttributeError):
        return False
