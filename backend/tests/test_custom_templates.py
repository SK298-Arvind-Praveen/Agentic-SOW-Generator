import unittest
from types import SimpleNamespace

from app.agents.custom_template_agent import CustomTemplateAgent
from app.agents.poc_writer_agent import POCWriterAgent, TemplateSection
from app.storage.custom_templates import CustomTemplateStore


class _FakeTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item):
        self.items[(Item["PK"], Item["SK"])] = dict(Item)

    def get_item(self, Key):
        return {"Item": self.items.get((Key["PK"], Key["SK"]))}

    def query(self, **_kwargs):
        return {"Items": list(self.items.values())}

    def delete_item(self, Key):
        self.items.pop((Key["PK"], Key["SK"]), None)


class CustomTemplateTests(unittest.TestCase):
    def setUp(self):
        CustomTemplateStore._cache.clear()

    def test_sanitizer_deduplicates_and_excludes_protected_sections(self):
        markdown = """## Cover Page
Copy title.
## risk management
Describe risks.
## 2. Risk Management
Duplicate.
## About ShellKode
Replace company copy.
## AWS Operations
Describe operations.
"""
        cleaned = CustomTemplateAgent._sanitize(markdown)
        sections = CustomTemplateAgent.sections_from_markdown(cleaned)
        self.assertEqual([item["label"] for item in sections], ["Risk Management", "AWS Operations"])
        self.assertNotIn("About ShellKode", cleaned)
        self.assertNotIn("Cover Page", cleaned)

    def test_semantic_duplicates_map_to_base_and_deliverable_scaffolding_is_removed(self):
        markdown = """## About the Client
Describe the customer profile.
## Terms & Conditions
Describe reusable terms.
## Scope of Work
Describe the scope structure.
## Out of Scope
Describe exclusions.
## Project Team Effort (per-deliverable)
Repeat effort under every deliverable.
## Deliverable Sections (numbered functional areas)
Repeat the functional areas.
## Governance Model
Describe governance.
"""
        cleaned = CustomTemplateAgent._sanitize(markdown)
        sections = CustomTemplateAgent.sections_from_markdown(cleaned)
        by_label = {item["label"]: item for item in sections}
        self.assertEqual(by_label["About the Client"]["base_section_id"], "about_client")
        self.assertEqual(by_label["Terms & Conditions"]["base_section_id"], "terms_conditions")
        self.assertEqual(by_label["Scope of Work"]["base_section_id"], "scope_of_work")
        self.assertEqual(by_label["Out of Scope"]["base_section_id"], "out_of_scope")
        self.assertTrue(by_label["Scope of Work"]["hidden"])
        self.assertFalse(by_label["Governance Model"]["hidden"])
        self.assertNotIn("Project Team Effort (per-deliverable)", cleaned)
        self.assertNotIn("Deliverable Sections (numbered functional areas)", cleaned)

    def test_numbered_subheadings_are_removed_without_requiring_metadata(self):
        markdown = """## Scope of Work
Describe its hierarchy only.
## 6.1 Requirement Analysis
Nested scope topic.
## Terms & Conditions
Describe the clause layout.
## 9.2 Payment Terms
Nested commercial topic.
"""
        cleaned = CustomTemplateAgent._sanitize(markdown)
        self.assertIn("## Scope of Work", cleaned)
        self.assertIn("## Terms & Conditions", cleaned)
        self.assertNotIn("Requirement Analysis", cleaned)
        self.assertNotIn("Payment Terms", cleaned)

    def test_stripped_numbered_subheading_is_removed_from_source_hint(self):
        source = """1. Scope of Work
1.1 Requirement Analysis
1.2 Platform Setup
2. Terms and Conditions
"""
        nested = CustomTemplateAgent.discover_numbered_subheadings(source)
        markdown = """## Scope of Work
Describe its hierarchy only.
## Requirement Analysis
Nested topic whose number was stripped by the model.
## Platform Setup
Another nested topic whose number was stripped.
## Terms and Conditions
Describe clause organization.
"""
        cleaned = CustomTemplateAgent._sanitize(
            markdown,
            allowed_headings=[],
            forbidden_nested_headings=nested,
        )
        self.assertIn("## Scope of Work", cleaned)
        self.assertIn("## Terms and Conditions", cleaned)
        self.assertNotIn("## Requirement Analysis", cleaned)
        self.assertNotIn("## Platform Setup", cleaned)

    def test_sanitizer_accepts_review_output_with_h1_headings(self):
        markdown = """# Project Overview
Describe the paragraph structure.

# Scope of Work
Describe the deliverable and module hierarchy.
"""
        cleaned = CustomTemplateAgent._sanitize(markdown)
        self.assertIn("## Project Overview", cleaned)
        self.assertIn("## Scope of Work", cleaned)
        self.assertNotIn("\n# Project Overview", cleaned)
        self.assertEqual(len(CustomTemplateAgent.sections_from_markdown(cleaned)), 2)

    def test_final_safety_gate_allows_generic_format_language(self):
        markdown = """[META_GENERATED]
## Scope of Work
Describe a hierarchy including deliverables, modules, bullets, and tables.
"""
        self.assertEqual(CustomTemplateAgent._hard_genericity_issues(markdown), [])

    def test_final_safety_gate_rejects_concrete_leakage(self):
        markdown = """## Pricing
Use https://example.com and state INR 12,500 dated 2026-09-21.
"""
        issues = CustomTemplateAgent._hard_genericity_issues(markdown)
        self.assertIn("contains a URL", issues)
        self.assertIn("contains a concrete price", issues)
        self.assertIn("contains a concrete date", issues)

    def test_visible_toc_parser_keeps_first_level_and_rejects_subtopics(self):
        source = """Table of Contents
1. About the Client ........ 2
2. Scope of Work ........ 4
2.1 Requirement Analysis ........ 5
2.2 Platform Setup ........ 6
3. Terms & Conditions ........ 8
"""
        headings = CustomTemplateAgent.discover_top_level_headings("sample.doc", source)
        self.assertEqual(
            headings, ["About the Client", "Scope of Work", "Terms & Conditions"]
        )

    def test_public_template_exposes_only_genuinely_unique_extracted_sections(self):
        public = CustomTemplateStore._public({
            "owner_email": "owner@shellkode.com",
            "sections": [
                {"id": "scope_of_work", "label": "Scope of Work", "hidden": True},
                {"id": "custom_abcd_governance", "label": "Governance Model", "hidden": False},
            ],
        }, "owner@shellkode.com")
        self.assertEqual(
            [item["label"] for item in public["sections"]], ["Governance Model"]
        )

    def test_presets_are_shared_but_only_owner_or_admin_can_delete(self):
        store = CustomTemplateStore(table=_FakeTable())
        created = store.create_draft(
            template_id="abc",
            markdown="[META_GENERATED]\n## Governance\nWrite governance.",
            sections=[{"id": "custom_abc_governance", "label": "Governance", "order": 0}],
            owner_email="owner@shellkode.com",
            author_name="Owner",
            source_filename="sample.docx",
            output_path="output/custom-templates/abc.md",
        )
        saved = store.save_preset(created["template_id"], "Reusable Governance", "owner@shellkode.com")
        listed = store.list_saved("viewer@shellkode.com")
        self.assertEqual(listed[0]["name"], "Reusable Governance")
        self.assertFalse(listed[0]["can_delete"])
        with self.assertRaises(PermissionError):
            store.delete(saved["template_id"], "viewer@shellkode.com")
        store.delete(saved["template_id"], "admin@shellkode.com", is_admin=True)

    def test_duplicate_preset_names_receive_windows_style_suffixes(self):
        store = CustomTemplateStore(table=_FakeTable())

        def create_and_save(template_id, requested_name):
            store.create_draft(
                template_id=template_id,
                markdown="[META_GENERATED]\n## Governance\nWrite governance.",
                sections=[{"id": f"custom_{template_id}", "label": "Governance", "order": 0}],
                owner_email="owner@shellkode.com",
                author_name="Owner",
                source_filename=f"{template_id}.docx",
                output_path=f"output/custom-templates/{template_id}.md",
            )
            return store.save_preset(template_id, requested_name, "owner@shellkode.com")

        self.assertEqual(create_and_save("one", "Client Template")["name"], "Client Template")
        self.assertEqual(create_and_save("two", "Client Template")["name"], "Client Template (01)")
        self.assertEqual(create_and_save("three", "client template")["name"], "client template (02)")

    def test_duplicate_suffix_keeps_name_within_eighty_characters(self):
        store = CustomTemplateStore(table=_FakeTable())
        long_name = "T" * 80
        for template_id in ("one", "two"):
            store.create_draft(
                template_id=template_id,
                markdown="[META_GENERATED]\n## Governance\nWrite governance.",
                sections=[],
                owner_email="owner@shellkode.com",
                author_name="Owner",
                source_filename="sample.docx",
                output_path=f"output/custom-templates/{template_id}.md",
            )
        store.save_preset("one", long_name, "owner@shellkode.com")
        duplicate = store.save_preset("two", long_name, "owner@shellkode.com")
        self.assertEqual(len(duplicate["name"]), 80)
        self.assertTrue(duplicate["name"].endswith(" (01)"))

    def test_custom_guidance_merges_with_matching_base_section(self):
        agent = POCWriterAgent.__new__(POCWriterAgent)
        agent.sections = [TemplateSection(
            "Scope of Work", "Base instructions", {"type": "GENERATED", "category_id": "scope_of_work"}, 0
        )]
        agent._merge_custom_template(
            "[META_GENERATED]\n## Scope of Work\nCustom structural instructions.",
            [{"id": "custom_abcd_scope", "label": "Scope of Work", "order": 0}],
        )
        self.assertEqual(len(agent.sections), 1)
        self.assertIn("Custom structural instructions", agent.sections[0].content)
        self.assertEqual(
            agent._selection_ids(agent.sections[0]),
            {"scope_of_work", "custom_abcd_scope"},
        )
        self.assertTrue(agent.sections[0].content.startswith("CUSTOM TEMPLATE GUIDANCE"))

    def test_semantic_duplicate_guidance_targets_base_category(self):
        agent = POCWriterAgent.__new__(POCWriterAgent)
        agent.sections = [TemplateSection(
            "About {COMPANY_NAME}", "Base company instructions",
            {"type": "GENERATED", "category_id": "about_client"}, 0,
        )]
        agent._merge_custom_template(
            "[META_GENERATED]\n## About the Client\nUse the uploaded template's two-paragraph profile structure.",
            [{
                "id": "about_client", "label": "About the Client", "order": 0,
                "base_section_id": "about_client", "hidden": True,
            }],
        )
        self.assertEqual(len(agent.sections), 1)
        self.assertTrue(agent.sections[0].content.startswith("CUSTOM TEMPLATE GUIDANCE"))
        self.assertIn("two-paragraph profile structure", agent.sections[0].content)


if __name__ == "__main__":
    unittest.main()
