"""CC span token extraction and pricing for the dispatcher cost sink."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from livespec_orchestrator_beads_fabro.commands._acp_model_identity import exact_model_identity
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
_GEN_AI_INPUT_TOKENS_ATTR = "gen_ai.usage.input_tokens"
_OUTPUT_TOKENS_ATTR = "output_tokens"
_GEN_AI_OUTPUT_TOKENS_ATTR = "gen_ai.usage.output_tokens"
_CACHE_WRITE_TOKENS_ATTR = "cache_creation_tokens"
_CACHE_READ_TOKENS_ATTR = "cache_read_tokens"
_MODEL_ATTR = "model"
_GEN_AI_REQUEST_MODEL_ATTR = "gen_ai.request.model"
_GEN_AI_RESPONSE_MODEL_ATTR = "gen_ai.response.model"
_REQUEST_ID_ATTR = "request_id"
_GEN_AI_RESPONSE_ID_ATTR = "gen_ai.response.id"
_NODE_ID_ATTR = "node_id"

# OTLP stamps span times in nanoseconds; the ACP event stream reports attempt
# durations in milliseconds. Named so the one conversion between them is
# auditable rather than an inline literal.
_NANOS_PER_MS = 1_000_000

# The model-naming attributes a span may carry, MOST-authoritative first. One
# tuple, read by both the priced-model resolver and the emitted-identity reader,
# so the two cannot come to prefer different attributes of the same span.
_MODEL_ATTR_PREFERENCE = (_MODEL_ATTR, _GEN_AI_RESPONSE_MODEL_ATTR, _GEN_AI_REQUEST_MODEL_ATTR)

# The correlation keys a CC span may carry, MOST-specific first; the cost
# sink is keyed by the FIRST present so the dispatcher's gate can look the
# derived cost up by `work_item_id`.
_COST_KEY_PREFERENCE = ("work.item.id", "livespec.dispatch.id")

# The token-scalar attribute keys; a span carrying NONE of these is not a
# token-bearing per-API-call span and contributes no cost.
_INPUT_TOKEN_ATTRS = (_INPUT_TOKENS_ATTR, _GEN_AI_INPUT_TOKENS_ATTR)
_OUTPUT_TOKEN_ATTRS = (_OUTPUT_TOKENS_ATTR, _GEN_AI_OUTPUT_TOKENS_ATTR)
_TOKEN_ATTRS = (
    _INPUT_TOKEN_ATTRS
    + _OUTPUT_TOKEN_ATTRS
    + (
        _CACHE_WRITE_TOKENS_ATTR,
        _CACHE_READ_TOKENS_ATTR,
    )
)


@dataclass(frozen=True, kw_only=True)
class SpanCost:
    """The cost contribution of one token-bearing CC span (leak-free).

    `started_at_ms` and `model_identity` are what make the per-attempt
    attribution of `SPECIFICATION/contracts.md` section "Factory-configurable
    ACP fallback priority" -> "Cost follows every attempt in a successful
    fallback run" possible at all: the cost gate reads this record OUT OF
    PROCESS, after the run is over, so a record carrying only a derived
    micro-USD cannot be re-attributed to an attempt window however good the
    window is.

    `model_identity` is the EXACT emitted identity, normalized by the one
    date-suffix rule and nothing else, and it is kept even when this build's
    built-in table cannot price it -- the committed model catalog or the
    candidate's own table may, and that decision belongs to the cost path
    rather than to the receiver. It is deliberately NOT `model_basis`, which is
    a priced-model LABEL that falls back to the configured default.
    """

    correlation_key: str
    dedup_key: str
    usd_micros: int
    tokens: TokenVector
    model_basis: str
    model_resolved: bool
    node_id: str | None
    started_at_ms: int | None = None
    model_identity: str | None = None


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
        input=_first_int_attr(attrs=attrs, keys=_INPUT_TOKEN_ATTRS),
        output=_first_int_attr(attrs=attrs, keys=_OUTPUT_TOKEN_ATTRS),
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
        model_basis=model_id,
        model_resolved=model_resolved,
        node_id=_node_id(attrs=attrs),
        started_at_ms=_started_at_ms(span=span),
        model_identity=_emitted_identity(attrs=attrs),
    )


def _started_at_ms(*, span: dict[str, object]) -> int | None:
    """The span's own start instant in epoch MILLISECONDS, or None when absent.

    OTLP carries `startTimeUnixNano` as nanoseconds, and as a STRING on the
    JSON transport because the value exceeds what JSON numbers are trusted to
    round-trip. Milliseconds is the unit the engine reports attempt durations
    in, so the conversion happens here, once, rather than at each comparison --
    mixing the two units puts a boundary a million-fold away from where the
    events put it.

    Read through `str()` rather than a type ladder because every transport
    shape collapses to one question -- are these digits? A digit string is the
    JSON transport's form and a bare int is the protobuf one; `None`, a bool, a
    float and a negative all answer no, which is the honest answer for each,
    since none of them is an instant this span began at.
    """
    digits = str(span.get("startTimeUnixNano", ""))
    return int(digits) // _NANOS_PER_MS if digits.isdigit() else None


def _emitted_identity(*, attrs: dict[str, object]) -> str | None:
    """The exact emitted model identity, whatever this build can price.

    Independent of the built-in price table on purpose: an identity the table
    does not carry may still be priced through the committed model catalog or
    the candidate's own explicit table, and filtering it here would make the
    catalog-first resolution unreachable for exactly the models the table was
    missing.

    An attribute that is present but BLANK is treated exactly as an absent one
    -- neither carries an identity -- so the scan continues to the next
    preference rather than stopping on a key that merely exists.
    """
    for key in _MODEL_ATTR_PREFERENCE:
        identity = exact_model_identity(raw_model=_text_attr(attrs=attrs, key=key))
        if identity is not None:
            return identity
    return None


def _text_attr(*, attrs: dict[str, object], key: str) -> str:
    """One attribute as text, with every non-text shape reading as absent."""
    value = attrs.get(key)
    return value if isinstance(value, str) else ""


def _string_and_int_attrs(*, span: dict[str, object]) -> dict[str, object]:
    """Flatten the span's OTLP attributes to a `key -> str|int` map (named keys only)."""
    out: dict[str, object] = {}
    raw_attrs = span.get("attributes")
    if not isinstance(raw_attrs, list):
        return out
    wanted = set(_TOKEN_ATTRS) | {
        _MODEL_ATTR,
        _GEN_AI_REQUEST_MODEL_ATTR,
        _GEN_AI_RESPONSE_MODEL_ATTR,
        _REQUEST_ID_ATTR,
        _GEN_AI_RESPONSE_ID_ATTR,
        _NODE_ID_ATTR,
        *_COST_KEY_PREFERENCE,
    }
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


def _first_int_attr(*, attrs: dict[str, object], keys: tuple[str, ...]) -> int:
    for key in keys:
        value = _int_attr(attrs=attrs, key=key)
        if value != 0:
            return value
    return 0


def _preferred_correlation_key(*, attrs: dict[str, object]) -> str | None:
    for candidate in _COST_KEY_PREFERENCE:
        value = attrs.get(candidate)
        if isinstance(value, str) and value != "":
            return value
    return None


def _resolve_model(*, attrs: dict[str, object], fallback_model: str) -> tuple[str, bool]:
    """Resolve the priced model id + whether it came from the span's own model."""
    for key in _MODEL_ATTR_PREFERENCE:
        normalized = normalize_model_id(raw_model=_text_attr(attrs=attrs, key=key))
        if normalized is not None:
            return normalized, True
    return fallback_model, False


def _node_id(*, attrs: dict[str, object]) -> str | None:
    value = attrs.get(_NODE_ID_ATTR)
    if isinstance(value, str) and value != "":
        return value
    return None


def _dedup_key(*, span: dict[str, object], attrs: dict[str, object]) -> str:
    for key in (_REQUEST_ID_ATTR, _GEN_AI_RESPONSE_ID_ATTR):
        request_id = attrs.get(key)
        if isinstance(request_id, str) and request_id != "":
            return request_id
    span_id = span.get("spanId")
    if isinstance(span_id, str) and span_id != "":
        return span_id
    return repr(sorted((k, str(v)) for k, v in attrs.items()))
