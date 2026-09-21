import unittest

from app.core.sow_quality import (
    clean_markdown_preserving_structure,
    merge_requirement_extractions,
    normalize_requirements,
    remove_client_facing_meta_language,
    remove_missing_information_disclaimers,
    validate_generated_sections,
)


class SowQualityTests(unittest.TestCase):
    def test_unknowns_are_not_silently_defaulted(self):
        req = normalize_requirements(
            {"key_features": ["Classify enquiries"], "ui_required": False},
            "Classify enquiries and route them to the right team.",
            "POC",
        )
        self.assertIsNone(req["data_volume_gb"])
        self.assertIsNone(req["concurrent_users"])
        self.assertIsNone(req["mrr_estimate"])
        self.assertEqual(req["aws_services"], [])
        self.assertGreaterEqual(len(req["open_clarifications"]), 4)
        self.assertTrue(req["timeline_is_assumption"])

    def test_markdown_cleanup_preserves_semantics(self):
        source = "### Functional Requirements\n\n- **FR-01:** Route records\n\n| ID | Result |\n|---|---|\n| 1 | Pass |"
        cleaned = clean_markdown_preserving_structure(source)
        self.assertIn("### Functional Requirements", cleaned)
        self.assertIn("- **FR-01:**", cleaned)
        self.assertIn("| ID | Result |", cleaned)

    def test_markdown_cleanup_blanks_editable_unknown_placeholders(self):
        source = (
            "| Field | Value |\n|---|---|\n"
            "| Start Date | Not specified |\n"
            "| Owner | **To be confirmed** |\n\n"
            "Contact: Not provided\n\n"
            "The source states that the threshold is not specified in the BRD."
        )
        cleaned = clean_markdown_preserving_structure(source)
        self.assertIn("| Start Date |  |", cleaned)
        self.assertIn("| Owner |  |", cleaned)
        self.assertIn("Contact:", cleaned)
        self.assertNotIn("Contact: Not provided", cleaned)
        self.assertIn("threshold is not specified in the BRD", cleaned)

    def test_chunk_merging_deduplicates_lists_and_keeps_late_evidence(self):
        merged = merge_requirement_extractions([
            {"aws_services": ["Amazon S3"], "timeline": None},
            {"aws_services": ["Amazon S3", "AWS Lambda"], "timeline": "6 weeks"},
        ])
        self.assertEqual(merged["aws_services"], ["Amazon S3", "AWS Lambda"])
        self.assertEqual(merged["timeline"], "6 weeks")

    def test_generation_gate_matches_benchmark_section_contract(self):
        missing, _ = validate_generated_sections({"project_overview": "x" * 100}, "POC")
        self.assertIn("scope_of_work", missing)
        self.assertIn("aws_pricing", missing)
        self.assertNotIn("testing_and_acceptance_plan", missing)
        self.assertNotIn("risks_and_mitigations", missing)

    def test_missing_information_disclaimers_are_removed_from_normal_sections(self):
        source = (
            "- **Mapping:** Define the source-to-target mapping; source volumes are not stated in the BRD.\n"
            "- **Performance:** Configure TAT timers; no numeric latency target is confirmed.\n"
            "- **Retention:** No retention policy is confirmed; retention remains an open clarification."
        )
        cleaned = remove_missing_information_disclaimers(source)
        self.assertIn("Define the source-to-target mapping", cleaned)
        self.assertIn("Configure TAT timers", cleaned)
        self.assertNotIn("not stated", cleaned)
        self.assertNotIn("confirmed", cleaned)
        self.assertNotIn("Retention", cleaned)

    def test_generation_gate_catches_extended_missing_information_language(self):
        missing, issues = validate_generated_sections(
            {"scope_of_work": "x" * 90 + " Pending customer confirmation."},
            "POC",
            required_keys={"scope_of_work"},
        )
        self.assertEqual(missing, [])
        self.assertTrue(any("describes absent information" in item for item in issues))

    def test_generation_gate_rejects_absence_language_even_in_open_clarifications(self):
        missing, issues = validate_generated_sections(
            {"open_clarifications": "| Module/Area | Open Item | Status / Note |\n|---|---|---|\n| Pricing | Volume was not provided |  |"},
            "POC",
            required_keys={"open_clarifications"},
        )
        self.assertEqual(missing, [])
        self.assertTrue(any("describes absent information" in item for item in issues))

    def test_missing_information_cleanup_covers_absence_and_availability_phrases(self):
        source = (
            "- Configure migration reconciliation; full-volume reconciliation is excluded due to the absence of record counts.\n"
            "- Integrate Cisco call controls; credentials are not available in the supplied material.\n"
            "- Preserve the source-backed ticket classification hierarchy."
        )
        cleaned = remove_missing_information_disclaimers(source)
        self.assertNotIn("absence of", cleaned.casefold())
        self.assertNotIn("not available", cleaned.casefold())
        self.assertIn("Preserve the source-backed ticket classification hierarchy", cleaned)

    def test_client_facing_cleanup_removes_provenance_and_absence_commentary(self):
        source = (
            "- Configure centralised logging (Confirmed).\n"
            "- Use an eight-week plan (Source Assumption).\n"
            "- The provider is not named in the source document.\n"
            "The generated visual shows the secure migration path."
        )
        cleaned = remove_client_facing_meta_language(source)
        self.assertIn("Configure centralised logging", cleaned)
        self.assertIn("Use an eight-week plan", cleaned)
        self.assertIn("architecture diagram", cleaned)
        self.assertNotIn("Confirmed", cleaned)
        self.assertNotIn("Source Assumption", cleaned)
        self.assertNotIn("source document", cleaned)


if __name__ == "__main__":
    unittest.main()
