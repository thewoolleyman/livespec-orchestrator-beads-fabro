"""CC span token extraction and pricing for the dispatcher cost sink."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_pricing import (
    DEFAULT_DISPATCH_COST_MODEL,
    TokenVector,
    derive_usd_micros,
    normalize_model_id,
)

__all__: list[str] = [
    "SpanCost",
    "span_cost",
]

# The CC span scalar attribute keys the token vector + model + dedup id are
# read from. These match the `_otel_scrub` allowlist (the efj rider keys);
# `model` + `request_id` are the efj additions to that allowlist.
_INPUT_TOKENS_ATTR = "input_tokens"
_OUTPUT_TOKENS_ATTR = "output_tokens"
_CACHE_WRITE_TOKENS_ATTR = "cache_creation_tokens"
_CACHE_READ_TOKENS_ATTR = "cache_read_tokens"
_MODEL_ATTR = "model"
_REQUEST_ID_ATTR = "request_id"

# The correlation keys a CC span may carry, MOST-specific first; the cost
# sink is keyed by the FIRST present so the dispatcher's gate can look the
# derived cost up by `work_item_id`.
_COST_KEY_PREFERENCE = ("work.item.id", "livespec.dispatch.id")

# The token-scalar attribute keys; a span carrying NONE of these is not a
# token-bearing per-API-call span and contributes no cost.
_TOKEN_ATTRS = (
    _INPUT_TOKENS_ATTR,
    _OUTPUT_TOKENS_ATTR,
    _CACHE_WRITE_TOKENS_ATTR,
    _CACHE_READ_TOKENS_ATTR,
)


@dataclass(frozen=True, kw_only=True)
class SpanCost:
    """The cost contribution of one token-bearing CC span (leak-free)."""

    correlation_key: str
    dedup_key: str
    usd_micros: int
    tokens: TokenVector
    model_resolved: bool


def span_cost(*, span: dict[str, object], default_model: str | None = None) -> SpanCost | None:
    """Derive one CC span's cost contribution, or None if it bears no cost.

    Reads ONLY the named token / model / id scalar attributes off the
    span's OTLP `attributes` list. Returns None when the span carries no
    token scalars (a non-API-call span: root interaction, tool, hook) or
    no correlation key (an unkeyable span). Otherwise prices the token
    vector at the span's `model` (normalized; an absent / unknown model
    falls back to `default_model`, defaulting to CC's own default model)
    and returns a `SpanCost` keyed by the correlation key + the
    per-API-call dedup key (`request_id` else `spanId`).
    """
    attrs = _string_and_int_attrs(span=span)
    if not any(name in attrs for name in _TOKEN_ATTRS):
        return None
    correlation_key = _preferred_correlation_key(attrs=attrs)
    if correlation_key is None:
        return None
    tokens = TokenVector(
        input=_int_attr(attrs=attrs, key=_INPUT_TOKENS_ATTR),
        output=_int_attr(attrs=attrs, key=_OUTPUT_TOKENS_ATTR),
        cache_write=_int_attr(attrs=attrs, key=_CACHE_WRITE_TOKENS_ATTR),
        cache_read=_int_attr(attrs=attrs, key=_CACHE_READ_TOKENS_ATTR),
    )
    fallback_model = default_model if default_model is not None else DEFAULT_DISPATCH_COST_MODEL
    model_id, model_resolved = _resolve_model(attrs=attrs, fallback_model=fallback_model)
    usd_micros = derive_usd_micros(tokens=tokens, model_id=model_id)
    dedup_key = _dedup_key(span=span, attrs=attrs)
    return SpanCost(
        correlation_key=correlation_key,
        dedup_key=dedup_key,
        usd_micros=usd_micros,
        tokens=tokens,
        model_resolved=model_resolved,
    )


def _string_and_int_attrs(*, span: dict[str, object]) -> dict[str, object]:
    """Flatten the span's OTLP attributes to a `key -> str|int` map (named keys only)."""
    out: dict[str, object] = {}
    raw_attrs = span.get("attributes")
    if not isinstance(raw_attrs, list):
        return out
    wanted = set(_TOKEN_ATTRS) | {_MODEL_ATTR, _REQUEST_ID_ATTR, *_COST_KEY_PREFERENCE}
    for raw in cast("list[object]", raw_attrs):
        if not isinstance(raw, dict):
            continue
        entry = cast("dict[str, object]", raw)
        key = entry.get("key")
        if not isinstance(key, str) or key not in wanted:
            continue
        value = entry.get("value")
        if not isinstance(value, dict):
            continue
        block = cast("dict[str, object]", value)
        if "intValue" in block:
            raw_int = block["intValue"]
            out[key] = int(raw_int) if isinstance(raw_int, str | int) else 0
            continue
        string_value = block.get("stringValue")
        if isinstance(string_value, str):
            out[key] = string_value
    return out


def _int_attr(*, attrs: dict[str, object], key: str) -> int:
    # `_string_and_int_attrs` only ever stores an `intValue`-coerced int or a
    # `stringValue` str under a token key, so a non-int here means the scalar
    # was absent / string-shaped -> 0 tokens (defensive).
    value = attrs.get(key)
    return value if isinstance(value, int) else 0


def _preferred_correlation_key(*, attrs: dict[str, object]) -> str | None:
    for candidate in _COST_KEY_PREFERENCE:
        value = attrs.get(candidate)
        if isinstance(value, str) and value != "":
            return value
    return None


def _resolve_model(*, attrs: dict[str, object], fallback_model: str) -> tuple[str, bool]:
    """Resolve the priced model id + whether it came from the span's own `model`."""
    raw_model = attrs.get(_MODEL_ATTR)
    if isinstance(raw_model, str):
        normalized = normalize_model_id(raw_model=raw_model)
        if normalized is not None:
            return normalized, True
    return fallback_model, False


def _dedup_key(*, span: dict[str, object], attrs: dict[str, object]) -> str:
    request_id = attrs.get(_REQUEST_ID_ATTR)
    if isinstance(request_id, str) and request_id != "":
        return request_id
    span_id = span.get("spanId")
    if isinstance(span_id, str) and span_id != "":
        return span_id
    return repr(sorted((k, str(v)) for k, v in attrs.items()))
