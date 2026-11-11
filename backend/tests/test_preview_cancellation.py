from unittest.mock import Mock, patch
import threading
import pytest


def test_worker_waits_for_inflight_graph_and_never_autosaves():
    from app.preview import async_preview, preview_handler
    started, finish = threading.Event(), threading.Event()
    preview = {"status": "generating"}
    def invoke(state):
        started.set()
        assert finish.wait(5)
        return {"poc_content": {"scope": "Never save this"}}
    graph = Mock()
    graph.invoke.side_effect = invoke
    complete = Mock()
    with (patch.object(preview_handler, "preview_storage", {"p": preview}),
          patch.object(async_preview, "preview_storage", {"p": preview}),
          patch("app.core.graph.create_fast_preview_graph", return_value=graph)):
        thread = async_preview.process_preview_async("p", {}, on_complete=complete)
        try:
            assert started.wait(5)
            with preview_handler.preview_lock:
                preview.update(cancel_requested=True, status="cancelling")
            assert thread.is_alive()
            assert preview["status"] == "cancelling"
        finally:
            finish.set()
            thread.join(5)
        assert not thread.is_alive()
        assert preview["status"] == "cancelled"
        assert preview["content"] == {}
        complete.assert_not_called()


def test_cancelled_model_response_is_discarded_and_call_count_released():
    from app.preview import preview_handler
    from app.preview.cancellation import current_preview, cancellable_call, GenerationCancelled
    preview = {"status": "generating"}
    @cancellable_call
    def model():
        assert preview["generation_calls_active"] == 1
        preview["cancel_requested"] = True
        return "late response"
    token = current_preview.set("p")
    try:
        with patch.object(preview_handler, "preview_storage", {"p": preview}):
            with pytest.raises(GenerationCancelled):
                model()
            assert preview["generation_calls_active"] == 0
    finally:
        current_preview.reset(token)


@pytest.mark.parametrize("active", ["generation_worker_active", "generation_calls_active", "draft_save_active"])
def test_cleanup_waits_for_all_workers(active):
    from app.core import server
    preview = {"status": "cancelling", "cancel_requested": True, active: 1}
    with patch.object(server, "preview_storage", {"p": preview}), patch.object(server, "DynamoDBHandler") as db:
        server._finish_preview_cancellation("p")
        assert preview["status"] == "cancelling"
        db.assert_not_called()
        preview[active] = 0
        server._finish_preview_cancellation("p")
        assert preview["status"] == "cancelled"


def test_cancellation_during_upload_removes_artifact_without_committing_draft(tmp_path):
    from app.core import server
    file = tmp_path / "draft.docx"
    file.write_bytes(b"draft")
    preview = {"status": "draft_pending", "mode": "POC", "metadata": {}, "content": {"scope": "test"}}
    def upload(*args, **kwargs):
        preview.update(cancel_requested=True, status="cancelling")
        return {"s3_url": "s3://files/cancelled.docx", "bucket": "files"}
    with (patch.object(server, "preview_storage", {"p": preview}),
          patch.object(server, "DynamoDBHandler") as db,
          patch("app.core.nodes.pdf_build_node", return_value={"output_path": str(file)}),
          patch.object(server, "upload_to_s3", side_effect=upload),
          patch.object(server, "get_s3_client") as s3,
          patch.object(server, "parse_s3_location", return_value=("files", "cancelled.docx")),
          patch.object(server, "save_to_dynamodb") as save):
        db.return_value.query_by_task_id.return_value = None
        result = server._save_preview_as_draft("p", automatic=True)
        assert not result["success"]
        assert preview["status"] == "cancelled"
        save.assert_not_called()
        s3.return_value.delete_object.assert_called_with(Bucket="files", Key="cancelled.docx")


def test_failed_rollback_keeps_cancelling_and_retries():
    from app.core import server
    record = {"status": "draft", "document_id": "d"}
    preview = {"status": "cancelling", "cancel_requested": True, "draft_save_started": True}
    with (patch.object(server, "preview_storage", {"p": preview}),
          patch.object(server, "DynamoDBHandler") as db,
          patch.object(server, "_delete_draft_record", side_effect=[RuntimeError("offline"), None]) as delete):
        db.return_value.query_by_task_id.side_effect = [record, None]
        server._finish_preview_cancellation("p")
        assert preview["status"] == "cancelling"
        server._finish_preview_cancellation("p")
        assert preview["status"] == "cancelled"
        assert delete.call_count == 2


def test_cancel_requires_ownership():
    from app.core import server
    preview = {"status": "generating"}
    with (patch.object(server, "preview_storage", {"p": preview}),
          patch.object(server, "_preview_denied", return_value=({"error": "denied"}, 403))):
        with server.app.test_request_context("/api/preview/p/cancel", method="POST"):
            assert server.cancel_preview_generation("p")[1] == 403
        assert not preview.get("cancel_requested")



def test_duplicate_upload_does_not_release_original_worker():
    from app.core import server
    preview = {"status": "generating", "reserved": False, "generation_worker_active": True}
    with (patch.object(server, "preview_storage", {"p": preview}),
          patch.object(server, "_business_unit_for_new_record", return_value=("GenAI", None)),
          patch.object(server, "_ownership_metadata", return_value={}),
          patch.object(server, "_preview_denied", return_value=None)):
        with server.app.test_request_context("/api/preview", method="POST", data={"reserved_preview_id": "p"}):
            _, status = server.generate_preview()
        assert status == 409
        assert preview["generation_worker_active"] is True
        assert preview["status"] == "generating"


def test_cancel_after_commit_uses_primary_key_even_if_task_index_lags(tmp_path):
    from app.core import server
    file = tmp_path / "draft.docx"
    file.write_bytes(b"draft")
    preview = {"status": "draft_pending", "mode": "POC", "metadata": {}, "content": {"scope": "test"}}
    def commit(**kwargs):
        preview.update(cancel_requested=True, status="cancelling")
        return {"success": True, "document_id": "d1", "timestamp": "created"}
    with (patch.object(server, "preview_storage", {"p": preview}),
          patch.object(server, "DynamoDBHandler") as db,
          patch("app.core.nodes.pdf_build_node", return_value={"output_path": str(file)}),
          patch.object(server, "upload_to_s3", return_value={"s3_url": "s3://files/draft.docx", "bucket": "files"}),
          patch.object(server, "get_s3_client"),
          patch.object(server, "parse_s3_location", return_value=("files", "draft.docx")),
          patch.object(server, "_semantic_index_metadata", return_value={}),
          patch.object(server, "save_to_dynamodb", side_effect=commit),
          patch.object(server, "_delete_draft_record") as delete):
        db.return_value.query_by_task_id.return_value = None
        server._save_preview_as_draft("p", automatic=True)
        assert preview["status"] == "cancelled"
        assert delete.call_args.args[0]["document_id"] == "d1"
        assert delete.call_args.args[0]["timestamp"] == "created"
