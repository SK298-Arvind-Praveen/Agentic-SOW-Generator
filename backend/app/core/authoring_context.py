"""Keep semantic requirements, not duplicated source payloads, in writer prompts."""
import re
from functools import lru_cache


def selected_region_instruction(metadata):
    selected = (metadata or {}).get('pricing_region')
    if not selected: return ''
    return (f'The user selected {selected} as the target AWS deployment Region. This overrides source-document '
            'target-region suggestions throughout scope, objectives, dependencies, exclusions and pricing. '
            'Preserve explicitly existing/source/external system and replication-origin Regions. ')


@lru_cache(maxsize=1)
def _region_names():
    # Installed SDK data is local and includes the provider's complete Region
    # labels. Country aliases are only used inside explicit AWS target clauses.
    import botocore.session
    names = {}
    for partition in botocore.session.get_session().get_data('endpoints')['partitions']:
        for code, item in partition.get('regions', {}).items():
            description = item.get('description', '')
            city = re.search(r'\(([^)]+)\)', description)
            for name in (description, city.group(1) if city else ''):
                if name: names.setdefault(name.casefold(), set()).add(code)
    names.update({'uk': {'eu-west-2'}, 'united kingdom': {'eu-west-2'},
                  'india': {'ap-south-1', 'ap-south-2'}})
    return names


def target_region_conflicts(text, metadata):
    """Locate only explicit target clauses; do not globally replace region names."""
    selected = str((metadata or {}).get('pricing_region') or '').lower()
    if not re.fullmatch(r'[a-z]{2}(?:-gov)?-[a-z]+-\d', selected): return []
    def target_clause(offset):
        start = max(text.rfind(sep, 0, offset) for sep in ('\n', '.', ';', '|')) + 1
        prefix = re.sub(r'[*_`]', '', text[start:offset]).lower()
        source = list(re.finditer(r'\b(?:source|existing|external|origin|on-premises)\b', prefix))
        # "Existing source deployment" describes a source noun; it is not a
        # later instruction to deploy. Explicit from/to binds both locations
        # correctly even when the migrated object is called a source database.
        if re.search(r'\b(?:migrat\w*|mov(?:e|ing))\b', prefix):
            movement = list(re.finditer(r'\b(?:from|to|into)\b', prefix))
            if movement:
                return movement[-1].group() in {'to', 'into'}
        target = list(re.finditer(r'\b(?:target|destination|deploy(?:s|ed|ing)?|provision(?:s|ed|ing)?|isolated|nonproduction)\b', prefix))
        if source:
            after_source = prefix[source[-1].end():]
            explicit_destination = re.search(r'\b(?:target|destination|isolated|nonproduction)\b', after_source)
            new_command = re.search(r'\b(?:and|then|but)\s+(?:then\s+)?(?:deploy|provision)\b', after_source)
            if not explicit_destination and not new_command:
                return False
        account = re.search(r'\b(?:grant|provide|access|create|configure|prepare)\b.{0,100}\bAWS\s+account\b', prefix, re.I)
        boundary = re.search(r'\b(?:other|additional)\b.{0,30}\bregions?\b.{0,20}\b(?:beyond|outside|than)\b', prefix)
        migration = re.search(r'\bmigrat\w*\b.{0,100}\b(?:to|into)\b', prefix)
        return bool(target or account or boundary or migration)
    names = _region_names()
    pattern = '|'.join(re.escape(name) for name in sorted(names, key=len, reverse=True))
    conflicts = []
    for match in re.finditer(r'\b[a-z]{2}(?:-gov)?-[a-z]+-\d\b', text, re.I):
        if not target_clause(match.start()): continue
        start, end = match.span()
        # Replace the complete contradictory location, never leave a target
        # such as "London (ap-south-1)" after correcting only its code.
        paired = re.search(r'\b(?P<label>'+pattern+r')\s*\(\s*$', text[:start], re.I)
        wrong_name = paired and selected not in names[paired.group('label').casefold()]
        if match.group().lower() == selected and not wrong_name: continue
        if paired and text[end:end+1] == ')': start, end = paired.start(), end+1
        conflicts.append({'start': start, 'end': end, 'from': text[start:end], 'to': selected})
    for match in re.finditer(r'\b(?:'+pattern+r')\b', text, re.I):
        if selected in names[match.group().casefold()] or not target_clause(match.start()): continue
        if any(r['start'] <= match.start() < r['end'] for r in conflicts): continue
        start = max(text.rfind(sep, 0, match.start()) for sep in ('\n', '.', ';', '|'))+1
        tail = re.split(r'[\n.;|]', text[match.end():], maxsplit=1)[0]
        clause = text[start:match.end()]+tail
        # Name-only geography is corrected only when explicitly described as an
        # AWS Region. Local time, support hours and source locations are facts.
        before = re.sub(r'[*_`]', '', text[start:match.start()])
        after = re.sub(r'[*_`]', '', tail)
        region_location = (re.search(r'\bregions?\s*(?:(?:in|of)\s+|[:=-]\s*)?(?:the\s+)?$', before, re.I)
            or re.match(r'\s+(?:AWS\s+)?(?:deployment\s+)?regions?\b', after, re.I))
        if region_location and re.search(r'\bAWS\b', clause, re.I):
            conflicts.append({'start': match.start(), 'end': match.end(), 'from': match.group(), 'to': selected})
    return sorted(conflicts, key=lambda item: item['start'])


def restore_target_region(text, metadata):
    repairs = target_region_conflicts(text, metadata)
    for repair in reversed(repairs):
        text = text[:repair['start']] + repair['to'] + text[repair['end']:]
    return text, repairs

# Strip the retired rag_context field from historical snapshots too; never use it
# as generation evidence or reconnect to its former table.
TRANSPORT_FIELDS = {'source_documents', 'supporting_context', 'source_text', 'raw_text',
                    'raw_content', 'rag_context', 'aws_pricing_result', 'token_usage'}


def authoring_facts(value):
    if isinstance(value, dict):
        return {key: authoring_facts(item) for key,item in value.items()
                if not str(key).startswith('_') and key not in TRANSPORT_FIELDS}
    if isinstance(value, list):
        return [authoring_facts(item) for item in value]
    return value


def boundary_summary(plan):
    return {
        'deliverables': [{key: d[key] for key in ('name','purpose') if key in d}
                         for d in plan.get('deliverables', [])],
        'cross_cutting_decisions': plan.get('cross_cutting_decisions', []),
        'open_boundaries': plan.get('open_boundaries', []),
    }
