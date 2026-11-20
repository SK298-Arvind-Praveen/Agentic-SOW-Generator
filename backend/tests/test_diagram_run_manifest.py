import base64
from copy import deepcopy

import pytest


def test_manifest_preserves_options_and_rejects_source_change(tmp_path):
    from app.diagram.run_manifest import GenerationManifest
    source = tmp_path / 'source.docx'
    source.write_bytes(b'source evidence')
    form = {'selected_sow_sections': ['scope_of_work', 'architecture_diagram', 'assumptions'],
            'timeline_format': 'gantt', 'pricing_region': 'ap-south-1'}
    manifest = GenerationManifest.create([source], form, {'ARCHITECTURE_PROCESS_FLOW': 'on'})
    manifest.verify_sources()
    assert manifest.form == form
    source.write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash'):
        manifest.verify_sources()


def asset():
    return {'status': 'ready', 'image_base64': base64.b64encode(b'png').decode(),
            'used_fallback': False, 'vision_review': {'status': 'passed', 'image_reviewed': True, 'issues': []}}


@pytest.mark.parametrize('change', [
    {'status': 'review_required'}, {'used_fallback': True}, {'validation_warnings': ['crossings']},
    {'vision_review': {'status': 'disabled'}}, {'quality_warnings': ['story wrong']},
    {'vision_review': {'status': 'passed', 'issues': [{'stage': 'story', 'detail': 'egress'}]}},
])
def test_image_exists_does_not_mean_verified(change):
    from app.diagram.run_manifest import assert_diagram_acceptance
    candidate = {**asset(), **change}
    with pytest.raises(AssertionError):
        assert_diagram_acceptance(candidate)


def test_missing_conceptual_or_empty_selected_section_cannot_pass():
    from app.diagram.run_manifest import assert_content_acceptance
    content = {'architecture_diagrams': [asset()], 'Project Timeline': '| Phase | Week |\n|---|---|'}
    with pytest.raises(AssertionError, match='conceptual'):
        assert_content_acceptance(content, ['conceptual_flow_diagram'])
    with pytest.raises(AssertionError, match='timelines_deliverables'):
        assert_content_acceptance(content, ['timelines_deliverables'])


def test_saved_v52_is_not_a_passing_full_request():
    import json
    from pathlib import Path
    from app.diagram.run_manifest import assert_diagram_acceptance
    path = Path('output/diagram-debug/20261118T122151_30960ee29f1a.json')
    if not path.exists(): pytest.skip('local v52 evidence not distributed')
    for candidate in json.loads(path.read_text(encoding='utf8'))['assets']:
        with pytest.raises(AssertionError): assert_diagram_acceptance(candidate)


def test_config_capture_never_contains_credentials():
    from app.diagram.run_manifest import capture_configuration
    settings = capture_configuration({'AWS_ACCESS_KEY_ID': 'secret', 'AWS_SECRET_ACCESS_KEY': 'secret',
        'AWS_SESSION_TOKEN': 'secret', 'ARCHITECTURE_PROCESS_FLOW': 'on', 'BEDROCK_REGION': 'us-east-1'})
    assert 'secret' not in str(settings)
    assert settings['ARCHITECTURE_PROCESS_FLOW'] == 'on'


def test_acceptance_rejects_blank_gantt_and_missing_pricing_link():
    from app.diagram.run_manifest import assert_content_acceptance
    state = {'metadata': {'timeline_format': 'gantt'}}
    for section, body in [('timelines_deliverables', '| Phase | Activity | W1 |\n|---|---|---|\n| Build | Setup | |'),
                          ('aws_pricing', '| Service | Cost |\n|---|---|\n| EC2 | 12 |')]:
        with pytest.raises(AssertionError):
            assert_content_acceptance({section: body}, [section], state)


def test_missing_artifact_version_is_not_implicitly_current():
    from app.diagram.run_manifest import assert_content_acceptance
    with pytest.raises(AssertionError, match='version'):
        assert_content_acceptance({'assumptions': 'The client supplies all required source records.'},
            ['assumptions'], {'architecture_version': 'new', 'artifact_architecture_versions': {}})


@pytest.mark.parametrize('name', ['architecture_design_prompt.md', 'poc_rules.json'])
def test_template_changes_invalidate_runtime_fingerprint(tmp_path, name):
    from app.diagram.run_manifest import code_fingerprint
    prompt=tmp_path/name
    prompt.write_text('Original contract',encoding='utf-8')
    before=code_fingerprint(tmp_path)
    prompt.write_text('Changed contract',encoding='utf-8')
    assert code_fingerprint(tmp_path)!=before


def test_content_acceptance_recognizes_writer_company_key():
    from app.diagram.run_manifest import assert_content_acceptance
    assert_content_acceptance({'about_company':'Example Retail runs physical stores and an online catalogue.'},['about_client'])


@pytest.mark.parametrize('same_activity', [False, True])
def test_word_gantt_validation_checks_rendered_bars_not_unicode_markers(tmp_path, same_activity):
    from types import SimpleNamespace
    from docx import Document
    from docx.oxml.ns import qn
    from app.document.document_builder import DocumentBuilder, SectionBuilder
    from app.diagram.run_manifest import export_section_failures
    source='| S.No | Activity | W1 | W2 |\n|---|---|---|---|\n| 1 | Configure infrastructure | ■ | |\n| 2 | Run tests | | ◆ |'
    builder=DocumentBuilder(SimpleNamespace());builder.doc=Document();builder._configure_styles()
    builder.doc.add_heading('Timelines and Deliverables',1)
    table=SectionBuilder(builder.doc,SimpleNamespace())._build_table_rows([['S.No','Activity','W1','W2'],
        ['1','Configure infrastructure','■',''],['2','Run tests','','◆']],gantt=True)
    if same_activity:
        source=source.replace('Run tests','Configure infrastructure')
        table.rows[2].cells[1].text='Configure infrastructure'
    path=tmp_path/'gantt.docx';builder.doc.save(path)
    assert not export_section_failures(path,{'timelines_deliverables':source},['timelines_deliverables'])
    if same_activity:
        for i in (2,3):
            a=table.rows[1].cells[i]._tc.find('.//'+qn('w:shd'))
            b=table.rows[2].cells[i]._tc.find('.//'+qn('w:shd'))
            ca,cb=a.get(qn('w:fill')),b.get(qn('w:fill'))
            a.set(qn('w:fill'),cb); b.set(qn('w:fill'),ca)
        builder.doc.save(path)
        assert export_section_failures(path,{'timelines_deliverables':source},['timelines_deliverables'])
    for cell in builder.doc.tables[-1]._tbl.findall('.//'+qn('w:tc')):
        for shade in cell.findall('.//'+qn('w:shd')):
            shade.set(qn('w:fill'),'FFFFFF')
    builder.doc.save(path)
    assert any('Gantt' in issue for issue in export_section_failures(
        path,{'timelines_deliverables':source},['timelines_deliverables']))
    for row in table.rows[1:]:
        for cell in row.cells[2:]:
            shade=cell._tc.find('.//'+qn('w:shd'))
            shade.set(qn('w:fill'),'CCFFCC')
    builder.doc.save(path)
    assert any('Gantt' in issue for issue in export_section_failures(
        path,{'timelines_deliverables':source},['timelines_deliverables']))


def test_export_parity_detects_dropped_or_stale_section(tmp_path):
    from docx import Document
    from app.diagram.run_manifest import export_section_failures
    doc=Document();doc.add_heading('Assumptions',1)
    doc.add_paragraph('The customer provides approved source documents.')
    path=tmp_path/'export.docx';doc.save(path)
    content={'assumptions':'The customer provides approved source documents.'}
    assert not export_section_failures(path,content,['assumptions'])
    assert export_section_failures(path,content,['assumptions','scope_of_work'])
    content['assumptions']='The vendor provides approved source documents.'
    assert export_section_failures(path,content,['assumptions'])


def test_word_gantt_requires_each_duplicate_row_to_be_rendered(tmp_path):
    from types import SimpleNamespace
    from docx import Document
    from app.document.document_builder import DocumentBuilder, SectionBuilder
    from app.diagram.run_manifest import export_section_failures

    key = 'timelines_deliverables'
    source = ('| S.No | Activity | W1 | W2 |\n| --- | --- | --- | --- |\n'
              '| 1 | Acceptance testing | ■ | |\n| 1 | Acceptance testing | ■ | |')
    builder = DocumentBuilder(SimpleNamespace())
    builder.doc = Document()
    builder._configure_styles()
    builder.doc.add_heading('Project Timeline', 1)
    SectionBuilder(builder.doc, SimpleNamespace()).parse_content(source)
    path = tmp_path / 'duplicate-activity.docx'
    builder.doc.save(path)
    assert not export_section_failures(path, {key: source}, [key])

    table = builder.doc.tables[0]
    table._tbl.remove(table.rows[2]._tr)
    builder.doc.save(path)
    assert any('Gantt' in issue for issue in export_section_failures(path, {key: source}, [key]))


@pytest.mark.parametrize('extra_table', [False, True])
def test_word_gantt_requires_single_grid_and_exact_contract_note_counts(tmp_path, extra_table):
    from types import SimpleNamespace
    from docx import Document
    from app.document.document_builder import DocumentBuilder, SectionBuilder
    from app.diagram.run_manifest import export_section_failures

    key = 'timelines_deliverables'
    contract_row = '| 2 | Five-business-day warranty | | ◆ |'
    source = ('| S.No | Activity | W1 | Contract Term After Go-Live |\n| --- | --- | --- | --- |\n'
              '| 1 | Deploy | ■ | |\n' + contract_row)
    builder = DocumentBuilder(SimpleNamespace())
    builder.doc = Document()
    builder._configure_styles()
    builder.doc.add_heading('Project Timeline', 1)
    SectionBuilder(builder.doc, SimpleNamespace()).parse_content(source)
    path = tmp_path / 'contract-notes.docx'
    builder.doc.save(path)
    assert not export_section_failures(path, {key: source}, [key])

    if extra_table:
        duplicate = deepcopy(builder.doc.tables[0]._tbl)
        builder.doc.tables[0]._tbl.addnext(duplicate)
        builder.doc.tables[1].rows[0].cells[2].text = 'Extra project week'
    else:
        source += '\n' + contract_row
    builder.doc.save(path)
    assert any('Gantt' in issue for issue in export_section_failures(path, {key: source}, [key]))


def test_word_fragment_hyperlinks_and_split_text_runs_remain_valid(tmp_path):
    import zipfile
    from types import SimpleNamespace
    from docx import Document
    from docx.oxml.ns import qn
    from app.document.document_builder import SectionBuilder
    from app.diagram.run_manifest import exported_hyperlinks, export_section_failures
    doc=Document(); doc.add_heading('Assumptions',1)
    p=doc.add_paragraph(); p.add_run('Ser'); p.add_run('vices use client-provided credentials.')
    SectionBuilder(doc,SimpleNamespace()).parse_content('[Open Link](https://calculator.aws/)')
    link=doc.element.body.find('.//'+qn('w:hyperlink')); link.set(qn('w:anchor'),'/estimate?id=saved123')
    path=tmp_path/'word.docx'; doc.save(path)
    with zipfile.ZipFile(path) as package:
        assert 'https://calculator.aws/#/estimate?id=saved123' in exported_hyperlinks(package)
    assert not export_section_failures(path,{'assumptions':'Services use client-provided credentials.'},['assumptions'])


def test_word_gantt_bold_note_label_is_included_in_exact_note_text(tmp_path):
    from types import SimpleNamespace
    from docx import Document
    from app.document.document_builder import DocumentBuilder, SectionBuilder
    from app.diagram.run_manifest import export_section_failures

    key = 'timelines_deliverables'
    source = ('| S.No | Activity | W1 |\n| --- | --- | --- |\n| 1 | Deploy | ■ |\n\n'
              '- **Warranty:** Covers stabilization.')
    builder = DocumentBuilder(SimpleNamespace())
    builder.doc = Document()
    builder._configure_styles()
    builder.doc.add_heading('Project Timeline', 1)
    SectionBuilder(builder.doc, SimpleNamespace()).parse_content(source)
    path = tmp_path / 'bold-note.docx'
    builder.doc.save(path)
    assert any(paragraph.text == 'Warranty: Covers stabilization.' for paragraph in builder.doc.paragraphs)
    assert not export_section_failures(path, {key: source}, [key])


def test_process_switch_is_checked_against_actual_export():
    from app.diagram.run_manifest import assert_process_flow_acceptance
    value={'drawio_xml':'<mxfile><mxCell edge="1" value="" /></mxfile>'}
    assert_process_flow_acceptance(value,False)
    with pytest.raises(AssertionError,match='missing'): assert_process_flow_acceptance(value,True)
    value['drawio_xml']='<mxfile><mxCell edge="1" value="Forward" /></mxfile>'
    with pytest.raises(AssertionError,match='captions'): assert_process_flow_acceptance(value,False)


def test_estimated_fallback_is_not_mistaken_for_calculator_success():
    from app.diagram.run_manifest import assert_content_acceptance
    content={'aws_pricing':'AWS Pricing Calculator: [Open Link](https://calculator.aws/#/estimate?id=saved123)'}
    state={'pricing_result':{'status':'hybrid_priced','estimate_url':'https://calculator.aws/#/estimate?id=saved123','monthly_cost':2200}}
    with pytest.raises(AssertionError,match='verified pricing evidence'): assert_content_acceptance(content,['aws_pricing'],state)


def test_incomplete_authoring_review_cannot_pass_full_request():
    from app.diagram.run_manifest import assert_authoring_acceptance
    for summary in ('', '**Generation quality gate:** Completed with review flags\n- Automated content flags: 1'):
        with pytest.raises(AssertionError,match='review incomplete'):
            assert_authoring_acceptance({'generation_quality_summary':summary})
    assert_authoring_acceptance({'generation_quality_summary':'**Generation quality gate:** Passed\n- Automated content flags: 0'})
def test_numbered_process_markers_are_not_mistaken_for_connector_captions():
    from app.diagram.run_manifest import assert_process_flow_acceptance
    step = {'id': 'ingress', 'number': 1, 'edge_ids': ['e0']}
    asset = {'renderer_details': {'process_flow': [step]},
             'spec': {'architecture_plan': {'process_story': {'steps': [step]}},
                      'edges': [{'source': 'a', 'target': 'b'}]},
             'drawio_xml': '<mxfile><diagram><mxGraphModel><root>'
                 '<mxCell id="process_flow_panel"/>'
                 '<mxCell id="flow_0" edge="1" value="" sourceNode="a" targetNode="b" originalEdgePaths="[[0]]"/>'
                 '<mxCell id="process_flow_marker_1" vertex="1" parent="flow_0" value="1" '
                 'processFlowStep="ingress" processFlowConnector="flow_0"><mxGeometry relative="1" width="30" height="30">'
                 '<mxPoint as="offset" x="35" y="-15"/></mxGeometry></mxCell>'
                 '</root></mxGraphModel></diagram></mxfile>'}
    assert_process_flow_acceptance(asset, True)
    for invalid in ('SQL', 'Forward', '2'):
        asset['drawio_xml'] = asset['drawio_xml'].replace('value="1"', f'value="{invalid}"')
        with pytest.raises(AssertionError, match='marker'):
            assert_process_flow_acceptance(asset, True)
        asset['drawio_xml'] = asset['drawio_xml'].replace(f'value="{invalid}"', 'value="1"')

def test_priced_total_cannot_hide_an_unpriced_selected_ec2_role():
    from app.diagram.run_manifest import assert_content_acceptance
    content = {'aws_pricing': 'AWS Pricing Calculator: [Open Link](https://calculator.aws/#/estimate?id=saved123)'}
    state = {'validated_requirements': {'approved_architecture': {'nodes': [
        {'id': key, 'icon_key': 'aws.service.compute.amazon-ec2', 'scope': 'az'}
        for key in ('app', 'runner')]}},
        'pricing_result': {'status': 'priced', 'estimate_url': 'https://calculator.aws/#/estimate?id=saved123',
                           'monthly_cost': 300}}
    with pytest.raises(AssertionError, match='EC2 resource coverage'):
        assert_content_acceptance(content, ['aws_pricing'], state)
    pricing = state['pricing_result']
    configs = [{'instance': key, 'resource_ids': [key], 'quantity': 1, 'monthly_hours': 40}
               for key in ('app', 'runner')]
    pricing.update(resource_coverage={'Amazon EC2': {'complete': True, 'configurations': configs}},
                   calculator_entries=[{'service': 'ec2Enhancement', 'instance': key} for key in ('app', 'runner')])
    assert_content_acceptance(content, ['aws_pricing'], state)
    configs.pop()
    with pytest.raises(AssertionError, match='EC2 resource coverage'):
        assert_content_acceptance(content, ['aws_pricing'], state)

