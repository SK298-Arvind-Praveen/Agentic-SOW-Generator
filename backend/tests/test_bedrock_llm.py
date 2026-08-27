import io
import json
import unittest

from app.core.bedrock_llm import BedrockLLM, model_for_task


class _Config:
    MODEL_ID = "writer"
    FAST_MODEL_ID = "fast"
    ANALYSIS_MODEL_ID = "analysis"
    WRITER_MODEL_ID = "writer"
    DIAGRAM_MODEL_ID = "diagram"
    EDITOR_MODEL_ID = "editor"
    FALLBACK_MODEL_ID = "fallback"


class _ConverseClient:
    def __init__(self):
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["modelId"] == "analysis":
            raise RuntimeError("primary unavailable")
        return {
            "output": {"message": {"content": [{"text": "complete"}]}},
            "usage": {"inputTokens": 10, "outputTokens": 4},
        }


class _NativeClient:
    def __init__(self):
        self.calls = []

    def invoke_model(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "body": io.BytesIO(json.dumps({
                "content": [{"text": "native"}],
                "usage": {"input_tokens": 3, "output_tokens": 2},
            }).encode("utf-8"))
        }


class BedrockLLMTests(unittest.TestCase):
    def test_task_routes_are_explicit(self):
        self.assertEqual(model_for_task(_Config(), "fast"), "fast")
        self.assertEqual(model_for_task(_Config(), "analysis"), "analysis")
        self.assertEqual(model_for_task(_Config(), "writer"), "writer")
        self.assertEqual(model_for_task(_Config(), "diagram"), "diagram")

    def test_converse_retries_only_with_the_requested_fallback(self):
        client = _ConverseClient()
        result = BedrockLLM(_Config(), client).generate(
            "prompt",
            task="analysis",
            fallback_model_id="fallback",
        )
        self.assertEqual(result.text, "complete")
        self.assertEqual(result.model_id, "fallback")
        self.assertEqual([call["modelId"] for call in client.calls], ["analysis", "fallback"])

    def test_native_fallback_keeps_old_clients_and_test_doubles_working(self):
        client = _NativeClient()
        result = BedrockLLM(_Config(), client).generate("prompt", task="writer")
        self.assertEqual(result.text, "native")
        self.assertEqual(result.input_tokens, 3)
        request = json.loads(client.calls[0]["body"])
        self.assertEqual(request["messages"][0]["content"], "prompt")


if __name__ == "__main__":
    unittest.main()
