import sys
import threading
import time
import types
import unittest

try:
    import boto3  # noqa: F401
except ModuleNotFoundError:
    sys.modules["boto3"] = types.SimpleNamespace(client=lambda *args, **kwargs: None)

from app.agents.poc_writer_agent import POCWriterAgent, TemplateSection


class _Config:
    SOW_SECTION_WORKERS = 4


class POCWriterConcurrencyTests(unittest.TestCase):
    def test_generated_sections_run_concurrently_and_reassemble_in_template_order(self):
        agent = POCWriterAgent.__new__(POCWriterAgent)
        agent.config = _Config()
        agent.template_type = "POC"
        agent.sections = [
            TemplateSection(
                f"Generated Section {index}",
                "Write a detailed section.",
                {"type": "GENERATED", "_explicit": True},
                index,
            )
            for index in range(6)
        ]

        active = 0
        max_active = 0
        lock = threading.Lock()

        def fake_generate(self, section, requirements, metadata, source_context, prior_summaries):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.04)
            with lock:
                active -= 1
            return f"Content for {section.name}"

        agent._generate_section = types.MethodType(fake_generate, agent)
        result = agent.generate_poc(
            requirements={"project_overview": "Test project"},
            metadata={
                "company_name": "Example Customer",
                "project_title": "Preview Performance Test",
                "author_org": "ShellKode",
            },
        )

        content_keys = [key for key in result if key != "generation_quality_summary"]
        self.assertEqual(
            content_keys,
            [f"generated_section_{index}" for index in range(6)],
        )
        self.assertGreaterEqual(max_active, 2)
        self.assertEqual(result["generated_section_0"], "Content for Generated Section 0")

    def test_worker_count_is_bounded_and_can_be_disabled(self):
        agent = POCWriterAgent.__new__(POCWriterAgent)
        agent.config = types.SimpleNamespace(SOW_SECTION_WORKERS=20)
        self.assertEqual(agent._section_worker_count(30), 8)
        agent.config = types.SimpleNamespace(SOW_SECTION_WORKERS=1)
        self.assertEqual(agent._section_worker_count(30), 1)


if __name__ == "__main__":
    unittest.main()
