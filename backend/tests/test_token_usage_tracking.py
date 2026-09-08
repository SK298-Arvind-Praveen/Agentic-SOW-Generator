from app.core.nodes import (
    _track_tokens,
    clear_token_usage,
    get_token_usage,
    start_token_usage,
    unbind_token_usage,
)


def test_token_usage_is_isolated_per_sow():
    first = start_token_usage("sow-a")
    try:
        _track_tokens(
            {"usage": {"input_tokens": 100, "output_tokens": 20}},
            model_id="analysis",
        )
        second = start_token_usage("sow-b")
        try:
            _track_tokens(
                {"usage": {"input_tokens": 7, "output_tokens": 3}},
                model_id="writer",
            )
        finally:
            unbind_token_usage(second)

        _track_tokens(
            {"usage": {"input_tokens": 30, "output_tokens": 5}},
            model_id="writer",
        )

        assert get_token_usage("sow-a")["total_tokens"] == 155
        assert get_token_usage("sow-a")["api_calls"] == 2
        assert get_token_usage("sow-b")["total_tokens"] == 10
        assert get_token_usage("sow-b")["models"] == {"writer": 1}
    finally:
        unbind_token_usage(first)
        clear_token_usage("sow-a")
        clear_token_usage("sow-b")
