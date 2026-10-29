import json
from types import SimpleNamespace

from app.agents.sow_reviewer_agent import SOWReviewerAgent, apply_corrections
from app.core.sow_quality import remove_client_facing_meta_language
from app.document.document_builder import DocumentBuilder
from app.pricing.renderer import _business_volume_rows, render_aws_pricing_section


def test_roles_title_resolves_saved_legacy_key():
    builder = DocumentBuilder.__new__(DocumentBuilder)
    table = '| Workstream | Shellkode | Client |\n|---|---|---|\n| Build | RA | CI |'
    assert builder._resolve_content('17. Roles and Responsibilities', {'raci_matrix': table}) == table
    assert builder._resolve_content('Roles and Responsibilities', {'raci_matrix': table}) == table


def test_invalid_raci_and_unknown_key_do_not_discard_valid_corrections():
    original = {'business_benefits': 'A long description.', 'raci_matrix': 'Existing table.'}
    payload = {'corrections': [
        {'section': 'about_client', 'after': 'Wrong key.'},
        {'section': 'business_benefits', 'after': '- Reduce repeat enquiries.'},
        {'section': 'raci_matrix', 'after': '| Work | Shellkode | Client |\n|---|---|---|\n| Build | RA | Provide access. |'},
    ]}
    result = SOWReviewerAgent(SimpleNamespace(), lambda p: json.dumps(payload)).review(
        original, {'business_benefits': 'business_benefits', 'raci_matrix': 'raci_matrix'}, {})
    assert result['business_benefits'] == '- Reduce repeat enquiries.'
    assert result['raci_matrix'] == original['raci_matrix']
    assert set(result) == set(original)


def test_bold_company_name_is_not_a_bullet():
    after = '**Acme** operates a shop.\n\nIts customers use its website.'
    assert apply_corrections({'about_company': 'Old profile.'}, {'corrections': [
        {'section': 'about_company', 'after': after}]}, {'about_company': 'about_client'}, {})['about_company'] == after


def test_removed_disclaimer_does_not_leave_dangling_semicolon():
    assert remove_client_facing_meta_language('- Connect the platforms; information was not provided.') == '- Connect the platforms.'
    assert remove_client_facing_meta_language('- Connect the platforms; the BRD lists the systems.') == '- Connect the platforms.'


def test_duplicate_patch_cannot_overwrite_first_valid_correction():
    payload = {'corrections': [
        {'section': 'duties', 'after': '- Review the design.'},
        {'section': 'duties', 'after': '- Approve everything.'}]}
    result = SOWReviewerAgent(SimpleNamespace(), lambda p: json.dumps(payload)).review(
        {'duties': 'Old duties.'}, {'duties': 'customer_responsibilities'}, {})
    assert result['duties'] == '- Review the design.'


def test_pricing_percentage_is_not_presented_as_call_count():
    rows = dict(_business_volume_rows([{'metric': 'Backend API calls', 'value': '60-70% of conversations'}]))
    assert rows['Interactions requiring backend API calls'] == '60-70% of conversations'
    result = render_aws_pricing_section({'region': 'ap-south-1'})
    assert '| AWS infrastructure |  |  |' in result
    assert 'homepage' not in result
    assert 'remain editable' not in result
