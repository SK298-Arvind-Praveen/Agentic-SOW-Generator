from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest

from app.diagram.process_flow import enabled,annotate
from app.diagram.service import DiagramSpec,Node,Edge


def test_toggle_defaults_off_and_accepts_on_off():
    assert not enabled(SimpleNamespace())
    for value in ('off','false','0',False):assert not enabled(SimpleNamespace(ARCHITECTURE_PROCESS_FLOW=value))
    for value in ('on','true','1',True):assert enabled(SimpleNamespace(ARCHITECTURE_PROCESS_FLOW=value))


def test_all_connector_captions_removed_without_touching_service_labels():
    from app.diagram.process_flow import remove_line_labels
    xml='<mxfile><diagram><mxGraphModel><root><mxCell id="edge_1" edge="1" value="SQL"/><mxCell id="flow_caption_1" value="Forward"/><mxCell id="interface_caption_1" value="HTTPS"/><mxCell id="label_db" value="Database"/></root></mxGraphModel></diagram></mxfile>'
    result=remove_line_labels(xml)
    root=ET.fromstring(result)
    assert root.find('.//mxCell[@edge="1"]').get('value')==''
    assert 'Forward' not in result and 'HTTPS' not in result and 'SQL' not in result
    assert root.find('.//mxCell[@id="label_db"]').get('value')=='Database'


def test_fanout_ports_stay_on_visible_icon():
    from app.diagram.review import local_routes
    spec=DiagramSpec('Ports',tuple(Node(k,k,'service',0,icon_key='icon') for k in ('a','b','c')),
        (Edge('a','b'),Edge('a','c')))
    positions={'a':(30,30,100,100),'b':(250,30,100,100),'c':(250,200,100,100)}
    paths=local_routes(spec,positions,{}, {},500,400,iconic=True,icon_bottom=True,
        terminal_sides={('a','b'):{'a':{'right'}},('a','c'):{'a':{'right'}}})
    assert all(abs((path[0][0]-80)**2+(path[0][1]-62)**2-26**2)<0.01 for path in paths)


def test_process_legend_preserves_graph_and_matches_numbered_relationships():
    from app.diagram.run_manifest import assert_process_flow_acceptance

    spec=DiagramSpec('Test',(Node('a','Client','actor',0,scope='external'),Node('b','API','service',1)),(Edge('a','b','HTTPS request'),))
    spec.architecture_plan['process_story']={'steps':[{'id':'s1','title':'Application access',
        'description':'Client sends application traffic through the secure API.',
        'node_ids':['a','b'],'edge_ids':['e0'],'flow_kind':'ingress'}]}
    xml='''<mxfile><diagram><mxGraphModel pageWidth="500" pageHeight="500"><root>
    <mxCell id="0"/><mxCell id="1" parent="0"/>
    <mxCell id="a" vertex="1" parent="1"><mxGeometry x="10" y="10" width="60" height="60"/></mxCell>
    <mxCell id="b" vertex="1" parent="1"><mxGeometry x="10" y="300" width="60" height="60"/></mxCell>
    <mxCell id="flow_0" edge="1" parent="1" sourceNode="a" targetNode="b"><mxGeometry relative="1"><mxPoint as="sourcePoint" x="40" y="70"/><mxPoint as="targetPoint" x="40" y="300"/></mxGeometry></mxCell>
    </root></mxGraphModel></diagram></mxfile>'''
    result,steps=annotate(xml,spec);root=ET.fromstring(result)
    assert len(root.findall('.//mxCell[@edge="1"]'))==1
    assert steps[0]['source']=='a' and steps[0]['target']=='b' and steps[0]['action']=='HTTPS request'
    assert root.find('.//mxCell[@id="process_flow_marker_1"]') is not None
    assert steps[0]['heading']=='Application access'
    assert steps[0]['description']=='Client sends application traffic through the secure API.'
    assert '&lt;b&gt;Application access&lt;/b&gt;' in result
    assert annotate(result,spec)[0]==result
    assert_process_flow_acceptance({'drawio_xml': result, 'spec': spec.as_dict(),
                                    'renderer_details': {'process_flow': steps}}, True)


def test_download_embeds_the_complete_process_flow_image():
    import base64,io,zipfile
    from PIL import Image
    from docx import Document
    from app.document.document_builder import DocumentBuilder
    image=io.BytesIO();Image.new('RGB',(1400,900),'white').save(image,format='PNG')
    payload=image.getvalue()
    builder=DocumentBuilder(SimpleNamespace());builder.doc=Document();builder._configure_styles()
    builder._add_architecture_diagram({'diagram_type':'architecture_overview',
        'image_base64':base64.b64encode(payload).decode(),'renderer_details':{'process_flow':[{'number':1}]}})
    output=io.BytesIO();builder.doc.save(output)
    with zipfile.ZipFile(output) as archive:
        assert archive.read('word/media/image1.png')==payload


def test_grouped_overview_connectors_are_traceable_without_changing_architecture():
    spec=DiagramSpec('Grouped',(Node('client','Customer','actor',0,scope='external'),
        Node('api','API','service',1),Node('worker','Worker','service',1)),
        (Edge('client','api','Send message'),Edge('api','worker','Invoke')),
        architecture_plan={'narrative_view':{'groups':[{'id':'chat','label':'Conversation Service','rows':[['api','worker']]}],
            'support':[],'roles':{},'links':[{'source':'client','target':'chat','label':'Send message'}]}})
    spec.architecture_plan['process_story']={'steps':[{'id':'s1','title':'Customer conversation',
        'description':'Customers send questions to the Conversation Service for assistance.',
        'node_ids':['client','api'],'edge_ids':['e0'],'flow_kind':'runtime'}]}
    xml='''<mxfile><diagram><mxGraphModel pageWidth="600" pageHeight="600"><root><mxCell id="0"/><mxCell id="1" parent="0"/>
    <mxCell id="cloud" vertex="1" parent="1"><mxGeometry x="10" y="100" width="560" height="450"/></mxCell>
    <mxCell id="client" vertex="1" parent="1"><mxGeometry x="10" y="10" width="50" height="50"/></mxCell>
    <mxCell id="chat" vertex="1" parent="1"><mxGeometry x="100" y="200" width="300" height="200"/></mxCell>
    <mxCell id="overview_link_0" edge="1" overviewSource="client" overviewTarget="chat" parent="1"><mxGeometry relative="1"><mxPoint as="sourcePoint" x="35" y="60"/><mxPoint as="targetPoint" x="100" y="200"/></mxGeometry></mxCell>
    </root></mxGraphModel></diagram></mxfile>'''
    result,steps=annotate(xml,spec)
    assert steps and steps[0]['source']=='client' and steps[0]['target']=='chat'
    assert steps[0]['edge_indices']==[0]
    assert 'Conversation Service' in result
    assert len(ET.fromstring(result).findall('.//mxCell[@edge="1"]'))==1


def test_decoration_failure_retains_primary_image_and_reports_warning(monkeypatch):
    from app.diagram import process_flow
    monkeypatch.setattr(process_flow,'annotate',lambda *args: (_ for _ in ()).throw(ValueError('bad annotation')))
    spec=DiagramSpec('Test',(Node('a','Service','service',0),),())
    png,xml,details=process_flow.decorate(b'primary','<mxfile/>',spec,
        SimpleNamespace(ARCHITECTURE_PROCESS_FLOW=True),lambda *a,**kw: (_ for _ in ()).throw(TimeoutError('export')))
    assert png==b'primary' and xml=='<mxfile/>'
    assert details['decoration_warnings'] and details['process_flow']==[]


def test_knowledge_sync_is_not_described_as_database_replication():
    from app.diagram.process_flow import describe
    nodes={'a':Node('a','Conversation service','service',0),
        'b':Node('b','Knowledge answering','service',1)}
    heading,sentence=describe(Edge('a','b','Retrieve / scheduled sync'),nodes)
    assert 'Database' not in heading and 'standby' not in sentence


def test_document_workflow_summaries_do_not_assume_migration_or_generic_interactions():
    from app.diagram.process_flow import describe
    nodes={'a':Node('a','Data Custodian','actor',0,scope='external'),
        'b':Node('b','Intake and Validation','service',1)}
    for label in ('Upload cohort','Start job','Export dataset','Open workbench','Fetch UI assets','Review actions','Review session'):
        heading,sentence=describe(Edge('a','b',label),nodes)
        assert heading!='Service interaction'
        assert 'migration' not in sentence.lower()


def test_decorated_export_retries_once_and_keeps_primary_if_both_fail():
    from app.diagram.process_flow import decorate
    calls=[]
    def render(*args,**kwargs):calls.append(1);raise TimeoutError('renderer down')
    png,xml,details=decorate(b'valid','<mxfile/>',DiagramSpec('Empty',(),()),
        SimpleNamespace(ARCHITECTURE_PROCESS_FLOW=False),render)
    assert png==b'valid' and xml=='<mxfile/>' and len(calls)==2
    assert details['decoration_warnings']


def test_generic_transport_and_ingestion_do_not_invent_private_or_knowledge_semantics():
    from app.diagram.process_flow import describe
    nodes={'client':Node('client','Customer','actor',0,scope='external'),
           'api':Node('api','API','service',1),
           'db':Node('db','Database','service',2)}
    heading,sentence=describe(Edge('client','api','HTTPS request'),nodes)
    assert 'private' not in (heading+sentence).lower()
    heading,sentence=describe(Edge('api','db','Ingest telemetry events'),nodes)
    assert 'telemetry' in sentence and 'knowledge' not in (heading+sentence).lower()
    heading,sentence=describe(Edge('api','db','Sync customer records'),nodes)
    assert 'customer records' in sentence
    assert 'standby' not in sentence and 'knowledge' not in (heading+sentence).lower()


def test_bidirectional_grouped_connection_preserves_both_actions_and_provenance():
    spec=DiagramSpec('Exchange',
        (Node('client','Customer','actor',0,scope='external'),Node('api','API','service',1)),
        (Edge('client','api','Send message'),Edge('api','client','Send reply')),
        architecture_plan={'narrative_view':{
            'groups':[{'id':'chat','label':'Conversation service','rows':[['api']]}],
            'links':[{'source':'client','target':'chat','label':'Send message'},
                     {'source':'chat','target':'client','label':'Send reply'}]}})
    spec.architecture_plan['process_story']={'steps':[{'id':'s1','title':'Customer conversation',
        'description':'Customer passes customer messages to Conversation service and receives replies back.',
        'node_ids':['client','api'],'edge_ids':['e0','e1'],'flow_kind':'runtime'}]}
    xml='''<mxfile><diagram><mxGraphModel pageWidth="600" pageHeight="600"><root>
    <mxCell id="0"/><mxCell id="1" parent="0"/>
    <mxCell id="overview_link_0" edge="1" overviewSource="client" overviewTarget="chat" parent="1" style="startArrow=block;endArrow=block;">
    <mxGeometry relative="1"><mxPoint as="sourcePoint" x="35" y="60"/><mxPoint as="targetPoint" x="100" y="200"/></mxGeometry></mxCell>
    </root></mxGraphModel></diagram></mxfile>'''
    result,steps=annotate(xml,spec)
    assert steps[0]['edge_indices']==[0,1]
    assert steps[0]['directions']==[
        {'source':'client','target':'api','action':'Send message','edge_index':0},
        {'source':'api','target':'client','action':'Send reply','edge_index':1},
    ]
    assert 'Customer passes customer messages to Conversation service' in steps[0]['description']
    assert 'receives replies back' in steps[0]['description']
    assert steps[0]['description'].count('.')==1
    assert 'Send message' in steps[0]['action'] and 'Send reply' in steps[0]['action']
    assert ET.fromstring(result).find('.//mxCell[@edge="1"]').get('style')=='startArrow=block;endArrow=block;'
    # A separately drawn one-way connector must not absorb its reverse link.
    _,one_way=annotate(xml.replace('startArrow=block;','startArrow=none;'),spec)
    assert one_way[0]['edge_indices']==[0]
    assert len(one_way[0]['directions'])==1


def test_internal_process_marker_stays_beside_wire_below_boundary_header():
    spec = DiagramSpec('Nested compute', (Node('a', 'Queue', 'service', 0), Node('b', 'Worker', 'service', 0)),
        (Edge('a', 'b', 'Enqueue work'),), architecture_plan={
            'narrative_view': {'groups': [{'id': 'processing', 'label': 'Processing', 'rows': [['a', 'b']]}]},
            'process_story': {'steps': [
                {'id': 'jobs', 'title': 'Process queued jobs', 'description': 'The worker processes jobs from the queue.',
                 'node_ids': ['a', 'b'], 'edge_ids': ['e0'], 'flow_kind': 'runtime'},
            ]},
        })
    xml = '''<mxfile><diagram><mxGraphModel pageWidth="500" pageHeight="400"><root>
    <mxCell id="0"/><mxCell id="1" parent="0"/>
    <mxCell id="processing" vertex="1" parent="1" value="Processing" style="verticalAlign=top;">
        <mxGeometry x="30" y="40" width="440" height="280"/></mxCell>
    <mxCell id="vpc" vertex="1" parent="processing" value="VPC" style="verticalAlign=top;">
        <mxGeometry x="15" y="45" width="410" height="200"/></mxCell>
    <mxCell id="a" vertex="1" parent="vpc"><mxGeometry x="20" y="32" width="60" height="60"/></mxCell>
    <mxCell id="b" vertex="1" parent="vpc"><mxGeometry x="290" y="32" width="60" height="60"/></mxCell>
    <mxCell id="flow_0" edge="1" parent="1" sourceNode="a" targetNode="b" originalEdgePaths="[[0]]">
        <mxGeometry relative="1"><mxPoint as="sourcePoint" x="125" y="135"/>
        <mxPoint as="targetPoint" x="335" y="135"/></mxGeometry></mxCell>
    </root></mxGraphModel></diagram></mxfile>'''

    result, _ = annotate(xml, spec)
    marker = ET.fromstring(result).find('.//mxCell[@id="process_flow_marker_1"]')
    assert marker.get('parent') == '1'
    assert marker.get('processFlowConnector') == 'flow_0'
    geometry = marker.find('mxGeometry')
    x, y, width, height = (float(geometry.get(k)) for k in ('x', 'y', 'width', 'height'))
    assert 125 <= x < x + width <= 335
    assert 135 < y <= 155 and y + height < 285


def test_internal_process_marker_uses_narrow_gap_between_service_rows():
    spec = DiagramSpec('Staged articles', tuple(Node(k, k, 'service', 0) for k in ('a', 'b', 'c', 'd')),
        (Edge('a', 'd', 'Load articles'),), architecture_plan={'process_story': {'steps': [
            {'id': 'articles', 'title': 'Load staged articles', 'description': 'The reader loads articles from the source.',
             'node_ids': ['a', 'd'], 'edge_ids': ['e0'], 'flow_kind': 'ingestion'},
        ]}})
    xml = '''<mxfile><diagram><mxGraphModel pageWidth="500" pageHeight="420"><root>
    <mxCell id="0"/><mxCell id="1" parent="0"/>
    <mxCell id="a" vertex="1" parent="1"><mxGeometry x="36" y="112" width="192" height="104"/></mxCell>
    <mxCell id="b" vertex="1" parent="1"><mxGeometry x="264" y="112" width="192" height="104"/></mxCell>
    <mxCell id="c" vertex="1" parent="1"><mxGeometry x="36" y="262" width="192" height="104"/></mxCell>
    <mxCell id="d" vertex="1" parent="1"><mxGeometry x="264" y="262" width="192" height="104"/></mxCell>
    <mxCell id="flow_0" edge="1" parent="1" sourceNode="a" targetNode="d" originalEdgePaths="[[0]]">
        <mxGeometry relative="1"><mxPoint as="sourcePoint" x="158" y="144"/>
        <Array as="points"><mxPoint x="244" y="144"/><mxPoint x="244" y="294"/></Array>
        <mxPoint as="targetPoint" x="334" y="294"/></mxGeometry></mxCell>
    </root></mxGraphModel></diagram></mxfile>'''

    result, _ = annotate(xml, spec)
    marker = ET.fromstring(result).find('.//mxCell[@id="process_flow_marker_1"]')
    assert marker.get('parent') == '1'
    geometry = marker.find('mxGeometry')
    x, y, width, height = (float(geometry.get(k)) for k in ('x', 'y', 'width', 'height'))
    assert 216 <= y < y + height <= 262
    assert min(abs(x - 244), abs(x + width - 244)) <= 10


@pytest.fixture
def tight_process_asset():
    spec = DiagramSpec('Reciprocal', tuple(Node(k, k, 'service', 0) for k in ('a', 'b', 'c')),
        (Edge('a', 'b', 'Request'), Edge('b', 'a', 'Reply'), Edge('b', 'c', 'Report')),
        architecture_plan={'process_story': {'steps': [
            {'id': 'request', 'edge_ids': ['e0'], 'node_ids': ['a', 'b'], 'flow_kind': 'runtime',
             'title': 'Send request', 'description': 'First service sends the request for processing.'},
            {'id': 'reply', 'edge_ids': ['e1'], 'node_ids': ['a', 'b'], 'flow_kind': 'runtime',
             'title': 'Receive reply', 'description': 'Second service returns the reply after processing.'},
        ]}})
    xml = '''<mxfile><diagram><mxGraphModel pageWidth="500" pageHeight="500"><root>
    <mxCell id="0"/><mxCell id="1" parent="0"/>
    <mxCell id="a" vertex="1" parent="1"><mxGeometry x="0" y="0" width="100" height="110"/></mxCell>
    <mxCell id="b" vertex="1" parent="1"><mxGeometry x="0" y="114" width="100" height="110"/></mxCell>
    <mxCell id="c" vertex="1" parent="1"><mxGeometry x="0" y="300" width="100" height="100"/></mxCell>
    <mxCell id="flow_0" edge="1" parent="1" sourceNode="a" targetNode="b" value=""
            originalEdgePaths="[[0],[1]]" style="startArrow=block;endArrow=block;">
    <mxGeometry relative="1"><mxPoint as="sourcePoint" x="50" y="110"/><mxPoint as="targetPoint" x="50" y="114"/></mxGeometry></mxCell>
    <mxCell id="flow_1" edge="1" parent="1" sourceNode="b" targetNode="c" value="" originalEdgePaths="[[2]]">
    <mxGeometry relative="1"><mxPoint as="sourcePoint" x="50" y="224"/><mxPoint as="targetPoint" x="50" y="300"/></mxGeometry></mxCell>
    </root></mxGraphModel></diagram></mxfile>'''
    result, steps = annotate(xml, spec)
    return {'drawio_xml': result, 'spec': spec.as_dict(), 'renderer_details': {'process_flow': steps}}


def test_reciprocal_tight_route_keeps_both_numbered_markers(tight_process_asset):
    from app.diagram.run_manifest import assert_process_flow_acceptance

    document = ET.fromstring(tight_process_asset['drawio_xml'])
    markers = document.findall('.//mxCell[@vertex="1"][@parent="flow_0"]')
    assert [marker.get('value') for marker in markers] == ['1', '2']
    assert [marker.get('processFlowStep') for marker in markers] == ['request', 'reply']
    offsets = [tuple(float(marker.find('mxGeometry/mxPoint[@as="offset"]').get(k)) for k in ('x', 'y'))
               for marker in markers]
    assert any(abs(a - b) >= 30 for a, b in zip(*offsets))
    assert all(not edge.get('value') for edge in document.findall('.//mxCell[@edge="1"]'))
    assert_process_flow_acceptance(tight_process_asset, True)


@pytest.mark.parametrize('mutation', ['missing', 'misattached', 'unrelated', 'unrelated_floating', 'hidden'])
def test_process_acceptance_checks_every_visible_marker_against_its_connector(tight_process_asset, mutation):
    from app.diagram.run_manifest import assert_process_flow_acceptance

    document = ET.fromstring(tight_process_asset['drawio_xml'])
    root = document.find('./diagram/mxGraphModel/root')
    marker = root.find('mxCell[@id="process_flow_marker_1"]')
    if marker is not None:
        if mutation == 'missing':
            root.remove(marker)
        elif mutation == 'misattached':
            marker.set('parent', 'flow_1')
        elif mutation == 'unrelated':
            marker.set('parent', 'flow_1')
            marker.set('processFlowConnector', 'flow_1')
        elif mutation == 'unrelated_floating':
            marker.set('parent', '1')
            marker.find('mxGeometry').attrib.pop('relative')
            marker.set('processFlowConnector', 'flow_1')
        else:
            marker.set('visible', '0')
    tight_process_asset['drawio_xml'] = ET.tostring(document, encoding='unicode')
    with pytest.raises(AssertionError, match='marker'):
        assert_process_flow_acceptance(tight_process_asset, True)
