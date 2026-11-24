"""Lossless prompt caching and bounded, run-isolated validated stage reuse."""
from collections import OrderedDict
from copy import deepcopy
from functools import wraps
import hashlib
import json
import os
import sys
import threading
import time
from app.core.model_profiles import resolve_model, MODEL_PROFILES


def enabled(name):
    return os.getenv(name, 'true').lower() in {'true', '1', 'yes', 'on'}


def prompt_blocks(model, prompt, system):
    # Remove only an exact repeated instruction prefix, never source paragraphs.
    if system and prompt.startswith(system):
        prompt = prompt[len(system):] or 'Follow the system instructions.'
    systems = [{'text': system}] if system else []
    blocks = [{'text': prompt}]
    supported = {MODEL_PROFILES[k]['id'] for k in ('sonnet-5.5', 'haiku', 'opus-5.5')}
    if not enabled('BEDROCK_PROMPT_CACHE_ENABLED') or resolve_model(model) not in supported:
        return blocks, systems
    ttl = os.getenv('BEDROCK_PROMPT_CACHE_TTL', '5m')
    checkpoint = {'cachePoint': {'type': 'default'}}
    if ttl == '1h': checkpoint['cachePoint']['ttl'] = '1h'
    # Conservative word threshold; provider enforces actual token eligibility.
    minimum = 4096 if resolve_model(model) == MODEL_PROFILES['haiku']['id'] else 512
    if len(system.split()) >= minimum:
        systems.append(deepcopy(checkpoint))
    # Writer baseline is identical across sections; dynamic evidence/section
    # instructions remain after the checkpoint without any truncation.
    marker = 'REFINEMENT PRESERVATION CONTRACT'
    split = prompt.find(marker)
    prefix = prompt[:split] if split > 0 else prompt
    if len((system + prefix).split()) >= minimum:
        blocks = [{'text': prefix}, deepcopy(checkpoint)]
        if split > 0: blocks.append({'text': prompt[split:]})
    return blocks, systems


class StageCache:
    def __init__(self, ttl=3600, capacity=128, clock=time.monotonic):
        self.ttl, self.capacity, self.clock = ttl, capacity, clock
        self.values = OrderedDict()
        self.lock = threading.Lock()

    def get(self, run, key):
        with self.lock:
            value = self.values.get((run, key))
            if value is None: return None
            if self.clock() - value[0] >= self.ttl:
                self.values.pop((run, key), None)
                return None
            self.values.move_to_end((run, key))
            return deepcopy(value[1])

    def put(self, run, key, value):
        with self.lock:
            self.values[(run, key)] = (self.clock(), deepcopy(value))
            self.values.move_to_end((run, key))
            while len(self.values) > self.capacity: self.values.popitem(last=False)

    def clear_run(self, run):
        with self.lock:
            for key in list(self.values):
                if key[0] == run: del self.values[key]


stage_cache = StageCache()


def run_id():
    nodes = sys.modules.get('app.core.nodes')
    value = nodes._token_usage_run.get() if nodes and hasattr(nodes, '_token_usage_run') else '__default__'
    return None if value == '__default__' else value


def stage_key(planner, stage, task='diagram'):
    from app.core.bedrock_llm import BedrockLLM, model_for_task, _additional_model_request_fields
    if not isinstance(BedrockLLM, type) or not isinstance(planner, BedrockLLM) or not run_id() or not enabled('SOW_STAGE_CACHE_ENABLED'):
        return None
    model = model_for_task(planner.config, task)
    # Prompt/schema lives in the full key at the validation boundary. Include
    # config and relevant environment switches; only a digest is retained.
    payload = [stage, model, getattr(planner, 'system_prompt', ''),
               {k: str(getattr(planner.config, k)) for k in dir(planner.config) if k.isupper()}, _additional_model_request_fields(model),
               sorted((k, v) for k, v in os.environ.items()
                      if k.startswith(('ARCHITECTURE_', 'BEDROCK_', 'SOW_')))]
    return stage + ':' + hashlib.sha256(json.dumps(payload, default=str).encode()).hexdigest()


def content_key(namespace, value):
    if not namespace: return None
    return hashlib.sha256((namespace + json.dumps(value, sort_keys=True, default=str)).encode()).hexdigest()


_metrics_lock = threading.Lock()
_metrics = OrderedDict()


def record(event):
    """Bounded aggregate metrics; no prompts, images or credentials stored."""
    run = run_id() or '__default__'
    with _metrics_lock:
        bucket = _metrics.setdefault(run, {})
        key = (event.get('stage', ''), event.get('model_id', ''))
        row = bucket.setdefault(key, {'stage': key[0], 'model_id': key[1],
            **{k: 0 for k in ('calls', 'failures', 'result_cache_hits', 'input_tokens',
                'output_tokens', 'cache_read_input_tokens', 'cache_write_input_tokens', 'elapsed_seconds')}})
        for k in row:
            if k not in {'stage', 'model_id'}: row[k] += event.get(k, 0)
        _metrics.move_to_end(run)
        while len(_metrics) > 128: _metrics.popitem(last=False)


def metrics(run):
    with _metrics_lock: return deepcopy(list(_metrics.get(run, {}).values()))


def clear(run):
    stage_cache.clear_run(run)
    with _metrics_lock: _metrics.pop(run, None)


def observe_call(fn):
    @wraps(fn)
    def wrapped(self, model_id, prompt, **kwargs):
        started = time.monotonic()
        event = {'stage': kwargs.get('call_name', 'Bedrock'), 'model_id': model_id, 'calls': 1}
        try:
            return fn(self, model_id, prompt, **kwargs)
        except Exception:
            event['failures'] = 1
            raise
        finally:
            event['elapsed_seconds'] = round(time.monotonic() - started, 3)
            record(event)
    return wrapped
