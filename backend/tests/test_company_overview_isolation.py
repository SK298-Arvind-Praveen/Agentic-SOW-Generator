from types import SimpleNamespace

import pytest

from app.agents.company_research_agent import CompanyResearchAgent
from app.agents.poc_writer_agent import POCWriterAgent, TemplateSection
from app.agents.sow_reviewer_agent import apply_corrections


PROFILE = ('Example Limited operates an online retail business serving customers through digital shopping channels. '
           'Its product range includes clothing, footwear and accessories offered across a variety of brands and categories. '
           'Customers browse and purchase these products through the company website and mobile application, supported by its retail operations and customer service teams.')
PROJECT = ('Every vehicle passes through 40 fitting stations. '
           'Station 27 uses pink slips and a scribe. '
           'The proposed solution captures defects by voice and sends them to SAP.')


def test_company_profile_accepts_one_company_only_paragraph():
    assert CompanyResearchAgent._company_profile_issues(PROFILE) == []


def test_company_profile_rejects_shop_floor_workflow_without_project_label():
    assert CompanyResearchAgent._company_profile_issues(
        'Bajaj Motor operates a vehicle assembly line. '
        'Inspection happens at Station 27. '
        'Inspectors record defects on pink and white slips.')


def test_research_does_not_turn_brd_into_company_facts(monkeypatch):
    monkeypatch.setattr('app.agents.company_web_research.research_sources', lambda *args: {'sources': [], 'status': 'unavailable'})
    agent = CompanyResearchAgent.__new__(CompanyResearchAgent)
    agent.config = SimpleNamespace()
    agent.llm = SimpleNamespace(generate=lambda *a, **k: SimpleNamespace(text=PROJECT))
    assert agent._research_company('Bajaj Motor', PROJECT) == ''


def test_research_isolates_company_facts_from_project_context(monkeypatch):
    monkeypatch.setattr('app.agents.company_web_research.research_sources', lambda *args: {'sources': [{'text': PROFILE}], 'status': 'verified_identity'})
    agent = CompanyResearchAgent.__new__(CompanyResearchAgent)
    agent.config = SimpleNamespace()
    prompts = []
    def generate(prompt, **kwargs):
        prompts.append(prompt)
        return SimpleNamespace(text=PROFILE)
    agent.llm = SimpleNamespace(generate=generate)
    assert agent._research_company('Example Limited', PROFILE + '\n' + PROJECT) == PROFILE
    assert 'pink slips' not in prompts[0]
    assert 'Station 27' not in prompts[0]


def test_writer_preserves_company_research_without_project_rewriting():
    agent = POCWriterAgent.__new__(POCWriterAgent)
    agent.config = SimpleNamespace()
    agent.template_type = 'POC'
    agent.global_template_contract = ''
    def unexpected_project_rewrite(*args, **kwargs):
        pytest.fail('Company research must not be rewritten with project context')
    agent._call_bedrock = unexpected_project_rewrite
    section = TemplateSection('About {COMPANY_NAME}', '', {'type': 'GENERATED', 'category_id': 'about_client'}, 1)
    result = agent._generate_section(section, {'requirements': [PROJECT]},
                                    {'company_name': 'Example Limited', 'company_description': PROFILE},
                                    PROJECT, [PROJECT])
    assert result == PROFILE


def test_fallback_does_not_reuse_contaminated_description():
    assert POCWriterAgent._about_company_fallback({
        'company_name': 'Bajaj Motor', 'company_description': PROJECT,
    }) == ''


def test_project_reviewer_cannot_replace_verified_company_profile():
    with pytest.raises(ValueError, match='company research'):
        apply_corrections({'about': PROFILE}, {'corrections': [
            {'section': 'about', 'after': PROJECT},
        ]}, {'about': 'about_client'}, {'requirements': PROJECT})


def test_public_lookup_rejects_similar_bajaj_identity(monkeypatch):
    from app.agents import company_sources
    monkeypatch.setattr(company_sources, '_request_json', lambda params: {'query': {'pages': [
        {'title': 'Bajaj Auto', 'extract': 'Bajaj Auto is an Indian automotive manufacturing company.'},
    ]}})
    result = company_sources.lookup_company_sources('Bajaj Motor')
    assert result['sources'] == []
    assert result['status'] == 'unavailable'


def test_public_lookup_records_source_for_exact_business_identity(monkeypatch):
    from app.agents import company_sources
    monkeypatch.setattr(company_sources, '_request_json', lambda params: {'query': {'pages': [
        {'title': 'Example', 'extract': PROFILE},
    ]}})
    result = company_sources.lookup_company_sources('Example Limited')
    assert result['status'] == 'verified_identity'
    assert result['sources'][0]['url'] == 'https://en.wikipedia.org/wiki/Example'


def test_public_lookup_prefers_company_article_over_incidental_parent_mention(monkeypatch):
    from app.agents import company_sources
    monkeypatch.setattr(company_sources, '_request_json', lambda params: {'query': {'pages': [
        {'title': 'Example Limited', 'extract': PROFILE},
        {'title': 'Parent Group', 'extract': 'Parent Group is a holding company. It owns Example Limited.'},
    ]}})
    result = company_sources.lookup_company_sources('Example Limited')
    assert len(result['sources']) == 1
    assert result['sources'][0]['title'] == 'Example Limited'


def test_verified_cache_handles_legal_suffix_without_aliasing_bajaj_auto(monkeypatch):
    from datetime import datetime, timezone
    from app.agents import company_sources
    monkeypatch.setattr(company_sources, 'datetime', SimpleNamespace(now=lambda tz: datetime(2026, 11, 19, tzinfo=timezone.utc)))
    assert company_sources._cached_sources('BAJAJ Motors')[0]['url'] == 'https://in.linkedin.com/company/bajaj-motors-limited'
    assert company_sources._cached_sources('Bajaj Auto') == []
    assert company_sources._cached_sources('Bajaj Motor') == []


def test_expired_company_cache_is_not_used_as_current_evidence(monkeypatch):
    from datetime import datetime, timezone
    from app.agents import company_sources
    monkeypatch.setattr(company_sources, 'datetime', SimpleNamespace(now=lambda tz: datetime(2030, 1, 1, tzinfo=timezone.utc)))
    assert company_sources._cached_sources('Bajaj Motors Ltd') == []


def test_unavailable_public_lookup_is_audited_without_company_fabrication(monkeypatch):
    from urllib.error import URLError
    from app.agents import company_sources
    def unavailable(params):
        raise URLError('offline')
    monkeypatch.setattr(company_sources, '_request_json', unavailable)
    result = company_sources.lookup_company_sources('Example Limited')
    assert result['sources'] == []
    assert result['status'] == 'unavailable'
    assert 'unavailable' in result['reason']


def test_source_request_uses_fixed_host_and_bounded_retry(monkeypatch):
    from urllib.error import URLError
    from urllib.parse import urlparse
    from app.agents import company_sources
    calls = []
    def offline(request, timeout):
        calls.append((request.full_url, timeout))
        raise URLError('offline')
    monkeypatch.setattr(company_sources, 'build_opener', lambda *args: SimpleNamespace(open=offline))
    with pytest.raises(URLError):
        company_sources._request_json({'gsrsearch': 'https://127.0.0.1/private'})
    assert len(calls) == 2
    assert all(urlparse(url).hostname == 'en.wikipedia.org' and timeout == 5 for url, timeout in calls)


@pytest.mark.parametrize('audit', [
    {},
    {'status': 'verified_identity', 'company_name': 'Other Company', 'sources': [{'text': PROFILE, 'url': 'https://example.com/about'}]},
    {'status': 'verified_identity', 'company_name': 'Example Limited', 'sources': []},
])
def test_research_node_does_not_reuse_unverified_extracted_profile(monkeypatch, audit):
    from datetime import datetime, timezone
    from app.core import nodes
    audit = dict(audit, checked_at=datetime.now(timezone.utc).isoformat())
    calls = []
    class Research:
        _company_profile_issues = staticmethod(CompanyResearchAgent._company_profile_issues)
        def __init__(self, config):
            self.company_source_audit = {'Example Limited': {'status': 'verified_identity', 'sources': []}}
        def research_multiple_companies(self, companies, source_context):
            calls.append(companies)
            return {'Example Limited': PROFILE, 'Shellkode': 'Vendor description.'}
    monkeypatch.setattr(nodes, 'CompanyResearchAgent', Research)
    monkeypatch.setattr(nodes, '_report_progress', lambda *args: None)
    metadata = {'company_name': 'Example Limited', 'author_org': 'Shellkode',
                'company_description': PROFILE, 'author_org_description': 'Vendor description.',
                'company_research_audit': audit}
    nodes.research_node({'metadata': metadata})
    assert calls == [['Shellkode', 'Example Limited']]


def test_research_node_reuses_source_verified_company_profile(monkeypatch):
    from datetime import datetime, timezone
    from app.core import nodes
    def unexpected_lookup(config):
        pytest.fail('Existing verified corporate research should be reused')
    unexpected_lookup._company_profile_issues = CompanyResearchAgent._company_profile_issues
    monkeypatch.setattr(nodes, 'CompanyResearchAgent', unexpected_lookup)
    monkeypatch.setattr(nodes, '_report_progress', lambda *args: None)
    metadata = {'company_name': 'Example Limited', 'author_org': 'Shellkode',
                'company_description': PROFILE, 'author_org_description': 'Vendor description.',
                'company_research_audit': {
                    'status': 'verified_identity', 'company_name': 'Example Limited',
                    'checked_at': datetime.now(timezone.utc).isoformat(),
                    'sources': [{'text': PROFILE, 'url': 'https://example.com/about'}],
                }}
    assert nodes.research_node({'metadata': metadata}) == {'current_step': 'research'}
