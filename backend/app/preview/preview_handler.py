"""
Preview Handler - Generate content without creating documents
Stores preview data in memory with unique preview IDs
Enhanced with automatic cleanup and storage monitoring
"""
import uuid
import json
import sys
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

_backend_root = str(Path(__file__).resolve().parents[2])
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from app.preview.preview_config import PreviewConfig

# In-memory storage for preview data
preview_storage = {}
preview_lock = threading.Lock()

class PreviewStatus:
    INITIALIZING = "initializing"
    RESEARCHING = "researching"
    ANALYZING = "analyzing"
    GENERATING = "generating"
    FINALIZING = "finalizing"
    READY = "ready"
    FAILED = "failed"
    EXPIRED = "expired"

def get_storage_stats():
    """Get current storage statistics - FIXED: No lock needed if called from within lock"""
    # Don't acquire lock here - let caller handle it
    total_previews = len(preview_storage)
    
    # Estimate memory usage
    total_size = 0
    for preview_data in preview_storage.values():
        # Rough estimate: JSON size of the preview data
        total_size += len(json.dumps(preview_data, default=str))
    
    memory_mb = total_size / (1024 * 1024)
    
    return {
        "total_previews": total_previews,
        "memory_usage_mb": round(memory_mb, 2),
        "max_previews": PreviewConfig.MAX_PREVIEWS,
        "max_memory_mb": PreviewConfig.MAX_MEMORY_MB,
        "memory_usage_percent": round((memory_mb / PreviewConfig.MAX_MEMORY_MB) * 100, 1)
    }

def get_storage_stats_safe():
    """Get storage stats with proper locking for external calls"""
    with preview_lock:
        return get_storage_stats()

def create_preview_id():
    """Generate unique preview ID"""
    return f"PREVIEW_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"

def store_preview_data(preview_id: str, content: Dict[str, Any], metadata: Dict[str, Any], mode: str):
    """
    Store preview data in memory - FIXED: Prevent deadlock
    
    Args:
        preview_id: Unique preview identifier
        content: Generated content structure
        metadata: Document metadata
        mode: POC, PROD, or POC_TO_PROD
    """
    with preview_lock:
        # Check limits and cleanup if needed (already inside lock)
        cleanup_by_limits()
        
        preview_storage[preview_id] = {
            "preview_id": preview_id,
            "status": PreviewStatus.INITIALIZING,  # Changed from READY to INITIALIZING
            "mode": mode,
            "metadata": metadata,
            "content": content,
            "created_at": datetime.now().isoformat(),
            "last_modified": datetime.now().isoformat(),
            "edit_count": 0
        }
        print(f"[PREVIEW] Stored preview: {preview_id}")
        return preview_storage[preview_id]

def get_preview_data(preview_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve preview data by ID"""
    with preview_lock:
        return preview_storage.get(preview_id)

def update_preview_data(preview_id: str, updated_content: Dict[str, Any]):
    """Update preview content after edits"""
    with preview_lock:
        if preview_id in preview_storage:
            # Debug: Log what we're updating
            old_content = preview_storage[preview_id]["content"]
            old_section_count = len(old_content)
            new_section_count = len(updated_content)
            
            print(f"[PREVIEW-UPDATE] Updating {preview_id}:")
            print(f"   Section count: {old_section_count} → {new_section_count}")
            
            # Check for any missing sections
            old_keys = set(old_content.keys())
            new_keys = set(updated_content.keys())
            
            if old_keys != new_keys:
                missing = old_keys - new_keys
                added = new_keys - old_keys
                if missing:
                    print(f"   ⚠️  Missing sections: {missing}")
                if added:
                    print(f"   ➕ Added sections: {added}")
            else:
                print(f"   ✅ All sections preserved")
            
            # Update the content
            preview_storage[preview_id]["content"] = updated_content
            preview_storage[preview_id]["last_modified"] = datetime.now().isoformat()
            preview_storage[preview_id]["edit_count"] += 1
            print(f"[PREVIEW] Updated preview: {preview_id} (edit #{preview_storage[preview_id]['edit_count']})")
            return True
        else:
            print(f"[PREVIEW-UPDATE] ❌ Preview {preview_id} not found in storage")
        return False

def delete_preview_data(preview_id: str):
    """Delete preview data from memory - called when finalized"""
    with preview_lock:
        if preview_id in preview_storage:
            del preview_storage[preview_id]
            print(f"[FINALIZE-CLEANUP] Deleted preview: {preview_id}")
            return True
        return False

def get_preview_stats():
    """Get statistics about current previews"""
    with preview_lock:
        stats = get_storage_stats()
        
        # Add age information
        current_time = datetime.now()
        ages = []
        
        for data in preview_storage.values():
            created_at = datetime.fromisoformat(data["created_at"])
            age_hours = (current_time - created_at).total_seconds() / 3600
            ages.append(age_hours)
        
        if ages:
            stats["oldest_preview_hours"] = round(max(ages), 1)
            stats["newest_preview_hours"] = round(min(ages), 1)
            stats["average_age_hours"] = round(sum(ages) / len(ages), 1)
        else:
            stats["oldest_preview_hours"] = 0
            stats["newest_preview_hours"] = 0
            stats["average_age_hours"] = 0
        
        return stats

def cleanup_old_previews(max_age_hours: int = 24):
    """Clean up previews older than specified hours - DISABLED for finalize-only cleanup"""
    # Previews are now only cleaned up when finalized, not by age
    print(f"[CLEANUP] Age-based cleanup disabled - previews persist until finalized")
    return 0

def cleanup_by_limits():
    """Clean up previews when storage limits are exceeded - DISABLED for finalize-only cleanup"""
    # Emergency cleanup disabled - previews only cleaned up when finalized
    print(f"[CLEANUP] Emergency cleanup disabled - previews persist until finalized only")
    return 0

def auto_cleanup_worker():
    """Background worker for automatic cleanup - DISABLED for finalize-only cleanup"""
    if not PreviewConfig.ENABLE_AUTO_CLEANUP:
        print("[STARTUP] Preview auto-cleanup disabled by configuration")
        return
    
    print("[STARTUP] Preview cleanup fully disabled - previews persist until finalized only")
    print("[STARTUP] No automatic cleanup will occur - previews only removed via finalize API")
    
    # No cleanup loop needed - previews only cleaned up when finalized
    while True:
        try:
            # Sleep indefinitely - no cleanup operations
            time.sleep(3600)  # Sleep 1 hour, but do nothing
            
        except Exception as e:
            print(f"[AUTO-CLEANUP] Error: {e}")
            time.sleep(300)  # Sleep 5 minutes on error

# Start automatic cleanup thread if enabled
if PreviewConfig.ENABLE_AUTO_CLEANUP:
    cleanup_thread = threading.Thread(target=auto_cleanup_worker, daemon=True)
    cleanup_thread.start()
    print(f"[STARTUP] Preview cleanup fully disabled: Finalize-only cleanup enabled")
    print(f"[STARTUP] Previews persist indefinitely until finalized (no automatic expiration)")
    print(f"[STARTUP] Emergency cleanup only when >150% of limits ({PreviewConfig.CLEANUP_INTERVAL_MINUTES}min interval)")
else:
    print("[STARTUP] Preview auto-cleanup disabled")

def extract_content_structure(final_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract structured content from graph output
    Organizes content into major sections and subsections
    
    Returns:
        Dict with poc_content structure compatible with document builder
    """
    poc_content = final_state.get("poc_content", {})
    
    # Return the poc_content directly - the document builder expects this format
    # Don't restructure it, as the builder knows how to handle the original format
    return poc_content
