"""Per-dispatch CC-token-derived cost sink (work-item livespec-impl-beads-efj).

The persisted accumulator that turns the per-API-call token counts the
host OTLP receiver (`_otel_receive._handle_traces`) already sees into the
OBSERVED per-dispatch cost the y0m spend cap reads — the seam that LIFTS
5v9's fail-closed refusal. It MIRRORS the `HeartbeatSink` discipline
verbatim (a small JSON file keyed on the correlation key, a
`threading.Lock` serializing the read-modify-write, an atomic `.tmp` +
`os.replace`, a fail-open corrupt-read → empty) because the live receiver
runs the same `ThreadingHTTPServer` worker-thread model and the cost
sink is read OUT OF PROCESS by the dispatcher's cost gate, exactly as
29f.6's `LivenessProbe` reads the heartbeat.

The correlation key is `work.item.id`, falling back to
`livespec.dispatch.id` — NOT `fabro.run_id`. CC spans carry `work.item.id`
+ `livespec.dispatch.id` (stamped via `OTEL_RESOURCE_ATTRIBUTES` in the
sandbox overlay, `_dispatcher_plan.cc_otel_overlay_env`); they do NOT
carry `fabro.run_id` (per `cc-otel-gap-analysis.md` §"Conclusion 9": the
join key is `work.item.id` / `livespec.dispatch.id`). The dispatcher's
cost gate then looks the derived cost up by `work_item_id`.

Anti-double-count (load-bearing — a spend cap must NOT over-count): CC
emits multiple span types per turn (root `claude_code.interaction`,
per-API-call `claude_code.llm_request`, tool / hook children). Only the
per-API-call span carries the token scalars, and each API call has a
unique `request_id`. `accumulate_span` records each token vector under
its (correlation-key, dedup-key) pair, where the dedup key is the span's
`request_id` when present (the authoritative per-API-call id) else its
`spanId` — so a re-delivered span (the receiver is fail-open and may see
a span twice) is counted ONCE and parent/child spans that lack token
scalars contribute nothing. The accumulated cost is the sum over the
DISTINCT dedup keys for a correlation key.

Credential hygiene: the sink reads ONLY the named scalar token / model /
id attributes by key and stores integer token sums + a derived integer
micro-USD — no goal text, no env values, no span blobs. This module is
stdlib-only (mirroring `_otel_receive`), with the pricing math delegated
to the pure `_dispatcher_cost_pricing` module.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from livespec_impl_beads.commands._dispatcher_cost_pricing import (
    DEFAULT_DISPATCH_COST_MODEL,
    TokenVector,
    derive_usd_micros,
    normalize_model_id,
)

__all__: list[str] = [
    "CostSink",
    "SpanCost",
    "cost_lookup_keys",
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
# derived cost up by `work.item.id` (the join key it always knows).
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
    """The cost contribution of one token-bearing CC span (leak-free).

    `correlation_key` is the `work.item.id` (or `livespec.dispatch.id`
    fallback) the cost accrues to; `dedup_key` is the per-API-call
    `request_id` (or `spanId` fallback) that makes a re-delivered span
    count once; `usd_micros` is the derived integer micro-USD cost. A span
    with no token scalars or no correlation key yields None from
    `span_cost` (it is not a cost-bearing span).
    """

    correlation_key: str
    dedup_key: str
    usd_micros: int


def cost_lookup_keys(*, work_item_id: str, dispatch_id: str | None) -> tuple[str, ...]:
    """The candidate cost-sink keys for one dispatch, MOST-specific first.

    Mirrors `_dispatcher_heartbeat_probe.heartbeat_lookup_keys`: the cost
    sink keys an accrual on the FIRST present of `work.item.id` /
    `livespec.dispatch.id`, so the gate looks the derived cost up by the
    work-item id (always known at gate time) then the dispatch id. Empty /
    duplicate candidates are dropped (an empty id can never key an
    accrual). Unlike the heartbeat keys these are NOT scrubbed — the cost
    sink stores the raw correlation key (a work-item / dispatch id is not
    credential-shaped), keeping the lookup an exact string match.
    """
    raw_candidates = (work_item_id, dispatch_id) if dispatch_id is not None else (work_item_id,)
    keys: list[str] = []
    for candidate in raw_candidates:
        if candidate == "" or candidate in keys:
            continue
        keys.append(candidate)
    return tuple(keys)


def span_cost(*, span: dict[str, object], default_model: str | None = None) -> SpanCost | None:
    """Derive one CC span's cost contribution, or None if it bears no cost.

    Reads ONLY the named token / model / id scalar attributes off the
    span's OTLP `attributes` list. Returns None when the span carries no
    token scalars (a non-API-call span — root interaction, tool, hook) or
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
    model_id = _resolve_model(attrs=attrs, fallback_model=fallback_model)
    usd_micros = derive_usd_micros(tokens=tokens, model_id=model_id)
    dedup_key = _dedup_key(span=span, attrs=attrs)
    return SpanCost(correlation_key=correlation_key, dedup_key=dedup_key, usd_micros=usd_micros)


@dataclass(kw_only=True)
class CostSink:
    """Persisted `{correlation-key -> {dedup-key -> usd_micros}}` map (efj).

    The per-dispatch cost accumulator the live receiver writes and the
    dispatcher's cost gate reads OUT OF PROCESS, mirroring `HeartbeatSink`.
    `accumulate_span` records a token-bearing span's derived cost under its
    (correlation-key, dedup-key) pair (a re-delivered span with the same
    dedup key overwrites rather than double-adds — idempotent); `usd_micros`
    reads back the SUM over the distinct dedup keys for a correlation key.
    Both are fail-open: a corrupt / unreadable file reads as empty rather
    than crashing the receiver's trace path.

    A `threading.Lock` serializes the read-modify-write so concurrent
    `ThreadingHTTPServer` worker threads never clobber the file (the
    identical discipline as `HeartbeatSink`).
    """

    path: Path
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def accumulate_span(self, *, span: dict[str, object], default_model: str | None = None) -> None:
        """Record one span's derived cost (idempotent per dedup key; fail-open).

        A non-cost-bearing span (no token scalars / no correlation key) is
        a no-op. Otherwise the span's derived micro-USD is stored under its
        (correlation-key, dedup-key) pair — re-delivery of the same span
        (same dedup key) overwrites the same slot rather than double-adding,
        so the sum stays the true per-dispatch cost.
        """
        cost = span_cost(span=span, default_model=default_model)
        if cost is None:
            return
        with self._lock:
            accruals = self._read()
            per_key = accruals.setdefault(cost.correlation_key, {})
            per_key[cost.dedup_key] = cost.usd_micros
            self._write(accruals=accruals)

    def usd_micros(self, *, key: str) -> int | None:
        """Return the accumulated micro-USD for `key`, or None if never accrued.

        The sum over the DISTINCT dedup keys recorded for the correlation
        key — None when no span has ever accrued to it (the unobservable
        condition the dispatcher's gate falls back to 5v9's fail-closed
        path on).
        """
        with self._lock:
            per_key = self._read().get(key)
        if not per_key:
            return None
        return sum(per_key.values())

    def _read(self) -> dict[str, dict[str, int]]:
        if not self.path.is_file():
            return {}
        try:
            raw: object = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(raw, dict):
            return {}
        accruals: dict[str, dict[str, int]] = {}
        for key, value in cast("dict[str, object]", raw).items():
            if not isinstance(value, dict):
                continue
            per_key: dict[str, int] = {}
            for dedup_key, micros in cast("dict[str, object]", value).items():
                if isinstance(micros, bool):
                    continue
                if isinstance(micros, int):
                    per_key[dedup_key] = micros
            accruals[key] = per_key
        return accruals

    def _write(self, *, accruals: dict[str, dict[str, int]]) -> None:
        text = json.dumps(accruals, separators=(",", ":"), sort_keys=True)
        tmp = self.path.with_name(f"{self.path.name}.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            _ = tmp.write_text(text, encoding="utf-8")
            _ = tmp.replace(self.path)
        except OSError:
            # Fail-open: a cost-write failure never crashes the receiver's
            # trace path (the cost gate degrades to 5v9's unobservable
            # fail-closed refusal, which is the safe direction).
            return


def _string_and_int_attrs(*, span: dict[str, object]) -> dict[str, object]:
    """Flatten the span's OTLP attributes to a `key -> str|int` map (named keys only).

    Reads ONLY the token / model / correlation attribute keys (credential
    hygiene — the broader span is never materialized). An OTLP int value
    arrives as a numeric string under `intValue`; it is coerced to `int`.
    A string value is kept as-is under `stringValue`.
    """
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


def _resolve_model(*, attrs: dict[str, object], fallback_model: str) -> str:
    raw_model = attrs.get(_MODEL_ATTR)
    if isinstance(raw_model, str):
        normalized = normalize_model_id(raw_model=raw_model)
        if normalized is not None:
            return normalized
    return fallback_model


def _dedup_key(*, span: dict[str, object], attrs: dict[str, object]) -> str:
    request_id = attrs.get(_REQUEST_ID_ATTR)
    if isinstance(request_id, str) and request_id != "":
        return request_id
    span_id = span.get("spanId")
    if isinstance(span_id, str) and span_id != "":
        return span_id
    # No request_id and no spanId: fall back to a structural identity so the
    # span still accrues once. (CC spans always carry a spanId; this is a
    # defensive fallback for a malformed span.)
    return repr(sorted((k, str(v)) for k, v in attrs.items()))
