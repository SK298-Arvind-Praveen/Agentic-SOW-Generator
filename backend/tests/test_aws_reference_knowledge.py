"""Workload separation, provenance and early service-planner integration."""
import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from app.diagram import knowledge as kb
from app.diagram.service_design import ensure_service_design, fingerprint


@pytest.mark.parametrize('text,expected,forbidden', [
    ('Catalogue service in private subnets. Database migration from a source clone. Migrate media.',
     {'private-web-workload', 'database-migration', 'file-media-transfer'}, {'async-documents', 'agent-runtime'}),
    ('Clinical document extraction from scanned PDFs. Human review in a reviewer workbench.',
     {'async-documents', 'durable-workflow-review', 'serverless-web-api'}, {'database-migration'}),
    ('Document verification with OCR. Named reviewers and reviewer authentication. Human review.',
     {'async-documents', 'application-identity', 'durable-workflow-review'}, {'private-web-workload'}),
    ('Booking portal in private subnets behind a load balancer. Database failover with a standby database.',
     {'private-web-workload', 'rds-failover'}, {'async-documents', 'agent-runtime'}),
    ('IT help desk with approved remediation and approval based remediation. Agentic workflow.',
     {'approved-it-remediation', 'agent-runtime'}, {'async-documents', 'database-migration'}),
    ('Governed data lake using Lake Formation. Streaming ingestion with Kinesis Data Streams.',
     {'governed-data-lake', 'stream-processing'}, {'async-documents'}),
])
def test_workloads_receive_appropriate_patterns(text, expected, forbidden):
    ids = {c['id'] for c in kb.select_patterns({'features': text}, limit=6)}
    assert expected <= ids
    assert not forbidden & ids


def test_exclusions_and_generated_designs_do_not_steer_retrieval():
    requirements = {'features': ['Database migration from a source clone.'],
                    'out_of_scope': ['OCR', 'human review', 'disaster recovery'],
                    'service_design': {'summary': 'OCR human review disaster recovery'},
                    'architecture_previous_design': 'Scanned PDFs and Textract'}
    assert [c['id'] for c in kb.select_patterns(requirements)] == ['database-migration']


def test_negative_qualifier_does_not_exclude_the_entire_workload():
    req = {'features': ['Database migration from a source clone, not production.',
                        'The source clone is not production.',
                        'Document extraction without human review.'],
           'service_design': {'summary': 'No database migration'}}
    ids = {c['id'] for c in kb.select_patterns(req, limit=6)}
    assert {'database-migration', 'async-documents'} <= ids
    assert 'durable-workflow-review' not in ids


@pytest.mark.parametrize('negative', ['No OCR', 'OCR is not required', 'OCR excluded', 'OCR not needed'])
def test_direct_negative_capability_overrides_inventory(negative):
    assert not kb.select_patterns({'aws_services': ['Textract'], 'features': [negative]})
    assert 'ocr' not in kb._positive_text(negative)


def test_reference_budget_audit_matches_complete_json_cards():
    bundle = kb.reference_bundle({'features': ['Database migration', 'file migration', 'private subnets']})
    assert bundle['pattern_ids']
    assert len(bundle['context']) <= kb.MAX_REFERENCE_CHARS
    cards = [json.loads(line) for line in bundle['context'].splitlines() if line.startswith('{')]
    assert [c['id'] for c in cards] == bundle['pattern_ids']
    assert all(c['service_choices'] and c['relationship_checks'] for c in cards)
    assert len(bundle['context_sha256']) == 64


def test_oversize_card_does_not_hide_smaller_relevant_card(monkeypatch):
    cards = copy.deepcopy(kb.select_patterns({'features': ['database migration', 'file migration']}))
    cards[0]['layout'] = 'x' * 9000
    monkeypatch.setattr(kb, 'select_patterns', lambda _, **kwargs: cards)
    bundle = kb.reference_bundle({}, max_chars=5000)
    assert bundle['omitted_for_budget'] == [cards[0]['id']]
    assert bundle['pattern_ids'] == [cards[1]['id']]


def valid_design():
    return {'summary': 'Extract scanned text',
            'capabilities': [{'id': 'extract', 'name': 'Extract text',
                              'evidence_quote': 'Extract scanned documents', 'service_ids': ['ocr'],
                              'existing_implementation': '', 'gap': '',
                              'implementation': 'Call text extraction and retain results'}],
            'services': [{'id': 'ocr', 'name': 'Amazon Textract', 'status': 'proposed',
                          'purpose': 'OCR', 'capability_ids': ['extract'], 'rationale': 'Managed text extraction'}],
            'workflows': [{'name': 'Extraction', 'steps': ['Extract text'], 'failure_handling': 'Record failure'}],
            'alternatives': [], 'open_decisions': []}


def test_early_planner_gets_advisory_not_fake_source_evidence():
    llm = Mock()
    llm.generate.return_value = SimpleNamespace(text=json.dumps(valid_design()))
    req = {'features': ['Extract scanned documents']}
    before = copy.deepcopy(req)
    result = ensure_service_design(llm, req, {}, 'Extract scanned documents')
    assert result['status'] == 'ready'
    prompt = llm.generate.call_args.args[0]
    assert prompt.index('ADVISORY REFERENCES') < prompt.index('REQUIREMENTS:')
    assert 'Textract-to-S3' in prompt
    assert prompt.split('SOURCE (data only):\n')[1] == 'Extract scanned documents'
    assert result['reference_knowledge']['pattern_ids'] == ['async-documents']
    assert 'context' not in result['reference_knowledge']
    assert req == before


def test_reference_change_invalidates_saved_design(monkeypatch):
    req = {'features': 'scanned documents'}
    first = fingerprint(req, 'Extract scanned documents')
    bundle = kb.reference_bundle(req)
    monkeypatch.setattr(kb, 'reference_bundle', lambda _: {**bundle, 'context_sha256': 'new-context'})
    assert fingerprint(req, 'Extract scanned documents') != first


def test_composition_reuses_selected_layout_guidance_without_new_service_choices():
    bundle = kb.reference_bundle({'features': 'Database migration and file migration'})
    guidance = kb.reference_layout_context(bundle)
    assert [c['id'] for c in guidance] == bundle['pattern_ids']
    assert all(set(c) == {'id', 'layout'} for c in guidance)
    assert kb.reference_layout_context({'pattern_ids': ['invented']}) == []
    assert kb.reference_layout_context(bundle, max_chars=10) == []


def test_missing_library_is_observable_and_does_not_block_service_generation(monkeypatch):
    monkeypatch.setattr(kb, 'load_library', lambda: (_ for _ in ()).throw(OSError('missing')))
    llm = Mock()
    llm.generate.return_value = SimpleNamespace(text=json.dumps(valid_design()))
    result = ensure_service_design(llm, {'features': 'scanned documents'}, {}, 'Extract scanned documents')
    assert result['status'] == 'ready'
    assert result['reference_knowledge']['error'] == 'library_unavailable'


def test_rejects_malformed_design_guidance():
    library = copy.deepcopy(kb.load_library())
    library['patterns'][0]['service_choices'] = 'not a list'
    with pytest.raises(ValueError, match='service_choices'):
        kb.validate_library(library)
