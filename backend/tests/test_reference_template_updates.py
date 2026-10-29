import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.agents.poc_writer_agent import POCWriterAgent
from app.core.sow_editorial import strip_bullet_leadins
from app.core.sow_section_preferences import parse_selected_section_ids, OPTIONAL_SECTION_IDS
from app.diagram.service import DiagramService, DiagramSpec, Node, Edge
from app.diagram.review import routes, geometry_report


def test_static_clauses_match_reference_transcriptions_in_every_mode():
    root = Path(__file__).resolve().parents[1] / 'templates'
    reference = json.loads((root / 'reference_static_sections.json').read_text(encoding='utf-8'))
    titles = {'service_agreement': 'Service Agreement', 'change_order': 'Change Order',
              'project_plan_termination': 'Project Plan Termination', 'marketing_authorization': 'Marketing Authorization',
              'terms_conditions': 'Terms & Conditions'}
    for filename in ('poc_template.md','production_template.md','poc_to_prod_template.md'):
        agent = POCWriterAgent.__new__(POCWriterAgent)
        agent.template_raw = (root / filename).read_text(encoding='utf-8')
        parsed = agent._parse_template()
        sections = {s.name:s for s in parsed}
        for key,title in titles.items():
            assert sections[title].section_type.value == 'STATIC'
            assert sections[title].content.strip() == reference[key]
        order = list(sections)
        arch = next(t for t in order if 'Architecture' in t)
        assert order.index(arch) < order.index('Scope of Work')
        tail = ['Roles and Responsibilities','Change Order','Project Plan Termination','Contacts and Reporting','Marketing Authorization','Terms & Conditions']
        assert [order.index(t) for t in tail] == sorted(order.index(t) for t in tail)


def test_bold_mini_headlines_are_removed_but_emphasis_and_tables_survive():
    assert strip_bullet_leadins('- **Commerce and order data**: SAP Hybris holds order data.') == '- SAP Hybris holds order data.'
    assert strip_bullet_leadins('- **Monitoring:** Configure alerts.') == '- Configure alerts.'
    assert strip_bullet_leadins('- **SAP Hybris** holds orders.') == '- **SAP Hybris** holds orders.'
    assert strip_bullet_leadins('| **Role** | Owner |') == '| **Role** | Owner |'


def test_new_sections_and_architecture_order():
    for item in ('service_agreement','business_benefits','raci_matrix','change_order','marketing_authorization'):
        assert item in OPTIONAL_SECTION_IDS
    assert parse_selected_section_ids(['scope_of_work','architecture_diagram'],'POC') == ['architecture_diagram','scope_of_work']


def test_architecture_is_written_before_scope_and_shared_without_renaming_saved_ids():
    from types import MethodType
    from app.agents.poc_writer_agent import TemplateSection
    from app.core.sow_section_preferences import SECTION_LABELS
    agent = POCWriterAgent.__new__(POCWriterAgent)
    agent.config = SimpleNamespace(SOW_SECTION_WORKERS=3)
    agent.template_type = 'POC'
    agent.global_template_contract = ''
    agent.sections = [TemplateSection('Scope of Work', '', {'type': 'GENERATED'}, 0),
                      TemplateSection('Solution Architecture', '', {'type': 'GENERATED'}, 1)]
    calls = []
    def generate(self, section, *args):
        calls.append(section.name)
        if section.name == 'Solution Architecture':
            return 'Amazon S3 stores documents; Amazon Textract extracts fields for review.'
        assert 'Amazon Textract' in self.solution_architecture_context
        return '- Connect document extraction to the review workflow.'
    agent._generate_section = MethodType(generate, agent)
    agent._review_document_relevance = lambda *args: set()
    progress = []
    output = agent.generate_poc({}, {'company_name': 'Test', 'project_title': 'Demo'},
        selected_sow_sections=['scope_of_work', 'architecture_diagram'], scope_architecture_plan={},
        progress_callback=lambda n,total,name: progress.append((n,total)))
    assert calls == ['Solution Architecture', 'Scope of Work']
    assert 'architecture_diagram' in output
    assert SECTION_LABELS['architecture_diagram'] == 'Solution Architecture'
    assert progress == [(1,2),(2,2)]


def test_routes_keep_connections_and_avoid_middle_node():
    spec = DiagramSpec('Test', (Node('a','A','process',0),Node('b','B','process',1),Node('c','C','process',2)), (Edge('a','c'),))
    positions = {'a':(10,150,100,60),'b':(170,150,100,60),'c':(330,150,100,60)}
    paths = routes(spec,positions)
    assert len(paths) == len(spec.edges)
    assert geometry_report(spec,positions,paths)['connector_node_intersections'] == 0


def test_asset_rendering_does_not_invoke_a_visual_reviewer():
    import io
    from PIL import Image
    png = io.BytesIO()
    Image.new('RGB',(100,100),'white').save(png,format='PNG')
    spec = DiagramSpec('Test',(Node('a','A','process',0),Node('b','B','process',1)),(Edge('a','b'),))
    service = DiagramService.__new__(DiagramService)
    service.config = SimpleNamespace()
    service.icon_registry = None
    service.llm = Mock()
    with patch('app.diagram.service.render_png',return_value=png.getvalue()):
        asset = service._asset('data_flow', 'Scope of Work', spec, {}, False)
    assert asset['spec'] == spec.as_dict()
    assert asset['image_base64']
    assert asset['drawio_xml']
    assert 'review' not in asset
    service.llm.generate.assert_not_called()
