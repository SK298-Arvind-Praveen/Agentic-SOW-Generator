"""Retiring schema retrieval must not retire source evidence or preview editing."""
from pathlib import Path



def test_no_legacy_table_dependencies_in_runtime_or_setup():
    root = Path(__file__).resolve().parents[1]
    for directory in (root / "app", root / "scripts"):
        for source in directory.rglob("*.py"):
            text = source.read_text(encoding="utf-8")
            for forbidden in ("DYNAMODB_TABLE_RAG_SCHEMA", "rag-schema", "app.rag"):
                assert forbidden not in text, (source, forbidden)
    assert not (root / "app/rag/ingest.py").exists()


def test_server_keeps_editor_but_has_no_schema_background_job():
    from app.core import server
    from app.agents.content_editor import SmartContentEditor
    assert server.SmartContentEditor is SmartContentEditor
    assert not hasattr(server, "retrieve_rag_data")
    assert not hasattr(server, "_schedule_finalized_rag")
    assert not hasattr(server, "ingest_to_rag_schema")
