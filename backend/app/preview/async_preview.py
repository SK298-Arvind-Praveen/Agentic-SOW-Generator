"""
Async Preview Processing for Better User Experience
"""
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Any

_backend_root = str(Path(__file__).resolve().parents[2])
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from app.preview.preview_handler import preview_storage, preview_lock, PreviewStatus

def process_preview_async(preview_id: str, initial_state: Dict[str, Any], use_fast_mode: bool = True):
    """
    Process preview generation in background thread
    Updates status in real-time with 5 distinct phases
    """
    def background_task():
        preview_started_at = float(initial_state.get("preview_started_at") or time.perf_counter())
        usage_context_token = None
        try:
            print(
                f"[PREVIEW {preview_id}] Worker started "
                f"({'FAST' if use_fast_mode else 'STANDARD'} mode)",
                flush=True,
            )
            # Reset token tracking for this preview generation
            from app.core.nodes import start_token_usage
            usage_context_token = start_token_usage(preview_id)
            
            def report_progress(progress: int, step: str) -> None:
                changed = False
                with preview_lock:
                    if preview_id not in preview_storage:
                        return
                    current = int(preview_storage[preview_id].get("progress", 0) or 0)
                    previous_step = str(preview_storage[preview_id].get("current_step", ""))
                    progress = max(current, min(int(progress), 99))
                    preview_storage[preview_id]["progress"] = progress
                    preview_storage[preview_id]["current_step"] = step
                    preview_storage[preview_id]["status"] = (
                        "researching" if progress < 30 else
                        "analyzing" if progress < 50 else
                        "validating" if progress < 60 else
                        "generating"
                    )
                    changed = progress != current or step != previous_step
                if changed:
                    print(f"[PREVIEW {preview_id}] {progress:3d}% — {step}", flush=True)

            report_progress(5, "Preparing preview workflow")
            graph_state = dict(initial_state)
            graph_state["progress_callback"] = report_progress

            refinement_request = graph_state.get("refinement_request")
            if isinstance(refinement_request, dict):
                report_progress(8, "Analyzing requested refinements")
                from app.agents.refinement_agent import SowRefinementAgent, format_refinement_brief
                plan = SowRefinementAgent().prepare(
                    str(refinement_request.get("baseline_sow") or ""),
                    str(refinement_request.get("instructions") or ""),
                    str(refinement_request.get("source_changes") or ""),
                )
                brief = format_refinement_brief(plan)
                baseline = str(refinement_request.get("baseline_sow") or "")
                changes = str(refinement_request.get("source_changes") or "")
                graph_state["objective"] = brief
                graph_state["additional_details"] = brief
                graph_state["supporting_context"] = "\n\n".join(filter(None, [
                    "CURRENT FINALIZED SOW — PRESERVE UNLESS THE REFINEMENT BRIEF CHANGES IT:\n" + baseline,
                    changes,
                ]))
                graph_state["refinement_plan"] = plan
                if plan.get("requested_deliverable_count"):
                    print(
                        f"[REFINE] Enforcing {plan['requested_deliverable_count']} deliverable(s): "
                        f"{', '.join(map(str, plan.get('requested_deliverable_names') or [])) or 'names to be architected'}",
                        flush=True,
                    )
                with preview_lock:
                    if preview_id in preview_storage:
                        preview_storage[preview_id]["refinement_plan"] = plan
                report_progress(12, "Refinement plan prepared")
            
            # Import here to avoid circular imports
            from app.core.graph import create_fast_preview_graph, create_preview_graph
            
            # Select graph based on mode
            if use_fast_mode:
                preview_graph = create_fast_preview_graph()
            else:
                preview_graph = create_preview_graph()
            
            # Run the actual graph
            final_state = preview_graph.invoke(graph_state)
            
            # Phase 5: Finalizing (90-100%)
            with preview_lock:
                if preview_id in preview_storage:
                    preview_storage[preview_id]["status"] = "finalizing"
                    preview_storage[preview_id]["progress"] = 96
                    preview_storage[preview_id]["current_step"] = "Finalizing content structure..."
            print(f"[PREVIEW {preview_id}]  96% — Finalizing content structure", flush=True)
            
            # Get the generated content
            poc_content = final_state.get("poc_content", {})
            print(f"   [ASYNC] poc_content has {len(poc_content)} sections: {list(poc_content.keys())[:5]}")

            from app.core.nodes import get_token_usage
            token_usage = get_token_usage(preview_id)
            final_state["token_usage"] = token_usage
            final_state["total_tokens"] = int(token_usage.get("total_tokens") or 0)

            # Update with final result - Status: Ready
            with preview_lock:
                if preview_id in preview_storage:
                    preview_storage[preview_id]["status"] = "ready"
                    preview_storage[preview_id]["content"] = poc_content
                    preview_storage[preview_id]["progress"] = 100
                    preview_storage[preview_id]["current_step"] = "Preview generation complete"
                    
                    # Store additional state data
                    preview_storage[preview_id]["final_state"] = final_state
                    preview_storage[preview_id]["token_usage"] = token_usage
                    preview_storage[preview_id]["total_tokens"] = int(token_usage.get("total_tokens") or 0)

                    # Preview stays in memory (preview_storage) - no database persistence needed
                    print(f"✅ Preview stored in memory: {preview_id}")

            # Print token usage summary after preview generation
            from app.core.nodes import print_token_summary
            print_token_summary(usage=token_usage)

            print(f"[PREVIEW {preview_id}] 100% — Preview generation complete", flush=True)
            scope_seconds = float(final_state.get("scope_generation_seconds") or 0.0)
            total_seconds = time.perf_counter() - preview_started_at
            print(f"[TIMING] Scope generation time: {scope_seconds:.2f} seconds", flush=True)
            print(f"[TIMING] Total preview time: {total_seconds:.2f} seconds", flush=True)
            
        except Exception as e:
            print(f"[PREVIEW {preview_id}] FAILED — {e}", flush=True)
            import traceback
            traceback.print_exc()
            
            # Update with error status
            with preview_lock:
                if preview_id in preview_storage:
                    preview_storage[preview_id]["status"] = "failed"
                    preview_storage[preview_id]["error"] = str(e)
                    preview_storage[preview_id]["current_step"] = f"Error: {str(e)}"
            from app.core.nodes import clear_token_usage
            clear_token_usage(preview_id)
        finally:
            if usage_context_token is not None:
                from app.core.nodes import unbind_token_usage
                unbind_token_usage(usage_context_token)
    
    # Start background thread
    thread = threading.Thread(target=background_task, daemon=True)
    thread.start()
    
    return thread


def get_preview_status(preview_id: str) -> Dict[str, Any]:
    """
    Get current status of preview generation
    """
    with preview_lock:
        if preview_id not in preview_storage:
            return {
                "success": False,
                "error": "Preview not found"
            }
        
        preview_data = preview_storage[preview_id]
        
        return {
            "success": True,
            "preview_id": preview_id,
            "status": preview_data.get("status", PreviewStatus.GENERATING),
            "progress": preview_data.get("progress", 0),
            "current_step": preview_data.get("current_step", "Initializing..."),
            "is_complete": preview_data.get("status") == PreviewStatus.READY,
            "has_error": preview_data.get("status") == PreviewStatus.FAILED,
            "error": preview_data.get("error"),
            "total_tokens": preview_data.get("total_tokens"),
            "token_usage": preview_data.get("token_usage"),
            "content": preview_data.get("content") if preview_data.get("status") == PreviewStatus.READY else None
        }
