import unittest

from app.core.sow_quality import (
    clean_markdown_preserving_structure,
    merge_requirement_extractions,
    normalize_requirements,
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


if __name__ == "__main__":
    unittest.main()
