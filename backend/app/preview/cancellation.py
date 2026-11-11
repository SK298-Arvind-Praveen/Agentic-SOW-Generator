"""Cooperative, request-scoped cancellation; never terminate Python threads."""
from contextvars import ContextVar
from functools import wraps

current_preview = ContextVar('cancellable_preview', default=None)


class GenerationCancelled(BaseException):
    """Bypass model retry/fallback handlers which catch ordinary exceptions."""


def cancellable_call(fn):
    """Count even detached reviewer calls until their network operation returns."""
    @wraps(fn)
    def wrapped(*args, **kwargs):
        preview_id = current_preview.get()
        if not preview_id:
            return fn(*args, **kwargs)
        from app.preview.preview_handler import preview_lock, preview_storage
        with preview_lock:
            live = preview_storage.get(preview_id)
            if not live or live.get('cancel_requested'):
                raise GenerationCancelled()
            live['generation_calls_active'] = live.get('generation_calls_active', 0) + 1
        try:
            result = fn(*args, **kwargs)
            check_cancelled(preview_id)
            return result
        finally:
            with preview_lock:
                live = preview_storage.get(preview_id)
                if live:
                    live['generation_calls_active'] = max(0, live.get('generation_calls_active', 1)-1)
    return wrapped


def check_cancelled(preview_id=None, *, storage=None):
    preview_id = preview_id or current_preview.get()
    if not preview_id:
        return
    from app.preview.preview_handler import preview_lock, preview_storage
    with preview_lock:
        preview = (preview_storage if storage is None else storage).get(preview_id)
        if preview is None or preview.get('cancel_requested'):
            raise GenerationCancelled('Preview generation cancelled')
