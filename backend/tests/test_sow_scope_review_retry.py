import json
from types import SimpleNamespace

import pytest

import app.agents.sow_reviewer_agent as module
from app.agents.sow_reviewer_agent import SOWReviewerAgent


def scope_fixture(count=2):
    scope = '\n\n'.join(f'### Module {i}\n\n- Deliver **module {i}** and report results.' for i in range(1, count + 1))
    context = {'scope_plan': {'deliverables': [{'display_name': 'Deliverable 1 - Build'}]}}
    table = '| Deliverable | Outcome |\n|---|---|\n| Deliverable 1 - Build | Service |\n\n'
    return scope, context, table


@pytest.mark.parametrize(('count', 'local'), [(10, True), (11, False)])
def test_scope_retry_uses_approved_structure_and_all_accepted_edits(tmp_path, count, local):
    scope, context, table = scope_fixture(count)
    original = {'scope': scope, 'benefits': '- Improve **service quality**.', 'terms': 'Protected.'}
    first_line = '- Deliver **module 1** and report results.'
    first_edit = '- Implement **module 1** and record outcomes.'
    last_line = f'- Deliver **module {count}** and report results.'
    last_edit = f'- Deliver **module {count}** and publish results.'
    accepted = scope.replace(last_line, last_edit)
    updated_benefit = '- Improve **service reliability**.'
    wrapper = table + '## Deliverable 1 - Build\n\n'
    rejected = {'section': 'scope', 'after': wrapper + scope.replace(first_line, first_edit)}
    if local:
        rejected.update(before=f'### Module 1\n\n{first_line}', after=wrapper + f'### Module 1\n\n{first_edit}')
    prompts = []
    repair_prompts = []

    def call(prompt):
        if 'SCOPE REPAIR' in prompt:
            repair_prompts.append(prompt)
            return json.dumps({'corrections': [{'proposal_id': 'scope-1', 'section': 'scope',
                                                'before': first_line, 'after': first_edit}], 'withdrawals': []})
        if 'keys (not category names or headings): ["benefits"]' in prompt:
            return json.dumps({'corrections': [{'section': 'benefits', 'after': updated_benefit}]})
        prompts.append(prompt)
        return json.dumps({'corrections': [rejected, {'section': 'scope', 'before': last_line, 'after': last_edit}]})

    reviewer = SOWReviewerAgent(SimpleNamespace(SOW_REVIEW_LOG_DIR=tmp_path), call)
    result = reviewer.review(original, {'scope': 'scope_of_work', 'benefits': 'business_benefits'}, context)
    assert result == {'scope': accepted.replace(first_line, first_edit), 'benefits': updated_benefit,
                      'terms': original['terms']}
    initial, = prompts
    repair, = repair_prompts
    assert 'single deliverable' in initial and 'no deliverable heading' in initial
    assert all(item in repair for item in (json.dumps(accepted), updated_benefit, json.dumps(rejected['after']),
                                           'Cannot add, remove, reorder or rename deliverable/module headings',
                                           'single deliverable', 'read-only'))
    assert json.dumps([f'### Module {i}' for i in range(1, count + 1)]) in repair
    audit = reviewer.last_review_audit
    batch = next(batch for batch in audit['batches'] if batch['sections'] == ['scope'])
    assert batch['changes'][0]['status'] == 'rejected'
    assert batch['changes'][0]['proposal_id'] == 'scope-1'
    assert batch['changes'][0]['suggestion'] == rejected
    assert batch['changes'][0]['resolved_by'] == 'scope_retry'
    assert batch['scope_retry']['changes'][0]['before'] == accepted
    assert audit['review_complete'] is True
    assert audit['rejected_sections'] == []


@pytest.mark.parametrize('unsafe_change', [
    'delete heading', 'rename heading', 'indented heading', 'tabbed heading', 'add table',
    'formatted table', 'modify peer', 'undo accepted edit', 'empty',
])
def test_unsafe_or_empty_retry_retains_accepted_content(tmp_path, unsafe_change):
    scope, context, table = scope_fixture()
    original = {'scope': scope, 'terms': 'Protected.'}
    before = '- Deliver **module 2** and report results.'
    after = '- Deliver **module 2** and review results.'
    accepted = scope.replace(before, after)
    patches = [{'section': 'scope', 'after': table + '## Deliverable 1 - Build\n\n' + scope},
               {'section': 'scope', 'after': scope.replace('### Module 2', '### New title')},
               {'section': 'scope', 'before': before, 'after': after}]
    repair = {
        'delete heading': [{'section': 'scope', 'after': accepted.split('\n\n### Module 2')[0]}],
        'rename heading': [{'section': 'scope', 'after': accepted.replace('### Module 1', '### Renamed')}],
        'indented heading': [{'section': 'scope', 'after': '  ### Deliverable 1 - Build\n\n' + accepted}],
        'tabbed heading': [{'section': 'scope', 'after': '###\tDeliverable 1 - Build\n\n' + accepted}],
        'add table': [{'section': 'scope', 'after': table + accepted}],
        'formatted table': [{'section': 'scope', 'after': table.replace('| Deliverable |', '| **Deliverable** |') + accepted}],
        'modify peer': [{'section': 'terms', 'after': 'Changed.'}],
        'undo accepted edit': [{'section': 'scope', 'before': after, 'after': before}],
        'empty': [],
    }[unsafe_change]
    if repair:
        repair[0].setdefault('before', accepted if repair[0]['section'] == 'scope' else 'Protected.')
        repair[0]['proposal_id'] = 'scope-1'
    calls = []

    def call(prompt):
        calls.append(prompt)
        return json.dumps({'corrections': patches} if len(calls) == 1 else {'corrections': repair, 'withdrawals': []})

    reviewer = SOWReviewerAgent(SimpleNamespace(SOW_REVIEW_LOG_DIR=tmp_path), call)
    assert reviewer.review(original, {'scope': 'scope_of_work'}, context) == {**original, 'scope': accepted}
    assert len(calls) == 2
    audit = reviewer.last_review_audit
    assert audit['review_complete'] is False
    assert 'scope' in audit['rejected_sections']
    batch = audit['batches'][0]
    assert all('resolved_by' not in entry for entry in batch['changes'])
    assert batch['scope_retry']['status'] == 'rejected'


@pytest.mark.parametrize('removed', ['heading', 'table'])
def test_multiple_deliverables_retry_keeps_required_structure(tmp_path, removed):
    table = ('| Deliverable | Outcome |\n|---|---|\n| Deliverable 1 - Build | Service |\n'
             '| Deliverable 2 - Handover | Training |')
    scope = (f'{table}\n\n### Deliverable 1 - Build\n\n#### Implementation\n\n- Build the **service** safely.\n\n'
             '### Deliverable 2 - Handover\n\n#### Enablement\n\n- Train the **support team** on the service.')
    plan = {'deliverables': [{'display_name': 'Deliverable 1 - Build'}, {'display_name': 'Deliverable 2 - Handover'}]}
    proposal = scope.replace(table + '\n\n', '') if removed == 'table' else scope.replace('#### Enablement\n\n', '')
    calls = []

    def call(prompt):
        calls.append(prompt)
        if len(calls) == 1:
            return json.dumps({'corrections': [{'section': 'scope', 'after': proposal}]})
        return json.dumps({'corrections': [{'proposal_id': 'scope-1', 'section': 'scope',
                                            'before': scope, 'after': proposal}], 'withdrawals': []})

    reviewer = SOWReviewerAgent(SimpleNamespace(SOW_REVIEW_LOG_DIR=tmp_path), call)
    assert reviewer.review({'scope': scope}, {'scope': 'scope_of_work'}, {'scope_plan': plan}) == {'scope': scope}
    assert len(calls) == 2
    assert all('multiple deliverables' in prompt and 'summary table' in prompt and '####' in prompt for prompt in calls)
    assert reviewer.last_review_audit['review_complete'] is False
    reason = reviewer.last_review_audit['batches'][0]['scope_retry']['changes'][0]['rejection_reason']
    assert reason == ('Cannot remove the deliverables summary table' if removed == 'table'
                      else 'Cannot add, remove, reorder or rename deliverable/module headings')


def test_scope_retry_cannot_start_after_shared_deadline(tmp_path, monkeypatch):
    scope, context, table = scope_fixture()
    clock = [0.0]
    monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    calls = []

    def call(prompt):
        calls.append(prompt)
        clock[0] = 1.0
        return json.dumps({'corrections': [{'section': 'scope', 'after': table + '## Deliverable 1 - Build\n\n' + scope}]})

    reviewer = SOWReviewerAgent(SimpleNamespace(SOW_REVIEW_LOG_DIR=tmp_path), call)
    assert reviewer.review({'scope': scope}, {'scope': 'scope_of_work'}, context, timeout=1.0) == {'scope': scope}
    assert len(calls) == 1
    assert reviewer.last_review_audit['review_complete'] is False
    assert reviewer.last_review_audit['batches'][0]['scope_retry']['status'] == 'deadline_exceeded'


def test_scope_retry_transient_error_uses_one_provider_attempt(tmp_path, monkeypatch):
    from botocore.exceptions import ReadTimeoutError

    scope, context, table = scope_fixture()
    calls = []

    def generate(self, model_id, prompt, **kwargs):
        calls.append(prompt)
        if len(calls) == 1:
            return SimpleNamespace(text=json.dumps({'corrections': [{'section': 'scope', 'after': table + scope}]}))
        raise ReadTimeoutError(endpoint_url='https://bedrock-runtime.us-east-1.amazonaws.com')

    monkeypatch.setattr(module.boto3, 'client', lambda *a, **kw: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(module.BedrockLLM, '_generate_once', generate)
    config = SimpleNamespace(SOW_REVIEW_LOG_DIR=tmp_path, BEDROCK_REGION='us-east-1', FAST_MODEL_ID='test')
    reviewer = SOWReviewerAgent(config)
    assert reviewer.review({'scope': scope}, {'scope': 'scope_of_work'}, context) == {'scope': scope}
    assert len(calls) == 2
    assert reviewer.last_review_audit['review_complete'] is False
    assert reviewer.last_review_audit['batches'][0]['scope_retry']['status'] == 'failed'


def test_cancelled_preview_cannot_start_scope_retry(tmp_path):
    from app.preview.cancellation import current_preview, GenerationCancelled
    from app.preview.preview_handler import preview_lock, preview_storage

    scope, context, table = scope_fixture()
    preview_id = 'test-scope-retry-cancelled'
    calls = []

    def call(prompt):
        calls.append(prompt)
        with preview_lock:
            preview_storage[preview_id]['cancel_requested'] = True
        return json.dumps({'corrections': [{'section': 'scope', 'after': table + scope}]})

    reviewer = SOWReviewerAgent(SimpleNamespace(SOW_REVIEW_LOG_DIR=tmp_path), call)
    with preview_lock:
        preview_storage[preview_id] = {'cancel_requested': False}
    token = current_preview.set(preview_id)
    try:
        with pytest.raises(GenerationCancelled):
            reviewer.review({'scope': scope}, {'scope': 'scope_of_work'}, context)
        assert len(calls) == 1
    finally:
        current_preview.reset(token)
        with preview_lock:
            preview_storage.pop(preview_id, None)


@pytest.mark.parametrize(('addressed_module', 'old_word', 'new_word', 'matches_target'), [
    (1, 'report', 'record', True),
    (3, 'report', 'record', False),
    (1, 'results', 'outcomes', False),
])
def test_retry_only_resolves_rejections_covered_by_its_changes(
        tmp_path, addressed_module, old_word, new_word, matches_target):
    scope, context, table = scope_fixture(3)
    proposals = []
    for number in (1, 2):
        line = f'### Module {number}\n\n- Deliver **module {number}** and report results.'
        proposals.append({'section': 'scope', 'before': line,
                          'after': f'## Module {number}\n\n- Deliver **module {number}** and record results.'})
    before = f'- Deliver **module {addressed_module}** and report results.'
    after = before.replace(old_word, new_word)

    def call(prompt):
        if 'SCOPE REPAIR' not in prompt:
            return json.dumps({'corrections': proposals})
        return json.dumps({'corrections': [{'proposal_id': 'scope-1', 'section': 'scope',
                                            'before': before, 'after': after}], 'withdrawals': []})

    reviewer = SOWReviewerAgent(SimpleNamespace(SOW_REVIEW_LOG_DIR=tmp_path), call)
    result = reviewer.review({'scope': scope}, {'scope': 'scope_of_work'}, context)
    audit = reviewer.last_review_audit
    batch = audit['batches'][0]
    assert result['scope'] == (scope.replace(before, after) if matches_target else scope)
    assert audit['review_complete'] is False
    assert audit['rejected_sections'] == (['scope'] if matches_target else ['scope', 'scope'])
    assert [entry['proposal_id'] for entry in batch['changes']] == ['scope-1', 'scope-2']
    assert [item['status'] for item in batch['scope_retry']['dispositions']] == [
        'repaired' if matches_target else 'unresolved', 'unresolved',
    ]


@pytest.mark.parametrize(('proposal_kind', 'withdrawable'), [
    ('added wrapper', True), ('added table', True), ('changed body', False),
    ('renamed module', False), ('deleted module', False), ('added wrapper and renamed module', False),
])
def test_explicit_withdrawal_only_clears_a_wrapper_addition(tmp_path, proposal_kind, withdrawable):
    scope, context, table = scope_fixture()
    wrapper = table + '## Deliverable 1 - Build\n\n'
    renamed = scope.replace('### Module 1', '### Module 1 and another language')
    proposal = {
        'added wrapper': wrapper + scope,
        'added table': table + scope,
        'changed body': wrapper + scope.replace('and report results', 'and record results', 1),
        'renamed module': renamed,
        'deleted module': scope.replace('### Module 1\n\n', ''),
        'added wrapper and renamed module': wrapper + renamed,
    }[proposal_kind]
    reason = 'The approved single deliverable already has the required structure.'

    def call(prompt):
        if 'SCOPE REPAIR' not in prompt:
            return json.dumps({'corrections': [{'section': 'scope', 'after': proposal}]})
        return json.dumps({'corrections': [], 'withdrawals': [{'proposal_id': 'scope-1', 'reason': reason}]})

    reviewer = SOWReviewerAgent(SimpleNamespace(SOW_REVIEW_LOG_DIR=tmp_path), call)
    assert reviewer.review({'scope': scope}, {'scope': 'scope_of_work'}, context) == {'scope': scope}
    audit = reviewer.last_review_audit
    assert audit['review_complete'] is withdrawable
    disposition, = audit['batches'][0]['scope_retry']['dispositions']
    assert disposition['status'] == ('withdrawn' if withdrawable else 'unresolved')
    if withdrawable:
        assert disposition['reason'] == reason
    else:
        assert audit['rejected_sections'] == ['scope']


@pytest.mark.parametrize('wrapper', [
    '  ### Deliverable 1 - Build\n\n',
    '###\tDeliverable 1 - Build\n\n',
    '| **Deliverable** | Outcome |\n|---|---|\n| Deliverable 1 - Build | Service |\n\n',
])
def test_scope_guard_rejects_renderer_visible_wrappers(wrapper):
    scope, _, _ = scope_fixture()
    with pytest.raises(ValueError):
        module.apply_corrections({'scope': scope}, {'corrections': [{'section': 'scope', 'after': wrapper + scope}]},
                                 {'scope': 'scope_of_work'}, {}, scope_deliverables=1)
