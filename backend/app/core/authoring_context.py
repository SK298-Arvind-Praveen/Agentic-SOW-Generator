"""Keep semantic requirements, not duplicated source payloads, in writer prompts."""

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
