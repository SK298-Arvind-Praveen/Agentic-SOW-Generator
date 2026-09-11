import json
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
                "About ShellKode",
                "About {COMPANY_NAME}",
                "1. Objective",
                "2. Current State",
                "3. Scope of Work",
                "4. Solution Architecture — AWS",
                "5. Open Clarifications",
                "6. Out of Scope",
                "Customer Dependencies",
                "7. Assumptions",
                "8. Timeline and Deliverables",
                "9. Success Criteria",
                "10. AWS Pricing",
                "Customer Responsibilities",
                "11. {AUTHOR_ORG_SHORT} Project Team Effort",
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

    def test_objective_section_does_not_repeat_objectives_subheading(self):
        self.assertNotIn("### 1.1 Objectives", self.template)
        objective_start = self.template.index("## 1. Objective")
        objective_end = self.template.index("[META_TABLE]", objective_start)
        self.assertIn("do not add an `Objectives` subsection", self.template[objective_start:objective_end])

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
            ("## 2. Current State", "REQUIRED COVERAGE"),
            ("## 3. Scope of Work", "DOCUMENT-WIDE COMPLETENESS CHECK"),
            ("## 4. Solution Architecture — AWS", "ARCHITECTURE EVIDENCE RULE"),
            ("## 5. Open Clarifications", "INCLUSION RULES"),
            ("## 6. Out of Scope", "CONDITIONAL COVERAGE"),
            ("## 7. Assumptions", "DISTINCTION RULES"),
            ("## 8. Timeline and Deliverables", "REQUIRED OUTPUT"),
            ("## 9. Success Criteria", "METRIC RULES"),
            ("## 10. AWS Pricing", "PROHIBITIONS"),
            ("## 11. {AUTHOR_ORG_SHORT} Project Team Effort", "WHEN STAFFING IS NOT SUPPLIED"),
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
        self.assertTrue(any("by deliverable" in issue for issue in issues))
        self.assertTrue(any("architected modules" in issue for issue in issues))

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

    def test_scope_has_no_fixed_module_or_word_limit_and_team_effort_key_is_stable(self):
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
        self.assertFalse(any("more than six modules" in issue for issue in issues))
        self.assertFalse(any("exceeds eight steps" in issue for issue in issues))
        self.assertIsNone(POCWriterAgent._section_word_limit(detailed_scope))

        bad_labels = (
            "### Deliverable: Platform\n#### Ticketing Module\n"
            "##### Task Statement\nHandle tickets.\n##### Objective\nResolve cases."
        )
        label_issues = POCWriterAgent._authoring_issues(bad_labels, detailed_scope)
        self.assertTrue(any("integrated into module content" in issue for issue in label_issues))
        self.assertTrue(POCWriterAgent._scope_block_structure_issues(
            "### Deliverable 1 - Platform\n#### Monitoring\n**Key Outputs:**\n- Dashboard"
        ))
        self.assertFalse(POCWriterAgent._scope_block_structure_issues(
            "### Deliverable 1 - Platform\n#### Monitoring\n"
            "- **Monitoring and alert activation:** Configure health metrics and severity-based notifications."
        ))

        agent = POCWriterAgent.__new__(POCWriterAgent)
        key = agent._section_key(
            "11. {AUTHOR_ORG_SHORT} Project Team Effort",
            {"author_org": "ShellKode", "author_org_short": "ShellKode"},
        )
        self.assertEqual(key, "shellkode_implementation_cost")

    def test_architect_scope_plan_preserves_dynamic_deliverables_and_modules(self):
        agent = POCWriterAgent.__new__(POCWriterAgent)
        agent.template_type = "POC"
        agent.config = types.SimpleNamespace(WRITER_MODEL_ID="writer")
        inventory = {"capability_units": [
            {"id": "CAP-001", "name": "Ticket Classification"},
            {"id": "CAP-002", "name": "Escalation Management"},
            {"id": "CAP-003", "name": "Email Assignment"},
        ]}
        response = """{
          "deliverables": [
            {"name":"Customer Service Platform","purpose":"Resolve contacts","boundary_type":"acceptance","separation_basis":"Separate acceptance", "modules":[
              {"name":"Ticket Classification","capability_ids":["CAP-001"],"task_statement":"Classify cases"},
              {"name":"Escalation Management","capability_ids":["CAP-002"],"task_statement":"Manage TAT breaches"}
            ]},
            {"name":"Email Operations","purpose":"Handle email","boundary_type":"release","separation_basis":"Separate release", "modules":[
              {"name":"Email Assignment","capability_ids":["CAP-003"],"task_statement":"Route messages"}
            ]}
          ],
          "open_boundaries": []
        }"""
        agent._call_bedrock = lambda *_args, **_kwargs: response
        plan = agent._architect_scope(
            {"key_deliverables": ["Ticket Classification", "Escalation Management", "Email Assignment"]},
            {"company_name": "Example", "project_title": "CRM"},
            "Tickets use TAT escalation. Emails use assignment rules.",
        )
        self.assertEqual(len(plan["deliverables"]), 2)
        self.assertEqual(len(plan["deliverables"][0]["modules"]), 2)

    def test_fragmented_scope_plan_is_consolidated_without_dropping_modules(self):
        agent = POCWriterAgent.__new__(POCWriterAgent)
        agent.template_type = "POC"
        agent.config = types.SimpleNamespace(WRITER_MODEL_ID="writer")
        inventory = {"capability_units": [
            {"id": f"CAP-{index:03d}", "name": name}
            for index, name in enumerate(("Web", "WhatsApp", "Hybris", "Genesys", "Reporting"), 1)
        ]}
        fragmented = {
            "deliverables": [
                {"name": "Channels", "modules": [{"name": "Web", "capability_ids": ["CAP-001"]}, {"name": "WhatsApp", "capability_ids": ["CAP-002"]}]},
                {"name": "Integrations", "modules": [{"name": "Hybris", "capability_ids": ["CAP-003"]}, {"name": "Genesys", "capability_ids": ["CAP-004"]}]},
                {"name": "Analytics", "modules": [{"name": "Reporting", "capability_ids": ["CAP-005"]}]},
            ]
        }
        consolidated = {
            "deliverables": [{
                "name": "AI Customer Support Platform",
                "purpose": "One implemented and accepted support platform",
                "separation_basis": "Single release and acceptance boundary",
                "modules": [
                    {"name": "Web", "capability_ids": ["CAP-001"]},
                    {"name": "WhatsApp", "capability_ids": ["CAP-002"]},
                    {"name": "Hybris", "capability_ids": ["CAP-003"]},
                    {"name": "Genesys", "capability_ids": ["CAP-004"]},
                    {"name": "Reporting", "capability_ids": ["CAP-005"]},
                ],
            }]
        }
        agent._call_bedrock = lambda *_args, **_kwargs: json.dumps(fragmented)
        plan = agent._architect_scope(
            {"key_deliverables": ["Web", "WhatsApp", "Hybris", "Genesys", "Reporting"]},
            {"company_name": "Tata CLiQ", "project_title": "Chatbot"},
            "All capabilities form one implementation release.",
        )
        self.assertEqual(len(plan["deliverables"]), 1)
        self.assertEqual(len(plan["deliverables"][0]["modules"]), 5)

    def test_authoring_prompt_preserves_source_assumption_and_conflict_status(self):
        agent = POCWriterAgent.__new__(POCWriterAgent)
        agent.template_type = "POC"
        agent.global_template_contract = "Evidence contract"
        agent.selected_section_preferences = ["out_of_scope"]
        agent.excluded_section_preferences = []
        agent.scope_architecture_plan = {}
        section = TemplateSection(
            "7. Out of Scope", "Write evidence-backed exclusions.",
            {"type": "GENERATED", "category_id": "out_of_scope"}, 0,
        )
        prompt = agent._build_individual_prompt(
            section,
            {"project_overview": "Customer support platform"},
            {"company_name": "Example", "project_title": "Chatbot", "author_org": "ShellKode"},
        )
        self.assertIn("Source Assumption", prompt)
        self.assertIn("Conflicts between uploaded sources are Open", prompt)
        self.assertIn("must not appear in Out of Scope", prompt)

    def test_scope_prompt_receives_shared_architect_blueprint(self):
        agent = POCWriterAgent.__new__(POCWriterAgent)
        agent.template_type = "POC"
        agent.global_template_contract = "Reference contract"
        agent.selected_section_preferences = ["scope_of_work"]
        agent.excluded_section_preferences = []
        agent.scope_architecture_plan = {
            "deliverables": [{"name": "Email Operations", "modules": [{"name": "Email Routing"}]}]
        }
        section = TemplateSection(
            "4. Scope of Work", "Use the architect plan.",
            {"type": "GENERATED", "category_id": "scope_of_work"}, 0,
        )
        prompt = agent._build_individual_prompt(
            section,
            {"project_overview": "Modernise service operations"},
            {"company_name": "Example", "project_title": "CRM", "author_org": "ShellKode"},
        )
        self.assertIn("SHARED SOLUTION-ARCHITECTURE WORK BREAKDOWN", prompt)
        self.assertIn("Email Routing", prompt)
        self.assertIn("No fixed word, deliverable, or module limit", prompt)

    def test_scope_is_generated_one_call_per_deliverable(self):
        agent = POCWriterAgent.__new__(POCWriterAgent)
        agent.template_type = "POC"
        agent.config = types.SimpleNamespace(WRITER_MODEL_ID="writer", FALLBACK_MODEL_ID="fallback")
        agent.scope_architecture_plan = {
            "deliverables": [
                {"name": "Ticketing", "modules": [{"name": "Case Lifecycle"}]},
                {"name": "Email", "modules": [{"name": "Email Assignment"}]},
            ]
        }
        prompts = []

        def fake_call(prompt, **_kwargs):
            prompts.append(prompt)
            if "Ticketing" in prompt:
                return "### Deliverable 1 - Ticketing\n#### Case Lifecycle\n- Configure the case lifecycle."
            return "### Deliverable 2 - Email\n#### Email Assignment\n- Configure email assignment."

        agent._call_bedrock = fake_call
        content = agent._generate_scope_deliverables({}, {}, "Source", [])
        self.assertEqual(len(prompts), 2)
        self.assertIn("| # | Deliverable | Included Modules | Core Outcome |", content)
        self.assertIn("#### Case Lifecycle", content)
        self.assertIn("#### Email Assignment", content)
        self.assertLess(content.index("Deliverable 1 - Ticketing"), content.index("Deliverable 2 - Email"))

    def test_scope_sanitises_leaked_reasoning_labels(self):
        cleaned = POCWriterAgent._sanitize_scope_reasoning_labels(
            "#### Monitoring\n- Configure metrics.\n\n**Validation Evidence:** Alarm demonstrated."
        )
        self.assertNotIn("Validation Evidence", cleaned)
        self.assertIn("- Alarm demonstrated.", cleaned)

    def test_scope_removes_evidence_status_meta_bullets(self):
        cleaned = POCWriterAgent._sanitize_scope_reasoning_labels(
            "#### Monitoring\n- Configure metrics.\n- **Evidence status:** Source Assumption."
        )
        self.assertNotIn("Evidence status", cleaned)
        self.assertNotIn("Source Assumption", cleaned)

    def test_about_company_cleanup_removes_engagement_problem_context(self):
        agent = POCWriterAgent.__new__(POCWriterAgent)
        cleaned = agent._clean_content(
            "Axis Securities operates in financial services.\n\n"
            "The requirements relevant to this engagement are addressed in the project scope.",
            "About Axis Securities",
        )
        self.assertEqual(cleaned, "Axis Securities operates in financial services.")


if __name__ == "__main__":
    unittest.main()
