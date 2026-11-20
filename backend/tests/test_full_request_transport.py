from contextlib import ExitStack
from copy import deepcopy
from unittest.mock import patch
import pytest

from scripts.full_request_archive import LocalRequestArchive, assert_download, assert_public_preview


def test_real_proxy_download_returns_exact_finalized_word_bytes(tmp_path, monkeypatch):
    from docx import Document
    from app.core import server
    monkeypatch.setenv('S3_BUCKET_NAME','verification-bucket')
    monkeypatch.setitem(server.app.config,'TESTING',True)
    source=tmp_path/'source.docx'; Document().save(source)
    archive=LocalRequestArchive(tmp_path,'verification-bucket')
    uploaded=archive.upload(source)
    saved=archive.save_record(metadata={'status':'completed','owner_email':'test-admin@shellkode.com'},
        s3_url=uploaded['https_url'],task_id='preview')
    with ExitStack() as stack:
        stack.enter_context(patch.object(server,'DynamoDBHandler',lambda *a,**k:archive.handler))
        stack.enter_context(patch.object(server,'get_s3_client',lambda:archive))
        result=assert_download(server.app.test_client(),saved,source)
        assert result['bytes']==source.stat().st_size
        altered=deepcopy(saved); altered['s3_url']=None
        with pytest.raises(AssertionError,match='no downloadable'): assert_download(server.app.test_client(),altered,source)
        altered=deepcopy(saved); altered['document_id']='not-saved'
        with pytest.raises(AssertionError,match='download failed'): assert_download(server.app.test_client(),altered,source)


def test_public_preview_must_preserve_content_order_and_version():
    content={'about_company':'Company profile','scope_of_work':'Agreed scope'}
    response={'content':content,'preview_section_order':list(content),'version':'v1'}
    selected=['about_client','scope_of_work']
    assert assert_public_preview(response,content,selected)==content
    for change in ({'content':{'scope_of_work':'Agreed scope'}},
                   {'preview_section_order':list(reversed(content))},{'version':None}):
        with pytest.raises(AssertionError): assert_public_preview({**response,**change},content,selected)


def test_local_archive_enforces_real_draft_transitions(tmp_path):
    archive=LocalRequestArchive(tmp_path,'verification-bucket')
    def save(status='draft',existing=None,owner='owner'):
        return archive.save_record(metadata={'status':status,'owner_email':owner},
            s3_url='https://verification-bucket.s3.amazonaws.com/document.docx',existing_document_id=existing)
    with pytest.raises(ValueError): save(existing='missing')
    draft=save()
    with pytest.raises(ValueError): save(existing=draft['document_id'],owner='different')
    final=save('completed',draft['document_id'])
    assert final['version']==draft['version'] and final['timestamp']==draft['timestamp']
    with pytest.raises(ValueError): save(existing=final['document_id'])
