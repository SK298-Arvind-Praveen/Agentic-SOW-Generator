import json
from types import SimpleNamespace

import pytest

from app.agents.sow_reviewer_agent import SOWReviewerAgent, apply_corrections
from app.core.sow_presentation import regroup_scope_modules


SCOPE = '''| Deliverable | Outcome |
|---|---|
| Build | Platform |
| Support | Operations |

### Deliverable 1 - Build

#### Notifications

- Send order alerts.
- Record delivery results.

#### Feedback

- Collect customer feedback.
- Record delivery results.

### Deliverable 2 - Support

#### Operations

- Resolve incidents during support hours.'''

GROUPS = [
    {'deliverable': 'Deliverable 1 - Build', 'heading': 'Customer Communications',
     'modules': ['Notifications', 'Feedback']},
    {'deliverable': 'Deliverable 2 - Support', 'heading': 'Operations', 'modules': ['Operations']},
]


def test_grouping_preserves_deliverables_table_and_every_unique_action():
    result = apply_corrections({'scope': SCOPE}, {'corrections': [
        {'section': 'scope', 'module_groups': GROUPS}
    ]}, {'scope': 'scope_of_work'}, {})['scope']
    assert result.startswith(SCOPE.split('###')[0].strip())
    assert result.count('### Deliverable') == 2
    assert result.count('#### ') == 2
    assert '#### Customer Communications' in result
    assert result.count('- Record delivery results.') == 1
    for action in ('Send order alerts.', 'Collect customer feedback.', 'Resolve incidents during support hours.'):
        assert '- ' + action in result


@pytest.mark.parametrize('modules', [['Notifications'], ['Notifications', 'Notifications', 'Feedback'],
                                     ['Notifications', 'Feedback', 'Operations'], ['Notifications', 'Invented']])
def test_grouping_rejects_dropped_duplicated_or_cross_deliverable_modules(modules):
    with pytest.raises(ValueError):
        regroup_scope_modules(SCOPE, [dict(GROUPS[0], modules=modules), GROUPS[1]])


def test_grouping_single_unwrapped_deliverable():
    result = regroup_scope_modules('### Alerts\n\n- Send alerts.\n\n### Feedback\n\n- Collect feedback.', [
        {'deliverable': '', 'heading': 'Communications', 'modules': ['Alerts', 'Feedback']}])
    assert result == '### Communications\n\n- Send alerts.\n- Collect feedback.'


def test_grouping_is_scope_only_and_ordinary_patch_cannot_rename_modules():
    with pytest.raises(ValueError):
        apply_corrections({'arch': SCOPE}, {'corrections': [{'section': 'arch', 'module_groups': GROUPS}]},
                          {'arch': 'architecture_diagram'}, {})
    with pytest.raises(ValueError):
        apply_corrections({'scope': SCOPE}, {'corrections': [{'section': 'scope', 'after': SCOPE.replace('#### Feedback', '#### Surveys')}]},
                          {'scope': 'scope_of_work'}, {})


@pytest.mark.parametrize('after', ['Route requests through the API. Store session state.',
                                 '- Route requests through the API. Store session state.',
                                 'Architecture overview\n\n- Route requests through the API.'])
def test_architecture_review_cannot_create_paragraphs(after):
    with pytest.raises(ValueError):
        apply_corrections({'arch': '- Route requests through the API.\n- Store session state.'},
                          {'corrections': [{'section': 'arch', 'after': after}]}, {'arch': 'architecture_diagram'}, {})


def test_architecture_review_accepts_concise_bullets():
    after = '- Route requests through the API and store session state.'
    assert apply_corrections({'arch': 'A long paragraph.'}, {'corrections': [{'section': 'arch', 'after': after}]},
                             {'arch': 'architecture_diagram'}, {})['arch'] == after


def test_multiple_independent_scope_edits_then_grouping_are_applied_and_logged(tmp_path):
    patches = [
        {'section': 'scope', 'before': '- Send order alerts.', 'after': '- Send **order alerts**.', 'reason': 'Emphasise action'},
        {'section': 'scope', 'before': '- Collect customer feedback.', 'after': '- Collect **customer feedback**.', 'reason': 'Emphasise action'},
        {'section': 'scope', 'module_groups': GROUPS, 'reason': 'Combine related customer communications'},
    ]
    reviewer = SOWReviewerAgent(SimpleNamespace(SOW_REVIEW_LOG_DIR=tmp_path), lambda p: json.dumps({'corrections': patches}))
    result = reviewer.review({'scope': SCOPE}, {'scope': 'scope_of_work'}, {})['scope']
    assert '- Send **order alerts**.' in result
    assert '- Collect **customer feedback**.' in result
    assert '#### Customer Communications' in result
    audit = json.loads(next(tmp_path.glob('*.json')).read_text())
    # Content/grouping succeeded, but untouched bullets still need emphasis.
    assert audit['incomplete_sections'] == []
    assert audit['review_complete'] is False
    assert audit['bullet_checks_after']['scope']['missing_inline_emphasis'] == [2, 4]
    assert [c['status'] for c in audit['batches'][0]['changes']] == ['applied'] * 3


def test_overlapping_scope_edits_are_rejected_without_discarding_independent_edit(tmp_path):
    patches = [
        {'section': 'scope', 'before': '- Send order alerts.', 'after': '- Send **order alerts**.'},
        {'section': 'scope', 'after': SCOPE},
        {'section': 'scope', 'before': '- Collect customer feedback.', 'after': '- Collect **customer feedback**.'},
    ]
    reviewer = SOWReviewerAgent(SimpleNamespace(SOW_REVIEW_LOG_DIR=tmp_path), lambda p: json.dumps({'corrections': patches}))
    result = reviewer.review({'scope': SCOPE}, {'scope': 'scope_of_work'}, {})['scope']
    assert '**order alerts**' in result and '**customer feedback**' in result
    changes = reviewer.last_review_audit['batches'][0]['changes']
    assert [c['status'] for c in changes] == ['applied', 'rejected', 'applied']
    assert 'Overlapping' in changes[1]['rejection_reason']
