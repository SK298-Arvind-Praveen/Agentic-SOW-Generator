"""One product retains phased rollout scope and a complete indicative schedule."""
import json
from types import SimpleNamespace

from app.agents.scope_architect_agent import ScopeArchitectAgent
from app.agents.poc_writer_agent import POCWriterAgent, TemplateSection
from app.core.section_formats import (
    finalize_gantt_markdown, has_complete_gantt_allocation, presentation_contract,
    retain_gantt_context,
)


def test_numbered_rollout_phases_are_not_explicit_deliverable_packages():
    quotes = ['Phase 1 Pilot: Station 27', 'Phase 2 Extend: Station 40', 'Phase 3 Scale: Stations 28 to 39']
    requirements = {'source_deliverables': [
        {'name': quote, 'evidence_quote': quote} for quote in quotes
    ]}
    assert ScopeArchitectAgent._explicit_source_deliverables(requirements, '\n'.join(quotes)) == []


def test_repeated_phase_split_is_consolidated_without_losing_phase_scope():
    names = ['Pilot', 'Extend', 'Scale']
    inventory = {'capability_units': [
        {'id': f'CAP-{i:03d}', 'name': name} for i, name in enumerate(names, 1)
    ]}
    fragmented = {'deliverables': [
        {'name': name, 'boundary_type': 'phase', 'separation_basis': f'Phase {i} rollout',
         'modules': [{'name': f'{name} workflow', 'capability_ids': [f'CAP-{i:03d}']}]}
        for i, name in enumerate(names, 1)
    ]}
    replies = iter([inventory, fragmented, fragmented])
    agent = ScopeArchitectAgent(SimpleNamespace(), call_fn=lambda *a, **k: json.dumps(next(replies)))
    plan = agent.architect({}, {'project_title': 'Voice Inspection'}, 'Pilot then Extend then Scale')
    assert len(plan['deliverables']) == 1
    modules = plan['deliverables'][0]['modules']
    assert [m['capability_ids'] for m in modules] == [['CAP-001'], ['CAP-002'], ['CAP-003']]
    assert all(name in modules[i]['name'] for i, name in enumerate(names))


def test_distinct_source_outputs_survive_phase_boundary_audit():
    source = 'Commission an assessment report. Deliver a separately commissioned inspection application.'
    plan = {'deliverables': [
        {'name': 'Assessment', 'boundary_type': 'phase', 'modules': [{}],
         'independent_output_evidence': 'Commission an assessment report.'},
        {'name': 'Inspection application', 'boundary_type': 'phase', 'modules': [{}],
         'independent_output_evidence': 'Deliver a separately commissioned inspection application.'},
    ]}
    assert ScopeArchitectAgent._deliverable_fragmentation_issues(plan, source) == []
    plan['deliverables'][1]['independent_output_evidence'] = 'Invented independent output'
    assert ScopeArchitectAgent._deliverable_fragmentation_issues(plan, source)


PARTIAL = ('| S.No | Activity | W1 | W2 |\n| --- | --- | --- | --- |\n'
           '| 1 | Pilot | ■ | ■ |\n| 2 | Extend | | |\n| 3 | Scale | | |')
COMPLETE = ('| S.No | Activity | W1 | W2 | W3 | W4 |\n| --- | --- | --- | --- | --- | --- |\n'
            '| 1 | Pilot | ■ | ■ | | |\n| 2 | Extend | | | ■ | |\n| 3 | Scale | | | | ■ |')


def test_later_phase_rows_require_allocation_and_extended_caption_matches_grid():
    assert not has_complete_gantt_allocation(PARTIAL)
    assert has_complete_gantt_allocation(COMPLETE)
    result = finalize_gantt_markdown(PARTIAL, {'planning_duration_weeks': 2}, COMPLETE)
    assert has_complete_gantt_allocation(result)
    assert 'Indicative 4-week' in result and 'subject to approval' in result
    assert finalize_gantt_markdown(result, {'planning_duration_weeks': 2}) == result


def test_estimated_schedule_contract_covers_all_phases_without_fixing_eight_weeks():
    requirements = {'planning_duration_weeks': 8}
    contract = presentation_contract('timelines_deliverables', {'timeline_format': 'gantt'}, requirements)
    assert 'ALL in-scope delivery phases' in contract
    assert 'extending it' in contract
    notes = POCWriterAgent._consistency_notes(requirements, {})
    assert any('extend the indicative horizon' in note for note in notes)


def test_repaired_full_schedule_replaces_obsolete_pilot_caption_but_retains_gate():
    previous = ('Indicative eight-week pilot planning schedule, subject to approval.\n\n'
                + PARTIAL + '\n\nPilot build starts after readiness approval.')
    repaired = finalize_gantt_markdown(COMPLETE, {'planning_duration_weeks': 2})
    result = retain_gantt_context(repaired, previous)
    assert 'eight-week pilot' not in result
    assert 'Indicative 4-week' in result
    assert 'Pilot build starts after readiness approval.' in result


def test_finalize_restores_all_rows_when_review_erases_only_later_phase_allocations():
    reviewed = ('Indicative two-week pilot planning schedule, subject to approval.\n\n'
                + PARTIAL + '\n\nPilot build starts after readiness approval.')
    result = finalize_gantt_markdown(reviewed, {'planning_duration_weeks': 2}, COMPLETE)
    assert has_complete_gantt_allocation(result)
    assert 'Indicative 4-week' in result
    assert 'two-week pilot' not in result
    assert 'Pilot build starts after readiness approval.' in result


def test_writer_retries_a_partially_allocated_estimated_schedule(monkeypatch):
    agent = POCWriterAgent.__new__(POCWriterAgent)
    agent.config = SimpleNamespace(SOW_SECTION_WORKERS=1)
    agent.template_type = 'POC'
    agent.sections = [TemplateSection('Project Timeline', '', {'type': 'TABLE', '_explicit': True}, 1)]
    generated = []

    def generate(*args):
        generated.append(args)
        return PARTIAL if len(generated) == 1 else COMPLETE

    monkeypatch.setattr(agent, '_generate_section', generate)
    monkeypatch.setattr(agent, '_review_document_relevance', lambda *args: set())
    result = agent.generate_poc({}, {'timeline_format': 'gantt'}, selected_sow_sections=['timelines_deliverables'])
    assert len(generated) == 2
    assert has_complete_gantt_allocation(result['timelines_and_deliverables'])
    assert 'Indicative 4-week' in result['timelines_and_deliverables']
    assert 'Indicative 2-week' not in result['timelines_and_deliverables']
