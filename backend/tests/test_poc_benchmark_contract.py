import re
import sys
import types
import unittest
from pathlib import Path

try:
    import boto3  # noqa: F401
except ModuleNotFoundError:
    sys.modules["boto3"] = types.SimpleNamespace(client=lambda *args, **kwargs: None)

from app.agents.poc_writer_agent import POCWriterAgent, TemplateSection


class PocBenchmarkContractTests(unittest.TestCase):
    def setUp(self):
        self.template = (
            Path(__file__).resolve().parents[1] / "templates" / "poc_template.md"
        ).read_text(encoding="utf-8")
        render_template = re.sub(
            r"<!-- BEGIN_GLOBAL_TEMPLATE_CONTRACT -->.*?"
            r"<!-- END_GLOBAL_TEMPLATE_CONTRACT -->",
            "",
            self.template,
            flags=re.S,
        )
        self.headings = re.findall(r"(?m)^## (.+)$", render_template)

    def test_template_exposes_the_customisable_section_catalogue(self):
        self.assertEqual(
            self.headings,
            [
                "{PROJECT_TITLE}",
                "Table_of_contents",
                "Document Version Control",
                "About {AUTHOR_ORG_SHORT}",
                "About {COMPANY_NAME}",
                "1. Objective",
                "2. Deliverables",
                "3. Current State",
                "4. Scope of Work",
                "5. Solution Architecture — AWS",
                "6. Open Clarifications",
                "7. Out of Scope",
                "Customer Dependencies",
                "8. Assumptions",
                "9. Timeline and Deliverables",
                "10. Success Criteria",
                "11. AWS Pricing",
                "Customer Responsibilities",
                "12. {AUTHOR_ORG_SHORT} Project Team Effort",
                "Project Plan Termination",
                "Contacts and Reporting",
                "Terms and Conditions",
                "Acceptance and Signatories to Statement of Work",
            ],
        )

    def test_removed_probe_sections_do_not_return(self):
        for heading in (
            "Testing and Acceptance Plan",
            "Risks and Mitigations",
            "Duration of Work",
            "Deliverable Acceptance",
            "Change Order",
            "Marketing Authorization",
        ):
            self.assertNotIn(f"## {heading}", self.template)

    def test_signatory_names_and_titles_are_blank(self):
        self.assertIn('"Client" verifies that the terms of this Statement of Work/Proposal', self.template)
        self.assertNotIn("Bhuvanesh CTO", self.template)
        self.assertNotIn("| XXX |", self.template)
        self.assertIn("| Name: | Name: |", self.template)
        self.assertIn("| Title: | Title: |", self.template)
        self.assertIn("| Date of acceptance: | Date of acceptance: |", self.template)

    def test_language_and_blank_signature_rules_cover_every_sow_mode(self):
        template_dir = Path(__file__).resolve().parents[1] / "templates"
        for name in ("poc_template.md", "production_template.md", "poc_to_prod_template.md"):
            body = (template_dir / name).read_text(encoding="utf-8")
            self.assertIn("British Indian English", body)
            self.assertNotIn("Bhuvanesh CTO", body)
            self.assertNotIn("Name: To be nominated", body)
            self.assertNotIn("Title: To be confirmed", body)

    def test_detailed_global_benchmark_contract_is_embedded(self):
        contract = re.search(
            r"<!-- BEGIN_GLOBAL_TEMPLATE_CONTRACT -->(.*?)"
            r"<!-- END_GLOBAL_TEMPLATE_CONTRACT -->",
            self.template,
            re.S,
        )
        self.assertIsNotNone(contract)
        body = contract.group(1)
        self.assertGreater(len(body.split()), 700)
        for required_rule in (
            "Evidence and inference policy",
            "Cross-section consistency rules",
            "Regulatory, compliance, AI, and human-review fidelity",
            "Reference-derived visual contract",
            "Heading hierarchy and numbering",
            "DM Sans",
            "#5D3FD3",
            "#1A4BD2",
            "Page X of Y",
            "British Indian English",
        ):
            self.assertIn(required_rule, body)

    def test_core_sections_retain_strict_local_authoring_rules(self):
        for section_title, required_text in (
            ("## Document Version Control", "REQUIRED STRUCTURE"),
            ("## 1. Objective", "BOUNDARIES"),
            ("## 2. Deliverables", "CONSISTENCY GATE"),
            ("## 3. Current State", "REQUIRED COVERAGE"),
            ("## 4. Scope of Work", "DOCUMENT-WIDE COMPLETENESS CHECK"),
            ("## 5. Solution Architecture — AWS", "ARCHITECTURE EVIDENCE RULE"),
            ("## 6. Open Clarifications", "INCLUSION RULES"),
            ("## 7. Out of Scope", "CONDITIONAL COVERAGE"),
            ("## 8. Assumptions", "DISTINCTION RULES"),
            ("## 9. Timeline and Deliverables", "REQUIRED OUTPUT"),
            ("## 10. Success Criteria", "METRIC RULES"),
            ("## 11. AWS Pricing", "PROHIBITIONS"),
            ("## 12. {AUTHOR_ORG_SHORT} Project Team Effort", "WHEN STAFFING IS NOT SUPPLIED"),
        ):
            start = self.template.index(section_title)
            next_section = self.template.find("\n[META_", start + len(section_title))
            block = self.template[start: next_section if next_section >= 0 else None]
            self.assertIn(required_text, block)

    def test_contract_is_prompted_but_never_parsed_as_document_sections(self):
        agent = POCWriterAgent.__new__(POCWriterAgent)
        agent.template_raw = self.template
        agent.template_type = "POC"
        agent.global_template_contract = agent._extract_global_template_contract(self.template)
        sections = agent._parse_template()
        self.assertEqual([section.name for section in sections], self.headings)

        section = TemplateSection(
            "3. Current State",
            "REQUIRED COVERAGE: describe evidence-backed current workflow.",
            {"type": "GENERATED", "_explicit": True},
            0,
        )
        prompt = agent._build_individual_prompt(
            section,
            {"project_overview": "Validate a workflow"},
            {
                "company_name": "Example Customer",
                "project_title": "Example POC",
                "author_org": "ShellKode",
            },
        )
        self.assertIn("GLOBAL TEMPLATE AND REFERENCE-BENCHMARK CONTRACT", prompt)
        self.assertIn("Reference-derived visual contract", prompt)
        self.assertIn("British Indian English", prompt)

        about_client = TemplateSection(
            "About {COMPANY_NAME}",
            "Write exactly two brief prose paragraphs.",
            {"type": "GENERATED", "_explicit": True},
            0,
        )
        about_prompt = agent._build_individual_prompt(
            about_client,
            {"project_overview": "Validate a workflow"},
            {
                "company_name": "Example Customer",
                "company_description": "Confirmed company research context.",
                "project_title": "Example POC",
                "author_org": "ShellKode",
            },
        )
        self.assertIn("Confirmed company research context.", about_prompt)

    def test_section_specific_generation_gates_reject_rudimentary_drafts(self):
        detailed_scope = TemplateSection(
            "4. Scope of Work", "", {"type": "GENERATED"}, 0
        )
        issues = POCWriterAgent._authoring_issues(
            "A generic implementation will be delivered.", detailed_scope
        )
        self.assertTrue(any("module/workstream" in issue for issue in issues))
        self.assertTrue(any("ID / Requirement / Detail" in issue for issue in issues))

        valid_architecture = TemplateSection(
            "5. Solution Architecture — AWS", "", {"type": "GENERATED"}, 0
        )
        architecture_body = (
            "### 5.2 High-Level Architecture\nDetailed component description and boundaries.\n\n"
            "### 5.3 End-to-End Data Flow\n1. Input is validated and processed.\n\n"
            "### 5.4 Low-Level Architecture\nDetailed topology.\n\n"
            "#### 5.4.3 Security and Observability\nLogs and controls are proposed."
        )
        architecture_issues = POCWriterAgent._authoring_issues(
            architecture_body, valid_architecture
        )
        for required in ("high-level architecture", "end-to-end data flow", "low-level architecture", "security and observability"):
            self.assertFalse(any(required in issue for issue in architecture_issues))

    def test_workflow_density_and_team_effort_key_are_enforced(self):
        detailed_scope = TemplateSection(
            "4. Scope of Work", "", {"type": "GENERATED"}, 0
        )
        modules = "\n\n".join(
            f"### 4.{index} Module {index}\n#### 4.{index}.1 Workflow\n" +
            "\n".join(f"{step}. Micro action {step}." for step in range(1, 10))
            for index in range(1, 8)
        )
        body = (
            modules +
            "\n\n| ID | Requirement | Detail |\n|---|---|---|\n| R-1 | Test | Evidence |\n\n"
            "#### 4.7.2 Dependencies and Validation\nEvidence is reviewed."
        )
        issues = POCWriterAgent._authoring_issues(body, detailed_scope)
        self.assertTrue(any("more than six modules" in issue for issue in issues))
        self.assertTrue(any("exceeds eight steps" in issue for issue in issues))

        agent = POCWriterAgent.__new__(POCWriterAgent)
        key = agent._section_key(
            "11. {AUTHOR_ORG_SHORT} Project Team Effort",
            {"author_org": "ShellKode", "author_org_short": "ShellKode"},
        )
        self.assertEqual(key, "shellkode_implementation_cost")


if __name__ == "__main__":
    unittest.main()
