from pathlib import Path
from docx import Document
from app.core.section_formats import sequence_gantt_rows, sequence_gantt_markdown
from app.document.document_builder import DocumentBuilder, PURPLE
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


def test_unknown_go_live_does_not_invent_support_dates():
    rows = [['S.No', 'Activity', 'W1', 'W2'], ['1', 'Hypercare', '◆', '◆']]
    assert sequence_gantt_rows(rows)[1][2:] == ['', '']


def test_correct_timeline_and_non_gantt_are_unchanged():
    rows = [['S.No', 'Activity', 'W1', 'W2'], ['1', 'Go-live', '■', ''],
            ['2', 'Hypercare', '', '◆']]
    assert sequence_gantt_rows(rows) == rows
    assert sequence_gantt_markdown('A normal paragraph.') == 'A normal paragraph.'


def test_headings_all_purple_and_one_point_five_spacing():
    builder = DocumentBuilder.__new__(DocumentBuilder)
    builder.doc = Document()
    builder._configure_styles()
    for name in ['Heading 1', 'Heading 2', 'Heading 3', 'Heading 4']:
        assert str(builder.doc.styles[name].font.color.rgb) == PURPLE
        assert builder.doc.styles[name].paragraph_format.line_spacing == 1.5


def test_pricing_is_one_text_table_with_range_outside_cells():
    text = render_aws_pricing_section({'status': 'hybrid_priced',
        'estimate_url': 'https://calculator.aws/#/estimate?id=abc',
        'fallback_estimate': {'monthly_base': 6500, 'monthly_low': 2800, 'monthly_high': 15000}})
    assert '| Item | Monthly (USD) | Estimate |' in text
    assert '| AWS infrastructure | 6,500.00 | Workload planning estimate;' in text
    assert '| Monthly planning range | USD 2,800.00' in text
    assert all(line.startswith('|') for line in text.splitlines() if line.strip())
    assert '[AWS Pricing Calculator]' in text
