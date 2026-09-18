"""Provider-neutral Bedrock text generation with task routing and telemetry."""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


TASK_MODEL_ATTRIBUTES = {
    "fast": "FAST_MODEL_ID",
    "analysis": "ANALYSIS_MODEL_ID",
    "writer": "WRITER_MODEL_ID",
    "diagram": "DIAGRAM_MODEL_ID",
    "editor": "EDITOR_MODEL_ID",
    "fallback": "FALLBACK_MODEL_ID",
}

_raw_output_lock = threading.Lock()
_raw_output_counter = 0

@dataclass(frozen=True)
class BedrockTextResult:
    text: str
    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = ""


class BedrockOutputTruncatedError(RuntimeError):
    """Raised when Bedrock exhausts the configured response allowance."""


def _stop_reason(payload: Dict[str, Any]) -> str:
    return str(payload.get("stopReason") or payload.get("stop_reason") or payload.get("completionReason") or "").strip()


def model_for_task(config: Any, task: str) -> str:
    attribute = TASK_MODEL_ATTRIBUTES.get(task, "WRITER_MODEL_ID")
    return str(getattr(config, attribute, getattr(config, "MODEL_ID", "")))


def _extract_text(payload: Dict[str, Any]) -> str:
    output = payload.get("output", {})
    message = output.get("message", {}) if isinstance(output, dict) else {}
    content = message.get("content", []) if isinstance(message, dict) else []
    if isinstance(content, list):
        text = "".join(
            str(block.get("text", ""))
            for block in content
            if isinstance(block, dict) and block.get("text") is not None
        )
        if text:
            return text.strip()

    content = payload.get("content", [])
    if isinstance(content, list):
        text = "".join(
            str(block.get("text", ""))
            for block in content
            if isinstance(block, dict) and block.get("text") is not None
        )
        if text:
            return text.strip()

    choices = payload.get("choices", [])
    if choices and isinstance(choices[0], dict):
        choice = choices[0]
        message = choice.get("message", {})
        if isinstance(message, dict) and message.get("content"):
            return str(message["content"]).strip()
        if choice.get("text"):
            return str(choice["text"]).strip()
    return str(payload.get("generation") or payload.get("outputText") or "").strip()


def _normalised_usage(payload: Dict[str, Any]) -> tuple[int, int]:
    usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
    return (
        int(usage.get("inputTokens", usage.get("input_tokens", 0)) or 0),
        int(usage.get("outputTokens", usage.get("output_tokens", 0)) or 0),
    )


def _supports_temperature(model_id: str) -> bool:
    """Application profiles may target models that reject legacy sampling fields."""
    return "application-inference-profile/" not in str(model_id).casefold()


def _additional_model_request_fields(model_id: str) -> Dict[str, Any]:
    """Keep Sonnet 5 profile calls fast and reserve output tokens for final JSON/text."""
    if "application-inference-profile/" in str(model_id).casefold():
        return {"thinking": {"type": "disabled"}}
    return {}


def _save_raw_output(call_name: str, text: str) -> Path:
    """Persist model text before any JSON/Markdown parsing for reproducible debugging."""
    global _raw_output_counter
    # Unit-test doubles return values such as "complete" and "native"; keeping
    # those beside real SOW traces makes production diagnosis misleading.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return Path()
    configured = os.environ.get("LLM_RAW_OUTPUT_DIR", "").strip()
    output_dir = (
        Path(configured).expanduser()
        if configured else Path(__file__).resolve().parents[2] / "output" / "llm-debug"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", call_name).strip("_") or "bedrock"
    with _raw_output_lock:
        _raw_output_counter += 1
        sequence = _raw_output_counter
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        path = output_dir / f"{timestamp}_{sequence:04d}_{safe_name}.txt"
        path.write_text(text or "", encoding="utf-8")
    print(f"   Raw model output: {path}", flush=True)
    return path


def _native_request(model_id: str, prompt: str, max_tokens: int, temperature: float) -> Dict[str, Any]:
    lowered = model_id.casefold()
    if "anthropic.claude" in lowered:
        request = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if _supports_temperature(model_id):
            request["temperature"] = temperature
        return request
    if "amazon.nova" in lowered:
        inference_config = {"maxTokens": max_tokens}
        if _supports_temperature(model_id):
            inference_config["temperature"] = temperature
        return {
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": inference_config,
        }
    request = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    if _supports_temperature(model_id):
        request["temperature"] = temperature
    return request


class BedrockLLM:
    """Call multiple Bedrock model families through one stable interface."""

    def __init__(self, config: Any, client: Any):
        self.config = config
        self.client = client

    def generate(
        self,
        prompt: str,
        *,
        task: str = "writer",
        max_tokens: int = 2048,
        temperature: float = 0.1,
        call_name: str = "Bedrock",
        model_id: Optional[str] = None,
        fallback_model_id: Optional[str] = None,
    ) -> BedrockTextResult:
        primary = model_id or model_for_task(self.config, task)
        # Honour the task-specific budget. The former unconditional 32K minimum
        # encouraged compact extraction and authoring tasks to expand until
        # they became slow or reached provider output limits.
        max_tokens = max(256, min(32768, int(max_tokens)))
        try:
            return self._generate_once(
                primary, prompt, max_tokens=max_tokens,
                temperature=temperature, call_name=call_name,
            )
        except Exception as primary_error:
            if isinstance(primary_error, BedrockOutputTruncatedError):
                expanded_tokens = min(
                    32768,
                    max(max_tokens * 2, max_tokens + 1024),
                )
                if expanded_tokens <= max_tokens:
                    raise
                print(
                    f"   ↻ {call_name} reached {max_tokens:,} output tokens; "
                    f"retrying once with {expanded_tokens:,}",
                    flush=True,
                )
                compact_retry_prompt = (
                    prompt
                    + "\n\nThe previous response reached its output allowance. Return a complete "
                    "response within this expanded allowance. Aggressively deduplicate repeated "
                    "facts and omit commentary, rationale, preambles and any fields or prose not "
                    "required by the requested output contract."
                )
                return self._generate_once(
                    primary,
                    compact_retry_prompt,
                    max_tokens=expanded_tokens,
                    temperature=temperature,
                    call_name=f"{call_name} expanded retry",
                )
            fallback = fallback_model_id
            if fallback and fallback != primary:
                print(f"   ⚠ {call_name} failed on {primary}; retrying with {fallback}: {primary_error}")
                return self._generate_once(
                    fallback, prompt, max_tokens=max_tokens,
                    temperature=temperature, call_name=f"{call_name} fallback",
                )
            raise

    def _generate_once(
        self,
        model_id: str,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        call_name: str,
    ) -> BedrockTextResult:
        # Converse is provider-neutral. A native InvokeModel fallback keeps unit
        # tests and older SDK-compatible deployments working.
        converse = getattr(self.client, "converse", None)
        if callable(converse):
            inference_config = {"maxTokens": int(max_tokens)}
            if _supports_temperature(model_id):
                inference_config["temperature"] = float(temperature)
            request = {
                "modelId": model_id,
                "messages": [{"role": "user", "content": [{"text": prompt}]}],
                "inferenceConfig": inference_config,
            }
            additional_fields = _additional_model_request_fields(model_id)
            if additional_fields:
                request["additionalModelRequestFields"] = additional_fields
            payload = converse(
                **request,
            )
        else:
            response = self.client.invoke_model(
                modelId=model_id,
                body=json.dumps(_native_request(model_id, prompt, max_tokens, temperature)),
            )
            payload = json.loads(response["body"].read())

        text = _extract_text(payload)
        _save_raw_output(call_name, text)
        if not text:
            raise RuntimeError(f"Bedrock model {model_id} returned no text")
        input_tokens, output_tokens = _normalised_usage(payload)
        stop_reason = _stop_reason(payload)

        try:
            from app.core.nodes import _track_tokens
            _track_tokens(
                {"usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                }},
                call_name,
                model_id=model_id,
            )
        except Exception:
            pass
        if stop_reason.casefold() in {"max_tokens", "max_token", "length"}:
            raise BedrockOutputTruncatedError(
                f"{call_name} was truncated after {output_tokens:,} output tokens "
                f"(stop reason: {stop_reason}). Generation halted."
            )
        return BedrockTextResult(
            text=text,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            stop_reason=stop_reason,
        )
