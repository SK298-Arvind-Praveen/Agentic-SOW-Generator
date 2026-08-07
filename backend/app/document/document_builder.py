"""
Document Builder - DOCX Generation
Generates DOCX documents directly with precise styling and formatting.

All updates included:
- Continuous sections (no page breaks)
- Professional footer with page numbers
- Single bullets (no doubles)
- DM Sans font throughout
- Bigger table cells with padding
- White background for all table rows (no alternating gray)
"""

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image as PILImage, ImageDraw, ImageFont
from datetime import datetime
import re
import os
from pathlib import Path
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# SPACING CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

# Font sizes (pt)
_FS_H1      = 17     # Heading 1
_FS_H2      = 14     # Heading 2/3
_FS_BODY    = 11     # Body Text
_FS_TABLE   = 10     # Table cells

# Line-height multipliers
_LS_BODY    = 1.70
_LS_H1      = 1.57
_LS_BULLET  = 1.30

# Space before / after (pt)
_SB_H1      =  0     # Reduced from 3 to 0 for tighter spacing
_SA_H1      =  0
_SB_H2      =  6     # Reduced from 8 to 6 for tighter spacing
_SA_H2      =  0
_SB_BODY    =  6     # Reduced from 8 to 6 for tighter spacing
_SA_BODY    =  0
_SB_BULLET  =  6     # Reduced from 8 to 6 for tighter spacing
_SA_BULLET  =  0

# Bullet indents (pt)
_IND_BULLET1 = 20
_IND_BULLET2 = 30

# Page margins (inches)
_MARGIN_LEFT   = 1.0
_MARGIN_RIGHT  = 1.0
_MARGIN_TOP    = 1.0
_MARGIN_BOTTOM = 1.0


# ─────────────────────────────────────────────────────────────────────────────
# DOCX HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def add_toc_field(doc):
    """Add a Table of Contents field to the document."""
    paragraph = doc.add_paragraph()
    run = paragraph.add_run()
    fldChar = OxmlElement('w:fldChar')
    fldChar.set(qn('w:fldCharType'), 'begin')
    
    instrText = OxmlElement('w:instrText')
    instrText.set(qn('xml:space'), 'preserve')
    instrText.text = 'TOC \\o "1-3" \\h \\z \\u'
    
    fldChar2 = OxmlElement('w:fldChar')
    fldChar2.set(qn('w:fldCharType'), 'separate')
    
    fldChar3 = OxmlElement('w:fldChar')
    fldChar3.set(qn('w:fldCharType'), 'end')
    
    run._r.append(fldChar)
    run._r.append(instrText)
    run._r.append(fldChar2)
    run._r.append(fldChar3)
    
    return paragraph


def generate_cover_image(data, config):
    """Generate cover page image using PIL with high quality."""
    try:
        base_cover = config.COVER_PAGE_IMAGE
        if not base_cover.exists():
            print(f"⚠ Cover image not found: {base_cover}")
            return None
            
        # Open image and convert to RGBA
        img = PILImage.open(base_cover).convert("RGBA")
        
        # Target A4 dimensions at high DPI (300 DPI)
        target_width = int(8.27 * 300)  # 2481 pixels
        target_height = int(11.69 * 300)  # 3507 pixels
        
        # Resize to exact A4 dimensions for perfect fit
        img = img.resize((target_width, target_height), PILImage.Resampling.LANCZOS)
        
        W, H = img.size
        draw = ImageDraw.Draw(img)
        
        # Scale factors for A4 at 300 DPI
        scale_x = W / 595
        scale_y = H / 842
        
        def from_pdf(x, y):
            """Convert PDF coords to PIL coords"""
            return int(x * scale_x), int(H - (y * scale_y))
        
        # Try to use custom fonts with multiple fallback paths
        try:
            font_path = None
            possible_paths = [
                "C:/Windows/Fonts/arial.ttf",  # Windows
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Debian/Ubuntu
                "/usr/share/fonts/dejavu/DejaVuSans.ttf",  # Some Linux
                "/System/Library/Fonts/Helvetica.ttc",  # macOS
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",  # RHEL/CentOS
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    font_path = path
                    break
            
            if not font_path:
                raise FileNotFoundError("No suitable font found")
            
            # Fonts (scaled up for high resolution)
            title_font = ImageFont.truetype(font_path, int(39 * scale_y))
            subtitle_font = ImageFont.truetype(font_path, int(16 * scale_y))
            body_font = ImageFont.truetype(font_path, int(11 * scale_y))
            small_font = ImageFont.truetype(font_path, int(10 * scale_y))
            
            print(f"✓ Using font: {font_path}")
            
        except Exception as e:
            print(f"⚠ Font loading error: {e}, using default font")
            # Fallback to default font with proper sizing
            title_font = ImageFont.load_default()
            subtitle_font = ImageFont.load_default()
            body_font = ImageFont.load_default()
            small_font = ImageFont.load_default()
        
        # Company name - purple
        draw.text(
            from_pdf(40, 620),
            data.get('company_name', ''),
            fill=(123, 63, 242),
            font=title_font
        )
        
        # Project title - gray (increased spacing from 580 to 560 for more gap)
        draw.text(
            from_pdf(40, 560),
            data.get('project_title', ''),
            fill=(102, 102, 102),
            font=subtitle_font
        )
        
        # Bottom block - white text
        draw.text(from_pdf(40, 140), data.get('author_org', ''), fill=(255, 255, 255), font=body_font)
        draw.text(from_pdf(40, 120), "Prepared by", fill=(255, 255, 255), font=small_font)
        draw.text(from_pdf(40, 100), data.get('author_name', ''), fill=(255, 255, 255), font=small_font)
        
        output_path = config.OUTPUT_DIR / "cover_temp.png"
        config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        # Save with maximum quality settings
        img.save(output_path, format='PNG', quality=100, optimize=False, dpi=(300, 300))
        print(f"✓ Cover image generated: {output_path} (High Quality: {W}x{H} @ 300 DPI)")
        return output_path
        
    except Exception as e:
        print(f"❌ Error generating cover image: {e}")
        import traceback
        traceback.print_exc()
        return None


# ─────────────────────────────────────────────────────────────────────────────
# SECTION BUILDER
# ─────────────────────────────────────────────────────────────────────────────

class SectionBuilder:
    """Helper that converts raw section content strings into DOCX paragraphs."""

    def __init__(self, doc, config):
        self.doc = doc
        self.config = config

    def _is_subheading(self, text):
        """
        Detect if a line is a subheading based on common patterns.
        Subheadings typically:
        - End with specific keywords (Implementation, Layer, Setup, Integration, etc.)
        - Are title case
        - Don't start with bullets or numbers
        - Are relatively short (< 80 chars)
        """
        if not text or len(text) > 80:
            return False
        
        # Common subheading ending patterns from templates
        subheading_patterns = [
            'Implementation',
            'Layer',
            'Setup',
            'Integration',
            'Operations',
            'Capabilities',
            'Readiness',
            'Deployment',
            'Environment',
            'Processing',
            'Validation',
            'Testing',
            'Overview',
            'Architecture',
            'Design',
            'Infrastructure',
            'Monitoring',
            'Security',
            'Storage',
            'Interface',
            'Scalability',
            'Compliance',
            'Topology',
            'Points',
            'Layers',
            'Objectives',  # NEW - for "Business Objectives", "Technical Objectives"
            'Vision',      # NEW - for "End-State Vision"
            'Exclusions',  # NEW - for "Functional Exclusions", "Technical Exclusions", etc.
        ]
        
        # Check if it ends with a common subheading pattern
        for pattern in subheading_patterns:
            if text.endswith(pattern):
                # Additional checks: should be title case and not too long
                words = text.split()
                if 2 <= len(words) <= 8:  # Reasonable word count for subheading
                    # Check if mostly title case (allowing for & and other connectors)
                    title_case_words = sum(1 for w in words if w[0].isupper() or w in ['&', 'and', 'or', 'of', 'the'])
                    if title_case_words >= len(words) * 0.7:  # At least 70% title case
                        return True
        
        return False

    def parse_content(self, content):
        """Convert raw content string into DOCX paragraphs."""
        paragraphs = []
        content = content.replace("<br>", "\n").replace("<br/>", "\n")
        
        # Clean up standalone asterisks
        content = re.sub(r'(?<!\w)\*+(?!\w)', '', content)
        content = re.sub(r'(\w)\*\s*$', r'\1', content, flags=re.MULTILINE)
        content = re.sub(r'(\w)\*(\s)', r'\1\2', content)

        for line in content.split('\n'):
            stripped = line.strip()

            if not stripped:
                continue

            # Skip main markdown headings but keep subsection headings (###)
            if stripped.startswith('###'):
                text = stripped[3:].strip()
                # Remove leading numbers like "1. ", "2. ", etc.
                text = re.sub(r'^\d+\.\s*', '', text)
                p = self.doc.add_paragraph()
                run = p.add_run(text)
                run.font.name = 'DM Sans'
                run.font.size = Pt(_FS_BODY)  # Same size as body text
                run.font.bold = True
                p.paragraph_format.space_before = Pt(_SB_H2)
                p.paragraph_format.space_after = Pt(_SA_H2)
                p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
                p.paragraph_format.line_spacing = _LS_BODY
                paragraphs.append(p)
                continue
            elif stripped.startswith('##') or stripped.startswith('#'):
                continue

            # Numbered list
            elif len(stripped) > 2 and stripped[0].isdigit() and stripped[1] == '.':
                p = self.doc.add_paragraph()
                self._add_runs_with_bold(p, stripped, size=_FS_BODY)
                self._apply_body_style(p)
                paragraphs.append(p)

            # Circle bullets
            elif '○' in stripped or '●' in stripped:
                text = stripped.replace('○', '').replace('●', '').strip()
                p = self.doc.add_paragraph()
                self._add_runs_with_bold(p, text, size=_FS_BODY)
                self._apply_bullet_style(p, level=1)
                paragraphs.append(p)

            # Roman-numeral bullets
            elif any(stripped.startswith(f"{num}.")
                     for num in ['i','ii','iii','iv','v','vi','vii','viii','ix','x']):
                p = self.doc.add_paragraph()
                self._add_runs_with_bold(p, stripped, size=_FS_BODY)
                self._apply_bullet_style(p, level=2)
                paragraphs.append(p)

            # Standard bullets
            elif stripped.startswith('•') or stripped.startswith('-') or stripped.startswith('*'):
                text = stripped[1:].strip()
                p = self.doc.add_paragraph()  # Create empty paragraph first
                self._add_runs_with_bold(p, text, size=_FS_BODY)  # Add text with bold support
                self._apply_bullet_style(p, level=0)
                paragraphs.append(p)

            # Normal paragraph (including those with **bold** text)
            else:
                # Check if this looks like a subheading (even without ### marker)
                if self._is_subheading(stripped):
                    # Remove any leading numbers
                    text = re.sub(r'^\d+\.\s*', '', stripped)
                    p = self.doc.add_paragraph()
                    run = p.add_run(text)
                    run.font.name = 'DM Sans'
                    run.font.size = Pt(_FS_BODY)  # Same size as body text
                    run.font.bold = True
                    p.paragraph_format.space_before = Pt(_SB_H2)
                    p.paragraph_format.space_after = Pt(_SA_H2)
                    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
                    p.paragraph_format.line_spacing = _LS_BODY
                    paragraphs.append(p)
                else:
                    # Normal paragraph - use _add_runs_with_bold to handle **bold** markdown
                    p = self.doc.add_paragraph()
                    self._add_runs_with_bold(p, stripped, size=_FS_BODY)
                    self._apply_body_style(p)
                    paragraphs.append(p)

        return paragraphs

    def _apply_heading_style(self, paragraph):
        """Apply Heading 1 style - custom formatting for better Google Docs compatibility."""
        # Don't use built-in 'Heading 1' style - Google Docs adds extra spacing to it
        # Instead, apply custom formatting directly
        for run in paragraph.runs:
            run.font.name = 'DM Sans'
            run.font.size = Pt(_FS_H1)
            run.font.bold = True
            run.font.color.rgb = RGBColor(123, 63, 242)
        
        # Explicitly set all spacing to 0 to prevent gaps
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        paragraph.paragraph_format.line_spacing = _LS_H1
        
        # Disable pagination controls
        paragraph.paragraph_format.keep_with_next = False
        paragraph.paragraph_format.page_break_before = False
        paragraph.paragraph_format.widow_control = False

    def _apply_subsection_style(self, paragraph):
        """Apply Heading 2/3 style."""
        for run in paragraph.runs:
            run.font.name = 'DM Sans'
            run.font.size = Pt(_FS_H2)
            run.font.bold = True
        paragraph.paragraph_format.space_before = Pt(_SB_H2)
        paragraph.paragraph_format.space_after = Pt(_SA_H2)
        paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        paragraph.paragraph_format.line_spacing = _LS_BODY

    def _apply_body_style(self, paragraph):
        """Apply body text style."""
        for run in paragraph.runs:
            run.font.name = 'DM Sans'
            run.font.size = Pt(_FS_BODY)
        paragraph.paragraph_format.space_before = Pt(_SB_BODY)
        paragraph.paragraph_format.space_after = Pt(_SA_BODY)
        paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        paragraph.paragraph_format.line_spacing = _LS_BODY
        paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    def _apply_bullet_style(self, paragraph, level=0):
        """Apply bullet list style using Word's numbering system."""
        from docx.oxml import parse_xml
        from docx.oxml.ns import nsdecls
        
        # Apply DM Sans font first
        for run in paragraph.runs:
            run.font.name = 'DM Sans'
            run.font.size = Pt(_FS_BODY)
        
        # Apply spacing
        paragraph.paragraph_format.space_before = Pt(_SB_BULLET)
        paragraph.paragraph_format.space_after = Pt(_SA_BULLET)
        paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        paragraph.paragraph_format.line_spacing = _LS_BULLET
        
        # Create numbering properties for bullet list
        # This creates a proper Word list that continues when you press Enter
        pPr = paragraph._element.get_or_add_pPr()
        
        # Remove any existing numbering
        numPr = pPr.find(qn('w:numPr'))
        if numPr is not None:
            pPr.remove(numPr)
        
        # Add new numbering properties
        numPr = parse_xml(r'<w:numPr %s><w:ilvl w:val="%d"/><w:numId w:val="1"/></w:numPr>' % (nsdecls('w'), level))
        pPr.append(numPr)
        
        # Set indentation
        if level > 0:
            paragraph.paragraph_format.left_indent = Pt(_IND_BULLET1 + (level * 18))
        
        # Ensure alignment
        paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    def has_table(self, content):
        """Return True if content contains a markdown pipe table."""
        if '|' in content and content.count('|') > 3:
            table_lines = [ln for ln in content.split('\n') if '|' in ln]
            return len(table_lines) >= 2
        return False

    def parse_table(self, content):
        """Split content into (intro_lines, table_lines)."""
        lines = content.split('\n')
        table_lines, intro_lines = [], []
        table_started = False

        for line in lines:
            if '|' in line:
                table_started = True
                table_lines.append(line)
            elif not table_started and line.strip():
                if not line.strip().startswith('#'):
                    intro_lines.append(line)

        return intro_lines, table_lines

    def _set_cell_vertical_align_top(self, cell):
        """Set table cell vertical alignment to top."""
        tcPr = cell._tc.get_or_add_tcPr()
        v_align = OxmlElement("w:vAlign")
        v_align.set(qn("w:val"), "top")
        tcPr.append(v_align)

    def _set_row_cant_split(self, row):
        """Prevent a table row from splitting across pages where possible."""
        trPr = row._tr.get_or_add_trPr()
        cant_split = OxmlElement("w:cantSplit")
        trPr.append(cant_split)

    def _set_cell_width(self, cell, width):
        """Set an explicit table cell width."""
        cell.width = int(width)
        tcPr = cell._tc.get_or_add_tcPr()
        tcW = tcPr.find(qn('w:tcW'))
        if tcW is None:
            tcW = OxmlElement('w:tcW')
            tcPr.append(tcW)
        tcW.set(qn('w:w'), str(int(width / 635)))  # EMU to twentieths of a point approximation
        tcW.set(qn('w:type'), 'dxa')

    def _shade_cell(self, cell, fill):
        """Apply cell background shading."""
        tcPr = cell._tc.get_or_add_tcPr()
        # Remove existing shading nodes to avoid duplicates
        for shd in list(tcPr.findall(qn('w:shd'))):
            tcPr.remove(shd)
        shading_elm = OxmlElement('w:shd')
        shading_elm.set(qn('w:fill'), fill)
        tcPr.append(shading_elm)

    def _set_cell_padding(self, cell, padding_twips=150):
        """Apply consistent cell padding."""
        tcPr = cell._tc.get_or_add_tcPr()
        # Remove existing margins to avoid duplicates when rebuilding
        for mar in list(tcPr.findall(qn('w:tcMar'))):
            tcPr.remove(mar)
        tcMar = OxmlElement('w:tcMar')
        for margin_name in ['top', 'left', 'bottom', 'right']:
            node = OxmlElement(f'w:{margin_name}')
            node.set(qn('w:w'), str(padding_twips))
            node.set(qn('w:type'), 'dxa')
            tcMar.append(node)
        tcPr.append(tcMar)

    def _write_rich_cell_content(self, cell, cell_text, is_header=False):
        """Write table cell content with support for <br>, bold titles, and bullets."""
        # Clear default cell text while preserving the first paragraph container.
        cell.text = ""

        text = str(cell_text or "")
        text = (
            text
            .replace("&lt;br&gt;", "<br>")
            .replace("&lt;br/&gt;", "<br>")
            .replace("&lt;br /&gt;", "<br>")
            .replace("<br/>", "<br>")
            .replace("<br />", "<br>")
            .replace("<br>", "\n")
            .replace("\\n", "\n")
        )

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if not lines:
            lines = [""]

        for idx, line in enumerate(lines):
            if idx == 0 and len(cell.paragraphs) == 1 and not cell.paragraphs[0].text:
                p = cell.paragraphs[0]
            else:
                p = cell.add_paragraph()

            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
            p.paragraph_format.line_spacing = 1.15

            if is_header:
                run = p.add_run(line.replace("**", ""))
                run.font.name = "DM Sans"
                run.font.bold = True
                run.font.color.rgb = RGBColor(255, 255, 255)
                run.font.size = Pt(_FS_TABLE)
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                continue

            # Bullet lines inside milestone cells.
            if line.startswith("•") or line.startswith("-"):
                bullet_text = line[1:].strip()
                
                # Use Word's list formatting for bullets in table cells
                from docx.oxml import parse_xml
                from docx.oxml.ns import nsdecls
                
                # Add the bullet text
                self._add_runs_with_bold(p, bullet_text, size=_FS_TABLE)
                
                # Apply numbering to make it a proper list
                pPr = p._element.get_or_add_pPr()
                
                # Remove any existing numbering
                numPr = pPr.find(qn('w:numPr'))
                if numPr is not None:
                    pPr.remove(numPr)
                
                # Add new numbering properties
                numPr = parse_xml(r'<w:numPr %s><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>' % nsdecls('w'))
                pPr.append(numPr)
                
                # Adjust spacing for table cells
                p.paragraph_format.space_before = Pt(2)
                p.paragraph_format.space_after = Pt(2)
                
                continue

            # Bold milestone title, e.g. **Discovery & Planning**.
            bold_match = re.fullmatch(r"\*\*(.+?)\*\*", line)
            if bold_match:
                run = p.add_run(bold_match.group(1))
                run.font.name = "DM Sans"
                run.font.bold = True
                run.font.size = Pt(_FS_TABLE)
                p.paragraph_format.space_after = Pt(5)
                continue

            # Normal or mixed-bold line.
            self._add_runs_with_bold(p, line, size=_FS_TABLE)

    def _add_runs_with_bold(self, paragraph, text, size=_FS_TABLE):
        """Add text to a paragraph while supporting **bold** spans."""
        parts = re.split(r"(\*\*.+?\*\*)", str(text))
        for part in parts:
            if not part:
                continue
            is_bold = part.startswith("**") and part.endswith("**")
            clean = part[2:-2] if is_bold else part.replace("**", "")
            run = paragraph.add_run(clean)
            run.font.name = "DM Sans"
            run.font.size = Pt(size)
            run.font.bold = is_bold

    def build_table(self, table_lines):
        """Build a DOCX table from markdown pipe rows with rich cell formatting."""
        table_data = []

        for line in table_lines:
            line = line.strip()
            if not line or all(c in '-| ' for c in line):
                continue

            parts = line.split('|')
            if parts and parts[0].strip() == '':
                parts.pop(0)
            if parts and parts[-1].strip() == '':
                parts.pop()

            cols = [col.strip() for col in parts]
            if not cols:
                continue

            table_data.append(cols)

        if not table_data:
            return None

        num_cols = len(table_data[0])

        # Normalize row lengths so malformed markdown rows do not break DOCX generation.
        normalized_rows = []
        for row in table_data:
            if len(row) < num_cols:
                row = row + [""] * (num_cols - len(row))
            elif len(row) > num_cols:
                row = row[:num_cols - 1] + [" | ".join(row[num_cols - 1:])]
            normalized_rows.append(row)
        table_data = normalized_rows

        table = self.doc.add_table(rows=len(table_data), cols=num_cols)
        table.style = None
        table.autofit = False
        table.allow_autofit = False

        # Calculate available width for A4 page with configured margins.
        page_width = Inches(8.27)
        available_width = page_width - Inches(_MARGIN_LEFT) - Inches(_MARGIN_RIGHT)

        # Timeline tables should have a narrow Timeframe column and wide Milestones column.
        header_first_col = table_data[0][0].strip().lower()
        if num_cols == 2 and header_first_col in ["timeframe", "duration"]:
            widths = [available_width * 0.22, available_width * 0.78]
        else:
            widths = [available_width / num_cols] * num_cols

        for idx, col in enumerate(table.columns):
            col.width = int(widths[idx])
            for cell in col.cells:
                self._set_cell_width(cell, widths[idx])

        # Fill table data with rich content.
        for i, row_data in enumerate(table_data):
            row = table.rows[i]
            self._set_row_cant_split(row)
            row.height = Inches(0.4)

            for j, cell_text in enumerate(row_data):
                cell = row.cells[j]
                self._set_cell_vertical_align_top(cell)
                self._set_cell_padding(cell, padding_twips=150)
                self._write_rich_cell_content(cell, cell_text, is_header=(i == 0))

                if i == 0:
                    self._shade_cell(cell, '7B3FF2')
                else:
                    self._shade_cell(cell, 'FFFFFF')

        # Add borders while retaining custom shading.
        table.style = 'Table Grid'
        table.alignment = WD_ALIGN_PARAGRAPH.LEFT

        # Remove table indentation so it aligns with section heading.
        tbl = table._element
        tblPr = tbl.tblPr
        if tblPr is None:
            tblPr = OxmlElement('w:tblPr')
            tbl.insert(0, tblPr)

        tblInd = tblPr.find(qn('w:tblInd'))
        if tblInd is None:
            tblInd = OxmlElement('w:tblInd')
            tblPr.append(tblInd)
        tblInd.set(qn('w:w'), '0')
        tblInd.set(qn('w:type'), 'dxa')

        return table


# ─────────────────────────────────────────────────────────────────────────────
# DOCUMENT BUILDER
# ─────────────────────────────────────────────────────────────────────────────

class DocumentBuilder:
    """Builds formatted DOCX documents dynamically from a sections dictionary."""

    def __init__(self, config):
        self.config = config
        self.doc = None
        self.section_builder = None
        self.toc_entries = []

    def _get_short_company_name(self, company_name: str) -> str:
        """Strip common legal suffixes from a company name."""
        suffixes = [
            ' Pvt Ltd', ' Private Limited', ' Pvt. Ltd.', ' Pvt.Ltd.',
            ' Ltd', ' LLC', ' Inc', ' Corporation',
            ' Corp', ' Limited', ' Co', ' Company',
        ]
        short = company_name or ''
        for suffix in suffixes:
            if short.lower().endswith(suffix.lower()):
                short = short[:len(short) - len(suffix)].strip()
                break
        return short

    def _name_to_key(self, name: str) -> str:
        """Convert a human-readable section name to a snake_case dict key."""
        key = name.lower()
        key = re.sub(r'[^\w\s-]', '', key)
        key = re.sub(r'[-\s]+', '_', key)
        return key

    def _is_similar(self, section_name: str, key: str) -> bool:
        """Fuzzy-match a section name against a dict key."""
        stopwords = {'the', 'of', 'and', 'to', 'a', 'in'}

        def _clean(text):
            text = text.lower()
            text = re.sub(r'[^\w\s]', '', text)
            return {w for w in text.split() if w not in stopwords}

        sw = _clean(section_name)
        kw = _clean(key.replace('_', ' '))
        if not sw or not kw:
            return False
        return len(sw & kw) / max(len(sw), len(kw)) > 0.5

    def _parse_toc_entries(self, sections: dict):
        """Populate self.toc_entries from the sections dict."""
        self.toc_entries = []
        reserved = {'toc_structure', 'table_of_contents', 'tableofcontents',
                    'table_contents', 'cover_page'}

        # Find explicit TOC structure
        toc_content = ''
        for key in ('toc_structure', 'table_of_contents', 'tableofcontents', 'table_contents'):
            if key in sections:
                toc_content = sections[key]
                print(f"✓ TOC found via key: {key}")
                break

        if not toc_content:
            for key, content in sections.items():
                kl = key.lower()
                if ('table' in kl and 'content' in kl) or 'toc' in kl:
                    toc_content = content
                    print(f"✓ TOC found via pattern match: {key}")
                    break

        # Parse TOC lines or fall back to section keys
        if toc_content:
            for line in toc_content.split('\n'):
                line = line.strip()
                if not line or line.startswith('#') or line.startswith('{'):
                    continue
                line = re.sub(r'^\d+\.\s*', '', line)
                if line and len(line) <= 100:
                    self.toc_entries.append(line)
        else:
            print("⚠ No explicit TOC found — generating from section keys")
            for key in sections:
                if key not in reserved and sections[key] and str(sections[key]).strip():
                    self.toc_entries.append(key.replace('_', ' ').title())

        print(f"✓ Final TOC: {len(self.toc_entries)} entries")

    def _add_bullet_numbering(self):
        """Add bullet list numbering definition to the document."""
        from docx.oxml import parse_xml
        from docx.oxml.ns import nsdecls
        
        # Get or create numbering part
        try:
            numbering_part = self.doc.part.numbering_part
        except:
            # Create numbering part if it doesn't exist
            from docx.oxml.numbering import CT_Numbering
            numbering_element = CT_Numbering()
            self.doc.part._element.body.append(numbering_element)
            numbering_part = self.doc.part.numbering_part
        
        # Add abstract numbering definition for bullets
        abstractNum_xml = '''
        <w:abstractNum w:abstractNumId="0" xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:multiLevelType w:val="hybridMultilevel"/>
            <w:lvl w:ilvl="0">
                <w:start w:val="1"/>
                <w:numFmt w:val="bullet"/>
                <w:lvlText w:val="•"/>
                <w:lvlJc w:val="left"/>
                <w:pPr>
                    <w:ind w:left="720" w:hanging="360"/>
                </w:pPr>
                <w:rPr>
                    <w:rFonts w:ascii="Symbol" w:hAnsi="Symbol" w:hint="default"/>
                </w:rPr>
            </w:lvl>
            <w:lvl w:ilvl="1">
                <w:start w:val="1"/>
                <w:numFmt w:val="bullet"/>
                <w:lvlText w:val="○"/>
                <w:lvlJc w:val="left"/>
                <w:pPr>
                    <w:ind w:left="1440" w:hanging="360"/>
                </w:pPr>
            </w:lvl>
        </w:abstractNum>
        '''
        
        # Add numbering instance
        num_xml = '''
        <w:num w:numId="1" xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:abstractNumId w:val="0"/>
        </w:num>
        '''
        
        try:
            numbering_element = self.doc.part.numbering_part.element
            numbering_element.append(parse_xml(abstractNum_xml))
            numbering_element.append(parse_xml(num_xml))
        except Exception as e:
            print(f"⚠️ Could not add numbering definition: {e}")

    def build_document(self, sections: dict, metadata: dict,
                       mode: str = "POC") -> Optional[Path]:
        """
        Build a DOCX document and return its path.
        """
        print(f"\n📋 DocumentBuilder.build_document() started")
        print(f"   Mode: {mode}")

        # Setup output path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix    = "PROD" if mode in ("PROD", "POC_TO_PROD") else "POC"
        docx_name  = f"{prefix}_{metadata['company_name'].replace(' ', '_')}_{timestamp}.docx"
        docx_path  = self.config.OUTPUT_DIR / docx_name

        self.config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        print(f"   Output path: {docx_path}")

        # Parse TOC
        self._parse_toc_entries(sections)

        # Build DOCX
        try:
            self._build_docx(docx_path, sections, metadata)
            print(f"✅ DOCX ready: {docx_path}")
            return docx_path
        except Exception as exc:
            print(f"❌ Error building DOCX: {exc}")
            import traceback
            traceback.print_exc()
            return None

    def _build_docx(self, output_path, sections, metadata):
        """Build the DOCX document."""
        self.doc = Document()
        self.section_builder = SectionBuilder(self.doc, self.config)
        
        # Initialize bullet list numbering definition
        self._add_bullet_numbering()

        # PAGE 1: COVER - Set margins to 0
        section = self.doc.sections[0]
        section.top_margin = Inches(0)
        section.bottom_margin = Inches(0)
        section.left_margin = Inches(0)
        section.right_margin = Inches(0)
        section.page_width = Inches(8.27)  # A4 width
        section.page_height = Inches(11.69)  # A4 height

        # Generate and add cover image
        cover_path = generate_cover_image(metadata, self.config)
        if cover_path and cover_path.exists():
            paragraph = self.doc.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = 1.0
            run = paragraph.add_run()
            # Use exact A4 width to fill the page completely
            run.add_picture(str(cover_path), width=Inches(8.27), height=Inches(11.69))

        # PAGE 2: TOC - Add new section with normal margins and footer
        section = self.doc.add_section()
        section.top_margin = Inches(_MARGIN_TOP)
        section.bottom_margin = Inches(_MARGIN_BOTTOM)
        section.left_margin = Inches(_MARGIN_LEFT)
        section.right_margin = Inches(_MARGIN_RIGHT)
        
        # Add footer to this section (will apply to all following pages)
        self._add_footer(section, metadata)

        # TOC Title
        toc_title = self.doc.add_heading('Table of Contents', level=1)
        toc_title_format = toc_title.runs[0].font
        toc_title_format.name = 'DM Sans'
        toc_title_format.color.rgb = RGBColor(123, 63, 242)
        toc_title_format.size = Pt(_FS_H1)

        # Add TOC field
        add_toc_field(self.doc)
        
        # Add page break after TOC
        self.doc.add_page_break()

        # CONTENT PAGES - All sections flow continuously (no page breaks between sections)
        for idx, section_name in enumerate(self.toc_entries):
            # Build section content (spacing controlled by heading space_before)
            self._build_section(section_name, sections, metadata)

        # Set document properties for metadata extraction in POC_TO_PROD
        try:
            props = self.doc.core_properties
            props.author = metadata.get('author_name', '')
            props.title = metadata.get('project_title', '')
            props.subject = metadata.get('company_name', '')
        except Exception:
            pass

        # Save document
        self.doc.save(str(output_path))
        print(f"✓ DOCX saved: {output_path}")
    
    def _add_footer(self, section, metadata):
        """Add branded footer with company name and page numbers."""
        footer = section.footer
        
        # Add a table for footer layout (2 columns: left for text, right for page number)
        footer_table = footer.add_table(rows=1, cols=2, width=Inches(6.5))
        footer_table.autofit = False
        
        # Left cell - Company confidential text
        left_cell = footer_table.rows[0].cells[0]
        left_paragraph = left_cell.paragraphs[0]
        org_short = self._get_short_company_name(metadata.get('author_org', ''))
        left_run = left_paragraph.add_run(f"{org_short} Confidential - for limited purposes only")
        left_run.font.name = 'DM Sans'
        left_run.font.size = Pt(9)
        left_run.font.color.rgb = RGBColor(123, 63, 242)
        left_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Right cell - Page number
        right_cell = footer_table.rows[0].cells[1]
        right_paragraph = right_cell.paragraphs[0]
        right_paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        
        # Add page number field
        right_run = right_paragraph.add_run()
        fldChar1 = OxmlElement('w:fldChar')
        fldChar1.set(qn('w:fldCharType'), 'begin')
        
        instrText = OxmlElement('w:instrText')
        instrText.set(qn('xml:space'), 'preserve')
        instrText.text = "PAGE"
        
        fldChar2 = OxmlElement('w:fldChar')
        fldChar2.set(qn('w:fldCharType'), 'end')
        
        right_run._r.append(fldChar1)
        right_run._r.append(instrText)
        right_run._r.append(fldChar2)
        right_run.font.name = 'DM Sans'
        right_run.font.size = Pt(9)
        right_run.font.color.rgb = RGBColor(123, 63, 242)
        
        # Add horizontal line above footer
        footer_para = footer.paragraphs[0]
        pPr = footer_para._element.get_or_add_pPr()
        pBdr = OxmlElement('w:pBdr')
        top = OxmlElement('w:top')
        top.set(qn('w:val'), 'single')
        top.set(qn('w:sz'), '6')  # Line thickness
        top.set(qn('w:space'), '1')
        top.set(qn('w:color'), '7B3FF2')  # Purple color
        pBdr.append(top)
        pPr.append(pBdr)

    def _build_section(self, section_name, sections, metadata):
        """Build a single section in the document."""
        print(f"🔍 Building section: '{section_name}'")
        
        # Find content
        section_key = self._name_to_key(section_name)
        content = sections.get(section_key, '')

        if not content:
            # Try fuzzy matching
            for key in sections:
                if self._is_similar(section_name, key):
                    content = sections[key]
                    break

        if not content:
            print(f"  ⚠ No content for '{section_name}' — skipping")
            return

        # Section heading
        heading = self.doc.add_heading(section_name, level=1)
        heading_format = heading.runs[0].font
        heading_format.name = 'DM Sans'
        heading_format.color.rgb = RGBColor(123, 63, 242)
        heading_format.size = Pt(_FS_H1)
        
        # Add bookmark to heading for TOC linking
        self._add_bookmark_to_heading(heading, section_name)

        # Check if content has table
        if self.section_builder.has_table(content):
            intro_lines, table_lines = self.section_builder.parse_table(content)
            
            # Add intro text
            if intro_lines:
                intro_text = '\n'.join(intro_lines).strip()
                p = self.doc.add_paragraph(intro_text)
                self.section_builder._apply_body_style(p)
            
            # Add table
            self.section_builder.build_table(table_lines)
        else:
            # Add regular content
            self.section_builder.parse_content(content)
    
    def _add_bookmark_to_heading(self, heading, section_name):
        """Add a bookmark to a heading paragraph for TOC linking."""
        # Create a unique bookmark ID from the section name
        bookmark_id = re.sub(r'[^\w]', '', section_name.replace(' ', '_'))
        bookmark_id = f"_Toc{bookmark_id}"
        
        # Get the paragraph element
        p = heading._element
        
        # Create bookmark start element
        bookmark_start = OxmlElement('w:bookmarkStart')
        bookmark_start.set(qn('w:id'), str(hash(bookmark_id) % 1000000))
        bookmark_start.set(qn('w:name'), bookmark_id)
        
        # Create bookmark end element
        bookmark_end = OxmlElement('w:bookmarkEnd')
        bookmark_end.set(qn('w:id'), str(hash(bookmark_id) % 1000000))
        
        # Insert bookmark elements around the paragraph content
        p.insert(0, bookmark_start)
        p.append(bookmark_end)
