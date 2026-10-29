"""Retiring schema retrieval must not retire source evidence or preview editing."""
from pathlib import Path
from unittest.mock import patch

import pytest


def test_no_legacy_table_dependencies_in_runtime_or_setup():
    root = Path(__file__).resolve().parents[1]
    for directory in (root / "app", root / "scripts"):
        for source in directory.rglob("*.py"):
            text = source.read_text(encoding="utf-8")
            for forbidden in ("DYNAMODB_TABLE_RAG_SCHEMA", "rag-schema", "app.rag"):
                assert forbidden not in text, (source, forbidden)
    assert not (root / "app/rag/ingest.py").exists()


def test_poc_conversion_preserves_uploaded_source_for_writer():
    from app.core import nodes
    from app.agents.poc_writer_agent import POCWriterAgent

    source = "Build a customer support assistant with escalation to live agents."
    with (patch.object(nodes, "read_document", return_value=source),
          patch.object(nodes, "_extract_metadata_with_llm", return_value={}),
          patch.object(nodes, "_extract_requirements_with_llm", return_value={})):
        result = nodes.poc_ingestion_node({
            "source_file": "source.docx", "metadata": {},
            "supporting_context": "Preserve existing requirements.",
        })
    assert result["poc_original_content"] == source
    evidence = POCWriterAgent._context_excerpt(result["supporting_context"])
    assert source in evidence
    assert "Preserve existing requirements." in evidence
    assert "rag_context" not in result


def test_conversion_without_source_does_not_fall_back_to_table():
    from app.core import nodes
    with pytest.raises(ValueError, match="source_file"):
        nodes.poc_ingestion_node({"metadata": {}})


def test_server_keeps_editor_but_has_no_schema_background_job():
    from app.core import server
    from app.agents.content_editor import SmartContentEditor
    assert server.SmartContentEditor is SmartContentEditor
    assert not hasattr(server, "retrieve_rag_data")
    assert not hasattr(server, "_schedule_finalized_rag")
    assert not hasattr(server, "ingest_to_rag_schema")
