import copy
import json
from types import SimpleNamespace

import pytest
from docx import Document
from docx.oxml.ns import qn

from app.diagram.architecture_text import (
    flow_order, missing_services, render_table, service_nodes, synchronize, validate_rows, write,
)


def asset():
    return {'spec':{'nodes':[
        {'id':'ocr','label':'Amazon Textract','scope':'regional'},
        {'id':'iam','label':'AWS Identity and Access Management','scope':'global','placement_role':'security'},
        {'id':'s3','label':'Amazon S3','scope':'regional','subtitle':'Uploaded documents'},
        {'id':'user','label':'Reviewer','scope':'external'}],
        'edges':[{'source':'s3','target':'ocr','label':'Read document'}]}}


def rows(spec=None):
    roles = {'s3':'Stores uploaded documents for Textract extraction',
             'ocr':'Extracts fields for human review', 'iam':'Controls workflow access to AWS APIs'}
    return [{'node_id':k,'role':roles.get(k,'Processes project requests')} for k in flow_order(spec or asset()['spec'])]


def model(responses):
    calls = []
    drafts = iter(responses)
    def generate(prompt, **kw):
        calls.append(prompt)
        value = next(drafts)
        return SimpleNamespace(text=value if isinstance(value,str) else json.dumps(value))
    return SimpleNamespace(generate=generate), calls


def test_generic_flow_cannot_pass_as_aws_architecture():
    assert len(missing_services('A generic pipeline',asset()['spec'])) == 3
    assert not missing_services('S3 stores documents for Textract with IAM permissions',asset()['spec'])
    assert 'Amazon S3' in missing_services('S3Backup',asset()['spec'])


def test_missing_components_trigger_focused_rewrite():
    llm,calls = model([{'rows':rows()[:-1]}, {'rows':rows()}])
    text,audit = write(llm,asset())
    assert len(calls)==2 and "missing=['iam']" in calls[1]
    assert audit['status']=='aligned' and audit['row_count']==3 and audit['attempts']==2
    assert text.splitlines()[2].startswith('| Amazon S3 |')
    assert 'bullet' not in text


@pytest.mark.parametrize('failure', ['duplicate','unknown','order','long','empty','multiline','iam','gate','wrong_type'])
def test_invalid_rows_are_retried(failure):
    draft = rows()
    if failure == 'duplicate': draft.append(draft[0])
    elif failure == 'unknown': draft[0]['node_id']='invented'
    elif failure == 'order': draft.reverse()
    elif failure == 'long': draft[0]['role']='word '*25
    elif failure == 'empty': draft[0]['role']=''
    elif failure == 'multiline': draft[0]['role']='Two lines\nhere'
    elif failure == 'iam': draft[2]['role']='Permissions S3 and Textract use to call one another'
    elif failure == 'gate': draft[1]['role']='Reviewer resolves all warnings'
    elif failure == 'wrong_type': draft[0]['node_id']=[]
    llm,calls=model([{'rows':draft},{'rows':rows()}])
    text,audit=write(llm,asset())
    assert len(calls)==2 and audit['status']=='aligned'
    assert not missing_services(text,asset()['spec'])


def test_synchronization_changes_only_selected_architecture_and_preserves_graph():
    content={'architecture_diagram':'Old bullets','scope_of_work':'Preserve','aws_pricing':'Price'}
    assets=[asset()]
    original=copy.deepcopy(assets[0]['spec'])
    llm,_=model([{'rows':rows()}])
    synchronize(llm,content,assets)
    assert content['scope_of_work']=='Preserve' and content['aws_pricing']=='Price'
    assert assets[0]['spec']==original
    assert assets[0]['text_alignment']['status']=='aligned'
    assert content['architecture_diagram'].startswith('| Service name | Role in the project |')
    excluded={'scope_of_work':'Only scope'}
    synchronize(None,excluded,assets)
    assert excluded=={'scope_of_work':'Only scope'}


def test_failed_repair_keeps_complete_table_and_honest_warning():
    content={'architecture_diagram':'Old incomplete bullets'}
    assets=[asset()]
    llm,calls=model(['bad JSON']*3)
    synchronize(llm,content,assets)
    assert len(calls)==3 and assets[0]['status']=='review_required'
    assert assets[0]['text_alignment']['status']=='needs_review'
    assert assets[0]['text_alignment']['row_count']==3
    assert assets[0]['validation_warnings']
    assert not missing_services(content['architecture_diagram'],assets[0]['spec'])
    assert 'Project role requires review' in content['architecture_diagram']


def test_cycles_branches_disconnected_nodes_and_shared_controls_have_stable_order():
    spec={'nodes':[{'id':k,'label':k,'scope':'regional'} for k in ['sink','b','start','a','orphan','kms']],
          'edges':[{'source':a,'target':b} for a,b in [('start','a'),('start','b'),('a','b'),('b','a'),('b','sink'),('kms','start')]]}
    spec['nodes'][-1]['placement_role']='security'
    before=copy.deepcopy(spec)
    order=flow_order(spec)
    assert set(order)==set(n['id'] for n in spec['nodes']) and len(order)==6
    assert order.index('start')<order.index('a')<order.index('sink')
    assert order.index('start')<order.index('b')<order.index('sink')
    assert order[-1]=='kms'
    assert order==flow_order(spec) and before==spec


def test_custom_names_repeated_services_and_markdown_characters_survive_word_export():
    from app.document.document_builder import DocumentBuilder, SectionBuilder, BRAND_BLUE, CONTENT_WIDTH_DXA
    spec={'nodes':[{'id':k,'label':name,'subtitle':purpose,'scope':'regional'} for k,name,purpose in [
        ('s3in','Amazon S3','Inputs'),('s3out','Amazon S3','Reports'),
        ('work','Clinical | Worker','Validate cases'),('az_a','Amazon EC2','Application'),('az_b','Amazon EC2','Application')]],
        'edges':[{'source':'s3in','target':'work'},{'source':'work','target':'s3out'}]}
    text=render_table(spec,[{'node_id':k,'role':'Store A | B <values> safely'} for k in flow_order(spec)])
    assert 'Amazon S3 — Inputs' in text and 'Amazon S3 — Reports' in text
    assert 'Application (az_a)' in text and 'Application (az_b)' in text
    doc=Document()
    builder=DocumentBuilder(SimpleNamespace())
    builder.doc=doc
    builder._configure_styles()
    SectionBuilder(doc,SimpleNamespace()).parse_content(text)
    table=doc.tables[0]
    assert len(table.rows)==6 and len(table.columns)==2
    assert any('Clinical | Worker' in row.cells[0].text for row in table.rows)
    assert all('A | B <values>' in row.cells[1].text for row in table.rows[1:])
    assert table.cell(0,0)._tc.tcPr.find(qn('w:shd')).get(qn('w:fill'))==BRAND_BLUE
    widths=SectionBuilder._column_widths([['Service name','Role in the project'],['Amazon S3','Stores uploads']])
    assert sum(widths)==CONTENT_WIDTH_DXA and widths[1]>widths[0]


def test_no_services_is_not_applicable():
    text,audit=write(None,{'spec':{'nodes':[]}},'Keep')
    assert text=='Keep' and audit['status']=='not_applicable'


def test_entry_and_authentication_precede_processing_not_shared_controls():
    spec={'nodes':[
        {'id':'work','label':'AWS Lambda','layer':2,'scope':'regional'},
        {'id':'auth','label':'Amazon Cognito','layer':1,'scope':'regional','placement_role':'security'},
        {'id':'edge','label':'Amazon CloudFront','layer':1,'scope':'global','placement_role':'entry'},
        {'id':'kms','label':'AWS KMS','layer':0,'scope':'regional','placement_role':'security'}],
        'edges':[], 'architecture_plan':{'narrative_view':{'groups':[{'rows':[['work','auth']]}]}}}
    assert flow_order(spec)==['edge','auth','work','kms']


def test_review_required_image_still_gets_complete_service_table():
    value=asset(); value.update(status='review_required',used_fallback=True)
    llm,_=model([{'rows':rows()}])
    content={'architecture_diagram':'Old'}
    synchronize(llm,content,[value])
    assert value['status']=='review_required' and value['text_alignment']['row_count']==3
