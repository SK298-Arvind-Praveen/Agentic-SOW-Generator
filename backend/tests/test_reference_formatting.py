from pathlib import Path
from types import SimpleNamespace
import zipfile
from docx import Document
from docx.oxml.ns import qn
from app.document.document_builder import DocumentBuilder, _embed_dm_sans
from app.pricing.renderer import render_aws_pricing_section


def test_typography_and_font_embedding(tmp_path):
    builder = DocumentBuilder.__new__(DocumentBuilder)
    builder.doc = Document()
    builder._configure_styles()
    for name, face, size in [('Normal', 'Albert Sans', 11), ('Heading 1', 'Space Grotesk', 20),
                              ('Heading 2', 'Albert Sans', 16), ('Heading 3', 'Albert Sans', 14)]:
        style = builder.doc.styles[name]
        assert style.font.name == face
        assert style.font.size.pt == size
        assert not style.element.xpath('.//w:pBdr')
    assert builder.doc.styles['Normal'].paragraph_format.line_spacing == 1.5
    output = tmp_path / 'fonts.docx'
    builder.doc.save(output)
    config = SimpleNamespace(ASSETS_DIR=Path(__file__).resolve().parents[1] / 'assets')
    for family in ('Albert Sans', 'Space Grotesk'):
        _embed_dm_sans(output, config, family)
    with zipfile.ZipFile(output) as archive:
        for family in ('AlbertSans', 'SpaceGrotesk'):
            for face in ('Regular', 'Bold'):
                assert len(archive.read(f'word/fonts/{family}-{face}.odttf')) > 1000


def test_compact_pricing_with_clickable_estimate_and_no_duplicate_totals():
    text = render_aws_pricing_section({'status': 'priced', 'monthly_cost': 2978.27,
        'currency': 'USD', 'estimate_url': 'https://calculator.aws/#/estimate?id=abc',
        'volume_metrics': [{'metric': 'Monthly audio minutes', 'value': '10000000'}]})
    assert '| Item | Monthly (USD) | Estimate |' in text
    assert '[AWS Pricing Calculator](https://calculator.aws/#/estimate?id=abc)' in text
    assert text.count('2,978.27') == 1
    assert '| Monthly audio minutes | 10000000 |' in text
    assert 'ARR' not in text and 'MRR' not in text and '| Metric |' not in text


def test_blank_stale_partial_and_fallback_are_honest():
    assert '| AWS infrastructure |  |  |' in render_aws_pricing_section({'status': 'stale', 'monthly_cost': 99})
    partial = render_aws_pricing_section({'status': 'partial_priced', 'calculator_monthly_cost': 1})
    assert 'components only | 1.00' in partial and 'total |  |' in partial
    fallback = render_aws_pricing_section({'status': 'fallback_priced', 'fallback_estimate': {'monthly_base': 150}})
    assert 'Workload planning estimate' in fallback and 'not an AWS quote' in fallback
    assert '[AWS Pricing Calculator]' not in fallback


def test_template_contracts_use_new_table():
    for file in ('poc_template.md', 'production_template.md', 'poc_to_prod_template.md'):
        text = (Path(__file__).resolve().parents[1] / 'templates' / file).read_text(encoding='utf-8')
        assert '| Item | Monthly (<actual currency>) | Estimate |' in text


def test_calculator_markdown_link_renders_as_named_word_hyperlink():
    from app.document.document_builder import SectionBuilder
    doc = Document()
    builder = SectionBuilder.__new__(SectionBuilder)
    builder.doc = doc
    paragraph = doc.add_paragraph()
    builder._add_rich_runs(paragraph, '[AWS Pricing Calculator](https://calculator.aws/#/estimate?id=abc)')
    assert paragraph._p.xpath('.//w:hyperlink/w:r/w:t')[0].text == 'AWS Pricing Calculator'
    assert not paragraph._p.xpath('./w:r/w:t')


def test_top_headings_have_no_rules():
    # These entry points create the TOC title and section title directly.
    import inspect
    assert '_set_paragraph_bottom_border' not in inspect.getsource(DocumentBuilder._build_section)
