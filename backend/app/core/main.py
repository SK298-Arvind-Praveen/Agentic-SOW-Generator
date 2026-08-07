import sys
from pathlib import Path
from datetime import datetime

_backend_root = str(Path(__file__).resolve().parents[2])
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

# ---- Minimal config ----
class TestConfig:
    OUTPUT_DIR = Path("./output")
    ASSETS_DIR = Path("./assets")
    COVER_PAGE_IMAGE = Path("./assets/cover.png")  # optional
    ARCHITECTURE_DIAGRAM = Path("./assets/arch.png")  # optional

    MARGIN_TOP = 72
    MARGIN_BOTTOM = 72
    MARGIN_LEFT = 72
    MARGIN_RIGHT = 72

    FONT_SIZE_HEADING1 = 16
    FONT_SIZE_HEADING2 = 14
    FONT_SIZE_BODY = 11
    LINE_SPACING = 1.4


# ---- Import your builder ----
from app.document.document_builder import DocumentBuilder


def run_test():
    config = TestConfig()
    builder = DocumentBuilder(config)

    sections = {
        "toc_structure": """
        1. About Shellkode
        2. Project Overview
        3. Architecture Diagram
        """,

        "about_shellkode": """
        Shellkode is a technology consulting company focused on AI and GenAI solutions.
        """,

        "project_overview": """
        This document is created to validate:
        - Footer violet divider
        - Correct TOC page numbers
        """,

        "architecture_diagram": """
        This section intentionally leaves space for an architecture diagram.
        """
    }

    metadata = {
        "company_name": "TCS",
        "author_org": "Shellkode Pvt Ltd",
        "author_name": "Abdul Rasith",
        "project_title": "PDF → DOCX Validation Test"
    }

    output = builder.build_document(
        sections=sections,
        metadata=metadata,
        mode="POC"
    )

    print("\n✅ Test completed")
    print("Output file:", output)


if __name__ == "__main__":
    run_test()
