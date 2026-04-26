from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from trading_wiki.core.llm import UsageRecord, call_structured


class _OutSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str
    score: int


def _mock_tool_use_response(
    input_payload: dict[str, object],
    input_tokens: int = 100,
    output_tokens: int = 50,
    tool_use_id: str = "tu_abc",
) -> MagicMock:
    """Build a mock Anthropic Message response with one tool_use block."""
    response = MagicMock()
    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.name = "submit_structured_output"
    tool_use_block.id = tool_use_id
    tool_use_block.input = input_payload
    response.content = [tool_use_block]
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens
    response.stop_reason = "tool_use"
    return response


@pytest.fixture(autouse=True)
def _set_anthropic_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake")


class TestCallStructuredHappyPath:
    @patch("trading_wiki.core.llm.anthropic.Anthropic")
    def test_returns_parsed_model_and_usage(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_tool_use_response(
            {"answer": "ok", "score": 7}
        )
        mock_client_cls.return_value = mock_client

        parsed, usage, history = call_structured(
            model="claude-sonnet-4-6",
            system="be terse",
            messages=[{"role": "user", "content": "hi"}],
            schema=_OutSchema,
        )

        assert parsed == _OutSchema(answer="ok", score=7)
        assert isinstance(usage, UsageRecord)
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.model == "claude-sonnet-4-6"
        # 100 * $3/MTok + 50 * $15/MTok = (300 + 750) / 1_000_000 = 0.00105
        assert usage.cost_estimate_usd == pytest.approx(0.00105, rel=1e-3)
        assert len(history) == 2
        assert history[0] == {"role": "user", "content": "hi"}
        assert history[1]["role"] == "assistant"

    @patch("trading_wiki.core.llm.anthropic.Anthropic")
    def test_calls_sdk_with_schema_bound_as_tool(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_tool_use_response(
            {"answer": "ok", "score": 1}
        )
        mock_client_cls.return_value = mock_client

        call_structured(
            model="claude-sonnet-4-6",
            system="sys",
            messages=[{"role": "user", "content": "u"}],
            schema=_OutSchema,
        )

        kwargs = mock_client.messages.create.call_args.kwargs
        assert kwargs["model"] == "claude-sonnet-4-6"
        assert kwargs["system"] == "sys"
        assert kwargs["messages"] == [{"role": "user", "content": "u"}]
        assert len(kwargs["tools"]) == 1
        assert kwargs["tools"][0]["input_schema"] == _OutSchema.model_json_schema()
        assert kwargs["tool_choice"] == {
            "type": "tool",
            "name": kwargs["tools"][0]["name"],
        }


class TestCallStructuredRetry:
    @patch("trading_wiki.core.llm.anthropic.Anthropic")
    def test_retries_once_on_schema_validation_failure_then_succeeds(self, mock_client_cls):
        mock_client = MagicMock()
        bad = _mock_tool_use_response(
            {"answer": "ok", "score": "not-an-int"},
            input_tokens=10,
            output_tokens=5,
            tool_use_id="tu_1",
        )
        good = _mock_tool_use_response(
            {"answer": "ok", "score": 7},
            input_tokens=20,
            output_tokens=10,
            tool_use_id="tu_2",
        )
        mock_client.messages.create.side_effect = [bad, good]
        mock_client_cls.return_value = mock_client

        parsed, usage, _ = call_structured(
            model="claude-sonnet-4-6",
            system="s",
            messages=[{"role": "user", "content": "u"}],
            schema=_OutSchema,
        )

        assert parsed == _OutSchema(answer="ok", score=7)
        assert mock_client.messages.create.call_count == 2
        assert usage.input_tokens == 30
        assert usage.output_tokens == 15
        # The retry call's last user message must be a tool_result with is_error.
        retry_msgs = mock_client.messages.create.call_args_list[1].kwargs["messages"]
        last_user = next(m for m in reversed(retry_msgs) if m["role"] == "user")
        assert last_user["content"][0]["type"] == "tool_result"
        assert last_user["content"][0]["tool_use_id"] == "tu_1"
        assert last_user["content"][0]["is_error"] is True

    @patch("trading_wiki.core.llm.anthropic.Anthropic")
    def test_raises_after_exhausting_retries(self, mock_client_cls):
        mock_client = MagicMock()
        bad = _mock_tool_use_response({"answer": "ok", "score": "still-bad"})
        mock_client.messages.create.side_effect = [bad, bad]
        mock_client_cls.return_value = mock_client

        with pytest.raises(ValidationError):
            call_structured(
                model="claude-sonnet-4-6",
                system="s",
                messages=[{"role": "user", "content": "u"}],
                schema=_OutSchema,
                max_validation_retries=1,
            )
        assert mock_client.messages.create.call_count == 2

    @patch("trading_wiki.core.llm.anthropic.Anthropic")
    def test_handles_response_with_no_tool_use_block(self, mock_client_cls):
        mock_client = MagicMock()
        no_tool_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        no_tool_response.content = [text_block]
        no_tool_response.usage.input_tokens = 5
        no_tool_response.usage.output_tokens = 5
        no_tool_response.stop_reason = "end_turn"

        good = _mock_tool_use_response({"answer": "ok", "score": 1})
        mock_client.messages.create.side_effect = [no_tool_response, good]
        mock_client_cls.return_value = mock_client

        parsed, _, _ = call_structured(
            model="claude-sonnet-4-6",
            system="s",
            messages=[{"role": "user", "content": "u"}],
            schema=_OutSchema,
        )
        assert parsed.answer == "ok"
        assert mock_client.messages.create.call_count == 2

    def test_raises_when_api_key_missing(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        # Force Settings() to return a stub with no key, regardless of .env.
        monkeypatch.setattr(
            "trading_wiki.core.llm.Settings",
            lambda: type("S", (), {"anthropic_api_key": None})(),
        )
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            call_structured(
                model="claude-sonnet-4-6",
                system="s",
                messages=[{"role": "user", "content": "u"}],
                schema=_OutSchema,
            )
