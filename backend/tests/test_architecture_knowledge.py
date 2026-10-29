import copy
import pytest
from app.diagram import knowledge as kb


@pytest.mark.parametrize('card', kb.load_library()['patterns'], ids=lambda c: c['id'])
def test_every_pattern_retrievable(card):
    assert card['id'] in [c['id'] for c in kb.select_patterns({'features': card['triggers']})]


@pytest.mark.parametrize('requirements', [
    {}, {'aws_services': ['Amazon S3', 'CloudWatch']},
    {'features': ['No OCR required. No Amazon Connect.']},
    {'out_of_scope': ['Amazon Connect', 'Fargate', 'OCR']},
    {'future_scope': 'Knowledge base'}, {'source_documents': 'GraphQL'},
    {'_architecture_reference_context': 'GraphQL'},
    {'features': 'Demographic forecasting'},
])
def test_no_irrelevant_or_excluded_matches(requirements):
    assert not kb.select_patterns(requirements)


def test_tata_does_not_select_connect_from_existing_voice_or_exclusions():
    req = {'features': ['Knowledge base grounded answers', 'Fargate chatbot'],
           'out_of_scope': ['Amazon Connect migration'],
           'integrations': ['Existing Genesys; voice is excluded']}
    ids = [c['id'] for c in kb.select_patterns(req)]
    assert 'knowledge-retrieval' in ids and 'container-ingress' in ids
    assert 'contact-centre' not in ids


def test_limit_context_and_no_mutation():
    req = {'features': sum([c['triggers'] for c in kb.load_library()['patterns']], [])}
    before = copy.deepcopy(req)
    assert len(kb.select_patterns(req, limit=100)) == 3
    assert len(kb.reference_context(req)) <= 5000
    assert kb.reference_context(req, max_chars=10) == ''
    assert req == before
    context = kb.reference_context(req)
    assert 'authorize unrelated integrations' in context
    assert 'record those as design choices' in context
    assert 'not confirmed requirements' in context


def test_exclusion_overrides_positive_inventory():
    req = {'aws_services': ['Amazon Connect', 'Textract'],
           'out_of_scope': ['Amazon Connect migration'],
           'features': ['No Textract processing']}
    assert not kb.select_patterns(req)


@pytest.mark.parametrize('description,expected', [
    ('Serve grounded answers from a knowledge base to customers', 'knowledge-retrieval'),
    ('Run a containerized application behind an existing ingress', 'container-ingress'),
    ('Extract fields through OCR from uploaded claims', 'async-documents'),
    ('Push real-time notifications to connected browsers', 'realtime-bff'),
    ('Receive partner file transfer into storage', 'hybrid-files'),
])
def test_workload_queries(description, expected):
    assert expected in [x['id'] for x in kb.select_patterns({'features': [description]})]


def test_validation_rejects_duplicates_and_untrusted_sources():
    data = copy.deepcopy(kb.load_library())
    data['patterns'].append(data['patterns'][0])
    with pytest.raises(ValueError):
        kb.validate_library(data)
    data = copy.deepcopy(kb.load_library())
    data['patterns'][0]['source_url'] = 'https://docs.aws.amazon.com.evil.test/a'
    with pytest.raises(ValueError):
        kb.validate_library(data)


def test_corrupt_library_does_not_break_generation(monkeypatch):
    def fail():
        raise ValueError('bad library')
    monkeypatch.setattr(kb, 'load_library', fail)
    assert kb.reference_context({'features': ['OCR']}) == ''


def test_diagram_prompt_receives_advisory_outside_source():
    from app.diagram.service import DiagramService
    prompt = DiagramService._prompt(None, {'features': ['document extraction']}, {}, '', ['architecture_overview'], [])
    assert 'async-documents' in prompt
    assert 'ADVISORY, NOT SOURCE REQUIREMENTS' in prompt


def test_library_is_not_authoritative_facts():
    from app.core.authoring_context import authoring_facts
    assert '_architecture_reference_context' not in authoring_facts({'_architecture_reference_context': 'AWS'})


def test_writer_injects_references_only_into_architecture():
    from app.agents.poc_writer_agent import POCWriterAgent, TemplateSection
    agent = POCWriterAgent.__new__(POCWriterAgent)
    agent.template_type = 'POC'
    agent.global_template_contract = ''
    req = {'features': ['document extraction']}
    for name, expected in [('Solution Architecture', True), ('About Client', False), ('Scope of Work', False)]:
        section = TemplateSection(name, '', {'type': 'GENERATED'}, 0)
        prompt = agent._build_individual_prompt(section, req, {'company_name': 'Example'})
        assert ('ADVISORY, NOT SOURCE REQUIREMENTS' in prompt) == expected
