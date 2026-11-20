"""Route diagnostics to their owner; presentation defects never authorize new services."""
from copy import deepcopy
import json
import re

STAGES = {'source', 'service_design', 'graph', 'story', 'layout', 'render', 'export', 'provider'}


def minor_text_finding(finding):
    """Only readable text contacts are advisory; a severity label is insufficient."""
    if finding.get('stage') != 'layout': return False
    rule = str(finding.get('rule_id', '')).lower()
    text = ' '.join(str(finding.get(k, '')) for k in ('description', 'evidence')).lower()
    if re.search(r'unreadable|illegible|obscur|hidden|disconnect|detach|wrong|ambiguous|incorrect|missing', text):
        return False
    return bool(re.search(r'(?:heading|label|text|caption).*(?:overlap|cross|touch)|(?:overlap|cross|touch).*(?:heading|label|text|caption)', rule)
                and re.search(r'heading|label|text|caption', text))


def normalize_finding(finding):
    value = dict(finding)
    if value.get('stage') not in STAGES:
        # Untyped legacy observations cannot authorize different services.
        value['stage'] = 'provider'
        value['rule_id'] = 'review.missing_stage'
    if value['stage'] in {'source', 'service_design', 'graph'} and not (
            value.get('evidence') and value.get('repair_instruction')
            and any(value.get(key) for key in ('node_ids', 'edge_ids'))):
        value['reported_stage'] = value['stage']
        value['stage'] = 'provider'
        value['rule_id'] = 'review.missing_semantic_evidence'
    value['kind'] = 'architecture' if value['stage'] in {'source', 'service_design', 'graph', 'story'} else 'visual'
    value.setdefault('rule_id', value['stage']+'.review')
    value.setdefault('severity', 'important')
    for key in ('node_ids', 'edge_ids', 'step_ids'): value.setdefault(key, [])
    value.setdefault('evidence', value.get('description', ''))
    value.setdefault('repair_instruction', value.get('description', ''))
    return value


def validate_finding(finding):
    """Validate fresh output while its bounded review correction is available."""
    if not isinstance(finding, dict) or finding.get('stage') not in STAGES:
        raise ValueError('Every image finding needs an explicit supported stage')
    if any(not isinstance(finding.get(k), str) or not finding[k].strip()
           for k in ('rule_id', 'severity', 'description', 'evidence', 'repair_instruction')):
        raise ValueError('Image findings require a rule, severity, evidence and targeted repair')
    for key in ('node_ids', 'edge_ids', 'step_ids'):
        if not isinstance(finding.get(key), list) or any(not isinstance(v, str) or not v for v in finding[key]):
            raise ValueError('Image findings require affected ID arrays')
    if finding['stage'] in {'source', 'service_design', 'graph', 'story', 'layout'} and not any(
            finding[k] for k in ('node_ids', 'edge_ids', 'step_ids')):
        raise ValueError('Cite the affected graph or story references')
    if finding['stage'] in {'source', 'service_design', 'graph'} and not (finding['node_ids'] or finding['edge_ids']):
        raise ValueError('A semantic replan requires concrete graph evidence')
    return normalize_finding(finding)


def repair_request(asset):
    review = asset.get('vision_review') or {}
    findings = [normalize_finding(i) for i in review.get('issues', []) if isinstance(i, dict)]
    stages = {f['stage'] for f in findings}
    semantic = bool(stages & {'source', 'service_design', 'graph'})
    if semantic or not asset.get('spec') or (asset.get('used_fallback') and not asset.get('retained_planned_spec')):
        return {'stage': 'graph', 'replan': True, 'findings': findings}
    stage = ('story' if 'story' in stages else 'layout' if stages & {'layout', 'render', 'export'}
             else 'provider' if 'provider' in stages or review.get('status') == 'unavailable' else 'layout')
    spec = deepcopy(asset['spec']); plan = spec.setdefault('architecture_plan', {})
    plan['repair_stage'] = stage
    if 'story' in stages:
        plan['story_feedback'] = json.dumps([f for f in findings if f['stage'] == 'story'])
    if stages & {'layout', 'render', 'export'} or stage == 'layout':
        plan['layout_feedback'] = json.dumps([f for f in findings if f['stage'] != 'story'])
        from app.diagram.routing_repair import repair_level
        plan['routing_repair'] = repair_level(plan.get('routing_repair')) + 1
    return {'stage': stage, 'replan': False, 'spec': spec, 'findings': findings}


def call_budget(name, candidate):
    if any(part in name for part in ('Process Story', 'Composition', 'Image Review')):
        return f'{name}/candidate-{candidate}', 2
    return name, 3
