import json
from types import SimpleNamespace
from app.pricing.service import AwsPricingService
from app.pricing.renderer import render_aws_pricing_section


class LLM:
    def __init__(self,*responses): self.responses=list(responses);self.prompts=[]
    def generate(self,prompt,**kwargs):
        self.prompts.append(prompt)
        return SimpleNamespace(text=json.dumps(self.responses.pop(0)))


class Client:
    def __init__(self,fail_build=False): self.builds=[];self.fail_build=fail_build
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def call(self,tool,args):
        if tool=='get_service_fields':
            return {'fields':[{'id':'monthlyRequests','type':'number'}]}
        if tool=='build_estimate':
            self.builds.append(json.loads(args['services']))
            if self.fail_build and len(self.builds)==1:
                return {'status':'needs_field_grounding','services_to_inspect':['aWSLambda'],'issues':['Repair input']}
            return {'sharable_url':'https://calculator.aws/#/estimate?id=test123'}
        raise AssertionError(tool)


def mapped(value=10000):
    return {'config':{'monthlyRequests':value},'sizing':[{'input':'Monthly requests',
        'value':str(value)+' requests','status':'Approximated','reason':'Small POC traffic'}]}


def test_estimation_accepts_missing_source_numbers_and_retries_bad_field_once():
    llm=LLM({'config':{'inventedField':2},'sizing':[{'input':'Requests','value':'2'}]},mapped())
    service=AwsPricingService(SimpleNamespace(),llm=llm)
    plan={'service_name':'AWS Lambda','_estimate_missing':True,'usage_facts':{}}
    entry,missing=service._prepare_service(Client(),plan,'ap-south-1')
    assert not missing and entry['config']['monthlyRequests']==10000
    assert entry['config']['region']=='ap-south-1'
    assert len(llm.prompts)==2 and 'Unknown field' in llm.prompts[1]
    assert plan['_sizing_details'][0]['status']=='Approximated'


def test_estimation_stops_after_one_failed_correction():
    llm=LLM({},{});service=AwsPricingService(SimpleNamespace(),llm=llm)
    entry,missing=service._prepare_service(Client(),{'service_name':'AWS Lambda','_estimate_missing':True},'eu-west-2')
    assert entry is None and missing and len(llm.prompts)==2


def test_saved_link_with_partial_service_still_gets_repair_retry():
    class PartialClient(Client):
        def call(self,tool,args):
            result=super().call(tool,args)
            if tool=='build_estimate' and len(self.builds)==1:
                result['services']=[{'service':'aWSLambda:AWS Lambda','success':True,
                    'partial':True,'missing_required_fields':['monthlyRequests']}]
            return result
    client=PartialClient()
    service=AwsPricingService(SimpleNamespace(AWS_PRICING_ESTIMATE_MISSING=True),
        llm=LLM({'region':'ap-south-1','services':[]},mapped(),mapped(20000)),client_factory=lambda:client)
    service._read_cost=lambda url:{'monthlyCost':12.5}
    result=service.generate({'aws_services':['AWS Lambda']},{'pricing_region':'ap-south-1'},'AWS Lambda')
    assert len(client.builds)==2 and result['status']=='priced'


def test_compact_table_omits_service_inventory_and_minor_inputs():
    result={'status':'priced','monthly_cost':100,'region':'us-west-2',
        'monthly_by_service':{'AWS KMS':1,'Amazon EC2':99},
        'sizing_details':[{'service':'AWS KMS','input':'Key count','value':'10','status':'Approximated'}],
        'volume_metrics':[{'metric':'database size','value':'100 GB','status':'Source-backed'},
            {'metric':'request rate','value':'50 requests/second','status':'Approximated'},
            {'metric':'database tables','value':'30'},{'metric':'cost consumption ceiling','value':'USD 3000'}]}
    text=render_aws_pricing_section(result)
    assert '100 GB' in text and '50 requests/second (Approximated)' in text
    assert 'AWS KMS' not in text and 'Key count' not in text and 'database tables' not in text
    assert 'Service | Sizing input' not in text and 'USD 3000' not in text


def test_website_region_wins_and_calculator_build_gets_one_repair():
    plan={'region':'eu-west-2','services':[]}
    llm=LLM(plan,mapped(),mapped(20000));client=Client(fail_build=True)
    service=AwsPricingService(SimpleNamespace(AWS_PRICING_ESTIMATE_MISSING=True),llm=llm,client_factory=lambda:client)
    service._read_cost=lambda url:{'monthlyCost':12.5,'monthlyByService':{'AWS Lambda':12.5}}
    result=service.generate({'aws_services':['AWS Lambda']},{'pricing_region':'ap-south-1'},'AWS Lambda in eu-west-2')
    assert result['status']=='priced' and result['region']=='ap-south-1'
    assert not result['missing_inputs'] and 'region_warning' not in result
    assert len(client.builds)==2 and client.builds[1][0]['config']['monthlyRequests']==20000
    text=render_aws_pricing_section(result)
    assert text.startswith('AWS Pricing Calculator: [Open Link](https://calculator.aws/#/estimate?id=test123)\n\n|')
    assert 'Approximated' in text and '20000 requests' in text and '12.50' in text


def test_no_charge_controls_are_accounted_for_without_fake_paid_inputs():
    service=AwsPricingService(SimpleNamespace(),llm=LLM())
    plan={'service_name':'AWS IAM','_estimate_missing':True}
    entry,missing=service._prepare_service(Client(),plan,'eu-west-2')
    assert entry is None and not missing and plan['_no_direct_charge']


def test_inferred_values_cannot_masquerade_as_confirmed_source():
    value=mapped();value['sizing'][0]['status']='Source-backed'
    service=AwsPricingService(SimpleNamespace(),llm=LLM(value))
    plan={'service_name':'AWS Lambda','_estimate_missing':True,'_sizing_context':'A small serverless POC'}
    service._prepare_service(Client(),plan,'eu-west-2')
    assert plan['_sizing_details'][0]['status']=='Approximated'


def test_units_and_scalar_wrappers_follow_live_contract_without_changing_quantities():
    from app.pricing.sizing import normalize_config
    config=normalize_config({'requests':{'value':1200},'storage':'20|gb|month'},
        {'requests':{'type':'numericInput'},'storage':{'type':'fileSize','defaultUnit':'gb|month'}})
    assert config=={'requests':'1200','storage':{'value':'20','unit':'gb|month'}}


def test_calculator_envelopes_are_unwrapped_without_losing_fields():
    from app.pricing.sizing import normalize_config
    assert normalize_config({'serviceCode':'test','fields':{'requests':{'value':25}}},
        {'requests':{'type':'numericInput'}})=={'requests':'25'}
    import pytest
    with pytest.raises(ValueError,match='Conflicting'):
        normalize_config({'requests':1,'fields':{'requests':2}}, {})


def test_fargate_memory_variant_preserves_quantity():
    from app.pricing.sizing import normalize_config
    result=normalize_config({'vcpuPerTask':'0.5','smallMemory':'2'},
        {'memoryStandardFargateOnDemand':{'type':'fileSize','defaultUnit':'gb|NA'}})
    assert result=={'vcpuPerTask':'0.5','memoryStandardFargateOnDemand':{'value':'2','unit':'gb|NA'}}


def test_vpc_pricing_includes_selected_network_features_without_duplicate_cloudwatch():
    req={'service_design':{'status':'ready','services':[
        {'name':'Amazon VPC','status':'proposed','purpose':'NAT gateway per AZ and interface endpoints'},
        {'name':'Amazon CloudWatch Logs','status':'proposed'},
        {'name':'Amazon CloudWatch','status':'proposed'}]}}
    assert AwsPricingService._candidate_services(req,{})==['Amazon VPC','Amazon CloudWatch','AWS NAT Gateway','AWS PrivateLink']


def test_autoscaling_never_double_counts_ec2():
    service=AwsPricingService(SimpleNamespace(),llm=LLM())
    plan={'service_name':'Amazon EC2 Auto Scaling','_estimate_missing':True}
    entry,missing=service._prepare_service(Client(),plan,'eu-west-2')
    assert entry is None and not missing and plan['_no_direct_charge']


def test_invalid_negative_consumption_is_corrected_before_calculator_submission():
    service=AwsPricingService(SimpleNamespace(),llm=LLM(mapped(-10),mapped(100)))
    entry,missing=service._prepare_service(Client(),{'service_name':'AWS Lambda','_estimate_missing':True},'eu-west-2')
    assert not missing and entry['config']['monthlyRequests']==100


def test_json_response_tolerates_trailing_model_wrapper_without_losing_fields():
    from app.pricing.service import _json_object
    assert _json_object('```json\n{"config":{"a":1},"sizing":[]}}\n```')=={'config':{'a':1},'sizing':[]}


def test_word_export_keeps_saved_link_before_tables_and_renders_approximation():
    from docx import Document
    from docx.oxml.ns import qn
    from app.document.document_builder import DocumentBuilder,SectionBuilder
    result={'status':'priced','estimate_url':'https://calculator.aws/#/estimate?id=test123',
        'region':'ap-south-1','monthly_cost':12.5,'monthly_by_service':{'AWS Lambda':12.5},
        'sizing_details':[{'service':'AWS Lambda','input':'Invocations','value':'10000 per month','status':'Approximated','reason':'Small POC'}]}
    doc=Document();builder=DocumentBuilder(SimpleNamespace());builder.doc=doc;builder._configure_styles()
    SectionBuilder(doc,SimpleNamespace()).parse_content(render_aws_pricing_section(result))
    children=list(doc.element.body)
    paragraph=next(x for x in children if x.tag==qn('w:p'))
    assert 'Open Link' in ''.join(paragraph.itertext())
    assert children.index(paragraph)<next(i for i,x in enumerate(children) if x.tag==qn('w:tbl'))
    assert any(r.target_ref==result['estimate_url'] for r in doc.part.rels.values())
    assert all(cell.text.strip() for table in doc.tables for row in table.rows for cell in row.cells)
    assert any('Approximated' in cell.text for table in doc.tables for row in table.rows for cell in row.cells)
    sizing_widths=SectionBuilder._column_widths([['Service','Sizing input','Value','Basis'],
        ['Amazon CloudWatch','Logs','5 GB','Approximated: POC usage']])
    assert sizing_widths[0] >= sum(sizing_widths)*0.20
