import json
from types import SimpleNamespace

from app.diagram.architecture_text import missing_services, synchronize, write


def asset():
    return {'spec':{'nodes':[
        {'id':'s3','label':'Amazon S3','scope':'regional'},
        {'id':'ocr','label':'Amazon Textract','scope':'regional'},
        {'id':'iam','label':'AWS Identity and Access Management','scope':'global'},
        {'id':'user','label':'Reviewer','scope':'external'}],
        'edges':[{'source':'s3','target':'ocr','label':'Read document'}]}}


def test_generic_flow_cannot_pass_as_aws_architecture():
    assert set(missing_services('- An extraction pipeline reads uploaded documents.',asset()['spec'])) == {
        'Amazon S3','Amazon Textract','AWS Identity and Access Management'}
    assert not missing_services('S3 holds documents that Textract reads using IAM permissions.',asset()['spec'])
    assert 'Amazon S3' in missing_services('S3Backup',asset()['spec'])


def test_missing_components_trigger_focused_rewrite():
    calls = []
    responses = iter(['- An extraction pipeline reads documents.',
                     '- Textract reads documents from Amazon S3 using IAM permissions.'])
    def generate(prompt,**kw):
        calls.append(prompt)
        return SimpleNamespace(text=json.dumps({'text':next(responses)}))
    text, audit = write(SimpleNamespace(generate=generate),asset(),'Generic old text')
    assert len(calls)==2 and 'Name and explain these diagram services' in calls[1]
    assert audit['status']=='aligned' and 'Textract' in text


def test_synchronization_changes_only_selected_architecture():
    content = {'architecture_diagram':'Generic text','scope_of_work':'Preserve this.','aws_pricing':'Price'}
    assets = [asset()]
    llm = SimpleNamespace(generate=lambda *a,**k: SimpleNamespace(text=json.dumps({
        'text':'- Amazon Textract reads S3 documents using IAM permissions.'})))
    synchronize(llm,content,assets)
    assert content['scope_of_work']=='Preserve this.' and content['aws_pricing']=='Price'
    assert 'Textract' in content['architecture_diagram']
    assert assets[0]['text_alignment']['status']=='aligned'
    # An excluded architecture section must not be inserted by the synchronizer.
    excluded = {'scope_of_work':'Only scope'}
    synchronize(llm,excluded,assets)
    assert excluded == {'scope_of_work':'Only scope'}


def test_failed_text_repair_is_logged_and_not_marked_aligned():
    content = {'architecture_diagram':'- Generic pipeline.'}
    assets = [asset()]
    llm = SimpleNamespace(generate=lambda *a,**k: SimpleNamespace(text='bad JSON'))
    synchronize(llm,content,assets)
    assert assets[0]['status']=='review_required'
    assert assets[0]['text_alignment']['missing_services']
    assert assets[0]['validation_warnings']
    assert content['architecture_diagram']=='- Generic pipeline.'


def test_component_coverage_alone_does_not_accept_incorrect_iam_or_release_gate():
    drafts = iter([
        '- IAM controls permissions S3 and Textract use to call one another.',
        '- Textract reads S3 with IAM permissions after a reviewer resolves all warnings.',
        '- Textract reads S3 with IAM permissions after required blocking warnings are resolved.'])
    prompts = []
    def generate(prompt,**kwargs):
        prompts.append(prompt)
        return SimpleNamespace(text=json.dumps({'text':next(drafts)}))
    text,audit = write(SimpleNamespace(generate=generate),asset())
    assert len(prompts)==3 and 'blocking warnings' in text
    assert audit['status']=='aligned'
