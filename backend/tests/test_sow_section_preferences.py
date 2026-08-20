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
    def test_section_word_limits_prioritise_concise_output(self):
        section = SimpleNamespace(name="Project Overview")
        detailed = SimpleNamespace(name="Detailed Scope of Work")
        self.assertEqual(POCWriterAgent._section_word_limit(section), 450)
        self.assertEqual(POCWriterAgent._section_word_limit(detailed), 1200)
        self.assertEqual(POCWriterAgent._section_token_budget(section), 900)
        self.assertEqual(POCWriterAgent._section_token_budget(detailed), 2400)
        verbose = " ".join(["detail"] * 451)
        issues = POCWriterAgent._authoring_issues(verbose, section)
        self.assertTrue(any("450-word section limit" in issue for issue in issues))

    def test_request_parsing_defaults_to_all_but_preserves_clear_optional(self):
        self.assertEqual(
            set(parse_selected_section_ids(None, "POC")),
            available_section_ids("POC"),
        )
        self.assertEqual(parse_selected_section_ids("[]", "POC"), [])
        self.assertEqual(
            parse_selected_section_ids('["timelines_deliverables", "aws_pricing"]', "POC"),
            ["timelines_deliverables", "aws_pricing"],
        )
        self.assertEqual(
            parse_selected_section_ids('["timeline", "pricing"]', "POC"),
            ["timelines_deliverables", "aws_pricing"],
        )
        with self.assertRaises(ValueError):
            parse_selected_section_ids('["not-a-section"]', "POC")

    def test_mandatory_and_optional_titles_are_classified(self):
        for title in ("{PROJECT_TITLE}", "Table_of_contents", "Document Control"):
            self.assertIsNone(section_category(title))
        expected_categories = {
            "About {AUTHOR_ORG_SHORT}": "about_shellkode",
            "About {COMPANY_NAME}": "about_client",
            "Project Overview": "project_overview",
            "Detailed Scope of Work": "scope_of_work",
            "Architecture and Integrations": "architecture_diagram",
            "Customer Dependencies": "customer_dependencies",
            "Assumptions": "assumptions",
            "Out of Scope": "out_of_scope",
            "Timeline and Deliverables": "timelines_deliverables",
            "AWS Pricing": "aws_pricing",
            "Customer Responsibilities": "customer_responsibilities",
            "Shellkode Project Team Effort": "project_team_effort",
            "Open Clarifications": "open_clarifications",
            "Success Criteria": "success_criteria",
            "Project Plan Termination": "project_plan_termination",
            "Contacts and Reporting": "contacts_reporting",
            "Terms and Conditions": "terms_conditions",
            "Acceptance and Signatories to Statement of Work": "acceptance_signatories",
        }
        for title, category in expected_categories.items():
            self.assertEqual(section_category(title), category, title)
        self.assertEqual(
            section_category("Acceptance and Signatories to Statement of Work"),
            "acceptance_signatories",
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
            selected_sow_sections=["timelines_deliverables"],
        )

        self.assertIn("timelines_and_deliverables", output)
        self.assertNotIn("project_overview", output)
        self.assertNotIn("scope_at_a_glance", output)
        self.assertNotIn("aws_pricing", output)
        self.assertNotIn("architecture_diagram", output)
        toc = output["toc_structure"]
        self.assertIn("Timeline and Deliverables", toc)
        self.assertNotIn("AWS Pricing", toc)
        self.assertNotIn("Signatories", toc)

    def test_selected_about_client_cannot_collapse_to_an_empty_body(self):
        backend = Path(__file__).resolve().parents[1]
        template = (backend / "templates" / "poc_template.md").read_text(encoding="utf-8")
        agent = POCWriterAgent.__new__(POCWriterAgent)
        agent.config = SimpleNamespace(SOW_SECTION_WORKERS=1)
        agent.template_type = "POC"
        agent.template_raw = template
        agent.global_template_contract = agent._extract_global_template_contract(template)
        agent.sections = agent._parse_template()

        def heading_only(self, section, requirements, metadata, source_context, consistency_notes):
            return f"## {self._replace_placeholders(section.name, metadata, requirements)}"

        agent._generate_section = MethodType(heading_only, agent)
        output = agent.generate_poc(
            requirements={"_original_objective": "Deliver a CRM integration"},
            metadata={
                "company_name": "Example Customer",
                "project_title": "CRM Integration",
                "author_name": "Author",
                "author_org": "ShellKode",
            },
            selected_sow_sections=["about_client"],
        )

        self.assertTrue(output["about_company"].strip())
        self.assertIn("About Example Customer", output["toc_structure"])


if __name__ == "__main__":
    unittest.main()
