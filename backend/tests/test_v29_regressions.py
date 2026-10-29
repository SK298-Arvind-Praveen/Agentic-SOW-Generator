import json
from types import SimpleNamespace

import pytest

from app.agents.poc_writer_agent import POCWriterAgent
from app.agents.sow_reviewer_agent import SOWReviewerAgent, apply_corrections
from app.core.sow_presentation import strip_text_diagrams
from app.document.document_builder import DocumentBuilder, SectionBuilder
from app.pricing.service import AwsPricingService


DRAWING = '```\n+------------------+\n| CUSTOMER CHANNELS |\n| App | Web |\n+---------|--------+\n          v\n+------------------+\n| PLATFORM         |\n+------------------+\n```\n\n- Connect **App** and **Web** to the platform.'
SCOPE = '| Deliverable | Outcome |\n|---|---|\n| Deliverable 1 - Build | Tool |\n\n### Deliverable 1 - Build\n\n#### Build\n\n- Connect the service.\n- Test the integration.'


def test_ascii_drawing_is_removed_before_cleaner_and_export():
    expected = '- Connect **App** and **Web** to the platform.'
    assert strip_text_diagrams(DRAWING) == expected
    writer = POCWriterAgent.__new__(POCWriterAgent)
    assert writer._clean_content(DRAWING, 'Solution Architecture') == expected
    builder = DocumentBuilder.__new__(DocumentBuilder)
    assert builder._resolve_section_content('7. Solution Architecture', {'architecture_diagram': DRAWING}, {}) == expected


def test_real_tables_and_ordinary_pipe_prose_are_not_lost():
    table = '| Service | Role |\n|---|---|\n| Gateway | Routing |'
    assert strip_text_diagrams(table) == table
    assert any(kind == 'table' for kind, _ in SectionBuilder._iter_blocks(table))
    assert not any(kind == 'table' for kind, _ in SectionBuilder._iter_blocks('| App | Web |\n| Platform |'))


@pytest.mark.parametrize('replacement', [
    SCOPE.replace('- Connect the service.\n- Test the integration.', 'Connect the service. Test the integration.'),
    SCOPE.replace('- Connect the service.\n- Test the integration.', '- Connect the service. Test the integration.'),
    SCOPE[SCOPE.index('###'):],
])
def test_reviewer_cannot_destroy_scope_layout(replacement):
    with pytest.raises(ValueError):
        apply_corrections({'scope': SCOPE}, {'corrections': [{'section': 'scope', 'after': replacement}]}, {'scope': 'scope_of_work'}, {})


def test_reviewer_accepts_consolidation_that_preserves_scope_layout():
    replacement = SCOPE.replace('- Connect the service.\n- Test the integration.', '- Connect and test the service.')
    assert apply_corrections({'scope': SCOPE}, {'corrections': [{'section': 'scope', 'after': replacement}]}, {'scope': 'scope_of_work'}, {})['scope'] == replacement


def test_scope_layout_rejection_is_audited(tmp_path):
    response = {'corrections': [{'section': 'scope', 'after': SCOPE.replace('- Connect the service.\n- Test the integration.', 'Connect and test the service.')}]}
    reviewer = SOWReviewerAgent(SimpleNamespace(SOW_REVIEW_LOG_DIR=tmp_path), lambda p: json.dumps(response))
    assert reviewer.review({'scope': SCOPE}, {'scope': 'scope_of_work'}, {})['scope'] == SCOPE
    audit = json.loads(next(tmp_path.glob('*.json')).read_text())
    assert audit['review_complete'] is False
    assert audit['rejected_sections'] == ['scope']


def test_catch_all_review_is_split_and_all_sections_have_one_owner(tmp_path):
    categories = dict((c, c) for c in ['scope_of_work', 'architecture_diagram', 'about_client', 'current_state',
        'project_overview', 'assumptions', 'out_of_scope', 'open_clarifications', 'business_benefits',
        'customer_responsibilities', 'customer_dependencies', 'raci_matrix', 'timelines_deliverables',
        'project_team_effort', 'success_criteria'])
    reviewer = SOWReviewerAgent(SimpleNamespace(SOW_REVIEW_LOG_DIR=tmp_path), lambda p: '{"corrections":[]}')
    reviewer.review({k: 'Content.' for k in categories}, categories, {})
    audit = json.loads(next(tmp_path.glob('*.json')).read_text())
    assert len(audit['batches']) == 6
    assert max(len(b['sections']) for b in audit['batches']) <= 4
    assert sorted(k for b in audit['batches'] for k in b['sections']) == sorted(categories)


def test_source_volume_shorthand_is_equivalent_not_missing():
    quote = '~50k conversations per month across the two current bots'
    plan = {'volume_metrics': [{'metric': 'monthly_conversations', 'value': '50000', 'evidence_quote': quote}]}
    assert AwsPricingService._validated_volume_metrics(plan, quote)[0]['value'] == '50000'
    plan['volume_metrics'][0]['value'] = '500000'
    assert AwsPricingService._validated_volume_metrics(plan, quote) == []
    plan['volume_metrics'][0].update(value='500000', evidence_quote='5 lakh conversations')
    assert AwsPricingService._validated_volume_metrics(plan, '5 lakh conversations')[0]['value'] == '500000'


def test_missing_review_is_not_reported_complete(tmp_path):
    def failed_call(prompt):
        raise TimeoutError('review deadline')
    reviewer = SOWReviewerAgent(SimpleNamespace(SOW_REVIEW_LOG_DIR=tmp_path), failed_call)
    assert reviewer.review({'arch': 'Existing prose.'}, {'arch': 'architecture_diagram'}, {}) == {'arch': 'Existing prose.'}
    assert reviewer.last_review_audit['review_complete'] is False
    assert reviewer.last_review_audit['incomplete_sections'] == ['arch']
