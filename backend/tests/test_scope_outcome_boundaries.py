from types import SimpleNamespace
from app.agents.scope_architect_agent import ScopeArchitectAgent
from app.agents.poc_writer_agent import POCWriterAgent
from app.core.scope_contract import DELIVERABLE_BOUNDARIES, CONCISE_SCOPE


def test_three_distinct_customer_outputs_are_not_collapsed():
    plan = {'deliverables': [
        {'name': name, 'separation_basis': 'Distinct customer output with its own usable result',
         'modules': [{'name': 'Implementation'}]}
        for name in ['Knowledge base', 'Claims chatbot', 'Automated ticketing system']]}
    assert ScopeArchitectAgent._deliverable_fragmentation_issues(plan) == []


def test_migration_lifecycle_is_not_six_deliverables():
    plan = {'deliverables': [
        {'name': name, 'separation_basis': 'Implementation workstream',
         'modules': [{'name': 'Work'}]}
        for name in ['Discovery', 'Cloud setup', 'Data migration', 'Reconciliation', 'Testing', 'Handover']]}
    assert ScopeArchitectAgent._deliverable_fragmentation_issues(plan)


def test_scope_planning_and_authoring_receive_shared_rule():
    prompts = []
    agent = ScopeArchitectAgent(SimpleNamespace(), call_fn=lambda p, **kw: prompts.append(p) or '{}')
    agent._call('Classify', 'Scope Boundary Classification')
    agent._call('Review', 'Scope Boundary Audit')
    assert all(DELIVERABLE_BOUNDARIES in p for p in prompts)
    writer = POCWriterAgent.__new__(POCWriterAgent)
    writer.llm = SimpleNamespace(generate=lambda p, **kw: prompts.append(p) or SimpleNamespace(text='body'))
    writer._call_bedrock('Write', call_name='Scope Deliverable 1')
    assert DELIVERABLE_BOUNDARIES in prompts[-1] and CONCISE_SCOPE in prompts[-1]
