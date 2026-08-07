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
        try:
            # Reset token tracking for this preview generation
            from app.core.nodes import reset_token_usage
            reset_token_usage()
            
            # Phase 1: Initializing (0-10%)
            with preview_lock:
                if preview_id in preview_storage:
                    preview_storage[preview_id]["status"] = "initializing"
                    preview_storage[preview_id]["progress"] = 5
                    preview_storage[preview_id]["current_step"] = "Setting up preview generation..."
            
            time.sleep(0.2)  # Brief pause for initialization
            
            # Phase 2: Research (10-30%)
            with preview_lock:
                if preview_id in preview_storage:
                    preview_storage[preview_id]["status"] = "researching"
                    preview_storage[preview_id]["progress"] = 15
                    preview_storage[preview_id]["current_step"] = "Researching company and project data..."
            
            time.sleep(0.5)
            
            # Phase 3: Analysis (30-60%)
            with preview_lock:
                if preview_id in preview_storage:
                    preview_storage[preview_id]["status"] = "analyzing"
                    preview_storage[preview_id]["progress"] = 35
                    preview_storage[preview_id]["current_step"] = "Analyzing requirements and objectives..."
            
            time.sleep(0.5)
            
            # Phase 4: Generation (60-90%)
            with preview_lock:
                if preview_id in preview_storage:
                    preview_storage[preview_id]["status"] = "generating"
                    preview_storage[preview_id]["progress"] = 65
                    preview_storage[preview_id]["current_step"] = "Generating document content..."
            
            # Import here to avoid circular imports
            from app.core.graph import create_fast_preview_graph, create_preview_graph
            
            # Select graph based on mode
            if use_fast_mode:
                preview_graph = create_fast_preview_graph()
            else:
                preview_graph = create_preview_graph()
            
            # Run the actual graph
            final_state = preview_graph.invoke(initial_state)
            
            # Phase 5: Finalizing (90-100%)
            with preview_lock:
                if preview_id in preview_storage:
                    preview_storage[preview_id]["status"] = "finalizing"
                    preview_storage[preview_id]["progress"] = 90
                    preview_storage[preview_id]["current_step"] = "Finalizing content structure..."
            
            time.sleep(0.3)
            
            # Get the generated content
            poc_content = final_state.get("poc_content", {})
            print(f"   [ASYNC] poc_content has {len(poc_content)} sections: {list(poc_content.keys())[:5]}")

            # Update with final result - Status: Ready
            with preview_lock:
                if preview_id in preview_storage:
                    preview_storage[preview_id]["status"] = "ready"
                    preview_storage[preview_id]["content"] = poc_content
                    preview_storage[preview_id]["progress"] = 100
                    preview_storage[preview_id]["current_step"] = "Preview generation complete"
                    
                    # Store additional state data
                    preview_storage[preview_id]["final_state"] = final_state

                    # Preview stays in memory (preview_storage) - no database persistence needed
                    print(f"✅ Preview stored in memory: {preview_id}")

            # Print token usage summary after preview generation
            from app.core.nodes import print_token_summary
            print_token_summary()

            print(f"✅ Async preview generation completed: {preview_id}")
            
        except Exception as e:
            print(f"❌ Async preview generation failed: {e}")
            import traceback
            traceback.print_exc()
            
            # Update with error status
            with preview_lock:
                if preview_id in preview_storage:
                    preview_storage[preview_id]["status"] = "failed"
                    preview_storage[preview_id]["error"] = str(e)
                    preview_storage[preview_id]["current_step"] = f"Error: {str(e)}"
    
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
            "content": preview_data.get("content") if preview_data.get("status") == PreviewStatus.READY else None
        }