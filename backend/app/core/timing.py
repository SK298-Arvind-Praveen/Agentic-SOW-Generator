"""Content-free wall-clock timing for pipeline diagnosis."""
from functools import wraps
import json
import time


def timed_stage(stage):
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            started = time.perf_counter()
            outcome = 'ok'
            try:
                return fn(*args, **kwargs)
            except BaseException as exc:
                outcome = type(exc).__name__
                raise
            finally:
                try:
                    from app.preview.cancellation import current_preview
                    preview = current_preview.get()
                    print('[TIMING] ' + json.dumps({
                        'stage': stage, 'preview_id': preview,
                        'elapsed_seconds': round(time.perf_counter() - started, 3),
                        'outcome': outcome,
                    }), flush=True)
                except Exception:
                    pass  # Diagnostics must never affect generation.
        return wrapped
    return decorate
