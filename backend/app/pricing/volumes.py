"""One concise workload basis shared by pricing and assumptions."""
import re


def selected_volumes(result):
    rows = []
    seen = set()
    resource_volumes = []
    for coverage in (result.get('resource_coverage') or {}).values():
        for config in coverage.get('configurations', []):
            if config.get('monthly_hours') is not None:
                resource_volumes.append({'metric': str(config.get('label') or 'Compute') + ' operating hours',
                    'value': f"{config.get('quantity', 1)} {'instance' if config.get('quantity', 1)==1 else 'instances'} × {config['monthly_hours']:g} h/month",
                    'status': config.get('runtime_status') or config.get('status')})
    for entry in [*resource_volumes, *(result.get('volume_metrics') or []), *(result.get('sizing_details') or [])]:
        label = str(entry.get('metric') or entry.get('input') or '').strip()
        value = str(entry.get('value') or '').strip()
        if not label or not value:
            continue
        if not re.search(r'request.rate|invocations|conversation|interaction|document.*volume|monthly.*(?:request|vehicle|inspection)|audio|speech|stream.*minute|hours|storage|database.*size|concurren|active.user', label, re.I):
            continue
        if re.search(r'cache|put|copy|list.request|log|vocabulary|defect.term|price|cost', label, re.I):
            continue
        key = re.sub(r'[^a-z0-9]', '', label.casefold())
        if key in seen:
            continue
        seen.add(key)
        status = str(entry.get('status') or '').casefold()
        approximate = status not in {'source', 'source-backed', 'source_backed', 'provided', 'explicit', 'brd', 'confirmed'}
        value = re.sub(r'\s*\((?:Approximated|Approx\.|Estimated)\)\s*$', '', value, flags=re.I)
        rows.append((label, value, approximate))
        if len(rows) == 5:
            break
    return rows


def volume_assumption(label, value):
    """Present the same sizing facts as prose, without table provenance markers."""
    label = re.sub(r'\s+assumption\s*$', '', label, flags=re.I).strip()
    value = re.sub(r'\s*\((?:Approx\.|Approximated|Estimated)\)', '', value, flags=re.I).strip().rstrip('.')
    # The table retains the calculation; prose leads with its resulting volume.
    if '≈' in value:
        value = value.rsplit('≈', 1)[1].strip()
    if re.fullmatch(r'monthly active users', label, re.I):
        value = re.sub(r'\s*(?:MAU|monthly active users)\b', '', value, flags=re.I).strip()
        return f'There are approximately {value} monthly active users.'
    if re.fullmatch(r'usage[- ]hours', label, re.I) and re.search(r'monthly operation', value, re.I):
        return 'Usage hours represent a typical month of operation, rather than the total POC duration.'
    if re.fullmatch(r'hours per day(?: at this rate)?', label, re.I):
        value = re.sub(r'hours/day', 'hours per day', value, flags=re.I)
        return f'Operations run for approximately {value}.'
    verb = 'are' if re.search(r'\b(?:requests|conversations|interactions|hours|invocations|users)$', label, re.I) else 'is'
    return f'{label[:1].upper() + label[1:]} {verb} estimated at {value}.'


def append_volume_assumptions(content, result):
    additions = []
    for label, value, estimated in selected_volumes(result):
        if not estimated:
            continue
        sentence = volume_assumption(label, value)
        # Also upgrade the old generated wording when editing an existing SOW.
        legacy = f'- Pricing assumes {label}: {value} (Approx.).'
        content = content.replace(legacy, '- ' + sentence)
        if sentence not in content and sentence not in additions:
            additions.append(sentence)
    return '\n'.join([content.rstrip(), *('- ' + text for text in additions)]).strip()
