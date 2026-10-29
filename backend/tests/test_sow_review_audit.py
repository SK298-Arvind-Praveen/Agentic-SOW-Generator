import json
from types import SimpleNamespace

from app.agents.sow_reviewer_agent import SOWReviewerAgent


def test_logs_suggestions_applied_rejected_and_reductions(tmp_path):
    original = {'duties': '- Provide credentials.\n- Provide access.', 'legal': 'Protected.'}
    payload = {'corrections': [
        {'section': 'duties', 'after': '- Provide access credentials.', 'reason': 'Merged duplicate access requests.'},
        {'section': 'legal', 'after': 'Changed.', 'reason': 'Not allowed.'}]}
    reviewer = SOWReviewerAgent(SimpleNamespace(SOW_REVIEW_LOG_DIR=tmp_path), lambda p: json.dumps(payload))
    result = reviewer.review(original, {'duties': 'customer_responsibilities'}, {'metadata': {'project_title': 'Demo'}})
    log = json.loads(next(tmp_path.glob('*_sow_review.json')).read_text(encoding='utf-8'))
    assert log['project'] == 'Demo'
    assert log['applied_sections'] == ['duties']
    assert log['words_after'] < log['words_before']
    applied, rejected = log['batches'][0]['changes']
    assert applied['status'] == 'applied' and applied['after'] == result['duties']
    assert '- Provide credentials.' in applied['diff']
    assert applied['suggestion']['reason'] == 'Merged duplicate access requests.'
    assert rejected['status'] == 'rejected' and rejected['rejection_reason'] == 'Uneditable section'
    assert result['legal'] == 'Protected.'


def test_parallel_batches_see_peer_sections_and_logs_are_unique(tmp_path):
    original = {'benefits': '- Faster handling.', 'scope': '### Build\n- Connect the service.',
                'dependencies': '- Provide API access.'}
    def call(prompt):
        assert 'REPETITION REDUCTION IS A PRIMARY REVIEW TASK' in prompt
        document = json.loads(prompt.split('DOCUMENT (only listed editable keys may be changed):\n')[1])
        assert document == original
        return '{"corrections":[]}'
    reviewer = SOWReviewerAgent(SimpleNamespace(SOW_REVIEW_LOG_DIR=tmp_path), call)
    for _ in range(2):
        assert reviewer.review(original, {'benefits': 'business_benefits', 'scope': 'scope_of_work',
                               'dependencies': 'customer_dependencies'}, {}) == original
    logs = list(tmp_path.glob('*_sow_review.json'))
    assert len(logs) == 2
    batches = json.loads(logs[0].read_text())['batches']
    assert sorted(k for b in batches for k in b['sections']) == sorted(original)


def test_malformed_output_is_logged_not_silently_reported_as_reviewed(tmp_path):
    reviewer = SOWReviewerAgent(SimpleNamespace(SOW_REVIEW_LOG_DIR=tmp_path), lambda p: '{broken')
    assert reviewer.review({'objective': 'Build.'}, {'objective': 'project_overview'}, {}) == {'objective': 'Build.'}
    batch = json.loads(next(tmp_path.glob('*.json')).read_text())['batches'][0]
    assert batch['status'] == 'failed'
    assert batch['raw_response'] == '{broken'
    assert 'JSONDecodeError' in batch['error']


def test_log_write_failure_does_not_lose_valid_correction(tmp_path):
    target = tmp_path / 'not_a_directory'
    target.touch()
    reviewer = SOWReviewerAgent(SimpleNamespace(SOW_REVIEW_LOG_DIR=target), lambda p:
        '{"corrections":[{"section":"duties","after":"- Review the design."}]}')
    assert reviewer.review({'duties': 'Long duties.'}, {'duties': 'customer_responsibilities'}, {})['duties'] == '- Review the design.'
