import base64
import io
from types import SimpleNamespace

from app.diagram.service import DiagramSpec, Node, Edge


def test_icon_bottom_preference_cannot_attach_to_empty_caption_space():
    from app.diagram.review import local_routes
    spec = DiagramSpec('Ports', tuple(Node(k, k, 'service', 0, icon_key='icon') for k in ('a','b')), (Edge('a','b'),))
    positions = {'a': (30,30,100,130), 'b': (30,250,100,130)}
    for preference in (False, True):
        path = local_routes(spec, positions, {}, {}, 500,500, iconic=True, icon_bottom=preference)[0]
        for key, (x,y) in [('a',path[0]), ('b',path[-1])]:
            px,py,pw,ph = positions[key]
            assert py <= y <= py+64, 'Connector attached below the visible icon'


def test_word_uses_a_dedicated_readable_figure_page_and_restores_page_setup():
    from PIL import Image
    from docx import Document
    from app.document.document_builder import DocumentBuilder
    image=io.BytesIO();Image.new('RGB',(2400,1500),'white').save(image,format='PNG')
    builder=DocumentBuilder(SimpleNamespace());builder.doc=Document();builder._configure_styles()
    original=(builder.doc.sections[-1].page_width,builder.doc.sections[-1].page_height)
    builder._add_architecture_diagram({'diagram_type':'architecture_overview',
        'image_base64':base64.b64encode(image.getvalue()).decode(),
        'renderer_details':{'process_flow':[{'number':1}]}})
    assert len(builder.doc.sections)>=3
    assert builder.doc.inline_shapes[0].width/914400 >= 9
    assert (builder.doc.sections[-1].page_width,builder.doc.sections[-1].page_height)==original


def test_figure_heading_moves_with_image_and_page_numbers_continue():
    from PIL import Image
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from app.document.document_builder import DocumentBuilder
    image=io.BytesIO();Image.new('RGB',(2400,1500),'white').save(image,format='PNG')
    builder=DocumentBuilder(SimpleNamespace());builder.doc=Document();builder._configure_styles()
    page_number=OxmlElement('w:pgNumType');page_number.set(qn('w:start'),'1')
    builder.doc.sections[0]._sectPr.append(page_number)
    builder.doc.add_paragraph('Previous content')
    heading=builder.doc.add_paragraph('Solution Architecture', style='Heading 1')
    builder._add_architecture_diagram({'diagram_type':'architecture_overview',
        'image_base64':base64.b64encode(image.getvalue()).decode()}, heading=heading)
    preceding=heading._p.getprevious()
    assert preceding.find('.//'+qn('w:sectPr')) is not None
    assert heading._p.getnext().find('.//'+qn('w:drawing')) is not None
    picture_paragraph = next(p for p in builder.doc.paragraphs if p._p.find('.//'+qn('w:drawing')) is not None)
    spacing = picture_paragraph.paragraph_format.line_spacing or picture_paragraph.style.paragraph_format.line_spacing
    assert spacing == 1, 'A 1.5-line picture paragraph overflows the physical figure page'
    for section in builder.doc.sections[1:]:
        pg=section._sectPr.find(qn('w:pgNumType'))
        assert pg is None or pg.get(qn('w:start')) is None


def test_visual_patch_cannot_remap_canonical_process_edge_ids():
    from app.agents.architecture_reviewer_agent import safe_layout_patch
    from app.diagram.contracts import freeze
    spec=DiagramSpec('Fixed story',(Node('app','App','service',0),Node('data','Data','service',1)),
        (Edge('app','data','Read'),Edge('data','app','Reply')),architecture_plan={
            'process_story':{'steps':[{'edge_ids':['e0']}]}})
    revised,decisions=safe_layout_patch(spec,{'edge_order':[1,0],'spacing_scale':1.1})
    assert freeze(revised)['version']==freeze(spec)['version']
    assert revised.edges==spec.edges and revised.spacing_scale==1.1
    assert next(d for d in decisions if d['field']=='edge_order')['status']=='rejected'
