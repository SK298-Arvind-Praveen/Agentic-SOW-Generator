"""Regressions for the Tata CLiQ v51 authored -> reviewed -> exported timeline."""
import json
from html import unescape
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document
from docx.oxml.ns import qn

from app.agents.poc_writer_agent import POCWriterAgent, TemplateSection
from app.core.sow_quality import normalize_requirements
from app.core.section_formats import finalize_gantt_markdown
from app.document.document_builder import DocumentBuilder, SectionBuilder


FIXTURE = json.loads((Path(__file__).parent / 'fixtures/tata_cliq_timeline.json').read_text(encoding='utf8'))

MIXED_GANTT = '''The eight-week implementation plan is indicative and subject to approval. Contract-term support follows go-live.

| S.No | Activity | W1 | W2 | W3 | W4 | W5 | W6 | W7 | W8 | Contract Term After Go-Live |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Solution design | ■ | ■ | | | | | | | |
| 2 | Systems integration | | ■ | ■ | ■ | | | | | |
| 3 | Business acceptance testing | | | | | | | ■ | | |
| 4 | Production deployment | | | | | | | | ■ | |
| 5 | Go-live support after deployment | | | | | | | | ◆ | |
| 6 | Ongoing support and continuous improvement | | | | | | | | | ◆ |
| 7 | Contract-exit transition and handover | | | | | | | | | ■ |

The client confirms production readiness before deployment.'''


@pytest.mark.parametrize('legacy_source', [False, True])
def test_mixed_gantt_exports_weekly_bars_and_contract_notes(tmp_path, legacy_source):
    from app.diagram.run_manifest import assert_content_acceptance, export_section_failures

    metadata = {'timeline_format': 'gantt'}
    key = 'timelines_deliverables'
    preview = finalize_gantt_markdown(MIXED_GANTT, {'planning_duration_weeks': 8})
    assert '| S.No | Activity | W1 | W2 | W3 | W4 | W5 | W6 | W7 | W8 |' in preview
    assert 'The client confirms production readiness before deployment.' in preview
    assert 'Contract-term support follows go-live.' in preview
    assert 'Ongoing support and continuous improvement' in preview
    assert 'Contract-exit transition and handover' in preview
    assert finalize_gantt_markdown(preview, {'planning_duration_weeks': 8}) == preview

    source = MIXED_GANTT if legacy_source else preview
    assert_content_acceptance({key: source}, [key], {'metadata': metadata})
    builder = DocumentBuilder(SimpleNamespace())
    builder.doc = Document()
    builder._configure_styles()
    builder.doc.add_heading('Project Timeline', 1)
    SectionBuilder(builder.doc, SimpleNamespace()).parse_content(source)
    path = tmp_path / 'mixed-timeline.docx'
    builder.doc.save(path)
    exported = Document(path)
    assert len(exported.tables) == 1
    table = exported.tables[0]
    assert [cell.text for cell in table.rows[0].cells] == ['S.No', 'Activity', 'W1', 'W2', 'W3', 'W4', 'W5', 'W6', 'W7', 'W8']
    assert [row.cells[1].text for row in table.rows[1:]] == [
        'Solution design', 'Systems integration', 'Business acceptance testing',
        'Production deployment', 'Go-live support after deployment',
    ]
    fill = qn('w:fill')
    shades = [[cell._tc.find('.//' + qn('w:shd')).get(fill) for cell in row.cells] for row in table.rows]
    assert shades[1][2:] == ['CCFFCC'] * 2 + ['FFFFFF'] * 6
    assert shades[4][2:] == ['FFFFFF'] * 7 + ['CCFFCC']
    assert shades[5][2:] == ['FFFFFF'] * 7 + ['4A86E8']
    assert any('Ongoing support and continuous improvement' in p.text and 'Contract Term After Go-Live' in p.text
               for p in exported.paragraphs)
    assert not export_section_failures(path, {key: source}, [key], metadata)

    for paragraph in exported.paragraphs:
        if 'Contract-exit transition and handover' in paragraph.text:
            paragraph.text = ''
    exported.save(path)
    assert export_section_failures(path, {key: source}, [key], metadata)


def test_notes_before_and_between_periods_preserve_milestones_and_support_duration():
    source = '''
| Notes | S.No | Activity | M1 | Outcome | M2 |
| --- | --- | --- | --- | --- | --- |
| Customer signs | 1 | Acceptance | ■ | Sign-off | |
| Cutover window | 2 | Production deployment | | Release | ■ |
| Subject to approval | 3 | Hypercare | ◆ | Handover | ◆ |
'''
    preview = finalize_gantt_markdown(source, {})
    assert '| S.No | Activity | M1 | M2 | M3 |' in preview
    assert '| 1 | Acceptance | ■ |  |  |' in preview
    assert '| 2 | Production deployment |  | ■ |  |' in preview
    assert '| 3 | Hypercare |  | ◆ | ◆ |' in preview
    assert 'Notes: Customer signs' in preview and 'Outcome: Sign-off' in preview
    assert 'Notes: Subject to approval' in preview and 'Outcome: Handover' in preview
    assert finalize_gantt_markdown(preview, {}) == preview


def test_explicit_support_period_is_preserved_without_separate_deployment_row():
    source = ('| S.No | Activity | W1 | W2 | Notes |\n| --- | --- | --- | --- | --- |\n'
              '| 1 | Build | ■ | | |\n'
              '| 2 | Go-live support and monitoring | | ◆ | Warranty starts in W2 |')
    preview = finalize_gantt_markdown(source, {})
    assert '| 2 | Go-live support and monitoring |  | ◆ |' in preview
    assert 'Warranty starts in W2' in preview


def test_escaped_pipes_in_activity_and_contract_note_survive_preview_and_word(tmp_path):
    from app.diagram.run_manifest import assert_content_acceptance, export_section_failures

    source = (r'| S.No | Activity | W1 | Contract Term After Go-Live |' '\n'
              r'| --- | --- | --- | --- |' '\n'
              r'| 1 | Configure X \| Y | ■ | Confirm X \| Y. |')
    key = 'timelines_deliverables'
    metadata = {'timeline_format': 'gantt'}
    preview = finalize_gantt_markdown(source, {})
    assert_content_acceptance({key: preview}, [key], {'metadata': metadata})
    assert 'Confirm X | Y.' in unescape(preview)

    builder = DocumentBuilder(SimpleNamespace())
    builder.doc = Document()
    builder._configure_styles()
    builder.doc.add_heading('Project Timeline', 1)
    SectionBuilder(builder.doc, SimpleNamespace()).parse_content(source)
    path = tmp_path / 'escaped-note.docx'
    builder.doc.save(path)
    table = builder.doc.tables[0]
    assert table.rows[1].cells[1].text == 'Configure X | Y'
    assert table.rows[1].cells[2]._tc.find('.//' + qn('w:shd')).get(qn('w:fill')) == 'CCFFCC'
    assert any('Confirm X | Y.' in p.text for p in builder.doc.paragraphs)
    assert not export_section_failures(path, {key: source}, [key], metadata)


@pytest.mark.parametrize('retry_allocated', [True, False])
@pytest.mark.parametrize('ragged', [False, True], ids=['complete-row', 'short-row'])
def test_blank_period_grid_uses_one_source_grounded_retry(monkeypatch, retry_allocated, ragged):
    from app.diagram.run_manifest import assert_content_acceptance

    blank = ('The client approves the deployment gate.\n\n'
             '| S.No | Activity | W1 | Contract Term After Go-Live |\n| --- | --- | --- | --- |\n'
             '| 1 | Deploy | | |\n| 2 | Five-business-day warranty | | ◆ |\n\n'
             'Monitoring remains active during warranty.')
    if ragged:
        blank = blank.replace('| 1 | Deploy | | |', '|1|Deploy||')
    metadata = {'timeline_format': 'gantt'}
    key = 'timelines_and_deliverables'
    with pytest.raises(AssertionError, match='allocation empty'):
        assert_content_acceptance({key: blank}, ['timelines_deliverables'], {'metadata': metadata})
    agent = POCWriterAgent.__new__(POCWriterAgent)
    agent.config = SimpleNamespace(SOW_SECTION_WORKERS=1)
    agent.template_type = 'POC'
    agent.sections = [TemplateSection('Project Timeline', '', {'type': 'TABLE', '_explicit': True}, 1)]
    prompts = []

    def generate(_section, requirements, _metadata, context, notes):
        prompts.append((requirements, context, notes))
        if len(prompts) == 2:
            mark = '■' if retry_allocated else ''
            return f'| S.No | Activity | W1 |\n| --- | --- | --- |\n| 1 | Deploy | {mark} |'
        return blank

    monkeypatch.setattr(agent, '_generate_section', generate)
    monkeypatch.setattr(agent, '_review_document_relevance', lambda *_args: set())
    output = agent.generate_poc(
        {'duration_weeks': 1, 'timeline': 'Production deploy is scheduled for W1.'}, metadata,
        selected_sow_sections=['timelines_deliverables'],
    )
    assert len(prompts) == 2 and prompts[0] == prompts[1]
    assert 'Five-business-day warranty' in output[key]
    assert 'Contract Term After Go-Live' in output[key]
    assert 'The client approves the deployment gate.' in output[key]
    assert 'Monitoring remains active during warranty.' in output[key]
    assert output[key].count('| S.No | Activity | W1 |') == int(retry_allocated)
    assert '- 2. Five-business-day warranty' in output[key]
    if retry_allocated:
        assert_content_acceptance(output, ['timelines_deliverables'], {'metadata': metadata})
    else:
        assert any('period allocation' in warning for warning in output['generation_quality_warnings'])
        with pytest.raises(AssertionError, match='allocation empty'):
            assert_content_acceptance(output, ['timelines_deliverables'], {'metadata': metadata})


def test_procurement_dates_do_not_make_an_estimated_build_duration_confirmed():
    requirements = normalize_requirements(FIXTURE['requirements'], mode='POC')
    assert requirements['duration_weeks'] is None
    assert requirements['planning_duration_weeks'] == 8
    assert requirements['timeline_is_assumption'] is True


def test_review_cannot_silently_erase_selected_indicative_gantt(monkeypatch, tmp_path):
    agent = POCWriterAgent.__new__(POCWriterAgent)
    agent.config = SimpleNamespace(SOW_SECTION_WORKERS=1)
    agent.template_type = 'POC'
    agent.sections = [TemplateSection('Project Timeline', '', {'type': 'TABLE', '_explicit': True}, 1)]
    monkeypatch.setattr(agent, '_generate_section', lambda *args: FIXTURE['authored'])

    def logged_review(output, *_args):
        output['timelines_and_deliverables'] = FIXTURE['reviewed']
        return set()

    monkeypatch.setattr(agent, '_review_document_relevance', logged_review)
    output = agent.generate_poc(
        FIXTURE['requirements'], {'timeline_format': 'gantt'},
        selected_sow_sections=['timelines_deliverables'],
    )
    preview = output['timelines_and_deliverables']
    assert '■' in preview, 'The selected Gantt must retain its indicative allocation after review'
    assert 'Indicative' in preview and '8-week' in preview
    assert 'subject to approval' in preview
    assert '| W1 | W2 | W3 | W4 | W5 | W6 | W7 | W8 |' in preview

    builder = DocumentBuilder(SimpleNamespace())
    builder.doc = Document()
    builder._configure_styles()
    SectionBuilder(builder.doc, SimpleNamespace()).parse_content(preview)
    path = tmp_path / 'timeline.docx'
    builder.doc.save(path)
    exported = Document(path)
    assert len(exported.tables) == 1
    chart = exported.tables[0]
    assert len(chart.columns) == 10
    fills = [[cell._tc.tcPr.find(qn('w:shd')).get(qn('w:fill')) for cell in row.cells]
             for row in chart.rows]
    assert fills[1][2:4] == ['CCFFCC', 'CCFFCC']
    hypercare = next(i for i, row in enumerate(chart.rows) if 'Hypercare' in row.cells[1].text)
    assert fills[hypercare][2:] == ['FFFFFF'] * 6 + ['4A86E8', '4A86E8']
    assert any('Indicative' in p.text and 'subject to approval' in p.text for p in exported.paragraphs)


def test_indicative_caption_does_not_bypass_support_sequencing():
    text = 'Indicative planning schedule.\n\n' + (
        '| S.No | Activity | W1 | W2 |\n| --- | --- | --- | --- |\n'
        '| 1 | Deployment to production | | ■ |\n'
        '| 2 | Hypercare | ◆ | |'
    )
    output = finalize_gantt_markdown(text, {'planning_duration_weeks': 2})
    assert '| 2 | Hypercare |  | ◆ |' in output
    assert output.count('Indicative') == 1
    assert finalize_gantt_markdown(output, {'planning_duration_weeks': 2}) == output


def test_missing_or_shorter_horizon_does_not_restore_an_unrelated_estimate():
    for requirements in ({}, {'planning_duration_weeks': 12}, {'duration_weeks': 8}):
        assert finalize_gantt_markdown(FIXTURE['reviewed'], requirements, FIXTURE['authored']) == FIXTURE['reviewed']


def test_restoring_authored_allocation_retains_reviewed_prose():
    reviewed = FIXTURE['reviewed'] + '\n\nMonitoring remains active during warranty.'
    output = finalize_gantt_markdown(reviewed, {'planning_duration_weeks': 8}, FIXTURE['authored'])
    assert '■' in output and 'Timeframe' not in output
    assert 'Monitoring remains active during warranty.' in output


def test_writer_and_reviewer_receive_the_same_explicit_planning_horizon(monkeypatch, tmp_path):
    from app.agents.sow_reviewer_agent import SOWReviewerAgent
    from app.core.section_formats import presentation_contract

    requirements = {'planning_duration_weeks': 13, 'duration_weeks': None}
    metadata = {'timeline_format': 'gantt'}
    agent = POCWriterAgent.__new__(POCWriterAgent)
    agent.config = SimpleNamespace()
    agent.template_type = 'POC'
    agent.global_template_contract = ''
    section = TemplateSection('Project Timeline', '', {'category_id': 'timelines_deliverables'}, 1)
    author_prompt = agent._build_individual_prompt(section, requirements, metadata, '')
    reviewer_prompts = []

    def review_call(prompt):
        reviewer_prompts.append(prompt)
        return '{"corrections": []}'

    reviewer = SOWReviewerAgent(SimpleNamespace(SOW_REVIEW_LOG_DIR=tmp_path), review_call)
    reviewer.review({'timelines_and_deliverables': FIXTURE['authored']},
                    {'timelines_and_deliverables': 'timelines_deliverables'},
                    {'requirements': requirements, 'metadata': metadata})
    contract = presentation_contract('timelines_deliverables', metadata, requirements)
    assert '13-week planning horizon' in contract
    assert 'subject to approval' in contract
    assert contract in author_prompt
    assert contract in reviewer_prompts[0]


def test_planning_gantt_contract_does_not_override_selected_milestone_table():
    from app.core.section_formats import presentation_contract
    contract = presentation_contract('timelines_deliverables', {'timeline_format': 'table'},
                                     {'planning_duration_weeks': 8})
    assert 'milestone table' in contract
    assert 'Gantt' not in contract
