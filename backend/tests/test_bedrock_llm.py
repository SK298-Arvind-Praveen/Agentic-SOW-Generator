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


def test_diagram_stream_preserves_text_usage_and_completion(monkeypatch):
    monkeypatch.setenv('BEDROCK_DIAGRAM_TRANSPORT','stream')
    class Client(_ConverseClient):
        def converse_stream(self, **kwargs):
            self.calls.append(kwargs)
            return {'stream': iter([
                {'contentBlockDelta': {'delta': {'text': '{"ok":'}}},
                {'contentBlockDelta': {'delta': {'text': 'true}'}}},
                {'messageStop': {'stopReason': 'end_turn'}},
                {'metadata': {'usage': {'inputTokens': 12, 'outputTokens': 8}}},
            ])}
    result = BedrockLLM(_Config(), Client()).generate('Diagram', task='diagram',
        model_id='arn:aws:bedrock:us-east-1:106611079163:application-inference-profile/hlc2w29214np')
    assert result.text == '{"ok":true}'
    assert result.output_tokens == 8


def test_interrupted_diagram_stream_is_not_accepted(monkeypatch):
    monkeypatch.setenv('BEDROCK_DIAGRAM_TRANSPORT','stream')
    import pytest
    class Client(_ConverseClient):
        def converse_stream(self, **kwargs):
            return {'stream': iter([{'contentBlockDelta': {'delta': {'text': 'partial'}}}])}
    with pytest.raises(BedrockOutputTruncatedError, match='completion event'):
        BedrockLLM(_Config(), Client()).generate('Diagram', task='diagram', retry_on_truncation=False,
            model_id='arn:aws:bedrock:us-east-1:106611079163:application-inference-profile/hlc2w29214np')


def test_second_attempt_uses_nonstreaming_same_model(monkeypatch):
    from app.diagram.reliability import pipeline_attempt, model_attempts
    monkeypatch.setenv('BEDROCK_DIAGRAM_TRANSPORT','auto')
    class Client(_ConverseClient):
        def converse_stream(self, **kwargs):
            raise AssertionError('Retry must use Converse')
    client = Client()
    token, ledger = pipeline_attempt.set(1), model_attempts.set({'Architecture Diagram':1})
    try:
        profile='arn:aws:bedrock:us-east-1:106611079163:application-inference-profile/hlc2w29214np'
        BedrockLLM(_Config(),client).generate('Graph',task='diagram',call_name='Architecture Diagram',model_id=profile)
        assert client.calls[0]['modelId'] == profile
        assert client.calls[0]['inferenceConfig']['maxTokens'] == 65536
    finally:
        model_attempts.reset(ledger)
        pipeline_attempt.reset(token)


def test_sonnet_55_profile_uses_verified_default_parameters():
    profile = 'arn:aws:bedrock:us-east-1:106611079163:application-inference-profile/hlc2w29214np'
    client = _ConverseClient()
    model = BedrockLLM(_Config(), client)
    model.generate('Diagram plan', task='diagram', model_id=profile)
    call = client.calls[0]
    assert call['modelId'] == profile
    assert not call.get('additionalModelRequestFields')
    assert 'temperature' not in call['inferenceConfig']
    assert call['inferenceConfig']['maxTokens'] == 32768


def test_opus_55_profile_uses_adaptive_thinking_without_temperature():
    profile = 'arn:aws:bedrock:us-east-1:106611079163:application-inference-profile/r0bnzxkwcgud'
    client = _ConverseClient()
    model = BedrockLLM(_Config(), client)
    model.generate('Diagram plan', task='diagram', model_id=profile)
    call = client.calls[0]
    assert call['modelId'] == profile
    assert call['additionalModelRequestFields']['thinking'] == {'type': 'adaptive'}
    assert 'temperature' not in call['inferenceConfig']


def test_opus_55_native_id_and_legacy_profile_settings():
    from app.core.bedrock_llm import _additional_model_request_fields, _supports_temperature
    assert _additional_model_request_fields('us.anthropic.claude-opus-5-5') == {'thinking': {'type': 'adaptive'}}
    assert not _supports_temperature('us.anthropic.claude-opus-5-5')
    assert _additional_model_request_fields('arn:aws:bedrock:us-east-1:106611079163:application-inference-profile/20kstbja9ona') == {'thinking': {'type': 'disabled'}}


def test_architecture_pipeline_owns_truncation_retry_and_expands_second_allowance():
    from app.diagram.reliability import pipeline_attempt
    import pytest
    client = _TruncatedClient()
    model = BedrockLLM(_Config(),client)
    for attempt in (1,2):
        token = pipeline_attempt.set(attempt)
        try:
            with pytest.raises(BedrockOutputTruncatedError):
                model.generate('Complete graph',task='diagram',max_tokens=5000,fallback_model_id='fallback')
        finally:
            pipeline_attempt.reset(token)
    assert len(client.calls) == 2
    assert [c['inferenceConfig']['maxTokens'] for c in client.calls] == [5000,10000]


def test_stage_limit_cannot_multiply_across_pipeline_restarts():
    from app.diagram.reliability import pipeline_attempt, model_attempts
    import pytest
    client = _ConverseClient()
    model = BedrockLLM(_Config(),client)
    run_token, ledger_token = pipeline_attempt.set(1), model_attempts.set({})
    try:
        model.generate('Graph',task='diagram',call_name='Architecture Diagram')
        model.generate('Correct graph',task='diagram',call_name='Architecture Diagram')
        model.generate('Third graph',task='diagram',call_name='Architecture Diagram')
        with pytest.raises(RuntimeError,match='two corrective retries'):
            model.generate('Fourth graph',task='diagram',call_name='Architecture Diagram')
        # A later independent stage still gets its own first and retry calls.
        model.generate('View',task='diagram',call_name='Architecture Narrative Composition')
        model.generate('Semantic repair',task='diagram',call_name='Architecture Plan Correction')
        model.generate('Repair transport retry',task='diagram',call_name='Architecture Plan Correction')
        model.generate('Third repair',task='diagram',call_name='Architecture Plan Correction')
        with pytest.raises(RuntimeError,match='two corrective retries'):
            model.generate('Fourth repair',task='diagram',call_name='Architecture Plan Correction')
        assert len(client.calls) == 7
    finally:
        model_attempts.reset(ledger_token)
        pipeline_attempt.reset(run_token)


def test_revised_image_retains_its_review_and_transport_retry_allowance():
    from app.diagram.reliability import pipeline_attempt, model_attempts
    import pytest
    client = _ConverseClient()
    model = BedrockLLM(_Config(),client)
    run_token, ledger_token = pipeline_attempt.set(1), model_attempts.set({})
    try:
        for _ in range(6):
            model.generate('Review', image_bytes=b'png', call_name='Architecture Narrative Image Review')
        with pytest.raises(RuntimeError,match='corrective retr'):
            model.generate('Review', image_bytes=b'png', call_name='Architecture Narrative Image Review')
        assert len(client.calls) == 6
    finally:
        model_attempts.reset(ledger_token)
        pipeline_attempt.reset(run_token)


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
    def test_visual_input_survives_expanded_output_retry(self):
        client = _AdaptiveTruncatedClient()
        BedrockLLM(_Config(), client).generate('Review diagram', image_bytes=b'png-fixture', max_tokens=2048)
        self.assertEqual(len(client.calls), 2)
        for call in client.calls:
            self.assertEqual(call['messages'][0]['content'][1]['image']['source']['bytes'], b'png-fixture')

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

    def test_optional_review_can_disable_expanded_retry(self):
        client = _TruncatedClient()
        with self.assertRaises(BedrockOutputTruncatedError):
            BedrockLLM(_Config(), client).generate(
                "review", max_tokens=2200, retry_on_truncation=False,
            )
        self.assertEqual(len(client.calls), 1)


if __name__ == "__main__":
    unittest.main()


class ArchitectureSystemPromptTests(unittest.TestCase):
    def test_system_prompt_is_separate_from_project_message_and_survives_fallback(self):
        client = _ConverseClient()
        llm = BedrockLLM(_Config(), client)
        llm.system_prompt = "Architecture rules"
        llm.generate("Project evidence", task="analysis", fallback_model_id="writer")
        self.assertEqual(len(client.calls), 2)
        for request in client.calls:
            self.assertEqual(request["system"], [{"text": "Architecture rules"}])
            self.assertEqual(request["messages"][0]["content"], [{"text": "Project evidence"}])
