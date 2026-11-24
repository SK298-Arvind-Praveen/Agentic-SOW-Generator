"""Semantic identity shared by authoring, diagrams, regeneration and export."""
from copy import deepcopy
from hashlib import sha256
import json

DEPENDENTS = ('scope_of_work', 'assumptions', 'aws_pricing', 'conceptual_flow_diagram',
              'architecture_diagram', 'service_table')


def bind_requirements(requirements, spec, registry):
    """Replace an earlier suggested inventory with the graph actually selected."""
    result = deepcopy(requirements)
    value = spec.as_dict() if hasattr(spec, 'as_dict') else spec
    result['approved_architecture'] = freeze(value)
    names = []
    for node in value.get('nodes', []):
        key = node.get('icon_key', '')
        if key.startswith('aws.') and node.get('scope') != 'external' and node.get('kind') != 'group':
            entry = registry.by_key.get(key, {})
            if entry.get('label'): names.append(entry['label'])
    if names:
        result['aws_services'] = list(dict.fromkeys(names))
        confirmed = set(result.get('architecture_confirmed_services') or [])
        result['confirmed_aws_services'] = [n for n in result['aws_services'] if n in confirmed]
        result['proposed_aws_services'] = [n for n in result['aws_services'] if n not in confirmed]
    design = value.get('architecture_plan', {}).get('service_design')
    if design:
        from app.core.solution_definition import bind_solution
        # Geometry/semantic repair may return only service mappings. It cannot
        # erase the source ledger, release decisions or delivery assumptions.
        previous = result.get('service_design') or {}
        design = {**{k: deepcopy(previous[k]) for k in (
            'requirement_ledger', 'delivery_baseline', 'architecture_choice',
            'frameworks', 'reference_pattern_ids', 'traceability_issues') if k in previous}, **design}
        result = bind_solution(result, design)
    return result


def freeze(spec):
    value = spec.as_dict() if hasattr(spec, 'as_dict') else spec
    nodes, edges = deepcopy(value.get('nodes', [])), deepcopy(value.get('edges', []))
    semantic = {'nodes': sorted(nodes, key=lambda n: n['id']),
                # Edge references are positional in persisted diagram contracts.
                # Reordering them must change the version to prevent e0 aliasing.
                'edges': edges}
    version = sha256(json.dumps(semantic, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    operations = []
    for i, edge in enumerate(edges):
        # Legacy edges have an action but no established initiator/data direction.
        # Never infer inbound request semantics from words like "route".
        operations.append({'id': f'e{i}', **edge, 'operation_type': edge.get('operation_type') or 'unknown',
                           'initiator': edge.get('initiator') or None,
                           'data_direction': edge.get('data_direction') or None,
                           'evidence_refs': edge.get('evidence_refs') or []})
    return {'version': version, 'nodes': nodes, 'edges': edges, 'operations': operations}


def stale_artifacts(version, artifacts):
    return [key for key, value in artifacts.items() if value != version]


def stamp(state, *names):
    result = dict(state.get('artifact_architecture_versions') or {})
    if state.get('architecture_version'):
        result.update({name: state['architecture_version'] for name in names})
    return result
