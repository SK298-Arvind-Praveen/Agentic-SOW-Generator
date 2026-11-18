"""Export live pricing results through the production Word table renderer."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from docx import Document
from docx.oxml.ns import qn
from app.document.document_builder import DocumentBuilder,SectionBuilder
from app.pricing.renderer import render_aws_pricing_section

for company in ('kingfisher','apollo','halfords'):
    directory=Path('output')/f'pricing-estimated-{company}'
    result=json.loads((directory/'result.json').read_text(encoding='utf8'))
    assert result['status']=='priced',company
    doc=Document();builder=DocumentBuilder(SimpleNamespace());builder.doc=doc;builder._configure_styles()
    doc.add_heading('AWS Pricing',level=1)
    SectionBuilder(doc,SimpleNamespace()).parse_content(render_aws_pricing_section(result))
    assert all(c.text.strip() for t in doc.tables for r in t.rows for c in r.cells),company
    assert any(r.target_ref==result['estimate_url'] for r in doc.part.rels.values())
    body=list(doc.element.body)
    first_table=next(i for i,e in enumerate(body) if e.tag==qn('w:tbl'))
    assert any('Open Link' in ''.join(e.itertext()) for e in body[:first_table])
    doc.save(directory/'pricing-validation.docx')
    print(company,len(doc.tables),sum(len(t.rows)-1 for t in doc.tables),'table rows validated')
