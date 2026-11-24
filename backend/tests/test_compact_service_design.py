from copy import deepcopy
import json
import pytest

from app.core.solution_definition import prepare_requirement_ledger, expand_design_references
from app.diagram.reliability import structured_retry


def test_ledger_deduplicates_overlap_but_preserves_distinct_conditions():
    rows = [dict(requirement='Upload PDFs', source_quote='Upload PDFs securely.', disposition='included'),
            dict(requirement='Upload PDFs', source_quote='Upload PDFs securely.', disposition='included'),
            dict(requirement='Future export', source_quote='Export is release two.', disposition='deferred', decision_reason='Release two')]
    ledger = prepare_requirement_ledger(rows, 'Upload PDFs securely. Export is release two.')
    assert len(ledger) == 2
    assert [r['id'] for r in ledger] == ['r1', 'r2']
    assert all(r['source_verified'] for r in ledger)


def test_compact_references_expand_without_mutating_source_or_losing_requirements():
    ledger = prepare_requirement_ledger([dict(requirement='Upload', source_quote='Upload PDFs securely.', disposition='included')], 'Upload PDFs securely.')
    raw = {'capabilities': [{'id': 'c1', 'requirement_ids': ['r1']}]}
    original = deepcopy(raw)
    expanded = expand_design_references(raw, ledger)
    assert expanded['capabilities'][0]['evidence_quote'] == ledger[0]['source_quote']
    assert expanded['requirement_ledger'][0]['capability_ids'] == ['c1']
    assert raw == original
    with pytest.raises(ValueError, match='Unknown requirement'):
        expand_design_references({'capabilities':[{'id':'c1', 'requirement_ids':['r9']}]}, ledger)
    with pytest.raises(ValueError, match='coverage'):
        expand_design_references({'capabilities':[]}, ledger)


def test_targeted_retry_keeps_valid_rows_and_revalidates_merged_result():
    prompts = []
    replies = iter([{'services':[{'id':'a','name':'valid'}, {'id':'b','name':'bad'}], 'summary':'keep'},
                    {'patch':{'services':[{'id':'b','name':'fixed'}]}}])
    def call(prompt):
        prompts.append(prompt)
        return json.dumps(next(replies))
    def validate(value):
        assert value['summary'] == 'keep'
        if value['services'][1]['name'] != 'fixed':
            raise ValueError('service b invalid')
        return value
    result = structured_retry(call, 'design', validate, attempts=2, targeted_repair=True)
    assert result['services'] == [{'id':'a','name':'valid'}, {'id':'b','name':'fixed'}]
    assert 'patch' in prompts[1]


def test_bad_patch_uses_complete_correction_with_remaining_attempt():
    replies = iter([{'summary':'bad'}, {'patch':{'invented':True}}, {'summary':'fixed'}])
    prompts = []
    def call(prompt):
        prompts.append(prompt)
        return json.dumps(next(replies))
    def validate(value):
        if value.get('summary') != 'fixed': raise ValueError('bad summary')
        return value
    assert structured_retry(call, 'design', validate, targeted_repair=True)['summary'] == 'fixed'
    assert 'COMPLETE corrected' in prompts[2]


def test_compact_live_contract_and_checkpoint_invalidation(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from app.diagram import service_design as module
    source = 'Upload PDF documents securely.'
    ledger = prepare_requirement_ledger([dict(requirement='Upload PDFs', source_quote=source,
        disposition='included')], source)
    value = {'summary':'Store PDFs', 'capabilities':[{'id':'c1', 'requirement_ids':['r1'],
        'service_ids':['s1'], 'implementation':'Store files'}],
        'services':[{'id':'s1','name':'Amazon S3','purpose':'Files','rationale':'Object storage','status':'proposed'}],
        'workflows':[{'steps':['Upload files'], 'failure_handling':'Retry failed uploads'}]}
    llm = Mock(config=SimpleNamespace(DIAGRAM_MODEL_ID='model-a'))
    llm.generate.return_value = SimpleNamespace(text=json.dumps(value))
    monkeypatch.setattr(module, 'run_id', lambda: 'compact-test-run')
    module._validated_designs.clear_run('compact-test-run')
    req = {'requirement_ledger':ledger, '_requirement_ledger_complete':True}
    first = module.ensure_service_design(llm, req, {}, source)
    assert first['status'] == 'ready', first
    assert first['services'][0]['capability_ids'] == ['c1']
    assert 'Reuse REQUIREMENTS.requirement_ledger' in llm.generate.call_args.args[0]
    assert 'Add requirement_ledger:' not in llm.generate.call_args.args[0]
    # Token-counter/stage-cache resets do not discard this checkpoint.
    from app.core.generation_efficiency import clear
    clear('compact-test-run')
    assert module.ensure_service_design(llm, req, {}, source) == first
    assert llm.generate.call_count == 1
    module.ensure_service_design(llm, req, {}, source + ' Retain files.')
    assert llm.generate.call_count == 2
    llm.config.DIAGRAM_MODEL_ID = 'model-b'
    module.ensure_service_design(llm, req, {}, source)
    assert llm.generate.call_count == 3


def test_missing_field_can_be_repaired_without_repeating_valid_fields():
    replies = iter([{'summary':'keep'}, {'patch':{'workflows':['upload']}}])
    def validate(value):
        if not value.get('workflows'): raise ValueError('Missing workflows')
        return value
    result = structured_retry(lambda p: json.dumps(next(replies)), 'design', validate,
                              attempts=2, targeted_repair=True, repair_fields=('workflows',))
    assert result == {'summary':'keep','workflows':['upload']}


def test_architect_can_add_only_source_grounded_omissions():
    source = 'Upload PDF documents. Retain logs for 30 days.'
    ledger = prepare_requirement_ledger([dict(requirement='Upload', source_quote='Upload PDF documents',
        disposition='included')], source)
    value = {'capabilities':[{'id':'c1','requirement_ids':['r1','new1']}],
        'delivery_baseline':{'technical_constraints':[{'requirement_ids':['new1']}]},
        'requirement_additions':[{'id':'new1','requirement':'Retain logs',
            'source_quote':'Retain logs for 30 days', 'disposition':'included'}]}
    result = expand_design_references(value, ledger, source)
    assert result['capabilities'][0]['requirement_ids'] == ['r1','r2']
    assert len(result['requirement_ledger']) == 2
    assert result['requirement_ledger'][1]['source_verified']
    assert result['delivery_baseline']['technical_constraints'][0]['requirement_ids'] == ['r2']
    value['requirement_additions'][0]['source_quote'] = 'Keep everything forever'
    with pytest.raises(ValueError, match='verified source'):
        expand_design_references(value, ledger, source)


@pytest.mark.parametrize('value', [None, [], {'capabilities':[None]}, {'capabilities':'invalid'}])
def test_malformed_compact_output_is_retryable(value):
    ledger = prepare_requirement_ledger([dict(requirement='Upload', source_quote='Upload PDF documents',
        disposition='included')], 'Upload PDF documents')
    with pytest.raises(ValueError):
        expand_design_references(value, ledger)


def test_recovered_analysis_cannot_activate_compact_mode():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from app.agents.objective_agent import ObjectiveAgent
    agent = ObjectiveAgent.__new__(ObjectiveAgent)
    agent.config = SimpleNamespace()
    row = {'requirement':'Upload', 'source_quote':'Upload PDF documents', 'disposition':'included'}
    agent.llm = Mock()
    raw = json.dumps({'requirement_ledger':[row]})
    agent.llm.generate.return_value = SimpleNamespace(text=raw)
    assert agent._analyze_chunk('Upload PDF documents', '', 1, 1)['_requirement_ledger_complete']
    agent.llm.generate.return_value = SimpleNamespace(text=raw[:-1])
    assert not agent._analyze_chunk('Upload PDF documents', '', 1, 1)['_requirement_ledger_complete']


def test_materialized_facts_keep_thresholds_and_do_not_promote_future_scope():
    from app.core.solution_definition import materialize_requirement_facts
    source = 'Retain logs for 30 days. Add publishing in release two.'
    ledger = prepare_requirement_ledger([
        dict(requirement='Retention', source_quote='Retain logs for 30 days', disposition='included', category='security'),
        dict(requirement='Publish', source_quote='Add publishing in release two', disposition='deferred', decision_reason='Release two')], source)
    result = materialize_requirement_facts({'requirement_ledger':ledger})
    assert result['security_requirements'] == ['Retain logs for 30 days']
    assert not result.get('functional_requirements')
    assert materialize_requirement_facts(result) == result


def test_cache_fingerprint_distinguishes_analysis_completeness():
    from app.diagram.service_design import fingerprint
    req = {'requirement_ledger':[{'id':'r1','source_quote':'Upload PDF documents'}]}
    assert fingerprint(req, 'Upload PDF documents') != fingerprint(
        {**req, '_requirement_ledger_complete':True}, 'Upload PDF documents')
