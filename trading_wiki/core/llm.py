"""Anthropic SDK wrapper. Owns auth, retries, JSON-mode-via-tool-use, usage logging.

See docs/superpowers/specs/2026-04-25-phase-2a-pass1-design.md §5.5.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import anthropic
import structlog
from pydantic import BaseModel, ValidationError

from trading_wiki.core.secrets import Settings

# Pricing as of April 2026 (USD per 1M tokens). See PROJECT_PLAN.md §Phase 2.
_PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-4-7": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
}

_TOOL_NAME = "submit_structured_output"

_log = structlog.get_logger(__name__)


@dataclass
class UsageRecord:
    model: str
    input_tokens: int
    output_tokens: int
    cost_estimate_usd: float


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    if model not in _PRICES_PER_MTOK:
        return 0.0
    in_rate, out_rate = _PRICES_PER_MTOK[model]
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000


def call_structured[T: BaseModel](
    *,
    model: str,
    system: str,
    messages: list[dict[str, Any]],
    schema: type[T],
    max_validation_retries: int = 1,
    max_tokens: int = 8192,
) -> tuple[T, UsageRecord, list[dict[str, Any]]]:
    """Make a schema-bound tool-use call, retrying on JSON / Pydantic validation errors.

    Returns ``(parsed_model, usage_record, message_history)``. ``message_history``
    is the input ``messages`` with the assistant turn appended; callers can append
    further turns and call again to do their own validation-retry.

    Network/rate-limit retries are handled by the Anthropic SDK's built-in retry
    config; this wrapper only handles validation retries (malformed JSON,
    Pydantic schema mismatches, missing tool_use block).

    Raises:
        RuntimeError: ``ANTHROPIC_API_KEY`` is not set.
        ValidationError: Pydantic validation failed after exhausting retries.
        anthropic.APIError: SDK-level error after exhausting network retries.
    """
    settings = Settings()
    if settings.anthropic_api_key is None:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Add it to .env (see .env.example).")
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())

    tool_def = {
        "name": _TOOL_NAME,
        "description": f"Submit a {schema.__name__} object.",
        "input_schema": schema.model_json_schema(),
    }

    history: list[dict[str, Any]] = list(messages)
    last_error: ValidationError | ValueError | None = None
    total_in = 0
    total_out = 0

    for attempt in range(max_validation_retries + 1):
        # The SDK uses very specific TypedDicts for messages/tools; our generic
        # dict shape works at runtime (verified by tests) but mypy can't prove it.
        response = client.messages.create(  # type: ignore[call-overload]
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=history,
            tools=[tool_def],
            tool_choice={"type": "tool", "name": _TOOL_NAME},
        )
        total_in += response.usage.input_tokens
        total_out += response.usage.output_tokens

        history = [*history, {"role": "assistant", "content": response.content}]

        tool_use = next(
            (b for b in response.content if getattr(b, "type", None) == "tool_use"),
            None,
        )
        if tool_use is None:
            last_error = ValueError("response had no tool_use block")
            _log.warning("llm.no_tool_use", attempt=attempt, model=model)
            if attempt == max_validation_retries:
                break
            history.append(
                {
                    "role": "user",
                    "content": (
                        "Your previous response did not call the tool. "
                        "Please call the tool with the structured output."
                    ),
                }
            )
            continue

        try:
            parsed = schema.model_validate(tool_use.input)
        except ValidationError as e:
            last_error = e
            _log.warning("llm.schema_validation_failed", attempt=attempt, error=str(e))
            if attempt == max_validation_retries:
                break
            history.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": (
                                f"Schema validation failed: {e}. "
                                "Please regenerate the output conforming to the schema."
                            ),
                            "is_error": True,
                        }
                    ],
                }
            )
            continue

        usage = UsageRecord(
            model=model,
            input_tokens=total_in,
            output_tokens=total_out,
            cost_estimate_usd=_estimate_cost(model, total_in, total_out),
        )
        _log.info(
            "llm.call_structured.ok",
            model=model,
            input_tokens=total_in,
            output_tokens=total_out,
            cost_estimate_usd=usage.cost_estimate_usd,
            attempts=attempt + 1,
        )
        return parsed, usage, history

    assert last_error is not None
    raise last_error
