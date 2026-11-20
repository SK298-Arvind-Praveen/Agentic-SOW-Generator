"""Full website-contract request with live models and real draft/final DOCX builds.

Only external archive/identity persistence is isolated. No planner, model, graph,
section authoring, diagram, review or document-builder mocks are permitted here.
"""
import argparse
import base64
from contextlib import ExitStack
import json
from pathlib import Path
import shutil
import sys
import time
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'): stream.reconfigure(encoding='utf8', errors='replace')
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--timeout', type=int, default=7200)
    args = parser.parse_args()
    from app.diagram.run_manifest import GenerationManifest, capture_configuration, code_fingerprint, digest, assert_content_acceptance, export_section_failures
    manifest = GenerationManifest.load(args.manifest)
    manifest.verify_sources()
    # Set only public feature flags before Config is instantiated. Model routing
    # is verified against the actual configured profiles, never silently changed.
    import os
    for key in ('ARCHITECTURE_PROCESS_FLOW', 'ARCHITECTURE_DIAGRAM_ENGINE', 'ARCHITECTURE_VISION_REVIEW_ENABLED'):
        if manifest.configuration.get(key) is not None:
            os.environ[key] = str(manifest.configuration[key]).lower()
    from app.core import server
    from app.core.config import Config
    config = Config()
    out = Path(args.output).resolve(); out.mkdir(parents=True, exist_ok=True)
    manifest.save(out / 'manifest.json')
    effective = capture_configuration(config)
    for key, expected in manifest.configuration.items():
        if expected is not None:
            truth = lambda v: str(v).lower() in {'true','on','1','yes'}
            actual = effective[key]
            assert (truth(expected) == truth(actual) if key == 'ARCHITECTURE_PROCESS_FLOW' else str(expected) == str(actual)), f'Configuration drift: {key}'
    fingerprint = code_fingerprint(Path(__file__).resolve().parents[1]/'app')
    template_fingerprint = code_fingerprint(Path(__file__).resolve().parents[1]/'templates')
    harness_files = [Path(__file__), Path(__file__).with_name('full_request_archive.py')]
    harness_fingerprints = {p.name: digest(p.read_bytes()) for p in harness_files}
    for source in harness_files: shutil.copyfile(source, out/source.name)
    (out/'runtime.json').write_text(json.dumps({'effective_configuration': effective,
        'code_fingerprint': fingerprint,
        'template_fingerprint': template_fingerprint,
        'harness_fingerprints': harness_fingerprints,
        'isolation': ['TESTING identity', 'S3/Drive/DynamoDB archive destinations only'],
        'transport': 'Flask HTTP multipart/reservation/status/finalize/proxy-download'}, indent=2), encoding='utf8')
    server.app.config['TESTING'] = True
    from scripts.full_request_archive import LocalRequestArchive, assert_download, assert_public_preview
    archive = LocalRequestArchive(out, config.S3_BUCKET_NAME)
    saved = archive.saved
    with ExitStack() as stack:
        for name, replacement in {
            'upload_to_s3': archive.upload, 'upload_generated_document': lambda *a, **k: None,
            'get_s3_client': lambda: archive, 'DynamoDBHandler': lambda *a, **k: archive.handler,
            'save_to_dynamodb': archive.save_record,
        }.items(): stack.enter_context(patch.object(server, name, replacement))
        client = server.app.test_client()
        reservation = client.post('/api/preview/reserve', json={})
        assert reservation.status_code in {200, 201, 202}, reservation.get_json()
        form = {k: json.dumps(v) if isinstance(v, (list, dict, bool)) else str(v)
                for k, v in manifest.form.items() if v is not None}
        form['reserved_preview_id'] = reservation.get_json()['preview_id']
        form['supporting_doc_count'] = str(len(manifest.sources))
        files = [(stack.enter_context(open(s['path'], 'rb')), s['filename']) for s in manifest.sources]
        response = client.post('/api/preview', data={**form, 'supporting_docs': files}, content_type='multipart/form-data')
        accepted = response.get_json()
        (out/'accepted.json').write_text(json.dumps(accepted, indent=2), encoding='utf8')
        assert response.status_code == 202, accepted
        assert accepted.get('supporting_documents_received') == len(files), 'upload count differs from selected files'
        assert accepted.get('supporting_documents_extracted') == len(files) and accepted.get('supporting_context_chars',0)>0, 'source extraction omitted a file'
        preview_id = accepted['preview_id']; deadline = time.monotonic()+args.timeout; previous = None
        while time.monotonic() < deadline:
            state = client.get('/api/preview/status/'+preview_id).get_json()
            marker = (state.get('status'), state.get('progress'), state.get('current_step'))
            if marker != previous: print('[FULL REQUEST]', marker, flush=True); previous = marker
            if state.get('has_error') or state.get('is_complete'): break
            time.sleep(2)
        else: raise TimeoutError('Full preview deadline exceeded')
        (out/'response.json').write_text(json.dumps(state, indent=2, default=str), encoding='utf8')
        with server.preview_lock: final = server.preview_storage[preview_id].get('final_state') or {}
        (out/'final-state.json').write_text(json.dumps(final, indent=2, default=str), encoding='utf8')
        assert not state.get('has_error'), state.get('error')
        content = assert_public_preview(state, final.get('poc_content') or {}, manifest.form['selected_sow_sections'])
        assets = content.get('architecture_diagram_assets', []) + ([content['conceptual_flow_asset']] if content.get('conceptual_flow_asset') else [])
        for i, asset in enumerate(assets):
            if asset.get('image_base64'): (out/f'diagram-{i+1}.png').write_bytes(base64.b64decode(asset['image_base64']))
            if asset.get('drawio_xml'): (out/f'diagram-{i+1}.drawio').write_text(asset['drawio_xml'], encoding='utf8')
        response = client.post('/api/finalize', json={'preview_id': preview_id})
        result = response.get_json()
        (out/'finalize.json').write_text(json.dumps(result, indent=2, default=str), encoding='utf8')
        assert response.status_code == 200 and result.get('success'), result
        assert len(saved) >= 2, 'Real draft and finalize builds must both export'
        download = assert_download(client, result, saved[-1])
        (out/'download.json').write_text(json.dumps(download, indent=2), encoding='utf8')
        failures = []
        from app.diagram.run_manifest import assert_authoring_acceptance
        try: assert_authoring_acceptance(content)
        except AssertionError as exc: failures.append(f'authoring: {exc}')
        from app.diagram.run_manifest import assert_process_flow_acceptance
        process_on = str(effective.get('ARCHITECTURE_PROCESS_FLOW')).lower() in {'on','true','1','yes'}
        for asset in content.get('architecture_diagram_assets', []):
            try: assert_process_flow_acceptance(asset, process_on)
            except (AssertionError, ValueError) as exc: failures.append(f'process flow: {exc}')
        for section in manifest.form['selected_sow_sections']:
            try: assert_content_acceptance(content, [section], final)
            except (AssertionError, ValueError, KeyError) as exc: failures.append(f'{section}: {exc}')
        if fingerprint != code_fingerprint(Path(__file__).resolve().parents[1]/'app'):
            failures.append('Application code changed during this request; run is not reproducible')
        if template_fingerprint != code_fingerprint(Path(__file__).resolve().parents[1]/'templates'):
            failures.append('Prompt/template files changed during this request')
        if harness_fingerprints != {p.name: digest(p.read_bytes()) for p in harness_files}:
            failures.append('Request harness changed during this request')
        durable_path = out/'draft-snapshot.json'
        if not durable_path.exists():
            failures.append('Draft content snapshot was not persisted')
        else:
            durable = json.loads(durable_path.read_text(encoding='utf8'))
            if json.dumps(durable.get('content'),sort_keys=True,default=str) != json.dumps(content,sort_keys=True,default=str):
                failures.append('Persisted draft content differs from the final preview')
            if (durable.get('final_state') or {}).get('architecture_version') != final.get('architecture_version'):
                failures.append('Persisted draft architecture version differs from the preview')
            if 'architecture_diagram' in manifest.form['selected_sow_sections']:
                from app.diagram.run_manifest import assert_architecture_identity
                try: assert_architecture_identity(durable.get('content') or {}, durable.get('final_state'))
                except (AssertionError, ValueError, KeyError) as exc:
                    failures.append(f'Persisted draft canonical identity: {exc}')
        for file in saved:
            failures.extend(f'{file.name}: {issue}' for issue in export_section_failures(
                file, content, manifest.form['selected_sow_sections'], final.get('metadata')))
            with zipfile.ZipFile(file) as doc:
                media = {digest(doc.read(n)) for n in doc.namelist() if n.startswith('word/media/')}
                for asset in assets:
                    if asset.get('image_base64'):
                        if digest(base64.b64decode(asset['image_base64'])) not in media:
                            failures.append(f'{file.name}: preview image differs from export')
                if 'aws_pricing' in manifest.form['selected_sow_sections']:
                    from app.diagram.run_manifest import exported_hyperlinks
                    links = exported_hyperlinks(doc)
                    if not any('calculator.aws/' in link for link in links): failures.append(f'{file.name}: pricing hyperlink absent')
                    estimate = (final.get('pricing_result') or {}).get('estimate_url')
                    if estimate and estimate not in links: failures.append(f'{file.name}: saved estimate hyperlink changed')
        summary = {'passed': not failures, 'failures': failures, 'preview_id': preview_id,
            'download': download,
            'document_exports': [str(p) for p in saved], 'source_extraction_digest': digest(final.get('supporting_context', '')),
            'tokens': final.get('token_usage')}
        (out/'acceptance.json').write_text(json.dumps(summary, indent=2), encoding='utf8')
        print('FULL REQUEST ACCEPTANCE', json.dumps(summary), flush=True)
        if failures: raise SystemExit(1)


if __name__ == '__main__': main()
