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


def append_volume_assumptions(content, result):
    additions = [f'- Pricing assumes {label}: {value} (Approx.).'
                 for label, value, estimated in selected_volumes(result) if estimated
                 and f'{label}: {value}' not in content]
    return '\n'.join([content.rstrip(), *additions]).strip()
