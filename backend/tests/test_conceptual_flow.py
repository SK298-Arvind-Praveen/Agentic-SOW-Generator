from pathlib import Path
from types import SimpleNamespace
import base64
import io
import pytest
from PIL import Image
from docx import Document
from app.diagram.conceptual import validate_plan, render, generate
from app.core.sow_section_preferences import parse_selected_section_ids
from app.document.document_builder import DocumentBuilder, SectionBuilder


def fixture_plan():
    return {'nodes': [
        {'id':'input','label':'Receive call recordings','kind':'input','stage':0,'evidence':'recordings'},
        {'id':'speech','label':'Transcribe speech','kind':'ai','stage':1,'evidence':'transcribe'},
        {'id':'mask','label':'Mask personal data','kind':'process','stage':2,'evidence':'mask'},
        {'id':'score','label':'Score call checks','kind':'process','stage':3,'evidence':'score'},
        {'id':'result','label':'Publish results','kind':'output','stage':4,'evidence':'results'}],
        'edges':[{'source':a,'target':b} for a,b in [('input','speech'),('speech','mask'),('mask','score'),('score','result')]]}


def test_render_and_document_placement(tmp_path):
    config = SimpleNamespace(ASSETS_DIR=Path('assets'), OUTPUT_DIR=tmp_path)
    png = render(validate_plan(fixture_plan()), config)
    assert Image.open(io.BytesIO(png)).width > 1000
    builder = DocumentBuilder(config)
    asset = {'image_base64':base64.b64encode(png).decode()}
    sections = {'toc_structure':'1. About Client\n2. Solution Architecture', 'conceptual_flow_asset':asset}
    builder._parse_toc_entries(sections)
    assert builder.toc_entries == ['1. About Client','2. Conceptual Flow Diagram','3. Solution Architecture']
    builder.doc = Document()
    builder.section_builder = SectionBuilder(builder.doc, config)
    builder._build_section('2. Conceptual Flow Diagram', sections, {}, 1)
    assert len(builder.doc.inline_shapes) == 1
    out = Path('output/conceptual-flow-smoke.png')
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(png)


def test_invalid_endpoint_rejected():
    plan = fixture_plan(); plan['edges'][0]['target'] = 'missing'
    with pytest.raises(ValueError): validate_plan(plan)


def test_cycle_rejected():
    plan = fixture_plan(); plan['edges'].append({'source':'result','target':'input'})
    with pytest.raises(ValueError): validate_plan(plan)


def test_opt_in_and_order():
    assert 'conceptual_flow_diagram' not in parse_selected_section_ids(None, 'POC')
    assert parse_selected_section_ids(['architecture_diagram','conceptual_flow_diagram'], 'POC') == ['architecture_diagram','conceptual_flow_diagram']


def test_generated_plan_with_mocked_model():
    import json
    class LLM:
        def generate(self, *args, **kwargs):
            from app.core.bedrock_llm import BedrockTextResult
            return BedrockTextResult(text=json.dumps(fixture_plan()), model_id='test')
    result = generate(LLM(), SimpleNamespace(ASSETS_DIR=Path('assets')), {},
                      'recordings transcribe mask score results', {})
    assert result['image_base64']


def test_same_stage_edges_are_relaid_out():
    plan = fixture_plan()
    plan['nodes'][1]['stage'] = 0
    plan['nodes'][2]['stage'] = 1
    plan['nodes'][3]['stage'] = 2
    plan['nodes'][4]['stage'] = 3
    assert [n['stage'] for n in validate_plan(plan)['nodes']] == [0,1,2,3,4]
