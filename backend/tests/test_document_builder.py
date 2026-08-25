import re
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from docx import Document
from docx.oxml.ns import qn

from app.document.document_builder import (
    CHROME_INSET_IN,
    DocumentBuilder,
    _bookmark_name,
    _find_libreoffice_binary,
    _pageref_results_from_xml,
)


class _Config:
    def __init__(self, output_dir):
        backend = Path(__file__).resolve().parents[1]
        self.OUTPUT_DIR = Path(output_dir)
        self.ASSETS_DIR = backend / "assets"
        self.COVER_PAGE_IMAGE = backend / "assets" / "coverpage.png"


class DocumentBuilderTests(unittest.TestCase):
    def test_bookmark_names_stay_within_word_limit_and_remain_unique(self):
        title = "10.2 Effort Basis and Key Assumptions Affecting Delivery"
        first = _bookmark_name(title, 1034)
        second = _bookmark_name(title, 1035)
        self.assertLessEqual(len(first), 40)
        self.assertLessEqual(len(second), 40)
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("SOW_1034_"))

    def test_finds_bundled_libreoffice_when_it_is_not_on_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_home = Path(temp_dir)
            bundled = (
                fake_home
                / ".cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/soffice"
            )
            bundled.parent.mkdir(parents=True)
            bundled.write_text("#!/bin/sh\n", encoding="utf-8")
            bundled.chmod(0o755)
            with patch("app.document.document_builder.shutil.which", return_value=None), patch(
                "app.document.document_builder.Path.home", return_value=fake_home
            ):
                self.assertEqual(
                    _find_libreoffice_binary(_Config(temp_dir)), str(bundled)
                )

    def test_builder_preserves_order_semantics_and_geometry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            builder = DocumentBuilder(_Config(temp_dir))
            sections = {
                "toc_structure": (
                    "1. Project Overview\n"
                    "2. Detailed Scope of Work\n"
                    "3. About Example Customer"
                ),
                "project_overview": (
                    "### Business Need\nA concise source-grounded overview.\n\n"
                    "- Confirm the selected workflow.\n"
                    "  - Record review evidence.\n"
                    "- Preserve the agreed boundary.\n\n"
                    "| Field | Value |\n|---|---|\n| Mode | POC |\n\n"
                    "Text after the first table must remain visible.\n\n"
                    "| ID | Evidence | Status |\n|---|---|---|\n| SC-01 | Test report | Proposed |"
                ),
                "scope_of_work": (
                    "### Module A\n#### Workflow\n1. Receive input.\n2. Validate input.\n\n"
                    "### Module B\n#### Workflow\n1. Process input.\n2. Record evidence.\n\n"
                    "### Effort Basis and Key Assumptions Affecting Delivery\n"
                    "A deliberately long TOC heading exercises the Word bookmark limit."
                ),
            }
            metadata = {
                "company_name": "Example Customer",
                "project_title": "Agentic CRM Platform",
                "author_name": "Test Author",
                "author_org": "ShellKode",
                "document_date": "18 August 2026",
                "version": "1.0",
            }
            output = builder.build_document(sections, metadata, mode="POC")
            self.assertIsNotNone(output)
            self.assertTrue(Path(output).exists())

            document = Document(output)
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
            self.assertIn("Table of Contents", text)
            self.assertIn("Text after the first table must remain visible.", text)
            paragraph_texts = [paragraph.text for paragraph in document.paragraphs]
            toc_index = paragraph_texts.index("Table of Contents")
            first_body_index = paragraph_texts.index("1. Project Overview")
            toc_text = "\n".join(
                paragraph.text for paragraph in document.paragraphs[toc_index:first_body_index]
            )
            self.assertIn("Business Need", toc_text)
            self.assertIn("Module A", toc_text)
            self.assertIn("Module B", toc_text)
            self.assertNotIn("About Example Customer", toc_text)
            toc_paragraphs = document.paragraphs[toc_index + 1:first_body_index]
            subtopic_rows = [
                paragraph for paragraph in toc_paragraphs
                if any(label in paragraph.text for label in ("Business Need", "Module A", "Module B"))
            ]
            self.assertTrue(subtopic_rows)
            self.assertTrue(all("\t" not in paragraph.text for paragraph in subtopic_rows))
            self.assertGreaterEqual(len(document.tables), 2)
            self.assertTrue(all(
                paragraph.alignment == 0
                for table in document.tables
                for row in table.rows
                for cell in row.cells
                for paragraph in cell.paragraphs
            ))
            table_captions = [
                paragraph for paragraph in document.paragraphs
                if re.match(r"^Table \d+:", paragraph.text)
            ]
            self.assertEqual(len(table_captions), len(document.tables))
            self.assertTrue(all(paragraph.style.font.italic for paragraph in table_captions))
            self.assertTrue(any(p.style.name == "Heading 2" and p.text == "1.1 Business Need" for p in document.paragraphs))
            self.assertTrue(any(p.style.name == "Heading 2" and p.text == "2.1 Module A" for p in document.paragraphs))
            self.assertTrue(any(p.style.name == "Heading 3" and p.text == "2.1.1 Workflow" for p in document.paragraphs))

            numbered = [
                paragraph for paragraph in document.paragraphs
                if paragraph.text in {"Receive input.", "Validate input.", "Process input.", "Record evidence."}
            ]
            num_ids = [
                paragraph._p.pPr.numPr.numId.val
                for paragraph in numbered
            ]
            self.assertEqual(num_ids[0], num_ids[1])
            self.assertEqual(num_ids[2], num_ids[3])
            self.assertNotEqual(num_ids[0], num_ids[2])

            bullets = [
                paragraph for paragraph in document.paragraphs
                if paragraph.text in {
                    "Confirm the selected workflow.",
                    "Record review evidence.",
                    "Preserve the agreed boundary.",
                }
            ]
            self.assertEqual(
                [paragraph._p.pPr.numPr.numId.val for paragraph in bullets],
                [91, 91, 91],
            )
            self.assertEqual(
                [paragraph._p.pPr.numPr.ilvl.val for paragraph in bullets],
                [0, 1, 0],
            )
            self.assertTrue(all(paragraph.alignment == 0 for paragraph in bullets))

            section = document.sections[-1]
            self.assertEqual(round(section.page_width.inches, 2), 8.5)
            self.assertEqual(round(section.page_height.inches, 2), 11.0)

            with zipfile.ZipFile(output) as package:
                document_xml_bytes = package.read("word/document.xml")
                xml = document_xml_bytes.decode("utf-8")
                numbering = package.read("word/numbering.xml").decode("utf-8")
            self.assertIn("w:tblHeader", xml)
            self.assertIn('<w:tblW', xml)
            self.assertIn('w:w="10282"', xml)
            self.assertIn('w:numId="91"', numbering)
            self.assertIn('w:numId="92"', numbering)
            self.assertIn("w:startOverride", numbering)
            self.assertIn("1.1 Business Need", xml)
            pageref_targets = re.findall(r"PAGEREF\s+([^\s<]+)\s+\\h", xml)
            bookmark_names = set(re.findall(r'<w:bookmarkStart[^>]+w:name="([^"]+)"', xml))
            self.assertTrue(pageref_targets)
            self.assertEqual(len(pageref_targets), 2)
            self.assertTrue(set(pageref_targets).issubset(bookmark_names))
            cached_page_numbers = _pageref_results_from_xml(document_xml_bytes)
            self.assertTrue(cached_page_numbers)
            self.assertTrue(all(value.isdigit() for value in cached_page_numbers.values()))

    def test_singular_timeline_title_resolves_shared_timeline_content_key(self):
        builder = DocumentBuilder.__new__(DocumentBuilder)
        sections = {"timelines_and_deliverables": "A source-grounded delivery sequence."}
        self.assertEqual(
            builder._resolve_content("3. Timeline and Deliverables", sections),
            "A source-grounded delivery sequence.",
        )

    def test_numbered_about_client_title_resolves_canonical_content_key(self):
        builder = DocumentBuilder.__new__(DocumentBuilder)
        metadata = {
            "company_name": "Example Customer",
            "author_org": "ShellKode",
        }
        self.assertEqual(
            builder._resolve_section_content(
                "2. About Example Customer",
                {"about_client": "A confirmed customer profile."},
                metadata,
            ),
            "A confirmed customer profile.",
        )

    def test_benchmark_order_chrome_and_wide_table_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            builder = DocumentBuilder(_Config(temp_dir))
            sections = {
                "toc_structure": (
                    "Document Version Control\n"
                    "1. Objective\n"
                    "Acceptance and Signatories to Statement of Work"
                ),
                "document_control_and_basis": (
                    "| Version | Date | Prepared By | Status | Classification |\n"
                    "|---|---|---|---|---|\n"
                    "| 1.0 | 18 August 2026 | Test Author | Draft for Client Review | Confidential |"
                ),
                "project_overview": (
                    "A source-grounded purpose.\n\n"
                    "| ID | Requirement | Source | Response | Output | Evidence | Owner | Status |\n"
                    "|---|---|---|---|---|---|---|---|\n"
                    "| R-1 | Route requests | BRD | Configure rules | Queue | Test log | Lead | Proposed |"
                ),
                "acceptance_and_signatories_to_statement_of_work": (
                    "| ShellKode | Example Customer |\n|---|---|\n"
                    "| Name: | Name: |\n| Title: | Title: |\n"
                    "| Signature: | Signature: |\n| Date: | Date: |"
                ),
            }
            metadata = {
                "company_name": "Example Customer",
                "project_title": "Agentic CRM Platform",
                "author_name": "Test Author",
                "author_org": "ShellKode",
                "document_date": "18 August 2026",
                "version": "1.0",
            }
            output = builder.build_document(sections, metadata, mode="POC")
            document = Document(output)
            body_text = [paragraph.text for paragraph in document.paragraphs]
            self.assertLess(body_text.index("Document Version Control"), body_text.index("Table of Contents"))
            self.assertLess(body_text.index("Table of Contents"), body_text.index("1. Objective"))
            self.assertEqual(len(document.tables), 4)  # 1 control + 2 split wide + 1 signature table

            signature_table = document.tables[-1]
            shading = signature_table.cell(0, 0)._tc.tcPr.find(qn("w:shd"))
            self.assertIsNotNone(shading)
            self.assertEqual(shading.get(qn("w:fill")), "5D3FD3")
            self.assertEqual(signature_table.cell(1, 0).text, "Name:")
            self.assertNotIn("Bhuvanesh", "\n".join(cell.text for row in signature_table.rows for cell in row.cells))

            control_header = document.tables[0].cell(0, 0)._tc.tcPr.find(qn("w:shd"))
            self.assertEqual(control_header.get(qn("w:val")), "clear")
            self.assertEqual(control_header.get(qn("w:color")), "auto")
            self.assertEqual(control_header.get(qn("w:fill")), "5D3FD3")

            content_section = document.sections[-1]
            self.assertAlmostEqual(content_section.left_margin.inches, 0.68, places=2)
            self.assertIn("Confidential Copyright © ShellKode 2026", content_section.footer.paragraphs[0].text)
            header_table = content_section.header.tables[0]
            left_header = header_table.cell(0, 0).paragraphs[0]
            right_header = header_table.cell(0, 2).paragraphs[0]
            self.assertAlmostEqual(
                left_header.paragraph_format.left_indent.inches,
                CHROME_INSET_IN,
                places=2,
            )
            self.assertAlmostEqual(
                right_header.paragraph_format.right_indent.inches,
                CHROME_INSET_IN,
                places=2,
            )
            self.assertTrue(left_header.text.startswith("Agentic CRM Platform"))
            self.assertEqual(left_header.alignment, 0)
            self.assertEqual(right_header.alignment, 2)
            self.assertEqual(content_section.footer.paragraphs[1].alignment, 1)

            with zipfile.ZipFile(output) as package:
                document_xml = package.read("word/document.xml").decode("utf-8")
                header_xml = "\n".join(
                    package.read(name).decode("utf-8")
                    for name in package.namelist()
                    if re.fullmatch(r"word/header\d+\.xml", name)
                )
                footer_xml = "\n".join(
                    package.read(name).decode("utf-8")
                    for name in package.namelist()
                    if re.fullmatch(r"word/footer\d+\.xml", name)
                )
                settings_xml = package.read("word/settings.xml").decode("utf-8")
                styles_xml = package.read("word/styles.xml").decode("utf-8")
                font_table_xml = package.read("word/fontTable.xml").decode("utf-8")
                font_relationships_xml = package.read(
                    "word/_rels/fontTable.xml.rels"
                ).decode("utf-8")
                package_names = set(package.namelist())
            self.assertEqual(document_xml.count('<w:br w:type="page"'), 2)
            self.assertNotIn('<w:pageBreakBefore w:val="0"', document_xml)
            self.assertIn("w:drawing", header_xml)
            self.assertIn("w:tbl", header_xml)
            self.assertIn('w:gridCol w:w="7200"', header_xml)
            self.assertIn('w:jc w:val="left"', header_xml)
            self.assertIn('w:jc w:val="right"', header_xml)
            self.assertIn("PAGE", footer_xml)
            self.assertIn("NUMPAGES", footer_xml)
            self.assertIn('<w:updateFields w:val="true"', settings_xml)
            self.assertNotIn("Courier", document_xml)
            for font_attribute in ("ascii", "hAnsi", "eastAsia", "cs"):
                self.assertIn(f'w:{font_attribute}="DM Sans"', styles_xml)
            self.assertIn('w:name="DM Sans"', font_table_xml)
            self.assertIn("w:embedRegular", font_table_xml)
            self.assertIn("w:embedBold", font_table_xml)
            self.assertIn("/relationships/font", font_relationships_xml)
            self.assertIn("word/fonts/DMSans-Regular.odttf", package_names)
            self.assertIn("word/fonts/DMSans-Bold.odttf", package_names)

            cover_extents = [
                int(value) for value in re.findall(r'<wp:extent[^>]+cy="(\d+)"', document_xml)
            ]
            self.assertTrue(cover_extents)
            self.assertEqual(max(cover_extents), round(11 * 914400))
            self.assertIn('behindDoc="1"', document_xml)
            self.assertIn('relativeFrom="page"', document_xml)


if __name__ == "__main__":
    unittest.main()
