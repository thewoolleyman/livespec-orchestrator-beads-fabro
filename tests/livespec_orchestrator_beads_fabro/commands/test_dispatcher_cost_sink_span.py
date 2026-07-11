"""Tests for CC span cost extraction and pricing."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_pricing import (
    TokenVector,
    derive_usd_micros,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_sink_span import span_cost


def _attr(
    *, key: str, string_value: str | None = None, int_value: int | None = None
) -> dict[str, object]:
    if int_value is not None:
        return {"key": key, "value": {"intValue": str(int_value)}}
    return {"key": key, "value": {"stringValue": string_value if string_value is not None else ""}}


def _cc_span(
    *,
    work_item_id: str | None = "li-efj",
    dispatch_id: str | None = None,
    request_id: str | None = "req-1",
    span_id: str = "span-1",
    model: str = "claude-opus-4-8",
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> dict[str, object]:
    """A synthetic CC `llm_request`-shaped span carrying per-API-call scalars."""
    attrs: list[dict[str, object]] = [
        _attr(key="model", string_value=model),
        _attr(key="input_tokens", int_value=input_tokens),
        _attr(key="output_tokens", int_value=output_tokens),
        _attr(key="cache_creation_tokens", int_value=cache_write_tokens),
        _attr(key="cache_read_tokens", int_value=cache_read_tokens),
    ]
    if work_item_id is not None:
        attrs.append(_attr(key="work.item.id", string_value=work_item_id))
    if dispatch_id is not None:
        attrs.append(_attr(key="livespec.dispatch.id", string_value=dispatch_id))
    if request_id is not None:
        attrs.append(_attr(key="request_id", string_value=request_id))
    return {"name": "claude_code.llm_request", "spanId": span_id, "attributes": attrs}


def test_span_cost_prices_token_vector_by_model() -> None:
    """A token-bearing span derives the priced micro-USD of its token vector."""
    span = _cc_span(
        input_tokens=1000, output_tokens=500, cache_write_tokens=200, cache_read_tokens=300
    )
    cost = span_cost(span=span)
    assert cost is not None
    expected = derive_usd_micros(
        tokens=TokenVector(input=1000, output=500, cache_write=200, cache_read=300),
        model_id="claude-opus-4-8",
    )
    assert cost.usd_micros == expected
    assert cost.correlation_key == "li-efj"
    assert cost.dedup_key == "req-1"


def test_span_cost_keys_on_work_item_id_first() -> None:
    """`work.item.id` is the correlation key when present (most-specific)."""
    span = _cc_span(work_item_id="li-x", dispatch_id="dispatch-y")
    cost = span_cost(span=span)
    assert cost is not None
    assert cost.correlation_key == "li-x"


def test_span_cost_falls_back_to_dispatch_id() -> None:
    """`livespec.dispatch.id` is the correlation key when `work.item.id` absent."""
    span = _cc_span(work_item_id=None, dispatch_id="dispatch-y")
    cost = span_cost(span=span)
    assert cost is not None
    assert cost.correlation_key == "dispatch-y"


def test_span_cost_dedup_key_falls_back_to_span_id() -> None:
    """The dedup key is `spanId` when no `request_id` is present."""
    span = _cc_span(request_id=None, span_id="span-abc")
    cost = span_cost(span=span)
    assert cost is not None
    assert cost.dedup_key == "span-abc"


def test_span_cost_unknown_model_priced_at_default() -> None:
    """A span with an unknown model is priced at the fallback (never free)."""
    span = _cc_span(
        model="some-future-model",
        input_tokens=1000,
        output_tokens=0,
        cache_write_tokens=0,
        cache_read_tokens=0,
    )
    cost = span_cost(span=span, default_model="claude-haiku-4-5")
    assert cost is not None
    assert cost.usd_micros == 1000


def test_span_cost_no_token_scalars_is_none() -> None:
    """A non-API-call span carries no token scalars."""
    span: dict[str, object] = {
        "name": "claude_code.interaction",
        "spanId": "root-1",
        "attributes": [_attr(key="work.item.id", string_value="li-efj")],
    }
    assert span_cost(span=span) is None


def test_span_cost_no_correlation_key_is_none() -> None:
    """A token-bearing span with no correlation key is unkeyable."""
    span = _cc_span(work_item_id=None, dispatch_id=None)
    assert span_cost(span=span) is None


def test_span_cost_attributes_not_a_list_is_none() -> None:
    """A span whose `attributes` is not a list carries no token scalars."""
    span: dict[str, object] = {"name": "x", "spanId": "s1", "attributes": "not-a-list"}
    assert span_cost(span=span) is None


def test_span_cost_skips_malformed_attribute_entries() -> None:
    """Non-dict attr entries, unwanted keys, and non-dict values are skipped."""
    span: dict[str, object] = {
        "name": "claude_code.llm_request",
        "spanId": "s1",
        "attributes": [
            "not-a-dict-entry",
            {"key": "unwanted.key", "value": {"stringValue": "ignored"}},
            {"key": "model", "value": "not-a-dict-value"},
            {"key": "work.item.id", "value": {"stringValue": "li-efj"}},
            {"key": "input_tokens", "value": {"intValue": "1000000"}},
        ],
    }
    cost = span_cost(span=span)
    assert cost is not None
    assert cost.correlation_key == "li-efj"
    assert cost.usd_micros == 5_000_000


def test_span_cost_non_string_string_value_is_ignored() -> None:
    """An attribute whose `stringValue` is not a string is ignored."""
    span: dict[str, object] = {
        "name": "claude_code.llm_request",
        "spanId": "s1",
        "attributes": [
            {"key": "work.item.id", "value": {"stringValue": 123}},
            {"key": "input_tokens", "value": {"intValue": "1000"}},
        ],
    }
    assert span_cost(span=span) is None


def test_span_cost_bool_token_value_counts_as_zero() -> None:
    """A bool-typed token scalar is treated as zero."""
    span: dict[str, object] = {
        "name": "claude_code.llm_request",
        "spanId": "s1",
        "attributes": [
            {"key": "work.item.id", "value": {"stringValue": "li-efj"}},
            {"key": "input_tokens", "value": {"boolValue": True}},
            {"key": "output_tokens", "value": {"intValue": "1000000"}},
        ],
    }
    cost = span_cost(span=span)
    assert cost is not None
    assert cost.usd_micros == 25_000_000


def test_span_cost_dedup_structural_fallback_when_no_ids() -> None:
    """A token-bearing span with no request_id AND no spanId still accrues once."""
    span: dict[str, object] = {
        "name": "claude_code.llm_request",
        "attributes": [
            {"key": "work.item.id", "value": {"stringValue": "li-efj"}},
            {"key": "input_tokens", "value": {"intValue": "1000000"}},
        ],
    }
    first = span_cost(span=span)
    second = span_cost(span=span)
    assert first is not None
    assert second is not None
    assert first.dedup_key == second.dedup_key
