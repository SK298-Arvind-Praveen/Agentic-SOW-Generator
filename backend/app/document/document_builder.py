"""Professional, deterministic DOCX builder for generated SOW content.

Design system: the ShellKode benchmark proposal system using DM Sans,
benchmark-matched purple/blue accents, compact tables, and fixed Letter geometry.
First page pattern: ``proposal_centerpiece`` over the existing brand artwork.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from PIL import Image as PILImage, ImageDraw, ImageFont
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import (
    WD_ALIGN_PARAGRAPH,
    WD_BREAK,
    WD_LINE_SPACING,
    WD_TAB_ALIGNMENT,
    WD_TAB_LEADER,
)
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Inches, Pt, RGBColor


PAGE_WIDTH_IN = 8.5
PAGE_HEIGHT_IN = 11.0
HORIZONTAL_MARGIN_IN = 0.68
TOP_MARGIN_IN = 0.66
BOTTOM_MARGIN_IN = 0.58
CONTENT_WIDTH_DXA = 10282
TABLE_INDENT_DXA = 0
FONT_NAME = "DM Sans"
PURPLE = "5D3FD3"
BLUE = "1A4BD2"
DARK_PURPLE = "3E2A91"
INK = "434343"
MUTED = "6F6F6F"
LIGHT_FILL = "F2F2F2"
BORDER = "D9D9D9"


def _set_font(run, name: str = FONT_NAME, size: Optional[float] = None,
              bold: Optional[bool] = None, italic: Optional[bool] = None,
              color: Optional[str] = None) -> None:
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    fonts = rpr.rFonts
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn(f"w:{attr}"), name)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def _add_field(paragraph, instruction: str, cached_text: str = "", size: float = 9):
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    begin.set(qn("w:dirty"), "true")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = cached_text
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for element in (begin, instr, separate, text, end):
        run._r.append(element)
    _set_font(run, size=size, color=MUTED)
    return run


def _bookmark_name(title: str, index: int = 0) -> str:
    slug = re.sub(r"[^A-Za-z0-9_]", "", title.replace(" ", "_"))[:32]
    return f"SOW_{index}_{slug}" if slug else f"SOW_{index}"


def _add_hyperlink(paragraph, text: str, anchor: str):
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("w:anchor"), anchor)
    hyperlink.set(qn("w:history"), "1")
    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), INK)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "none")
    fonts = OxmlElement("w:rFonts")
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn(f"w:{attr}"), FONT_NAME)
    size = OxmlElement("w:sz")
    size.set(qn("w:val"), "15")
    rpr.extend([fonts, color, underline, size])
    text_node = OxmlElement("w:t")
    text_node.text = text
    run.extend([rpr, text_node])
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def _mark_update_fields(document: Document) -> None:
    settings = document.settings._element
    existing = settings.find(qn("w:updateFields"))
    if existing is None:
        existing = OxmlElement("w:updateFields")
        settings.append(existing)
    existing.set(qn("w:val"), "true")


def _load_cover_font(config, bold: bool, size: int):
    filename = "DMSans-Bold.ttf" if bold else "DMSans-Regular.ttf"
    path = Path(config.ASSETS_DIR) / "fonts" / filename
    if path.exists():
        return ImageFont.truetype(str(path), size)
    for fallback in ("/System/Library/Fonts/Helvetica.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.exists(fallback):
            return ImageFont.truetype(fallback, size)
    return ImageFont.load_default()


def _wrapped_lines(draw, text: str, font, max_width: int, max_lines: int = 3) -> List[str]:
    words = str(text or "").split()
    lines: List[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        width = draw.textbbox((0, 0), trial, font=font)[2]
        if current and width > max_width:
            lines.append(current)
            current = word
            if len(lines) >= max_lines - 1:
                break
        else:
            current = trial
    if current and len(lines) < max_lines:
        lines.append(current)
    consumed = " ".join(lines)
    if len(consumed) < len(str(text or "").strip()) and lines:
        while draw.textbbox((0, 0), lines[-1] + "...", font=font)[2] > max_width and lines[-1]:
            lines[-1] = lines[-1][:-1]
        lines[-1] = lines[-1].rstrip() + "..."
    return lines


def generate_cover_image(data: Dict[str, Any], config) -> Optional[Path]:
    """Render a Letter-sized branded cover with bundled fonts and safe wrapping."""
    base = Path(config.COVER_PAGE_IMAGE)
    if not base.exists():
        return None
    try:
        dpi = 240
        width, height = int(PAGE_WIDTH_IN * dpi), int(PAGE_HEIGHT_IN * dpi)
        image = PILImage.open(base).convert("RGBA").resize((width, height), PILImage.Resampling.LANCZOS)
        draw = ImageDraw.Draw(image)
        title_font = _load_cover_font(config, True, 78)
        project_font = _load_cover_font(config, False, 39)
        body_font = _load_cover_font(config, False, 25)
        small_font = _load_cover_font(config, False, 22)

        x, max_width = int(0.72 * dpi), int(7.0 * dpi)
        y = int(2.65 * dpi)
        for line in _wrapped_lines(draw, data.get("company_name", ""), title_font, max_width, 2):
            draw.text((x, y), line, fill=(123, 63, 242), font=title_font)
            y += 92
        y += 30
        for line in _wrapped_lines(draw, data.get("project_title", ""), project_font, max_width, 3):
            draw.text((x, y), line, fill=(90, 90, 90), font=project_font)
            y += 52

        lower_y = int(9.05 * dpi)
        draw.text((x, lower_y), str(data.get("author_org", "")), fill="white", font=body_font)
        draw.text((x, lower_y + 44), "Prepared by", fill="white", font=small_font)
        draw.text((x, lower_y + 78), str(data.get("author_name", "")), fill="white", font=small_font)
        meta = f"{data.get('document_date', '')}  |  Version {data.get('version', '1.0')}"
        draw.text((x, lower_y + 116), meta, fill="white", font=small_font)

        output = Path(config.OUTPUT_DIR) / "cover_temp.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        image.convert("RGB").save(output, "PNG", dpi=(dpi, dpi))
        return output
    except Exception as exc:
        print(f"⚠ Cover image generation failed: {exc}")
        return None


class SectionBuilder:
    """Render ordered Markdown blocks without losing text after tables."""

    def __init__(self, doc: Document, config):
        self.doc = doc
        self.config = config
        self.bullet_num_id = 91
        self.number_num_id = 92

    def parse_content(
        self,
        content: str,
        heading_prefix: Optional[str] = None,
        heading_anchor_map: Optional[Dict[str, str]] = None,
        bookmark_callback: Optional[Any] = None,
    ) -> List[Any]:
        added: List[Any] = []
        heading_counters = {2: 0, 3: 0, 4: 0}
        active_number_num_id: Optional[int] = None
        for kind, payload in self._iter_blocks(content or ""):
            if kind != "number":
                active_number_num_id = None
            if kind == "table":
                tables = self.build_table(payload)
                if tables is not None:
                    if isinstance(tables, list):
                        added.extend(tables)
                    else:
                        added.append(tables)
            elif kind == "heading":
                level, text = payload
                text = self._numbered_heading_text(
                    text, level, heading_prefix, heading_counters
                )
                paragraph = self.doc.add_paragraph(style=f"Heading {level}")
                self._add_rich_runs(paragraph, text)
                anchor = (heading_anchor_map or {}).get(text)
                if anchor and bookmark_callback:
                    bookmark_callback(paragraph, anchor)
                added.append(paragraph)
            elif kind == "bullet":
                level, text = payload
                paragraph = self.doc.add_paragraph()
                self._add_rich_runs(paragraph, text)
                self._apply_numbering(paragraph, self.bullet_num_id, level)
                added.append(paragraph)
            elif kind == "number":
                level, text = payload
                paragraph = self.doc.add_paragraph()
                self._add_rich_runs(paragraph, text)
                if active_number_num_id is None:
                    active_number_num_id = self._new_numbering_instance(self.number_num_id)
                self._apply_numbering(paragraph, active_number_num_id, level)
                added.append(paragraph)
            elif kind == "caption":
                paragraph = self.doc.add_paragraph(style="Caption")
                self._add_rich_runs(paragraph, payload)
                added.append(paragraph)
            else:
                paragraph = self.doc.add_paragraph()
                self._add_rich_runs(paragraph, payload)
                added.append(paragraph)
        return added

    @classmethod
    def enumerate_headings(
        cls, content: str, heading_prefix: Optional[str]
    ) -> List[Tuple[str, int]]:
        """Return the same numbered heading labels used during rendering."""
        counters = {2: 0, 3: 0, 4: 0}
        result: List[Tuple[str, int]] = []
        for kind, payload in cls._iter_blocks(content or ""):
            if kind != "heading":
                continue
            level, text = payload
            result.append((cls._numbered_heading_text(text, level, heading_prefix, counters), level))
        return result

    @staticmethod
    def _numbered_heading_text(
        text: str,
        level: int,
        heading_prefix: Optional[str],
        counters: Dict[int, int],
    ) -> str:
        clean = re.sub(r"^\d+(?:\.\d+)*[.)]?\s*", "", str(text)).strip()
        if not heading_prefix or not re.fullmatch(r"\d+", str(heading_prefix)):
            return clean
        level = min(4, max(2, level))
        counters[level] += 1
        for child_level in range(level + 1, 5):
            counters[child_level] = 0
        # A malformed H3/H4 without its parent should still receive a stable,
        # non-zero hierarchy rather than displaying e.g. 4.0.1.
        for parent_level in range(2, level):
            if counters[parent_level] == 0:
                counters[parent_level] = 1
        suffix = ".".join(str(counters[item]) for item in range(2, level + 1))
        return f"{heading_prefix}.{suffix} {clean}"

    def _new_numbering_instance(self, abstract_num_id: int) -> int:
        """Create a fresh Word numbering instance so each workflow restarts at 1."""
        numbering = self.doc.part.numbering_part.element
        existing_ids = []
        for element in numbering.findall(qn("w:num")):
            value = element.get(qn("w:numId"))
            if value and str(value).isdigit():
                existing_ids.append(int(value))
        num_id = max(existing_ids + [99]) + 1
        num = OxmlElement("w:num")
        num.set(qn("w:numId"), str(num_id))
        abstract = OxmlElement("w:abstractNumId")
        abstract.set(qn("w:val"), str(abstract_num_id))
        num.append(abstract)
        for level in range(3):
            override = OxmlElement("w:lvlOverride")
            override.set(qn("w:ilvl"), str(level))
            start = OxmlElement("w:startOverride")
            start.set(qn("w:val"), "1")
            override.append(start)
            num.append(override)
        numbering.append(num)
        return num_id

    @staticmethod
    def _iter_blocks(content: str):
        lines = content.replace("<br/>", "<br>").splitlines()
        index = 0
        prose: List[str] = []

        def flush_prose():
            nonlocal prose
            if prose:
                joined = " ".join(part.strip() for part in prose if part.strip())
                prose = []
                if joined:
                    return ("prose", joined)
            return None

        while index < len(lines):
            raw = lines[index]
            stripped = raw.strip()
            if not stripped:
                block = flush_prose()
                if block:
                    yield block
                index += 1
                continue
            if re.match(r"^\s*\|.+\|\s*$", raw):
                block = flush_prose()
                if block:
                    yield block
                table_lines = []
                while index < len(lines) and re.match(r"^\s*\|.+\|\s*$", lines[index]):
                    table_lines.append(lines[index])
                    index += 1
                yield ("table", table_lines)
                continue
            heading = re.match(r"^(#{3,5})\s+(.+)$", stripped)
            if heading:
                block = flush_prose()
                if block:
                    yield block
                level = min(4, max(2, len(heading.group(1)) - 1))
                yield ("heading", (level, heading.group(2).strip()))
                index += 1
                continue
            bullet = re.match(r"^(\s*)[-*•○]\s+(.+)$", raw)
            if bullet:
                block = flush_prose()
                if block:
                    yield block
                yield ("bullet", (min(len(bullet.group(1)) // 2, 2), bullet.group(2).strip()))
                index += 1
                continue
            numbered = re.match(r"^(\s*)\d+[.)]\s+(.+)$", raw)
            if numbered:
                block = flush_prose()
                if block:
                    yield block
                yield ("number", (min(len(numbered.group(1)) // 2, 2), numbered.group(2).strip()))
                index += 1
                continue
            if re.match(r"^(Table|Figure)\s+\d*[:.-]", stripped, re.I):
                block = flush_prose()
                if block:
                    yield block
                yield ("caption", stripped)
                index += 1
                continue
            if stripped.startswith("#"):
                index += 1
                continue
            prose.append(stripped)
            index += 1
        block = flush_prose()
        if block:
            yield block

    def _add_rich_runs(self, paragraph, text: str, size: Optional[float] = None, color: Optional[str] = None):
        parts = re.split(r"(\*\*.+?\*\*|(?<!\*)\*[^*]+?\*(?!\*)|`.+?`)", str(text))
        for part in parts:
            if not part:
                continue
            bold = part.startswith("**") and part.endswith("**")
            italic = not bold and part.startswith("*") and part.endswith("*")
            code = part.startswith("`") and part.endswith("`")
            clean = part[2:-2] if bold else part[1:-1] if italic or code else part
            run = paragraph.add_run(clean)
            _set_font(run, "Courier New" if code else FONT_NAME, size=size, bold=bold, italic=italic, color=color)

    @staticmethod
    def _apply_numbering(paragraph, num_id: int, level: int) -> None:
        ppr = paragraph._element.get_or_add_pPr()
        numpr = ppr.find(qn("w:numPr"))
        if numpr is not None:
            ppr.remove(numpr)
        numpr = OxmlElement("w:numPr")
        ilvl = OxmlElement("w:ilvl")
        ilvl.set(qn("w:val"), str(level))
        numid = OxmlElement("w:numId")
        numid.set(qn("w:val"), str(num_id))
        numpr.extend([ilvl, numid])
        ppr.append(numpr)

    @staticmethod
    def _parse_table_rows(lines: Sequence[str]) -> List[List[str]]:
        rows: List[List[str]] = []
        for line in lines:
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if cells and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells):
                continue
            if cells:
                rows.append(cells)
        if not rows:
            return []
        width = max(len(row) for row in rows)
        return [row + [""] * (width - len(row)) for row in rows]

    @staticmethod
    def _column_widths(rows: Sequence[Sequence[str]]) -> List[int]:
        columns = len(rows[0])
        headers = [cell.lower() for cell in rows[0]]
        # Stable semantic layouts keep control fields compact and reserve room
        # for the narrative evidence/criteria columns that need it most.
        semantic_patterns = (
            (("week", "phase", "activities", "deliverable", "dependency", "owner"),
             [720, 1200, 2700, 1800, 1500, 1440]),
            (("timeframe", "phase", "activities", "deliverable", "customer", "exit"),
             [900, 1400, 2450, 1600, 1400, 1610]),
            (("id", "requirement", "priority", "description", "source", "acceptance"),
             [650, 1750, 820, 2050, 1400, 2690]),
            (("id", "requirement", "status", "delivery", "output", "validation"),
             [650, 2200, 900, 1900, 1100, 2610]),
            (("id", "deliverable", "format", "owner", "timing", "acceptance"),
             [650, 2300, 1050, 1100, 1300, 2960]),
            (("id", "deliverable", "format", "owner", "evidence", "timing"),
             [650, 2400, 1100, 1000, 2800, 1410]),
            (("component", "purpose", "data", "integration", "security", "owner"),
             [1400, 1800, 1500, 1500, 1900, 1260]),
            (("layer", "component", "purpose", "data", "control", "status"),
             [1200, 1800, 1800, 1500, 1800, 1260]),
            (("id", "risk", "likelihood", "mitigation", "contingency", "owner"),
             [650, 1800, 1200, 2300, 2200, 1210]),
            (("id", "risk", "likelihood", "impact", "mitigation", "contingency", "owner", "trigger"),
             [550, 1500, 850, 700, 1650, 1550, 1000, 1560]),
            (("id", "risk", "cause", "likelihood", "impact", "mitigation", "contingency", "owner"),
             [540, 1200, 1050, 850, 750, 1800, 1800, 1370]),
        )
        for signature, widths in semantic_patterns:
            if columns == len(signature) and all(token in headers[index] for index, token in enumerate(signature)):
                scaled = [round(width * CONTENT_WIDTH_DXA / sum(widths)) for width in widths]
                scaled[-1] += CONTENT_WIDTH_DXA - sum(scaled)
                return scaled
        patterns = {
            2: {
                ("timeframe", "milestones"): [2100, 7260],
                ("id", "description"): [1500, 7860],
            },
            3: {},
        }
        for signature, widths in patterns.get(columns, {}).items():
            if all(any(token in headers[i] for token in (signature[i],)) for i in range(columns)):
                scaled = [round(width * CONTENT_WIDTH_DXA / sum(widths)) for width in widths]
                scaled[-1] += CONTENT_WIDTH_DXA - sum(scaled)
                return scaled
        scores = []
        for col in range(columns):
            lengths = [min(len(re.sub(r"<br>", " ", row[col])), 120) for row in rows]
            header = headers[col]
            score = max(10, sum(lengths) / max(1, len(lengths)))
            if any(token in header for token in ("id", "week", "status", "date", "owner", "role", "priority")):
                score *= 0.65
            if any(token in header for token in ("description", "activities", "deliverable", "evidence", "criteria", "requirement", "mitigation")):
                score *= 1.5
            scores.append(max(score, 8))
        minimum = 1050 if columns <= 6 else 800
        widths = [max(minimum, round(CONTENT_WIDTH_DXA * score / sum(scores))) for score in scores]
        while sum(widths) > CONTENT_WIDTH_DXA:
            index = max(range(columns), key=lambda i: widths[i])
            if widths[index] <= minimum:
                break
            widths[index] -= 10
        while sum(widths) < CONTENT_WIDTH_DXA:
            widths[max(range(columns), key=lambda i: scores[i])] += 1
        return widths

    def build_table(self, lines: Sequence[str]):
        rows = self._parse_table_rows(lines)
        if not rows:
            return None
        if len(rows[0]) > 5:
            # Word cannot keep six-to-eight narrative columns readable on a
            # portrait Letter page. Preserve every value while splitting the
            # record into continuation tables that repeat the identifier.
            tables = []
            for start in range(1, len(rows[0]), 4):
                columns = [0] + list(range(start, min(start + 4, len(rows[0]))))
                continuation_rows = [[row[index] for index in columns] for row in rows]
                tables.append(self._build_table_rows(continuation_rows))
            return tables
        return self._build_table_rows(rows)

    def _build_table_rows(self, rows: Sequence[Sequence[str]]):
        cols = len(rows[0])
        # A single-row Markdown table is used by the legacy signature block
        # for signer names and acceptance dates. It is a continuation/data
        # row, not a header, so do not render it as a purple header band.
        has_header = len(rows) > 1
        widths = self._column_widths(rows)
        font_size = 7.25 if cols == 5 else 7.5 if cols == 4 else 8
        table = self.doc.add_table(rows=len(rows), cols=cols)
        table.alignment = WD_TABLE_ALIGNMENT.LEFT
        table.autofit = False
        table.style = "Table Grid"
        self._set_table_geometry(table, widths)
        self._set_table_borders(table)

        for row_index, values in enumerate(rows):
            row = table.rows[row_index]
            self._set_row_cant_split(row)
            if has_header and row_index == 0:
                self._set_repeat_header(row)
            for col_index, value in enumerate(values):
                cell = row.cells[col_index]
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                self._set_cell_margins(cell)
                self._set_cell_width(cell, widths[col_index])
                fill = PURPLE if has_header and row_index == 0 else (LIGHT_FILL if row_index % 2 == 1 else "FFFFFF")
                self._set_cell_shading(cell, fill)
                paragraph = cell.paragraphs[0]
                paragraph.paragraph_format.space_before = Pt(1)
                paragraph.paragraph_format.space_after = Pt(1)
                paragraph.paragraph_format.line_spacing = 1.0
                align_center = row_index > 0 and (
                    len(value) < 28 or any(token in rows[0][col_index].lower() for token in ("id", "status", "date", "week", "priority"))
                )
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER if align_center else WD_ALIGN_PARAGRAPH.LEFT
                pieces = re.split(r"<br\s*/?>", value, flags=re.I)
                for piece_index, piece in enumerate(pieces):
                    if piece_index:
                        paragraph.add_run().add_break(WD_BREAK.LINE)
                    self._add_rich_runs(
                        paragraph,
                        re.sub(r"^[•-]\s*", "", piece.strip()),
                        size=font_size,
                        color="FFFFFF" if has_header and row_index == 0 else INK,
                    )
                for run in paragraph.runs:
                    if has_header and row_index == 0:
                        run.bold = True
        spacer = self.doc.add_paragraph()
        spacer.paragraph_format.space_after = Pt(0)
        spacer.paragraph_format.line_spacing = 0.5
        return table

    @staticmethod
    def _set_table_geometry(table, widths: Sequence[int]) -> None:
        tbl = table._tbl
        tblpr = tbl.tblPr
        layout = tblpr.find(qn("w:tblLayout"))
        if layout is None:
            layout = OxmlElement("w:tblLayout")
            tblpr.append(layout)
        layout.set(qn("w:type"), "fixed")
        tblw = tblpr.find(qn("w:tblW"))
        if tblw is None:
            tblw = OxmlElement("w:tblW")
            tblpr.append(tblw)
        tblw.set(qn("w:w"), str(CONTENT_WIDTH_DXA))
        tblw.set(qn("w:type"), "dxa")
        indent = tblpr.find(qn("w:tblInd"))
        if indent is None:
            indent = OxmlElement("w:tblInd")
            tblpr.append(indent)
        indent.set(qn("w:w"), str(TABLE_INDENT_DXA))
        indent.set(qn("w:type"), "dxa")
        grid = tbl.tblGrid
        for child in list(grid):
            grid.remove(child)
        for width in widths:
            col = OxmlElement("w:gridCol")
            col.set(qn("w:w"), str(width))
            grid.append(col)

    @staticmethod
    def _set_table_borders(table) -> None:
        tblpr = table._tbl.tblPr
        borders = tblpr.find(qn("w:tblBorders"))
        if borders is None:
            borders = OxmlElement("w:tblBorders")
            tblpr.append(borders)
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            element = borders.find(qn(f"w:{edge}"))
            if element is None:
                element = OxmlElement(f"w:{edge}")
                borders.append(element)
            element.set(qn("w:val"), "single")
            element.set(qn("w:sz"), "4")
            element.set(qn("w:space"), "0")
            element.set(qn("w:color"), BORDER)

    @staticmethod
    def _set_cell_width(cell, width: int) -> None:
        tcpr = cell._tc.get_or_add_tcPr()
        tcw = tcpr.find(qn("w:tcW"))
        if tcw is None:
            tcw = OxmlElement("w:tcW")
            tcpr.append(tcw)
        tcw.set(qn("w:w"), str(width))
        tcw.set(qn("w:type"), "dxa")

    @staticmethod
    def _set_cell_margins(cell) -> None:
        tcpr = cell._tc.get_or_add_tcPr()
        margins = tcpr.find(qn("w:tcMar"))
        if margins is None:
            margins = OxmlElement("w:tcMar")
            tcpr.append(margins)
        for side, value in (("top", 55), ("bottom", 55), ("start", 75), ("end", 75)):
            element = margins.find(qn(f"w:{side}"))
            if element is None:
                element = OxmlElement(f"w:{side}")
                margins.append(element)
            element.set(qn("w:w"), str(value))
            element.set(qn("w:type"), "dxa")

    @staticmethod
    def _set_cell_shading(cell, fill: str) -> None:
        tcpr = cell._tc.get_or_add_tcPr()
        shading = tcpr.find(qn("w:shd"))
        if shading is None:
            shading = OxmlElement("w:shd")
            tcpr.append(shading)
        # Word requires an explicit shading pattern; LibreOffice is more
        # forgiving. Without w:val, Word may omit the purple fill while the
        # white header text remains, making every table header look blank.
        shading.set(qn("w:val"), "clear")
        shading.set(qn("w:color"), "auto")
        shading.set(qn("w:fill"), fill)

    @staticmethod
    def _set_repeat_header(row) -> None:
        trpr = row._tr.get_or_add_trPr()
        header = trpr.find(qn("w:tblHeader"))
        if header is None:
            header = OxmlElement("w:tblHeader")
            trpr.append(header)
        header.set(qn("w:val"), "1")

    @staticmethod
    def _set_row_cant_split(row) -> None:
        trpr = row._tr.get_or_add_trPr()
        if trpr.find(qn("w:cantSplit")) is None:
            trpr.append(OxmlElement("w:cantSplit"))

    def has_table(self, content: str) -> bool:
        return bool(re.search(r"(?m)^\s*\|.+\|\s*$", content or ""))

    def parse_table(self, content: str):
        """Compatibility helper that retains all non-table text in source order."""
        table_lines = [line for line in (content or "").splitlines() if re.match(r"^\s*\|.+\|\s*$", line)]
        other = [line for line in (content or "").splitlines() if line not in table_lines and line.strip()]
        return other, table_lines


class DocumentBuilder:
    """Build a branded, accessible, navigable DOCX from section Markdown."""

    RESERVED_KEYS = {
        "cover_page", "toc_structure", "table_of_contents", "tableofcontents",
        "table_contents", "generation_quality_summary",
    }

    def __init__(self, config):
        self.config = config
        self.doc: Optional[Document] = None
        self.section_builder: Optional[SectionBuilder] = None
        self.toc_entries: List[str] = []
        self.expanded_toc_entries: List[Tuple[str, str, int]] = []
        self.subheading_anchor_maps: Dict[str, Dict[str, str]] = {}
        self._bookmark_ids = 0

    @staticmethod
    def _get_short_company_name(company_name: str) -> str:
        name = company_name or ""
        for suffix in (" Pvt Ltd", " Private Limited", " Ltd", " LLC", " Inc", " Corporation", " Corp", " Limited", " Company"):
            if name.lower().endswith(suffix.lower()):
                return name[:-len(suffix)].strip()
        return name

    @staticmethod
    def _name_to_key(name: str) -> str:
        name = re.sub(r"^\s*\d+(?:\.\d+)*[.)]?\s*", "", name)
        return re.sub(r"[-\s]+", "_", re.sub(r"[^\w\s-]", "", name.lower())).strip("_")

    @staticmethod
    def _is_similar(section_name: str, key: str) -> bool:
        stop = {"the", "of", "and", "to", "a", "in", "for"}
        words_a = set(re.findall(r"\w+", section_name.lower())) - stop
        words_b = set(re.findall(r"\w+", key.replace("_", " ").lower())) - stop
        return bool(words_a and words_b and len(words_a & words_b) / max(len(words_a), len(words_b)) >= 0.55)

    def _parse_toc_entries(self, sections: Dict[str, Any]) -> None:
        content = next((str(sections[key]) for key in ("toc_structure", "table_of_contents", "tableofcontents", "table_contents") if sections.get(key)), "")
        entries: List[str] = []
        lines = [line for line in content.splitlines() if line.strip()]
        for line in lines:
            match = re.match(r"^\s*\d+[.)]\s+(.+?)\s*$", line)
            if match:
                # Explicit template numbering is part of the document contract;
                # never discard it based on the presence/absence of front matter.
                entries.append(line.strip())
                continue
            plain = line.strip()
            if plain and not plain.startswith(("#", "|", "[")):
                entries.append(plain)
        if not entries:
            entries = [key.replace("_", " ").title() for key, value in sections.items() if key not in self.RESERVED_KEYS and value]
        self.toc_entries = entries

    def _configure_styles(self) -> None:
        assert self.doc is not None
        styles = self.doc.styles
        normal = styles["Normal"]
        normal.font.name = FONT_NAME
        normal.font.size = Pt(9.25)
        normal._element.rPr.rFonts.set(qn("w:ascii"), FONT_NAME)
        normal._element.rPr.rFonts.set(qn("w:hAnsi"), FONT_NAME)
        normal.paragraph_format.space_before = Pt(0)
        normal.paragraph_format.space_after = Pt(4)
        normal.paragraph_format.line_spacing = 1.12
        normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        normal.paragraph_format.widow_control = True

        tokens = {
            "Heading 1": (16.25, PURPLE, 15, 6),
            "Heading 2": (11.5, BLUE, 10, 3.5),
            "Heading 3": (9.75, DARK_PURPLE, 7, 2.5),
            "Heading 4": (9.1, INK, 5, 2),
        }
        for style_name, (size, color, before, after) in tokens.items():
            style = styles[style_name]
            style.font.name = FONT_NAME
            style.font.size = Pt(size)
            style.font.bold = True
            style.font.color.rgb = RGBColor.from_string(color)
            style._element.rPr.rFonts.set(qn("w:ascii"), FONT_NAME)
            style._element.rPr.rFonts.set(qn("w:hAnsi"), FONT_NAME)
            style.paragraph_format.space_before = Pt(before)
            style.paragraph_format.space_after = Pt(after)
            style.paragraph_format.keep_with_next = True
            style.paragraph_format.widow_control = True
            style.paragraph_format.page_break_before = False

        caption = styles["Caption"]
        caption.font.name = FONT_NAME
        caption.font.size = Pt(7.5)
        caption.font.italic = True
        caption.font.color.rgb = RGBColor.from_string(MUTED)
        caption.paragraph_format.space_before = Pt(4)
        caption.paragraph_format.space_after = Pt(4)

    def _add_numbering(self) -> None:
        assert self.doc is not None
        numbering = self.doc.part.numbering_part.element
        for abstract_id, num_id, fmt, text_values in (
            (91, 91, "bullet", ["•", "○", "▪"]),
            (92, 92, "decimal", ["%1.", "%2.", "%3."]),
        ):
            abstract = OxmlElement("w:abstractNum")
            abstract.set(qn("w:abstractNumId"), str(abstract_id))
            multi = OxmlElement("w:multiLevelType")
            multi.set(qn("w:val"), "hybridMultilevel")
            abstract.append(multi)
            for level in range(3):
                lvl = OxmlElement("w:lvl")
                lvl.set(qn("w:ilvl"), str(level))
                start = OxmlElement("w:start")
                start.set(qn("w:val"), "1")
                numfmt = OxmlElement("w:numFmt")
                numfmt.set(qn("w:val"), fmt)
                lvltext = OxmlElement("w:lvlText")
                lvltext.set(qn("w:val"), text_values[level])
                lvl_just = OxmlElement("w:lvlJc")
                lvl_just.set(qn("w:val"), "left")
                ppr = OxmlElement("w:pPr")
                tabs = OxmlElement("w:tabs")
                tab = OxmlElement("w:tab")
                tab.set(qn("w:val"), "num")
                tab.set(qn("w:pos"), str(540 + level * 360))
                tabs.append(tab)
                indent = OxmlElement("w:ind")
                indent.set(qn("w:left"), str(540 + level * 360))
                indent.set(qn("w:hanging"), "280")
                spacing = OxmlElement("w:spacing")
                spacing.set(qn("w:after"), "80")
                spacing.set(qn("w:line"), "290")
                spacing.set(qn("w:lineRule"), "auto")
                ppr.extend([tabs, indent, spacing])
                lvl.extend([start, numfmt, lvltext, lvl_just, ppr])
                abstract.append(lvl)
            num = OxmlElement("w:num")
            num.set(qn("w:numId"), str(num_id))
            ref = OxmlElement("w:abstractNumId")
            ref.set(qn("w:val"), str(abstract_id))
            num.append(ref)
            numbering.extend([abstract, num])

    def build_document(self, sections: Dict[str, Any], metadata: Dict[str, Any], mode: str = "POC") -> Optional[Path]:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = "PROD" if mode in ("PROD", "POC_TO_PROD") else "POC"
        safe_company = re.sub(r"[^A-Za-z0-9_-]+", "_", metadata.get("company_name", "Client")).strip("_")
        path = Path(self.config.OUTPUT_DIR) / f"{prefix}_{safe_company}_{timestamp}.docx"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._parse_toc_entries(sections)
        try:
            self._build_docx(path, sections, metadata, mode)
            return path
        except Exception as exc:
            print(f"❌ Error building DOCX: {exc}")
            import traceback
            traceback.print_exc()
            return None

    def _build_docx(self, output_path: Path, sections: Dict[str, Any], metadata: Dict[str, Any], mode: str) -> None:
        self.doc = Document()
        self._configure_styles()
        self._add_numbering()
        self.section_builder = SectionBuilder(self.doc, self.config)
        _mark_update_fields(self.doc)
        self.toc_entries = [self._resolve_title(entry, metadata) for entry in self.toc_entries]

        cover_section = self.doc.sections[0]
        cover_section.page_width = Inches(PAGE_WIDTH_IN)
        cover_section.page_height = Inches(PAGE_HEIGHT_IN)
        cover_section.top_margin = cover_section.bottom_margin = Inches(0)
        cover_section.left_margin = cover_section.right_margin = Inches(0)
        # The cover is already isolated in its own section.  Avoid w:titlePg:
        # LibreOffice can incorrectly reuse that page style after later breaks.
        cover_section.different_first_page_header_footer = False
        cover_path = generate_cover_image(metadata, self.config)
        if cover_path:
            paragraph = self.doc.add_paragraph()
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = Pt(1)
            run = paragraph.add_run()
            shape = run.add_picture(
                str(cover_path),
                width=Inches(PAGE_WIDTH_IN),
                height=Inches(PAGE_HEIGHT_IN),
            )
            # A full-page inline image participates in line layout: Word can
            # push the following section break to an empty page. Anchor the
            # cover to the page at (0, 0), behind text, so it has no pagination
            # footprint while remaining full bleed.
            self._anchor_cover_to_page(shape)
            docpr = shape._inline.docPr
            docpr.set("descr", f"Cover for {metadata.get('project_title', 'Statement of Work')} prepared for {metadata.get('company_name', 'the customer')}")

        content_section = self.doc.add_section(WD_SECTION.NEW_PAGE)
        content_section.page_width = Inches(PAGE_WIDTH_IN)
        content_section.page_height = Inches(PAGE_HEIGHT_IN)
        content_section.top_margin = Inches(TOP_MARGIN_IN)
        content_section.bottom_margin = Inches(BOTTOM_MARGIN_IN)
        content_section.left_margin = content_section.right_margin = Inches(HORIZONTAL_MARGIN_IN)
        content_section.header_distance = Inches(0.28)
        content_section.footer_distance = Inches(0.25)
        # add_section() clones the preceding cover section's title-page flag.
        # Clear it so later page-break-before headings do not inherit the cover
        # section's first-page header/footer treatment in LibreOffice.
        content_section.different_first_page_header_footer = False
        content_section.header.is_linked_to_previous = False
        content_section.footer.is_linked_to_previous = False
        self._add_header_footer(content_section, metadata, mode)
        self._prepare_expanded_toc(sections)

        # The benchmark places Document Control immediately after the cover,
        # then the TOC, then the substantive body. Keep that ordering while
        # retaining Document Control in the TOC and its bookmark map.
        preface_position = next(
            (index for index, name in enumerate(self.toc_entries)
             if name.casefold().startswith("document control")),
            None,
        )
        if preface_position is not None:
            self._build_section(
                self.toc_entries[preface_position], sections, metadata, preface_position
            )
            self.doc.add_page_break()

        self._add_toc()
        self.doc.add_page_break()
        for position, section_name in enumerate(self.toc_entries):
            if position == preface_position:
                continue
            self._build_section(section_name, sections, metadata, position)

        props = self.doc.core_properties
        props.author = metadata.get("author_name", "")
        props.last_modified_by = metadata.get("author_name", "")
        props.title = metadata.get("project_title", "")
        props.subject = f"{mode} Statement of Work for {metadata.get('company_name', '')}"
        props.keywords = "Statement of Work, SOW, AWS, ShellKode"
        props.comments = "Generated from source-grounded requirements; proposals and open clarifications are labelled."
        self.doc.save(str(output_path))
        if cover_path:
            try:
                cover_path.unlink()
            except OSError:
                pass
        print(f"✓ DOCX saved: {output_path}")

    @staticmethod
    def _anchor_cover_to_page(shape) -> None:
        inline = shape._inline
        inline.tag = qn("wp:anchor")
        for attribute, value in (
            ("distT", "0"), ("distB", "0"), ("distL", "0"), ("distR", "0"),
            ("simplePos", "0"), ("relativeHeight", "0"), ("behindDoc", "1"),
            ("locked", "0"), ("layoutInCell", "1"), ("allowOverlap", "1"),
        ):
            inline.set(attribute, value)
        simple = OxmlElement("wp:simplePos")
        simple.set("x", "0")
        simple.set("y", "0")
        horizontal = OxmlElement("wp:positionH")
        horizontal.set("relativeFrom", "page")
        horizontal_offset = OxmlElement("wp:posOffset")
        horizontal_offset.text = "0"
        horizontal.append(horizontal_offset)
        vertical = OxmlElement("wp:positionV")
        vertical.set("relativeFrom", "page")
        vertical_offset = OxmlElement("wp:posOffset")
        vertical_offset.text = "0"
        vertical.append(vertical_offset)
        inline.insert(0, simple)
        inline.insert(1, horizontal)
        inline.insert(2, vertical)
        effect = inline.find(qn("wp:effectExtent"))
        wrap = OxmlElement("wp:wrapNone")
        if effect is not None:
            inline.insert(list(inline).index(effect) + 1, wrap)
        else:
            extent = inline.find(qn("wp:extent"))
            inline.insert(list(inline).index(extent) + 1 if extent is not None else 3, wrap)

    def _add_header_footer(self, section, metadata: Dict[str, Any], mode: str) -> None:
        header = section.header
        trailing_paragraph = header.paragraphs[0]
        trailing_paragraph.paragraph_format.space_before = Pt(0)
        trailing_paragraph.paragraph_format.space_after = Pt(0)
        trailing_paragraph.paragraph_format.line_spacing = Pt(1)
        header_table = header.add_table(
            rows=1, cols=2, width=Inches(PAGE_WIDTH_IN - 2 * HORIZONTAL_MARGIN_IN)
        )
        header_table.alignment = WD_TABLE_ALIGNMENT.LEFT
        header_table.autofit = False
        header_widths = [8600, CONTENT_WIDTH_DXA - 8600]
        SectionBuilder._set_table_geometry(header_table, header_widths)
        self._remove_table_borders(header_table)
        # Put the table before the required trailing paragraph in the header.
        header._element.remove(header_table._tbl)
        header._element.insert(0, header_table._tbl)
        left_cell, right_cell = header_table.rows[0].cells
        for cell, width in zip((left_cell, right_cell), header_widths):
            SectionBuilder._set_cell_width(cell, width)
            self._set_zero_cell_margins(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        left_paragraph = left_cell.paragraphs[0]
        right_paragraph = right_cell.paragraphs[0]
        left_paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
        right_paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        for paragraph in (left_paragraph, right_paragraph):
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = 1.0
        header_title = metadata.get("document_header_title")
        if not header_title:
            mode_label = {
                "POC": "POC",
                "PROD": "Production",
                "POC_TO_PROD": "POC to Production",
            }.get(mode, mode)
            project = metadata.get("project_title", "Statement of Work")
            header_title = project if "sow" in project.casefold() else f"{project} – SOW ({mode_label})"
        left = left_paragraph.add_run(str(header_title))
        _set_font(left, size=6.5, bold=True, color=BLUE)
        logo_path = Path(self.config.ASSETS_DIR) / "ShellKode.png"
        if logo_path.exists():
            logo_run = right_paragraph.add_run()
            shape = logo_run.add_picture(str(logo_path), width=Inches(0.72))
            shape._inline.docPr.set("descr", "ShellKode")
        else:
            right = right_paragraph.add_run(self._get_short_company_name(metadata.get("author_org", "ShellKode")))
            _set_font(right, size=7, bold=True, color=BLUE)

        footer = section.footer
        paragraph = footer.paragraphs[0]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
        paragraph.paragraph_format.space_before = Pt(2)
        paragraph.paragraph_format.tab_stops.add_tab_stop(Inches(7.14), WD_TAB_ALIGNMENT.RIGHT)
        self._set_paragraph_top_border(paragraph, BORDER)
        org = self._get_short_company_name(metadata.get("author_org", "ShellKode"))
        year_match = re.search(r"\b(20\d{2})\b", str(metadata.get("document_date", "")))
        year = year_match.group(1) if year_match else str(datetime.now().year)
        left = paragraph.add_run(f"Confidential Copyright © {org} {year}")
        _set_font(left, size=5.75, color=MUTED)
        right = paragraph.add_run("\tPage ")
        _set_font(right, size=5.75, color=MUTED)
        _add_field(paragraph, "PAGE", "1", size=5.75)
        of = paragraph.add_run(" of ")
        _set_font(of, size=5.75, color=MUTED)
        _add_field(paragraph, "NUMPAGES", "1", size=5.75)

    @staticmethod
    def _remove_table_borders(table) -> None:
        tblpr = table._tbl.tblPr
        borders = tblpr.find(qn("w:tblBorders"))
        if borders is None:
            borders = OxmlElement("w:tblBorders")
            tblpr.append(borders)
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            element = borders.find(qn(f"w:{edge}"))
            if element is None:
                element = OxmlElement(f"w:{edge}")
                borders.append(element)
            element.set(qn("w:val"), "nil")

    @staticmethod
    def _set_zero_cell_margins(cell) -> None:
        tcpr = cell._tc.get_or_add_tcPr()
        margins = tcpr.find(qn("w:tcMar"))
        if margins is None:
            margins = OxmlElement("w:tcMar")
            tcpr.append(margins)
        for side in ("top", "bottom", "start", "end"):
            element = margins.find(qn(f"w:{side}"))
            if element is None:
                element = OxmlElement(f"w:{side}")
                margins.append(element)
            element.set(qn("w:w"), "0")
            element.set(qn("w:type"), "dxa")

    def _prepare_expanded_toc(self, sections: Dict[str, Any]) -> None:
        """Build a benchmark-like TOC containing top-level and H2 entries."""
        self.expanded_toc_entries = []
        self.subheading_anchor_maps = {}
        subheading_index = 1000
        for position, entry in enumerate(self.toc_entries, 1):
            top_anchor = _bookmark_name(entry, position)
            self.expanded_toc_entries.append((entry, top_anchor, 1))
            content = self._resolve_content(entry, sections)
            major_match = re.match(r"^\s*(\d+)[.)]?\s+", entry)
            major = major_match.group(1) if major_match else None
            anchor_map: Dict[str, str] = {}
            for label, level in SectionBuilder.enumerate_headings(content, major):
                if level != 2:
                    continue
                subheading_index += 1
                anchor = _bookmark_name(label, subheading_index)
                anchor_map[label] = anchor
                self.expanded_toc_entries.append((label, anchor, 2))
            self.subheading_anchor_maps[entry] = anchor_map

    @staticmethod
    def _set_paragraph_top_border(paragraph, color: str) -> None:
        ppr = paragraph._element.get_or_add_pPr()
        borders = ppr.find(qn("w:pBdr"))
        if borders is None:
            borders = OxmlElement("w:pBdr")
            ppr.append(borders)
        top = OxmlElement("w:top")
        top.set(qn("w:val"), "single")
        top.set(qn("w:sz"), "4")
        top.set(qn("w:space"), "4")
        top.set(qn("w:color"), color)
        borders.append(top)

    @staticmethod
    def _set_paragraph_bottom_border(paragraph, color: str) -> None:
        ppr = paragraph._element.get_or_add_pPr()
        borders = ppr.find(qn("w:pBdr"))
        if borders is None:
            borders = OxmlElement("w:pBdr")
            ppr.append(borders)
        bottom = borders.find(qn("w:bottom"))
        if bottom is None:
            bottom = OxmlElement("w:bottom")
            borders.append(bottom)
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "8")
        bottom.set(qn("w:space"), "3")
        bottom.set(qn("w:color"), color)

    def _add_toc(self) -> None:
        assert self.doc is not None
        title = self.doc.add_paragraph(style="Heading 1")
        title.add_run("Table of Contents")
        self._set_paragraph_bottom_border(title, PURPLE)
        entries = self.expanded_toc_entries or [
            (entry, _bookmark_name(entry, index), 1)
            for index, entry in enumerate(self.toc_entries, 1)
        ]
        entries_are_numbered = any(re.match(r"^\d+[.)]\s+", entry[0]) for entry in entries if entry[2] == 1)
        for index, (entry, anchor, level) in enumerate(entries, 1):
            paragraph = self.doc.add_paragraph()
            paragraph.paragraph_format.left_indent = Inches(0.02 if level == 1 else 0.22)
            paragraph.paragraph_format.space_after = Pt(1.3 if level == 1 else 0.5)
            paragraph.paragraph_format.line_spacing = 1.0
            paragraph.paragraph_format.tab_stops.add_tab_stop(Inches(7.0), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
            display = entry if entries_are_numbered or level > 1 else f"{index}. {entry}"
            _add_hyperlink(paragraph, display, anchor)
            tab = paragraph.add_run("\t")
            toc_size = 7.5 if level == 1 else 6.75
            _set_font(tab, size=toc_size)
            _add_field(paragraph, f"PAGEREF {anchor} \\h", "", size=toc_size)

    def _resolve_content(self, section_name: str, sections: Dict[str, Any]) -> str:
        key = self._name_to_key(section_name)
        aliases = {
            "document_control": ("document_control_and_basis",),
            "purpose_and_scope_of_this_deliverable": ("project_overview",),
            "deliverable_scope_at_a_glance": ("scope_at_a_glance",),
            "current_state": ("current_state_and_business_context",),
            "executive_summary_and_project_overview": ("project_overview", "project_overview_objectives"),
            "detailed_scope_of_work": ("scope_of_work",),
            "detailed_production_scope_of_work": ("scope_of_work",),
            "architecture_overview": ("architecture_diagram", "architecture_integrations"),
            "solution_architecture_aws": ("architecture_diagram", "architecture_integrations"),
            "architecture_and_integrations": ("architecture_integrations", "architecture_diagram"),
            "assumptions_and_dependencies": ("assumptions",),
            "terms_and_conditions": ("terms_conditions",),
        }
        if key.endswith("_project_team_effort"):
            aliases[key] = ("shellkode_implementation_cost", "implementation_cost")
        for candidate in (key,) + aliases.get(key, ()):
            if sections.get(candidate):
                return str(sections[candidate])
        for candidate, content in sections.items():
            if candidate not in self.RESERVED_KEYS and content and self._is_similar(section_name, candidate):
                return str(content)
        return ""

    @staticmethod
    def _resolve_title(title: str, metadata: Dict[str, Any]) -> str:
        replacements = {
            "{AUTHOR_ORG_SHORT}": DocumentBuilder._get_short_company_name(metadata.get("author_org", "ShellKode")),
            "{COMPANY_NAME}": metadata.get("company_name", "Customer"),
            "{COMPANY_NAME_SHORT}": DocumentBuilder._get_short_company_name(metadata.get("company_name", "Customer")),
            "{PROJECT_TITLE}": metadata.get("project_title", "Project"),
        }
        resolved = title
        for placeholder, value in replacements.items():
            resolved = resolved.replace(placeholder, str(value))
        return resolved

    def _build_section(self, section_name: str, sections: Dict[str, Any], metadata: Dict[str, Any], position: int) -> None:
        assert self.doc is not None and self.section_builder is not None
        author_about = f"About {self._get_short_company_name(metadata.get('author_org', 'ShellKode'))}"
        customer_about = f"About {metadata.get('company_name', 'Customer')}"
        if section_name.casefold() == author_about.casefold():
            content = str(sections.get("about_shellkode", ""))
        elif section_name.casefold() == customer_about.casefold():
            content = str(sections.get("about_company", ""))
        else:
            content = self._resolve_content(section_name, sections)
        if not content:
            print(f"⚠ No content for {section_name!r}; omitted from body")
            return
        heading = self.doc.add_paragraph(style="Heading 1")
        heading.add_run(section_name)
        self._set_paragraph_bottom_border(heading, PURPLE)
        self._add_bookmark_to_heading(heading, section_name, position + 1)
        major_match = re.match(r"^\s*(\d+)[.)]?\s+", section_name)
        major = major_match.group(1) if major_match else None
        self.section_builder.parse_content(
            content,
            heading_prefix=major,
            heading_anchor_map=self.subheading_anchor_maps.get(section_name, {}),
            bookmark_callback=self._add_bookmark_with_anchor,
        )

    def _add_bookmark_with_anchor(self, paragraph, anchor: str) -> None:
        self._bookmark_ids += 1
        bookmark_id = self._bookmark_ids
        start = OxmlElement("w:bookmarkStart")
        start.set(qn("w:id"), str(bookmark_id))
        start.set(qn("w:name"), anchor)
        end = OxmlElement("w:bookmarkEnd")
        end.set(qn("w:id"), str(bookmark_id))
        paragraph._p.insert(0, start)
        paragraph._p.append(end)

    def _add_bookmark_to_heading(self, heading, section_name: str, position: Optional[int] = None) -> None:
        self._bookmark_ids += 1
        bookmark_id = self._bookmark_ids
        anchor = _bookmark_name(section_name, position or bookmark_id)
        start = OxmlElement("w:bookmarkStart")
        start.set(qn("w:id"), str(bookmark_id))
        start.set(qn("w:name"), anchor)
        end = OxmlElement("w:bookmarkEnd")
        end.set(qn("w:id"), str(bookmark_id))
        heading._p.insert(0, start)
        heading._p.append(end)


def add_toc_field(doc):
    """Backward-compatible dynamic TOC field helper."""
    paragraph = doc.add_paragraph()
    _add_field(paragraph, 'TOC \\o "1-3" \\h \\z \\u', "Update field to refresh table of contents")
    return paragraph
