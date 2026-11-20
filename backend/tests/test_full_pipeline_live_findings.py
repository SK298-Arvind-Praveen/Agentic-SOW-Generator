from app.diagram.service_design import unlisted_dependencies


def test_optional_existing_identity_service_does_not_force_new_provisioning():
    design = {'services': [{'name': 'AWS Identity and Access Management'}, {'name': 'AWS CloudTrail'}],
        'capabilities': [{'implementation': 'Vendor operator access uses scoped IAM roles with MFA, or an existing IAM Identity Center instance if TUL provides one, and is logged by CloudTrail.'}],
        'workflows': []}
    assert unlisted_dependencies(design) == []


def test_required_identity_service_still_needs_inventory_coverage():
    design = {'services': [{'name': 'AWS CloudTrail'}],
        'capabilities': [{'implementation': 'Deploy AWS IAM Identity Center for operator access.'}], 'workflows': []}
    assert 'AWS IAM Identity Center' in unlisted_dependencies(design)


def test_model_refusal_is_not_a_valid_company_profile():
    from app.agents.company_research_agent import CompanyResearchAgent
    refusal = ('I do not have reliable, widely-established factual information about this company. '
               'I cannot responsibly write the two paragraphs requested.\n\n'
               'I recommend consulting the official website for accurate information.')
    assert CompanyResearchAgent._company_profile_issues(refusal)
def test_selected_scheduler_is_not_misread_as_an_unlisted_event_bus():
    from app.diagram.service_design import unlisted_dependencies
    design={'services':[{'name':'Amazon EventBridge Scheduler'},{'name':'AWS Lambda'}],
        'capabilities':[{'implementation':'EventBridge Scheduler invokes Lambda for knowledge sync.'}],
        'workflows':[]}
    assert unlisted_dependencies(design)==[]
    design['capabilities'][0]['implementation']+=' An Amazon EventBridge event bus routes business events.'
    assert 'Amazon EventBridge' in unlisted_dependencies(design)

