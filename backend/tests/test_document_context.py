import unittest

from app.core.document_context import chunk_document, select_section_evidence


class DocumentContextTests(unittest.TestCase):
    def test_chunking_retains_the_beginning_middle_and_end(self):
        source = "\n\n".join(
            f"Section {index}\nEvidence marker {index} " + ("detail " * 90)
            for index in range(30)
        )
        chunks = chunk_document(source, max_chars=4000, overlap_chars=500)
        combined = "\n".join(chunks)
        self.assertGreater(len(chunks), 1)
        self.assertIn("Evidence marker 0", combined)
        self.assertIn("Evidence marker 15", combined)
        self.assertIn("Evidence marker 29", combined)

    def test_section_evidence_uses_relevant_late_content_not_a_prefix_slice(self):
        source = (
            "Company background\nGeneral introductory material.\n\n"
            + ("Unrelated narrative. " * 300)
            + "\n\nAWS PRICING\nThe confirmed monthly budget is INR 450,000."
        )
        evidence = select_section_evidence(source, "AWS Pricing", max_chars=1000)
        self.assertIn("INR 450,000", evidence)


if __name__ == "__main__":
    unittest.main()
