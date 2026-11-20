"""Bounded-purpose context, with complete source coverage and no calculator payload."""
from copy import deepcopy
from hashlib import sha256

FIELDS = frozenset('project_overview business_problem desired_outcomes current_state key_features functional_requirements non_functional_requirements confirmed_aws_services proposed_aws_services aws_services architecture_components workflow_steps use_cases primary_personas data_sources data_characteristics integration_details security_requirements compliance_requirements performance_requirements accuracy_metrics success_metrics key_deliverables source_deliverables ui_required industry planning_assumptions open_clarifications source_basis requirements_provenance technical_requirements assumptions out_of_scope architecture_notes dependencies risks_and_mitigations confirmed_requirements service_design scope_boundaries architecture_evidence_policy architecture_confirmed_services'.split())


def architecture_context(requirements, metadata):
    source = str(requirements.get('architecture_source_context') or requirements.get('_original_objective') or '')
    return {'requirements': {k: deepcopy(v) for k, v in requirements.items() if k in FIELDS},
            'source': source,
            'selected_region': metadata.get('pricing_region') or metadata.get('region') or 'Unspecified',
            'evidence_chunks': [{'start': i, 'end': min(i+24000, len(source)),
                'sha256': sha256(source[i:i+24000].encode()).hexdigest()} for i in range(0, len(source), 24000)]}
