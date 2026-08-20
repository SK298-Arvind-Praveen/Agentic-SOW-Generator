import unittest
from pathlib import Path
from types import MethodType, SimpleNamespace

from app.agents.poc_writer_agent import POCWriterAgent
from app.core.sow_section_preferences import (
    available_section_ids,
    parse_selected_section_ids,
    section_category,
)


class SowSectionPreferenceTests(unittest.TestCase):
    def test_request_parsing_defaults_to_all_but_preserves_clear_optional(self):
        self.assertEqual(
            set(parse_selected_section_ids(None, "POC")),
            available_section_ids("POC"),
        )
        self.assertEqual(parse_selected_section_ids("[]", "POC"), [])
        self.assertEqual(
            parse_selected_section_ids('["timeline", "pricing"]', "POC"),
            ["timeline", "pricing"],
        )
        with self.assertRaises(ValueError):
            parse_selected_section_ids('["not-a-section"]', "POC")

    def test_mandatory_and_optional_titles_are_classified(self):
        for title in (
            "{PROJECT_TITLE}", "Table_of_contents", "Document Control",
            "1. Purpose and Scope of This Deliverable",
            "2. Deliverable Scope at a Glance",
        ):
            self.assertIsNone(section_category(title))
        self.assertEqual(section_category("9. Timeline and Deliverables"), "timeline")
        self.assertEqual(section_category("11. AWS Pricing"), "pricing")
        self.assertEqual(
            section_category("Acceptance and Signatories to Statement of Work"),
            "signatures",
        )

    def test_writer_generates_only_selected_optional_sections_and_rebuilds_toc(self):
        backend = Path(__file__).resolve().parents[1]
        template = (backend / "templates" / "poc_template.md").read_text(encoding="utf-8")
        agent = POCWriterAgent.__new__(POCWriterAgent)
        agent.config = SimpleNamespace(SOW_SECTION_WORKERS=1)
        agent.template_type = "POC"
        agent.template_raw = template
        agent.global_template_contract = agent._extract_global_template_contract(template)
        agent.sections = agent._parse_template()

        def fake_generate(self, section, requirements, metadata, source_context, consistency_notes):
            return f"Generated content for {section.name}."

        agent._generate_section = MethodType(fake_generate, agent)
        output = agent.generate_poc(
            requirements={"_original_objective": "Deliver a CRM integration"},
            metadata={
                "company_name": "Example Customer",
                "project_title": "CRM Integration",
                "author_name": "Author",
                "author_org": "ShellKode",
            },
            selected_sow_sections=["timeline"],
        )

        self.assertIn("project_overview", output)
        self.assertIn("scope_at_a_glance", output)
        self.assertIn("timelines_and_deliverables", output)
        self.assertNotIn("aws_pricing", output)
        self.assertNotIn("architecture_diagram", output)
        toc = output["toc_structure"]
        self.assertIn("Timeline and Deliverables", toc)
        self.assertNotIn("AWS Pricing", toc)
        self.assertNotIn("Signatories", toc)


if __name__ == "__main__":
    unittest.main()
