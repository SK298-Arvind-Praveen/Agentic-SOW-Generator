from types import SimpleNamespace
import pytest
from app.agents import company_web_research as web
from app.agents.poc_writer_agent import POCWriterAgent, TemplateSection


@pytest.fixture(autouse=True)
def no_network_extract(monkeypatch):
    monkeypatch.setattr(web, '_request_json', lambda params: {})


def test_search_expands_intro_for_multiple_candidates(monkeypatch):
    calls=[]
    monkeypatch.setattr(web, '_request_json', lambda params: calls.append(params) or {})
    web._wikipedia_candidates('Unilever Ltd')
    assert calls[0]['exintro'] == 1  # Multi-page extracts require intro mode.


@pytest.mark.parametrize('name,title',[('TVS Motors','TVS Motor Company'),('Infosys Ltd','Infosys'),('Apollo Hospital','Apollo Hospitals'),('Infosis','Infosys')])
def test_generic_name_variations(name,title,monkeypatch):
    monkeypatch.setattr(web,'_wikipedia_candidates',lambda query:[{'title':title,'extract':title+' is a multinational company.'}])
    monkeypatch.setattr(web,'_official_website',lambda page:'')
    result=web.research_sources(name)
    assert result['status']=='verified_identity'
    assert result['resolved_name']==title


def test_does_not_replace_unknown_subsidiary_with_group(monkeypatch):
    monkeypatch.setattr(web,'_wikipedia_candidates',lambda q:[{'title':'Bajaj Auto','extract':'Bajaj Auto is a manufacturer.'}])
    assert web.research_sources('Bajaj Motors Ltd')['sources']==[]


def test_network_failure_is_audited(monkeypatch):
    def fail(q): raise OSError('offline')
    monkeypatch.setattr(web,'_wikipedia_candidates',fail)
    result=web.research_sources('Unknown Company')
    assert result['status']=='unavailable' and not result['sources']
    assert len(result['attempts'])==2


def test_private_discovery_address_is_rejected():
    with pytest.raises(ValueError): web._public_url('http://127.0.0.1/private')


def test_no_match_keeps_paragraph_blank_and_warns_in_preview(monkeypatch):
    agent=POCWriterAgent.__new__(POCWriterAgent)
    agent.config=SimpleNamespace(SOW_SECTION_WORKERS=1)
    agent.template_type='POC'
    agent.global_template_contract=''
    agent.sections=[TemplateSection('About {COMPANY_NAME}','',{'type':'GENERATED','category_id':'about_client','_explicit':True},1)]
    monkeypatch.setattr(agent,'_review_document_relevance',lambda *args:set())
    result=agent.generate_poc({}, {'company_name':'Unknown Firm'},selected_sow_sections=['about_client'])
    assert any('About Client is blank' in w for w in result['generation_quality_warnings'])
    assert not any('client organisation' in str(v) for v in result.values())
    assert result.get('about_unknown_firm','')==''


def test_preview_warning_is_not_exported_as_a_document_section():
    from app.document.document_builder import DocumentBuilder
    assert 'generation_quality_warnings' in DocumentBuilder.RESERVED_KEYS
