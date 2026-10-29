import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.poc_writer_agent import POCWriterAgent, TemplateSection
from app.core.sow_editorial import editorial_category, validate_editorial_revision


def test_revision_keeps_numbers_and_rejects_structural_damage():
    original = {"success": "- Test the platform with 500 concurrent sessions.",
                "assumptions": "- The platform includes reporting dashboards."}
    categories = {"success": "success_criteria", "assumptions": "assumptions"}
    good = {"success": "- Test 500 concurrent sessions.", "assumptions": ""}
    validate_editorial_revision(original, good, categories)
    for bad in (
        {"success": good["success"]},
        {**good, "scope_of_work": "Changed"},
        {**good, "success": ""},
        {**good, "success": "- Test 700 concurrent sessions."},
        {**good, "success": ["Test"]},
    ):
        with pytest.raises(ValueError):
            validate_editorial_revision(original, bad, categories)


def test_targeted_review_only_receives_editable_section_permissions(monkeypatch):
    agent = POCWriterAgent.__new__(POCWriterAgent)
    agent.config = SimpleNamespace(WRITER_MODEL_ID="test")
    sections = [TemplateSection(name, "", {"type": kind, **extra}, i)
                for i, (name, kind, extra) in enumerate([
                    ("Scope of Work", "GENERATED", {}),
                    ("Assumptions", "GENERATED", {}),
                    ("Customer Dependencies", "GENERATED", {}),
                    ("About ShellKode", "STATIC", {}),
                    ("AWS Pricing", "TABLE", {}),
                    ("Out of Scope", "GENERATED", {"custom_template": True}),
                ])]
    output = {agent._section_key(s.name, {}): "Protected body" for s in sections}
    output.update(assumptions="- Reporting is included in scope.",
                  customer_dependencies="- Provide API documentation.\n- Provide API credentials.")
    before = dict(output)
    calls = []

    def review(self, document, categories, context):
        calls.append(categories)
        return {**document, 'customer_dependencies': '- Provide API documentation and credentials.'}
    monkeypatch.setattr('app.agents.sow_reviewer_agent.SOWReviewerAgent.review', review)
    omissions = agent._review_document_relevance(output, sections, {})
    assert omissions == set()
    assert len(calls) == 1
    assert 'scope_of_work' in calls[0]
    assert 'aws_pricing' not in calls[0]
    assert 'about_shellkode' not in calls[0]
    assert 'out_of_scope' not in calls[0]
    for key in set(before) - {"assumptions", "customer_dependencies"}:
        assert output[key] == before[key]


def test_editorial_purposes_are_not_ui_groupings():
    assert editorial_category("Security, Privacy and Compliance", "architecture_diagram") == "security_requirements"
    assert editorial_category("2. Current State", None) == "current_state"
    assert editorial_category("Risks and Mitigations", "assumptions") == "risks_mitigations"


def test_all_modes_use_exact_requested_shellkode_paragraph():
    expected = "ShellKode is a cloud-native company with a global presence, delivering services from multiple strategic locations worldwide. We empower organizations to embrace change, accelerate innovation, and unlock holistic business value by placing Cloud and Data at the core of their digital transformation. At ShellKode, we are committed to continuous improvement and innovation, consistently exploring new ways to leverage modern technologies to drive agility, resilience, and long-term success for our customers."
    folder = Path(__file__).resolve().parents[1] / "templates"
    for name in ("poc_template.md", "production_template.md", "poc_to_prod_template.md"):
        body = (folder / name).read_text(encoding="utf-8")
        actual = body.split("## About ShellKode\n", 1)[1].split("[META_", 1)[0].strip()
        assert actual == expected
        assert "one primary home" in body
        assert "Create a dependency register" not in body
        assert "SC-01 onward" not in body
