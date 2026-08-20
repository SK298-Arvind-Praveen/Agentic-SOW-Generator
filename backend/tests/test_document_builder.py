import re
import tempfile
import unittest
import zipfile
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

from app.document.document_builder import CHROME_INSET_IN, DocumentBuilder


class _Config:
    def __init__(self, output_dir):
        backend = Path(__file__).resolve().parents[1]
        self.OUTPUT_DIR = Path(output_dir)
        self.ASSETS_DIR = backend / "assets"
        self.COVER_PAGE_IMAGE = backend / "assets" / "coverpage.png"


class DocumentBuilderTests(unittest.TestCase):
    def test_builder_preserves_order_semantics_and_geometry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            builder = DocumentBuilder(_Config(temp_dir))
            sections = {
                "toc_structure": "1. Project Overview\n2. Detailed Scope of Work",
                "project_overview": (
                    "### Business Need\nA concise source-grounded overview.\n\n"
                    "| Field | Value |\n|---|---|\n| Mode | POC |\n\n"
                    "Text after the first table must remain visible.\n\n"
                    "| ID | Evidence | Status |\n|---|---|---|\n| SC-01 | Test report | Proposed |"
                ),
                "scope_of_work": (
                    "### Module A\n#### Workflow\n1. Receive input.\n2. Validate input.\n\n"
                    "### Module B\n#### Workflow\n1. Process input.\n2. Record evidence."
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
            self.assertGreaterEqual(len(document.tables), 2)
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

            section = document.sections[-1]
            self.assertEqual(round(section.page_width.inches, 2), 8.5)
            self.assertEqual(round(section.page_height.inches, 2), 11.0)

            with zipfile.ZipFile(output) as package:
                xml = package.read("word/document.xml").decode("utf-8")
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
            self.assertTrue(set(pageref_targets).issubset(bookmark_names))

    def test_singular_timeline_title_resolves_shared_timeline_content_key(self):
        builder = DocumentBuilder.__new__(DocumentBuilder)
        sections = {"timelines_and_deliverables": "A source-grounded delivery sequence."}
        self.assertEqual(
            builder._resolve_content("3. Timeline and Deliverables", sections),
            "A source-grounded delivery sequence.",
        )

    def test_benchmark_order_chrome_and_wide_table_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            builder = DocumentBuilder(_Config(temp_dir))
            sections = {
                "toc_structure": (
                    "Document Control\n"
                    "1. Purpose and Scope of This Deliverable\n"
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
            self.assertLess(body_text.index("Document Control"), body_text.index("Table of Contents"))
            self.assertLess(body_text.index("Table of Contents"), body_text.index("1. Purpose and Scope of This Deliverable"))
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
            self.assertAlmostEqual(
                content_section.header.tables[0].cell(0, 0).paragraphs[0].paragraph_format.left_indent.inches,
                CHROME_INSET_IN,
                places=2,
            )
            self.assertAlmostEqual(
                content_section.header.tables[0].cell(0, 1).paragraphs[0].paragraph_format.right_indent.inches,
                CHROME_INSET_IN,
                places=2,
            )
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
