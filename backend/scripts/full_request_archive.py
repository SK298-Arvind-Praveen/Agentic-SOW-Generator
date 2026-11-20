"""Local archive adapter for live generation tests, retaining real API contracts.

No model, authoring, renderer, document builder, URL parser, access-control or
download-handler behavior is replaced. Only remote object/record storage is local.
"""
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import json
import shutil
from unittest.mock import MagicMock
import zipfile


DOCX_TYPE = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'


class LocalRequestArchive:
    def __init__(self, directory, bucket):
        self.directory, self.bucket = Path(directory), bucket
        self.saved, self.objects, self.records = [], {}, {}
        self.handler = MagicMock()
        self.handler.get_next_version.return_value = 1
        self.handler.get_document_by_id.side_effect = lambda key: self.records.get(key)
        self.handler.query_by_task_id.side_effect = lambda key: next(
            (v for v in self.records.values() if v.get('task_id') == key), None)
        self.handler.table.query.side_effect = lambda **kw: {'Items': [self.records[key]]
            if (key := kw.get('ExpressionAttributeValues', {}).get(':document_id')) in self.records else []}

    def upload(self, file, **kwargs):
        target = self.directory / f'export-{len(self.saved)+1}.docx'
        shutil.copyfile(file, target); self.saved.append(target)
        key = f'verification/{self.directory.name}/{target.name}'
        self.objects[self.bucket, key] = (target.read_bytes(), DOCX_TYPE)
        return {'s3_url': f's3://{self.bucket}/{key}', 'https_url': f'https://{self.bucket}.s3.amazonaws.com/{key}',
                'bucket': self.bucket, 'key': key, 'file_size': target.stat().st_size}

    def save_record(self, **kwargs):
        key = kwargs.get('existing_document_id') or f'verification-{len(self.records)+1}'
        prior = self.records.get(key, {})
        if kwargs.get('existing_document_id'):
            if not prior or prior.get('status') != 'draft':
                raise ValueError('The draft no longer exists or has already been completed')
            if prior.get('owner_email') != kwargs.get('metadata', {}).get('owner_email'):
                raise ValueError('Draft ownership cannot be changed')
        record = {**kwargs.get('metadata', {}), 'document_id': key, 's3_url': kwargs['s3_url'],
                  'task_id': kwargs.get('task_id'), 'version': prior.get('version', 'v1'),
                  'timestamp': prior.get('timestamp') or datetime.now(timezone.utc).isoformat()}
        self.records[key] = record
        return {'success': True, **record}

    def put_object(self, *, Bucket, Key, Body, ContentType=None, **kwargs):
        payload = Body.encode() if isinstance(Body, str) else bytes(Body)
        self.objects[Bucket, Key] = (payload, ContentType or 'application/octet-stream')
        if Key.endswith('.json'):
            (self.directory/'draft-snapshot.json').write_bytes(payload)
        return {}

    def get_object(self, *, Bucket, Key, **kwargs):
        payload, kind = self.objects[Bucket, Key]
        return {'Body': BytesIO(payload), 'ContentLength': len(payload), 'ContentType': kind}

    def delete_object(self, *, Bucket, Key, **kwargs):
        self.objects.pop((Bucket, Key), None)
        return {}


def assert_download(client, result, expected_path):
    assert result.get('success') and result.get('document_id') and result.get('s3_url'), 'finalize returned no downloadable document'
    response = client.post('/api/proxy-download', json={k: result[k] for k in ('s3_url', 'document_id')})
    assert response.status_code == 200, f'download failed: {response.get_json()}'
    payload = response.data
    assert payload and int(response.headers['Content-Length']) == len(payload), 'download empty or incomplete'
    assert response.mimetype == DOCX_TYPE, 'download is not a Word document'
    assert 'attachment;' in response.headers.get('Content-Disposition', '') and '.docx' in response.headers['Content-Disposition']
    assert sha256(payload).digest() == sha256(Path(expected_path).read_bytes()).digest(), 'download differs from finalized Word export'
    with zipfile.ZipFile(BytesIO(payload)) as doc:
        assert 'word/document.xml' in doc.namelist(), 'download lacks Word document content'
    return {'bytes': len(payload), 'sha256': sha256(payload).hexdigest(), 'content_type': response.mimetype}


def assert_public_preview(public, internal, selected):
    from app.core.sow_section_preferences import section_category
    content = public.get('content')
    assert isinstance(content, dict) and content, 'public preview has no content'
    assert json.dumps(content, sort_keys=True, default=str) == json.dumps(internal, sort_keys=True, default=str), 'public preview differs from generated content'
    def category(key):
        return 'about_client' if key == 'about_company' else section_category(key) or key
    order = [category(k) for k in public.get('preview_section_order', [])]
    assert order == [k for k in selected if k != 'conceptual_flow_diagram'], 'public preview section order differs from selected order'
    assert public.get('version') or (public.get('metadata') or {}).get('version'), 'public preview version missing'
    return content
