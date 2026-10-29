import json
from pathlib import Path
from types import SimpleNamespace

from app.agents.poc_writer_agent import POCWriterAgent
from app.agents.sow_reviewer_agent import SOWReviewerAgent
from app.core.sow_quality import remove_missing_information_disclaimers, remove_client_facing_meta_language
from app.core.sow_section_preferences import SECTION_LABELS, section_category


def test_cleanup_preserves_clause_punctuation():
    sentence = '- Review the design; approval confirms the agreed scope.'
    assert remove_missing_information_disclaimers(sentence) == sentence
    assert remove_client_facing_meta_language(sentence) == sentence


def test_roles_rename_preserves_legacy_selection_and_removes_legend():
    assert SECTION_LABELS['raci_matrix'] == 'Roles and Responsibilities'
    assert section_category('Roles and Responsibilities') == section_category('RACI Matrix') == 'raci_matrix'
    agent = POCWriterAgent.__new__(POCWriterAgent)
    assert agent._section_key('Roles and Responsibilities', {}) == 'raci_matrix'
    body = '| Workstream | Shellkode | Client |\n|---|---|---|\n| Build | RA | CI |\n\nLegend:<br> R = Responsible'
    for title in ('RACI Matrix', 'Roles and Responsibilities'):
        assert 'Legend' not in agent._clean_content(body, title)
    for path in (Path(__file__).resolve().parents[1] / 'templates').glob('*template.md'):
        assert '## Roles and Responsibilities' in path.read_text(encoding='utf-8')


def test_parallel_reviewer_accepts_short_replacement_contract_and_checks_language():
    document = {'benefits':'Long paragraph.', 'scope_of_work':'### Build\n- Deliver the tool.', 'project_overview':'Tool.'}
    def call(prompt):
        assert 'complete grammatical sentences' in prompt
        assert 'no legend' in prompt
        # Only the ownership batch containing benefits may modify this key.
        editable = prompt.split('EDITABLE PURPOSES:\n')[1].split('\nBULLET REVIEW CHECKS')[0]
        return json.dumps({'corrections': [{'section':'benefits','after':'- Reduce manual handling.'}] if 'benefits' in json.loads(editable) else []})
    reviewed = SOWReviewerAgent(SimpleNamespace(), call).review(document,
        {'benefits':'business_benefits', 'scope_of_work':'scope_of_work', 'project_overview':'project_overview'}, {})
    assert reviewed['benefits'] == '- Reduce manual handling.'
    assert reviewed['scope_of_work'] == document['scope_of_work']
