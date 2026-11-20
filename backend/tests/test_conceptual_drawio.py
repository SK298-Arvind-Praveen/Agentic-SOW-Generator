import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from xml.etree import ElementTree as ET
import pytest
from app.diagram.conceptual_drawio import validate, xml_for, generate


def plan():
    groups=[]
    for id,kind,label in [('a','channels','Request'),('b','application','Process'),('c','outputs','Result')]:
        groups.append({'label':label,'kind':kind,'components':[{'id':id,'label':label,
            'technology':'','responsibility':'Handle <project> & data','evidence':'source'}]})
    return {'zones':groups,'bands':[], 'edges':[{'source':'a','target':'b','kind':'request'},
        {'source':'b','target':'c','kind':'async'}], 'workflow':[{'component':id,'label':id} for id in 'abc']}


def test_xml_has_real_nodes_and_connections():
    root=ET.fromstring(xml_for(validate(plan())))
    cells=root.findall('.//mxCell'); ids={c.get('id') for c in cells}
    edges=[c for c in cells if c.get('edge')]
    assert len(edges)==2
    assert all(c.get('source') in ids and c.get('target') in ids for c in edges)
    assert 'dashed=1' in edges[1].get('style')
    assert not any('TYPICAL END-TO-END' in c.get('value','') for c in cells)
    assert not {'workflow', 'legend'} & ids


def test_long_connections_remain_edges_without_reference_footer():
    value = plan()
    value['edges'].append({'source': 'a', 'target': 'c', 'kind': 'two_way'})
    root = ET.fromstring(xml_for(validate(value)))
    cells = root.findall('.//mxCell')
    assert len([c for c in cells if c.get('edge')]) == 2
    assert len(json.loads(root.find('.//mxGraphModel').get('conceptualPlan'))['edges']) == 3
    assert not any(c.get('id', '').startswith('reference') for c in cells)


def test_invalid_reference():
    value=plan(); value['edges'][0]['target']='missing'
    with pytest.raises(ValueError): validate(value)


def test_real_response_contract_and_renderer():
    llm=SimpleNamespace(generate=lambda *a,**k:SimpleNamespace(text=json.dumps(plan())))
    with patch('app.diagram.conceptual_drawio.render_drawio', side_effect=lambda xml:(b'png',xml,{'renderer':'test'})) as renderer:
        asset=generate(llm,None,{},'source',{})
    assert renderer.call_count==1
    assert asset['drawio_xml'] and asset['image_base64']
    assert asset['diagram_type']=='conceptual_flow'


def test_supplied_prompt_is_system_message_without_mutating_shared_llm():
    calls = []
    class LLM:
        system_prompt = 'Architecture system prompt'
        def generate(self, prompt, **kwargs):
            calls.append((self.system_prompt, prompt))
            return SimpleNamespace(text=json.dumps(plan()))
    llm = LLM()
    with patch('app.diagram.conceptual_drawio.render_drawio', side_effect=lambda xml: (b'png', xml, {})):
        generate(llm, None, {}, 'PROJECT SOURCE', {})
    expected = (Path(__file__).parents[1] / 'templates/conceptual_flow_prompt.md').read_text(encoding='utf-8')
    assert calls[0][0] == expected
    assert 'PROJECT SOURCE' in calls[0][1]
    assert 'takes precedence' not in calls[0][1]
    assert 'No overall title' not in calls[0][1]
    assert llm.system_prompt == 'Architecture system prompt'


def test_export_failure_preserves_all_layers_and_components():
    import base64, io
    from PIL import Image
    from app.diagram.conceptual_drawio import layout_for
    value=plan()
    value['bands']=[{'label':'Governance', 'kind':'security', 'components':[
        {'id':'review','label':'Review Board','technology':'','responsibility':'Approval','evidence':'source'}]}]
    config=SimpleNamespace(ASSETS_DIR=Path(__file__).parents[1]/'assets')
    llm=SimpleNamespace(generate=lambda *a,**k:SimpleNamespace(text=json.dumps(value)))
    with patch('app.diagram.conceptual_drawio.render_drawio',side_effect=RuntimeError('Export offline')):
        asset=generate(llm,config,{},'source',{})
    assert asset['plan']==value
    assert asset['renderer_details']['renderer']=='local layered conceptual'
    geometry=layout_for(value,config)
    assert len(geometry['boxes'])==4
    assert geometry['groups'][1]['y']>geometry['groups'][0]['y']
    assert geometry['groups'][-1]['x']>geometry['groups'][0]['x']
    assert Image.open(io.BytesIO(base64.b64decode(asset['image_base64']))).size[0]==1500


def test_valid_richer_plan_is_not_rejected_for_27_relationships():
    value=plan()
    value['edges']=[{'source':'a','target':'b','kind':'request','label':str(i)} for i in range(32)]
    value['zones'][1]['components'][0]['responsibility']='A detailed responsibility that is longer than the former seventy-five character validation limit.'
    assert validate(value) is value


def test_overview_shows_short_copy_and_preserves_skip_links():
    from app.diagram.conceptual_drawio import layout_for
    value=plan()
    for i,g in enumerate(value['zones']):g['id']=f'layer{i}'
    value['title']='Catalogue migration to AWS'
    value['zones'][0]['components'][0]['responsibility']='A long explanation that belongs in the SOW, not inside the diagram card.'
    value['edges'].append({'source':'a','target':'c','kind':'async','label':'Copy data'})
    value['layer_links']=[{'source':'layer0','target':'layer1','kind':'request','label':'Requests'},
                          {'source':'layer0','target':'layer2','kind':'async','label':'Copy data'}]
    root=ET.fromstring(xml_for(validate(value)))
    cells=root.findall('.//mxCell')
    assert any(c.get('value')=='Copy data' for c in cells)
    assert not any('long explanation' in c.get('value','') for c in cells)
    assert any(c.get('id')=='title' for c in cells)
    assert len(layout_for(value)['links'])==2
    value['layer_links'][1]['source']='layer2'
    value['layer_links'][1]['target']='layer0'
    with pytest.raises(ValueError,match='same direction'):validate(value)


def test_overview_rejects_unconnected_main_layer():
    value=plan()
    for i,g in enumerate(value['zones']):g['id']=f'layer{i}'
    value['layer_links']=[{'source':'layer0','target':'layer1','kind':'request','label':'Requests'}]
    with pytest.raises(ValueError,match='Every main layer'):validate(value)


def test_reverse_layer_links_share_one_clear_label_and_keep_both_directions():
    from app.diagram.conceptual_drawio import layout_for
    value=plan()
    for i,g in enumerate(value['zones']): g['id']=f'layer{i}'
    value['edges'].append({'source':'c','target':'b','kind':'request'})
    value['layer_links']=[{'source':'layer0','target':'layer1','kind':'request','label':'Requests'},
        {'source':'layer1','target':'layer2','kind':'request','label':'Test calls'},
        {'source':'layer2','target':'layer1','kind':'request','label':'Stub calls'}]
    layout=layout_for(validate(value))
    assert len(layout['links'])==2
    assert layout['links'][1][2:4]==(True,True)
    assert layout['links'][1][-1]=='Test calls / Stub calls'
    assert layout['groups'][0]['heading'][0].startswith('1 ')


@pytest.mark.parametrize('count,qualifier',[(1,'One AZ'),(2,'EC2 · Two AZs'),(3,'3-AZ deployment')])
def test_selected_az_count_must_be_visible_not_hidden_in_metadata(count,qualifier):
    from app.diagram.conceptual_drawio import validate_design_detail
    value=plan(); selected={'az_counts_by_vpc':{'App':count}}
    value['zones'][1]['components'][0]['responsibility']=qualifier
    with pytest.raises(ValueError,match='short visible qualifier'): validate_design_detail(value,selected)
    value['zones'][1]['components'][0]['technology']=qualifier
    assert validate_design_detail(value,selected) is value


def test_selected_design_is_passed_separately_from_source_without_mutation():
    import copy
    from app.diagram.conceptual_drawio import design_context
    requirements={'_conceptual_selected_architecture':{'nodes':[
        {'id':'a','label':'App','scope':'az','vpc':'App VPC','availability_zone':'az_a'},
        {'id':'b','label':'Replica','scope':'az','vpc':'App VPC','availability_zone':'az_b'}],
        'service_design':{'summary':'Selected EC2 design'}}}
    before=copy.deepcopy(requirements)
    context=design_context(requirements)
    assert context['az_counts_by_vpc']=={'App VPC':2}
    assert context['status']=='selected_design_not_client_facts'
    calls=[]; value=plan(); value['zones'][1]['components'][0]['technology']='Two AZs'
    llm=SimpleNamespace(generate=lambda prompt,**kwargs:(calls.append(prompt) or SimpleNamespace(text=json.dumps(value))))
    with patch('app.diagram.conceptual_drawio.render_drawio',side_effect=lambda xml:(b'png',xml,{})):
        generate(llm,None,requirements,'Original client BRD',{})
    assert 'Original client BRD' in calls[0] and 'Selected EC2 design' in calls[0]
    assert requirements==before
    assert design_context({})['az_counts_by_vpc']=={}


def test_document_identity_owns_conceptual_title():
    value = plan()
    value['title'] = 'TVS Motor: inspection'
    llm = SimpleNamespace(generate=lambda *args, **kwargs: SimpleNamespace(text=json.dumps(value)))
    requirements = {'_document_identity': {'company_name': 'Bajaj Motors', 'project_title': 'Voice inspection'}}
    with patch('app.diagram.conceptual_drawio.render_drawio', side_effect=lambda xml: (b'png', xml, {})):
        result = generate(llm, None, requirements, 'Source mentions another company', {})
    assert result['plan']['title'] == 'Bajaj Motors: Voice inspection'
    assert 'TVS Motor' not in result['drawio_xml']
