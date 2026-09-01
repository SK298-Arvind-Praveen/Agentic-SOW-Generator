import re
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
        self.assertEqual(POCWriterAgent._section_word_limit(section), 320)
        self.assertEqual(POCWriterAgent._section_word_limit(detailed), 900)
        self.assertEqual(POCWriterAgent._section_token_budget(section), 900)
        self.assertEqual(POCWriterAgent._section_token_budget(detailed), 1800)
        verbose = " ".join(["detail"] * 321)
        issues = POCWriterAgent._authoring_issues(verbose, section)
        self.assertTrue(any("320-word section limit" in issue for issue in issues))

    def test_writer_flags_excessive_subsections(self):
        section = SimpleNamespace(name="Project Overview")
        content = "### Context\n- Point.\n### Outcome\n- Point.\n### Another Heading\n- Point."
        issues = POCWriterAgent._authoring_issues(content, section)
        self.assertTrue(any("too many subsections" in issue for issue in issues))

    def test_writer_removes_plural_only_restatement_of_parent_heading(self):
        agent = POCWriterAgent.__new__(POCWriterAgent)
        cleaned = agent._clean_content(
            "### 1.1 Objectives\n\n- Validate exception routing.",
            "1. Objective",
        )
        self.assertEqual(cleaned, "- Validate exception routing.")

    def test_request_parsing_defaults_to_all_but_preserves_clear_optional(self):
        self.assertEqual(
            set(parse_selected_section_ids(None, "POC")),
            available_section_ids("POC"),
        )
        self.assertEqual(parse_selected_section_ids("[]", "POC"), [])
        self.assertEqual(
            parse_selected_section_ids('["aws_pricing", "timelines_deliverables"]', "POC"),
            ["aws_pricing", "timelines_deliverables"],
        )
        self.assertEqual(
            parse_selected_section_ids('["pricing", "timeline", "pricing"]', "POC"),
            ["aws_pricing", "timelines_deliverables"],
        )
        with self.assertRaises(ValueError):
            parse_selected_section_ids('["not-a-section"]', "POC")

    def test_mandatory_and_optional_titles_are_classified(self):
        for title in ("{PROJECT_TITLE}", "Table_of_contents"):
            self.assertIsNone(section_category(title))
        expected_categories = {
            "Document Version Control": "document_version_control",
            "About {AUTHOR_ORG_SHORT}": "about_shellkode",
            "About ShellKode": "about_shellkode",
            "About {COMPANY_NAME}": "about_client",
            "Objective": "project_overview",
            "Deliverables": "scope_of_work",
            "Scope of Work": "scope_of_work",
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

    def test_writer_uses_user_selected_order_for_toc_and_output(self):
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
            selected_sow_sections=[
                "aws_pricing",
                "project_overview",
                "scope_of_work",
            ],
        )

        toc = output["toc_structure"]
        self.assertLess(toc.index("AWS Pricing"), toc.index("Objective"))
        self.assertLess(toc.index("Current State"), toc.index("Deliverables"))

        output_keys = list(output)
        self.assertLess(output_keys.index("aws_pricing"), output_keys.index("project_overview"))
        self.assertLess(output_keys.index("current_state_and_business_context"), output_keys.index("scope_at_a_glance"))

    def test_dynamic_toc_numbers_document_control_and_acceptance(self):
        backend = Path(__file__).resolve().parents[1]
        template = (backend / "templates" / "poc_template.md").read_text(encoding="utf-8")
        agent = POCWriterAgent.__new__(POCWriterAgent)
        agent.template_type = "POC"
        agent.template_raw = template
        agent.global_template_contract = agent._extract_global_template_contract(template)
        sections = agent._parse_template()
        toc = agent._dynamic_toc(
            sections,
            {
                "company_name": "Example Customer",
                "company_name_short": "Example Customer",
                "project_title": "CRM Integration",
                "author_name": "Author",
                "author_org": "ShellKode",
                "author_org_short": "ShellKode",
            },
        )
        lines = toc.splitlines()
        self.assertRegex(lines[0], r"^1\. Document Version Control$")
        acceptance = next(line for line in lines if "Acceptance and Signatories" in line)
        self.assertRegex(acceptance, r"^\d+\. Acceptance and Signatories")
        self.assertTrue(all(re.match(r"^\d+\. ", line) for line in lines))

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

    def test_about_client_contract_requires_two_plain_paragraphs(self):
        section = SimpleNamespace(name="About {COMPANY_NAME}")
        valid = "Axis Securities operates in financial services.\n\nIts confirmed project context concerns customer service modernisation."
        self.assertEqual(POCWriterAgent._authoring_issues(valid, section), [])

        invalid = "### Company Profile\n- Financial services organisation"
        issues = POCWriterAgent._authoring_issues(invalid, section)
        self.assertTrue(any("exactly two brief paragraphs" in issue for issue in issues))
        self.assertTrue(any("must not contain subsections" in issue for issue in issues))

    def test_about_shellkode_is_static_and_verbatim(self):
        backend = Path(__file__).resolve().parents[1]
        template = (backend / "templates" / "poc_template.md").read_text(encoding="utf-8")
        agent = POCWriterAgent.__new__(POCWriterAgent)
        agent.config = SimpleNamespace(SOW_SECTION_WORKERS=1)
        agent.template_type = "POC"
        agent.template_raw = template
        agent.global_template_contract = agent._extract_global_template_contract(template)
        agent.sections = agent._parse_template()

        def fail_if_generated(*_args, **_kwargs):
            raise AssertionError("Static ShellKode profile must not call the LLM")

        agent._generate_section = MethodType(fail_if_generated, agent)
        output = agent.generate_poc(
            requirements={"_original_objective": "Create a concise SOW"},
            metadata={
                "company_name": "Example Customer",
                "project_title": "Example Project",
                "author_name": "Author",
                "author_org": "ShellKode",
            },
            selected_sow_sections=["about_shellkode"],
        )
        self.assertEqual(
            output["about_shellkode"],
            "**ShellKode** is a cloud-native technology company focused on helping organizations modernize their IT environments through Cloud, Data, AI/ML, and Generative AI. The company works with businesses to build scalable, enterprise-grade solutions that improve operational efficiency, generate insights, and solve complex technology challenges.\n\n"
            "ShellKode’s key capabilities include Cloud Strategy & Consulting, Cloud Migration & Modernization, Data Engineering & Analytics, Machine Learning, Generative AI, and Agentic AI. Its AI offerings include intelligent document processing, RAG-based knowledge systems, AI agents, conversational assistants, speech analytics, computer vision, and multilingual AI solutions.\n\n"
            "The company works across industries including BFSI, Retail & E-commerce, Logistics & Supply Chain, and Healthcare, delivering solutions that combine cloud infrastructure, enterprise data, and AI. ShellKode also has a strong AWS focus, with capabilities around AWS cloud migration, modernization, and Generative AI solutions.",
        )


if __name__ == "__main__":
    unittest.main()
