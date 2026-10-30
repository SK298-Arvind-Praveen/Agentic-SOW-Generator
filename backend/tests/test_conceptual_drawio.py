import json
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
    assert any('TYPICAL END-TO-END' in c.get('value','') for c in cells)


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
