from pathlib import Path
from docx import Document
from app.core.section_formats import sequence_gantt_rows, sequence_gantt_markdown
from app.document.document_builder import DocumentBuilder, BRAND_BLUE
from app.pricing.renderer import render_aws_pricing_section


def test_hypercare_uses_project_clock_and_preserves_two_week_duration():
    rows = [['S.No', 'Activity'] + [f'W{i}' for i in range(1, 9)],
            ['1', 'Production deployment'] + [''] * 7 + ['■'],
            ['2', 'Post-go-live support and hypercare'] + ['◆', '◆'] + [''] * 6]
    result = sequence_gantt_rows(rows)
    assert result[0][-2:] == ['W8', 'W9']
    assert result[2][2:9] == [''] * 7
    assert result[2][-2:] == ['◆', '◆']
    assert result[1][-2:] == ['■', '']
    assert len(rows[0]) == 10  # no mutation
    assert sequence_gantt_rows(result) == result


def test_unknown_go_live_preserves_explicit_support_dates_without_filling_blanks():
    rows = [['S.No', 'Activity', 'W1', 'W2'], ['1', 'Hypercare', '◆', '◆']]
    assert sequence_gantt_rows(rows) == rows
    blank = [['S.No', 'Activity', 'W1', 'W2'], ['1', 'Hypercare', '', '']]
    assert sequence_gantt_rows(blank) == blank


def test_correct_timeline_and_non_gantt_are_unchanged():
    rows = [['S.No', 'Activity', 'W1', 'W2'], ['1', 'Go-live', '■', ''],
            ['2', 'Hypercare', '', '◆']]
    assert sequence_gantt_rows(rows) == rows
    assert sequence_gantt_markdown('A normal paragraph.') == 'A normal paragraph.'


def test_headings_all_brand_blue_and_one_point_five_spacing():
    builder = DocumentBuilder.__new__(DocumentBuilder)
    builder.doc = Document()
    builder._configure_styles()
    for name in ['Heading 1', 'Heading 2', 'Heading 3', 'Heading 4']:
        assert str(builder.doc.styles[name].font.color.rgb) == BRAND_BLUE
        assert builder.doc.styles[name].paragraph_format.line_spacing == 1.5


def test_pricing_saved_link_precedes_tables_and_preserves_planning_range():
    from io import BytesIO
    from types import SimpleNamespace
    from docx.oxml.ns import qn
    from app.document.document_builder import SectionBuilder

    saved_url = 'https://calculator.aws/#/estimate?id=abc'
    text = render_aws_pricing_section({'status': 'hybrid_priced',
        'estimate_url': saved_url,
        'fallback_estimate': {'monthly_base': 6500, 'monthly_low': 2800, 'monthly_high': 15000}})
    assert '| Item | Monthly (USD) | Estimate |' in text
    assert '| AWS infrastructure | 6,500.00 | Workload planning estimate;' in text
    assert '| Monthly planning range | USD 2,800.00–15,000.00 |' in text
    lines = text.splitlines()
    assert lines[0] == f'AWS Pricing Calculator: [Open Link]({saved_url})'
    assert lines[1] == ''
    assert lines[2] == '| Item | Monthly (USD) | Estimate |'
    assert all(line.startswith('|') for line in lines[2:] if line.strip())
    assert '[AWS Pricing Calculator]' in text

    # Exercise Word export and reopen the saved package: visible link text
    # alone must not pass when its relationship or position is lost.
    doc = Document()
    builder = DocumentBuilder.__new__(DocumentBuilder)
    builder.doc = doc
    builder._configure_styles()
    SectionBuilder(doc, SimpleNamespace()).parse_content(text)
    package = BytesIO()
    doc.save(package)
    package.seek(0)
    exported = Document(package)
    children = list(exported.element.body)
    first_paragraph = next(child for child in children if child.tag == qn('w:p'))
    first_table = next(child for child in children if child.tag == qn('w:tbl'))
    assert children.index(first_paragraph) < children.index(first_table)
    assert ''.join(node.text or '' for node in first_paragraph.iter(qn('w:t'))) == 'AWS Pricing Calculator: Open Link'
    links = first_paragraph.findall(qn('w:hyperlink'))
    assert len(links) == 1
    assert ''.join(node.text or '' for node in links[0].iter(qn('w:t'))) == 'Open Link'
    relation = exported.part.rels[links[0].get(qn('r:id'))]
    assert relation.is_external and relation.target_ref == saved_url
    assert exported.tables[0].cell(1, 1).text == '6,500.00'
    assert any(row.cells[0].text == 'Monthly planning range'
               and row.cells[1].text == 'USD 2,800.00–15,000.00'
               for table in exported.tables for row in table.rows)
