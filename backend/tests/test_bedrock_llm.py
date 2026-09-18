import io
import json
import unittest

from app.core.bedrock_llm import BedrockLLM, BedrockOutputTruncatedError, model_for_task


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


class _TruncatedClient:
    def __init__(self):
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "output": {"message": {"content": [{"text": '{"partial":'}]}},
            "usage": {"inputTokens": 8, "outputTokens": 32768},
            "stopReason": "max_tokens",
        }


class _AdaptiveTruncatedClient:
    def __init__(self):
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["inferenceConfig"]["maxTokens"] < 4096:
            return {
                "output": {"message": {"content": [{"text": '{"partial":'}]}},
                "usage": {"inputTokens": 8, "outputTokens": 2048},
                "stopReason": "max_tokens",
            }
        return {
            "output": {"message": {"content": [{"text": '{"complete":true}'}]}},
            "usage": {"inputTokens": 12, "outputTokens": 8},
            "stopReason": "end_turn",
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

    def test_application_inference_profile_omits_deprecated_temperature(self):
        profile = (
            "arn:aws:bedrock:us-east-1:106611079163:"
            "application-inference-profile/20kstbja9ona"
        )
        config = _Config()
        config.WRITER_MODEL_ID = profile
        client = _ConverseClient()

        result = BedrockLLM(config, client).generate(
            "prompt", task="writer", temperature=0.2,
        )

        self.assertEqual(result.model_id, profile)
        self.assertEqual(client.calls[0]["inferenceConfig"], {"maxTokens": 2048})
        self.assertEqual(
            client.calls[0]["additionalModelRequestFields"],
            {"thinking": {"type": "disabled"}},
        )

    def test_legacy_model_keeps_supported_temperature(self):
        client = _ConverseClient()
        BedrockLLM(_Config(), client).generate("prompt", task="writer", temperature=0.2)
        self.assertEqual(client.calls[0]["inferenceConfig"]["temperature"], 0.2)
        self.assertNotIn("additionalModelRequestFields", client.calls[0])

    def test_max_token_stop_is_a_hard_failure(self):
        client = _TruncatedClient()
        with self.assertRaises(BedrockOutputTruncatedError):
            BedrockLLM(_Config(), client).generate(
                "prompt", task="writer", max_tokens=32768,
                fallback_model_id="fallback", call_name="Structured Output",
            )
        self.assertEqual(len(client.calls), 1)

    def test_truncated_output_retries_once_with_an_expanded_allowance(self):
        client = _AdaptiveTruncatedClient()
        result = BedrockLLM(_Config(), client).generate(
            "prompt", task="writer", max_tokens=2048,
            call_name="Structured Output",
        )
        self.assertEqual(result.text, '{"complete":true}')
        self.assertEqual(
            [call["inferenceConfig"]["maxTokens"] for call in client.calls],
            [2048, 4096],
        )
        self.assertIn("Aggressively deduplicate", client.calls[1]["messages"][0]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
