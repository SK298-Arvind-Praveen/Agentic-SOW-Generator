"""Source traceability and a shared, versioned authoring baseline.

Missing/invalid new metadata remains diagnostic, never a reason to discard a
usable service design. We never invent a requirement citation or exclusion.
"""
from copy import deepcopy
from hashlib import sha256
import json
import re


AUTHORING_RULES = '''SHARED SOLUTION DEFINITION
Use service_design as the common baseline for scope, architecture, service roles,
timeline, effort and pricing. Its requirement_ledger records included, deferred
and excluded requirements with source excerpts. Preserve release boundaries;
POC mode alone never authorizes dropping an explicitly requested release.
Do not independently replace the selected runtime/framework or change scope.
Use delivery_baseline for releases, dependencies and technical constraints.
Delivery authoring owns duration and staffing estimates; pricing owns workload
sizing. Reuse their existing estimates, label assumptions and preserve units. Do not treat
an unknown value as zero or manufacture a confirmed commitment. Record conflicts
as open decisions. Frameworks are implementation choices, not separately billed
AWS services. A layout change cannot alter this baseline.
'''


def attach_traceability(design, evidence):
    result = deepcopy(design)
    issues = []
    ledger = []
    rows = result.get('requirement_ledger') or []
    if not rows:
        issues.append('Requirement ledger was not returned; coverage needs review.')
    for i, original in enumerate(rows):
        if not isinstance(original, dict):
            issues.append(f'Invalid requirement entry {i + 1}.')
            continue
        row = deepcopy(original)
        words = re.findall(r'\w+', str(row.get('source_quote', '')))
        match = re.search(r'(?<!\w)' + r'\W+'.join(map(re.escape, words)) + r'(?!\w)',
                          evidence, re.I) if words else None
        row['id'] = f'r{i + 1}'
        row['source_verified'] = bool(match)
        if match:
            row['source_quote'] = match.group()
            row['source_ref'] = {'sha256': sha256(evidence.encode()).hexdigest(),
                                 'start': match.start(), 'end': match.end()}
        else:
            row.pop('source_ref', None)
            row['disposition'] = 'unresolved'
            issues.append(f"{row['id']}: source excerpt could not be verified.")
        if row.get('disposition') not in {'included', 'deferred', 'excluded'}:
            row['disposition'] = 'unresolved'
            issues.append(f"{row['id']}: disposition needs review.")
        if row['disposition'] in {'deferred', 'excluded'} and not row.get('decision_reason'):
            issues.append(f"{row['id']}: release decision needs justification.")
        ledger.append(row)
    result['requirement_ledger'] = ledger
    result['traceability_issues'] = issues
    return result


def bind_solution(requirements, design):
    result = deepcopy(requirements)
    result['service_design'] = deepcopy(design)
    baseline = {k: deepcopy(design.get(k)) for k in (
        'summary', 'requirement_ledger', 'architecture_choice', 'frameworks',
        'services', 'capabilities', 'workflows', 'delivery_baseline', 'open_decisions')}
    baseline['version'] = sha256(json.dumps(baseline, sort_keys=True, default=str).encode()).hexdigest()
    # A reference/version avoids duplicating the full contract in every prompt.
    result['solution_definition'] = {'version': baseline['version'],
        'contract': 'service_design', 'authoring_rules': AUTHORING_RULES}
    return result


def prepare_requirement_ledger(rows, evidence):
    """Assign IDs after chunk merge; only collapse identical requirements."""
    unique, seen = [], set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        item = {k: deepcopy(v) for k, v in row.items()
                if k not in {'id', 'source_ref', 'source_verified', 'capability_ids'}}
        key = json.dumps(item, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return attach_traceability({'requirement_ledger': unique}, evidence)['requirement_ledger']


def materialize_requirement_facts(requirements):
    """Populate legacy fact arrays from citations, rather than generating them twice."""
    result = deepcopy(requirements)
    fields = {'functional':'functional_requirements', 'nonfunctional':'non_functional_requirements',
              'security':'security_requirements', 'performance':'performance_requirements',
              'integration':'integration_details'}
    for row in result.get('requirement_ledger', []):
        if not row.get('source_verified') or row.get('disposition') != 'included':
            continue
        field = fields.get(row.get('category'), 'functional_requirements')
        text = row['source_quote']
        values = result.setdefault(field, [])
        if text not in values:
            values.append(text)
    return result


def expand_design_references(design, ledger, evidence=''):
    """Restore the existing downstream contract without model repetition."""
    if not isinstance(design, dict):
        raise ValueError('Service design must be an object')
    result = deepcopy(design)
    if not ledger:
        return result  # Legacy callers still supply evidence quotes themselves.
    if any(not isinstance(row, dict) or not row.get('id') for row in ledger):
        raise ValueError('Requirement ledger needs valid IDs')
    by_id = {row['id']: deepcopy(row) for row in ledger}
    if len(by_id) != len(ledger):
        raise ValueError('Requirement ledger IDs must be unique')
    additions = result.pop('requirement_additions', [])
    if not isinstance(additions, list):
        raise ValueError('Requirement additions must be a list')
    aliases = {}
    for original in additions:
        if not isinstance(original, dict) or not isinstance(original.get('id'), str):
            raise ValueError('Requirement additions need unique temporary IDs')
        alias = original['id']
        if alias in by_id or alias in aliases:
            raise ValueError('Requirement addition IDs must be unique')
        verified = attach_traceability({'requirement_ledger':[original]}, evidence)
        if verified['traceability_issues']:
            raise ValueError('Requirement addition needs verified source and disposition')
        row = verified['requirement_ledger'][0]
        row['id'] = f'r{len(by_id) + 1}'
        aliases[alias] = row['id']
        by_id[row['id']] = row
    covered = set()
    for row in by_id.values():
        row['capability_ids'] = []
    caps = result.get('capabilities')
    if not isinstance(caps, list) or any(not isinstance(cap, dict) for cap in caps):
        raise ValueError('Capabilities must be a list of objects')
    for cap in caps:
        refs = cap.get('requirement_ids', [])
        if isinstance(refs, list) and all(isinstance(ref, str) for ref in refs):
            refs = [aliases.get(ref, ref) for ref in refs]
            cap['requirement_ids'] = refs
        else:
            raise ValueError('Unknown requirement references: expected ID strings')
        if not isinstance(refs, list) or not refs or any(ref not in by_id for ref in refs):
            raise ValueError(f"Unknown requirement references for capability {cap.get('id')}")
        for ref in refs:
            by_id[ref]['capability_ids'].append(cap['id'])
            covered.add(ref)
        cap['evidence_quote'] = by_id[refs[0]]['source_quote']
    missing = [r['id'] for r in by_id.values() if r.get('disposition') == 'included' and r['id'] not in covered]
    if missing:
        raise ValueError('Requirement coverage missing: ' + ', '.join(missing))
    result['requirement_ledger'] = list(by_id.values())
    def resolve_refs(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'requirement_ids':
                    if not isinstance(child, list) or not all(isinstance(ref, str) for ref in child):
                        raise ValueError('Requirement references must be ID lists')
                    refs = [aliases.get(ref, ref) for ref in child]
                    if any(ref not in by_id for ref in refs):
                        raise ValueError('Unknown requirement references in design')
                    value[key] = refs
                else:
                    resolve_refs(child)
        elif isinstance(value, list):
            for child in value:
                resolve_refs(child)
    resolve_refs(result)
    return result
