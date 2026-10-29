from types import SimpleNamespace

from app.agents.poc_writer_agent import POCWriterAgent, TemplateSection
from app.pricing.service import AwsPricingService
from app.pricing.renderer import render_aws_pricing_section


def test_comma_formatted_source_volume_is_retained_and_rendered():
    source = '~50,000 conversations per month across the two current bots'
    metrics = AwsPricingService._validated_volume_metrics({'volume_metrics': [{
        'metric': 'current_monthly_conversations', 'value': '50000', 'evidence_quote': source}]}, source)
    assert len(metrics) == 1
    assert '50000' in render_aws_pricing_section({'volume_metrics': metrics})
    assert AwsPricingService._validated_volume_metrics({'volume_metrics': [{
        'metric': 'current_monthly_conversations', 'value': '90000', 'evidence_quote': source}]}, source) == []


def test_valid_company_profile_does_not_enter_generic_bullet_rewrite():
    agent = POCWriterAgent.__new__(POCWriterAgent)
    agent.config = SimpleNamespace(FAST_MODEL_ID='haiku', WRITER_MODEL_ID='sonnet')
    agent._build_individual_prompt = lambda *a, **k: 'Company prompt'
    profile = 'Example operates an online retail business. It sells clothing and accessories.\n\nIts customers use its website and mobile application to place orders.'
    calls = []
    agent._call_bedrock = lambda *a, **k: calls.append(k) or profile
    section = TemplateSection('About {COMPANY_NAME}', '', {'type':'GENERATED', 'category_id':'about_client'}, 1)
    result = agent._generate_section(section, {}, {'company_name':'Example'}, '', [])
    assert result == profile
    assert len(calls) == 1
