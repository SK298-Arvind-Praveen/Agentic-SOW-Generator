import json
import time
from types import SimpleNamespace

import pytest

from app.agents.sow_reviewer_agent import SOWReviewerAgent, apply_corrections


def test_assumptions_and_exclusions_share_review_with_scope_evidence():
    original = {
        'work': '- Deliver a **unified platform** for both brands.',
        'premises': '- Both brands use a **unified platform**.',
        'excluded': '- A **unified platform** is excluded.\n- Replacement of existing APIs is **excluded**.',
    }
    calls = []
    def call(prompt):
        keys = json.loads(prompt.split('Use only these exact section keys (not category names or headings): ')[1].split('\n')[0])
        calls.append(keys)
        assert original['work'] in json.loads(prompt.split('DOCUMENT (only listed editable keys may be changed):\n')[1]).values()
        if 'premises' not in keys:
            return json.dumps({'corrections': []})
        assert 'excluded' in keys
        assert 'one boundary check' in prompt
        assert 'shared keywords alone' in prompt
        return json.dumps({'corrections': [
            {'section': 'premises', 'after': '', 'reason': 'Confirmed platform commitment belongs in Scope, not Assumptions.'},
            {'section': 'excluded', 'after': '- Replacement of existing APIs is **excluded**.',
             'reason': 'Remove unified-platform exclusion contradicting Scope; retain separate API boundary.'},
        ]})
    result = SOWReviewerAgent(SimpleNamespace(), call).review(original, {
        'work': 'scope_of_work', 'premises': 'assumptions', 'excluded': 'out_of_scope',
    }, {'requirements': ['Unified platform; integrate existing APIs without replacement.']})
    assert any({'premises', 'excluded'} <= set(keys) for keys in calls)
    assert result['premises'] == ''
    assert result['excluded'] == '- Replacement of existing APIs is **excluded**.'
    assert result['work'] == original['work']


@pytest.mark.parametrize('category', ['assumptions', 'out_of_scope'])
def test_irrelevant_contract_list_can_be_removed_without_filler(category):
    original = {'section': '- Irrelevant filler.'}
    assert apply_corrections(original, {'corrections': [{'section': 'section', 'after': ''}]},
                             {'section': category}, {})['section'] == ''


def test_scope_cannot_be_erased_when_removing_contract_filler():
    with pytest.raises(ValueError, match='Cannot erase'):
        apply_corrections({'scope': '- Deliver agreed work.'},
                          {'corrections': [{'section': 'scope', 'after': ''}]},
                          {'scope': 'scope_of_work'}, {})


def test_targeted_correction_has_context_and_preserves_protected_text():
    original = {'duties': '- Provide credentials.\n- Provide API documentation.', 'legal': 'Exact clause'}
    def call(prompt):
        assert 'customer_access' in prompt and 'POC' in prompt
        return json.dumps({'corrections': [{'section': 'duties', 'before': original['duties'],
                                           'after': '- Provide API documentation and credentials.'}]})
    result = SOWReviewerAgent(SimpleNamespace(), call).review(original,
        {'duties': 'customer_responsibilities'}, {'mode': 'POC', 'requirements': ['customer_access']})
    assert result['legal'] == original['legal']
    assert result['duties'] != original['duties']
    assert original['duties'].count('\n') == 1


@pytest.mark.parametrize('patch', [
    {'section': 'legal', 'before': 'Exact clause', 'after': 'Changed'},
    {'section': 'scope', 'before': '- Test 50 sessions.', 'after': '- Test 900 sessions.'},
    {'section': 'scope', 'before': '### Module A', 'after': '### New module'},
    {'section': 'scope', 'before': 'nonexistent', 'after': ''},
])
def test_unsafe_patch_transaction_is_rejected(patch):
    with pytest.raises(ValueError):
        apply_corrections({'legal': 'Exact clause', 'scope': '### Module A\n- Test 50 sessions.'},
                          {'corrections': [patch]}, {'scope': 'scope_of_work'}, {})


def test_timeout_and_malformed_response_do_not_apply_partial_changes():
    original = {'objective': 'Build a tool.'}
    def slow(prompt):
        time.sleep(.1)
        return '{"corrections":[]}'
    started = time.monotonic()
    assert SOWReviewerAgent(SimpleNamespace(), slow).review(original, {'objective':'project_overview'}, {}, timeout=.01) == original
    assert time.monotonic() - started < .08
    assert SOWReviewerAgent(SimpleNamespace(), lambda p: '{"corrections":[').review(original, {'objective':'project_overview'}, {}) == original


def test_about_company_patch_requires_two_paragraphs():
    with pytest.raises(ValueError):
        apply_corrections({'about': 'A company.'}, {'corrections':[
            {'section':'about','before':'A company.','after':'One sentence.'}]}, {'about':'about_client'}, {})


def test_raci_correction_rejects_vendor_only_uat_accountability():
    original = {'raci': '| Workstream | Shellkode | Client |\n|---|---|---|\n| UAT | RA | C |'}
    replacement = original['raci'].replace('UAT', 'Business acceptance')
    with pytest.raises(ValueError):
        apply_corrections(original, {'corrections':[{'section':'raci', 'before':original['raci'],
                          'after':replacement}]}, {'raci':'raci_matrix'}, {})
    corrected = replacement.replace('| RA | C |', '| RC | RA |')
    assert apply_corrections(original, {'corrections':[{'section':'raci', 'before':original['raci'],
        'after':corrected}]}, {'raci':'raci_matrix'}, {})['raci'] == corrected
