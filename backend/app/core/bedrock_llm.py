"""Provider-neutral Bedrock text generation with task routing and telemetry."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional


TASK_MODEL_ATTRIBUTES = {
    "fast": "FAST_MODEL_ID",
    "analysis": "ANALYSIS_MODEL_ID",
    "writer": "WRITER_MODEL_ID",
    "diagram": "DIAGRAM_MODEL_ID",
    "editor": "EDITOR_MODEL_ID",
    "fallback": "FALLBACK_MODEL_ID",
}

@dataclass(frozen=True)
class BedrockTextResult:
    text: str
    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0


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


def _native_request(model_id: str, prompt: str, max_tokens: int, temperature: float) -> Dict[str, Any]:
    lowered = model_id.casefold()
    if "anthropic.claude" in lowered:
        return {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
    if "amazon.nova" in lowered:
        return {
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
        }
    return {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }


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
        try:
            return self._generate_once(
                primary, prompt, max_tokens=max_tokens,
                temperature=temperature, call_name=call_name,
            )
        except Exception as primary_error:
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
            payload = converse(
                modelId=model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={
                    "maxTokens": int(max_tokens),
                    "temperature": float(temperature),
                },
            )
        else:
            response = self.client.invoke_model(
                modelId=model_id,
                body=json.dumps(_native_request(model_id, prompt, max_tokens, temperature)),
            )
            payload = json.loads(response["body"].read())

        text = _extract_text(payload)
        if not text:
            raise RuntimeError(f"Bedrock model {model_id} returned no text")
        input_tokens, output_tokens = _normalised_usage(payload)

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
        return BedrockTextResult(
            text=text,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
