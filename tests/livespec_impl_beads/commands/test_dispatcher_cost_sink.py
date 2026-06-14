"""Tests for the per-dispatch CC-token cost sink (work-item livespec-impl-beads-efj).

The sink half of efj's cap-wiring: `CostSink` is the persisted
`{correlation-key -> {dedup-key -> usd_micros}}` accumulator the live
receiver writes and the dispatcher's cost gate reads OUT OF PROCESS,
mirroring `HeartbeatSink`. `span_cost` extracts + prices one CC span's
token vector. These tests pin the keying (`work.item.id` then
`livespec.dispatch.id`), the anti-double-count dedup (per `request_id`,
span-id fallback), the accumulation sum, the atomic / corrupt-tolerant
persistence, and that non-token-bearing spans are no-ops.

Hermetic: every span is a synthetic OTLP span dict, the sink writes to a
`tmp_path` file. No real CC session / OTLP egress is launched.
"""

from __future__ import annotations

import json
from pathlib import Path

from livespec_impl_beads.commands._dispatcher_cost_pricing import (
    TokenVector,
    derive_usd_micros,
)
from livespec_impl_beads.commands._dispatcher_cost_sink import (
    CostSink,
    cost_lookup_keys,
    span_cost,
)


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
    """A synthetic CC `llm_request`-shaped span carrying per-API-call scalars.

    The three correlation/id params (`work_item_id`, `dispatch_id`,
    `request_id`) are individually omittable via None (the keying / dedup
    branches under test); the model + four token scalars are always
    stamped (a test wanting a non-token-bearing span builds the dict
    inline).
    """
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


# --- span_cost: extraction + pricing -------------------------------------


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
    # haiku input rate 1.00 per MTok -> 1000 tokens == 1000 micro-USD.
    assert cost.usd_micros == 1000


def test_span_cost_no_token_scalars_is_none() -> None:
    """A non-API-call span (root interaction / tool) carries no token scalars."""
    span: dict[str, object] = {
        "name": "claude_code.interaction",
        "spanId": "root-1",
        "attributes": [_attr(key="work.item.id", string_value="li-efj")],
    }
    assert span_cost(span=span) is None


def test_span_cost_no_correlation_key_is_none() -> None:
    """A token-bearing span with no correlation key is unkeyable (None)."""
    span = _cc_span(work_item_id=None, dispatch_id=None)
    assert span_cost(span=span) is None


# --- CostSink: accumulation + persistence --------------------------------


def test_sink_accumulates_single_span(tmp_path: Path) -> None:
    """One span accrues its derived cost under its correlation key."""
    sink = CostSink(path=tmp_path / "cost.json")
    span = _cc_span(
        input_tokens=1_000_000, output_tokens=0, cache_write_tokens=0, cache_read_tokens=0
    )
    sink.accumulate_span(span=span)
    # 1M opus input tokens == 5_000_000 micro-USD.
    assert sink.usd_micros(key="li-efj") == 5_000_000


def test_sink_sums_distinct_api_calls(tmp_path: Path) -> None:
    """Two spans with DISTINCT request ids sum (two API calls = two charges)."""
    sink = CostSink(path=tmp_path / "cost.json")
    sink.accumulate_span(
        span=_cc_span(
            request_id="req-a",
            input_tokens=1_000_000,
            output_tokens=0,
            cache_write_tokens=0,
            cache_read_tokens=0,
        )
    )
    sink.accumulate_span(
        span=_cc_span(
            request_id="req-b",
            input_tokens=1_000_000,
            output_tokens=0,
            cache_write_tokens=0,
            cache_read_tokens=0,
        )
    )
    assert sink.usd_micros(key="li-efj") == 10_000_000


def test_sink_dedupes_redelivered_span(tmp_path: Path) -> None:
    """A re-delivered span (same request_id) is counted ONCE, not double.

    The receiver is fail-open and may see a span twice; the anti-double-
    count dedup keys on `request_id` so the per-dispatch cost is not
    inflated — load-bearing because a spend cap must not over-count.
    """
    sink = CostSink(path=tmp_path / "cost.json")
    span = _cc_span(
        request_id="req-dup",
        input_tokens=1_000_000,
        output_tokens=0,
        cache_write_tokens=0,
        cache_read_tokens=0,
    )
    sink.accumulate_span(span=span)
    sink.accumulate_span(span=span)
    assert sink.usd_micros(key="li-efj") == 5_000_000


def test_sink_no_cost_for_unknown_key(tmp_path: Path) -> None:
    """A key that never accrued reads None (the unobservable condition)."""
    sink = CostSink(path=tmp_path / "cost.json")
    assert sink.usd_micros(key="li-never") is None


def test_sink_non_token_span_is_noop(tmp_path: Path) -> None:
    """A non-token-bearing span does not create an accrual."""
    sink = CostSink(path=tmp_path / "cost.json")
    root: dict[str, object] = {
        "name": "claude_code.interaction",
        "spanId": "root-1",
        "attributes": [_attr(key="work.item.id", string_value="li-efj")],
    }
    sink.accumulate_span(span=root)
    assert sink.usd_micros(key="li-efj") is None


def test_sink_persists_across_instances(tmp_path: Path) -> None:
    """The accrual round-trips through the on-disk file (read out of process)."""
    path = tmp_path / "cost.json"
    CostSink(path=path).accumulate_span(
        span=_cc_span(
            input_tokens=1_000_000, output_tokens=0, cache_write_tokens=0, cache_read_tokens=0
        )
    )
    assert CostSink(path=path).usd_micros(key="li-efj") == 5_000_000


def test_sink_atomic_write_leaves_no_tmp(tmp_path: Path) -> None:
    """The atomic `.tmp` + replace leaves only the final file (no stray tmp)."""
    path = tmp_path / "cost.json"
    CostSink(path=path).accumulate_span(span=_cc_span())
    assert path.is_file()
    assert not path.with_name(f"{path.name}.tmp").exists()


def test_sink_tolerates_corrupt_file(tmp_path: Path) -> None:
    """A corrupt cost file reads as empty (fail-open), never crashing."""
    path = tmp_path / "cost.json"
    _ = path.write_text("{ not json", encoding="utf-8")
    sink = CostSink(path=path)
    assert sink.usd_micros(key="li-efj") is None
    # A later accrual recovers (overwrites the corrupt file).
    sink.accumulate_span(
        span=_cc_span(
            input_tokens=1_000_000, output_tokens=0, cache_write_tokens=0, cache_read_tokens=0
        )
    )
    assert sink.usd_micros(key="li-efj") == 5_000_000


def test_sink_tolerates_non_object_file(tmp_path: Path) -> None:
    """A non-mapping cost file reads as empty (fail-open)."""
    path = tmp_path / "cost.json"
    _ = path.write_text("[1, 2, 3]", encoding="utf-8")
    assert CostSink(path=path).usd_micros(key="li-efj") is None


def test_sink_skips_non_int_and_bool_micros(tmp_path: Path) -> None:
    """A bool / non-int stored micros value is skipped on read (defensive)."""
    path = tmp_path / "cost.json"
    _ = path.write_text(
        json.dumps({"li-efj": {"req-a": True, "req-b": 7, "req-c": "x"}}), encoding="utf-8"
    )
    # Only the genuine int (7) survives.
    assert CostSink(path=path).usd_micros(key="li-efj") == 7


# --- defensive / fail-open branches --------------------------------------


def test_span_cost_attributes_not_a_list_is_none() -> None:
    """A span whose `attributes` is not a list carries no token scalars (None)."""
    span: dict[str, object] = {"name": "x", "spanId": "s1", "attributes": "not-a-list"}
    assert span_cost(span=span) is None


def test_span_cost_skips_malformed_attribute_entries() -> None:
    """Non-dict attr entries, unwanted keys, and non-dict values are skipped.

    The span still prices off its well-formed token + correlation attrs;
    the malformed neighbours are ignored (fail-open attribute reading).
    """
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
    # model value was malformed -> default model (opus) priced: 1M input == 5_000_000.
    assert cost.usd_micros == 5_000_000


def test_span_cost_non_string_string_value_is_ignored() -> None:
    """An attribute whose `stringValue` is not a string is ignored (no key)."""
    span: dict[str, object] = {
        "name": "claude_code.llm_request",
        "spanId": "s1",
        "attributes": [
            {"key": "work.item.id", "value": {"stringValue": 123}},  # non-string
            {"key": "input_tokens", "value": {"intValue": "1000"}},
        ],
    }
    # work.item.id was non-string -> no correlation key -> unkeyable.
    assert span_cost(span=span) is None


def test_span_cost_bool_token_value_counts_as_zero() -> None:
    """A bool-typed token scalar is treated as zero (defensive `_int_attr`)."""
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
    # input counted as 0, output 1M opus == 25_000_000.
    assert cost.usd_micros == 25_000_000


def test_span_cost_dedup_structural_fallback_when_no_ids() -> None:
    """A token-bearing span with no request_id AND no spanId still accrues once.

    The structural-identity dedup fallback: a malformed span lacking both
    ids gets a stable key derived from its attrs so it is counted, but a
    re-delivery of the SAME malformed span still dedupes.
    """
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
    assert first.dedup_key == second.dedup_key  # stable -> dedupes on re-delivery


def test_sink_read_skips_non_dict_per_key_value(tmp_path: Path) -> None:
    """A stored correlation-key value that is not a mapping is skipped on read."""
    path = tmp_path / "cost.json"
    _ = path.write_text(
        json.dumps({"li-efj": "not-a-mapping", "li-ok": {"req-a": 7}}), encoding="utf-8"
    )
    sink = CostSink(path=path)
    assert sink.usd_micros(key="li-efj") is None
    assert sink.usd_micros(key="li-ok") == 7


def test_sink_read_skips_record_missing_usd_micros(tmp_path: Path) -> None:
    """A record-dict lacking `usd_micros` is skipped (a malformed record).

    The richer record form requires `usd_micros`; a dedup value that is a
    dict without it (or with a non-int / bool one) is dropped on read so a
    malformed record never poisons the sum.
    """
    path = tmp_path / "cost.json"
    _ = path.write_text(
        json.dumps(
            {
                "li-efj": {
                    "req-no-usd": {"input": 5},  # no usd_micros -> skipped
                    "req-bool-usd": {"usd_micros": True},  # bool usd -> skipped
                    "req-str-usd": {"usd_micros": "x"},  # str usd -> skipped
                    "req-ok": {"usd_micros": 9, "input": 1},
                }
            }
        ),
        encoding="utf-8",
    )
    sink = CostSink(path=path)
    # Only the well-formed record survives.
    assert sink.usd_micros(key="li-efj") == 9
    report = sink.cost_report(key="li-efj")
    assert report is not None
    assert report.usd_micros == 9
    assert report.input_tokens == 1


def test_sink_write_is_fail_open_on_oserror(tmp_path: Path) -> None:
    """A write to an unwritable path is swallowed (fail-open), never raising.

    The cost sink path points INTO a regular file (so `mkdir`/write raises
    OSError); `accumulate_span` must not propagate it — the cost gate
    degrades to the fail-closed path, the safe direction.
    """
    blocker = tmp_path / "blocker"
    _ = blocker.write_text("i am a file", encoding="utf-8")
    sink = CostSink(path=blocker / "cost.json")  # parent is a file -> mkdir/write fails
    # Must NOT raise.
    sink.accumulate_span(
        span=_cc_span(
            input_tokens=1_000_000, output_tokens=0, cache_write_tokens=0, cache_read_tokens=0
        )
    )
    assert sink.usd_micros(key="li-efj") is None


# --- cost_lookup_keys ----------------------------------------------------


def test_cost_lookup_keys_work_item_then_dispatch() -> None:
    """Lookup candidates are the work-item id then the dispatch id."""
    assert cost_lookup_keys(work_item_id="li-x", dispatch_id="d-y") == ("li-x", "d-y")


def test_cost_lookup_keys_drops_dispatch_when_none() -> None:
    """A None dispatch id yields just the work-item id."""
    assert cost_lookup_keys(work_item_id="li-x", dispatch_id=None) == ("li-x",)


def test_cost_lookup_keys_drops_empty_and_duplicate() -> None:
    """Empty / duplicate candidates are dropped (no redundant lookup)."""
    assert cost_lookup_keys(work_item_id="li-x", dispatch_id="li-x") == ("li-x",)
    assert cost_lookup_keys(work_item_id="li-x", dispatch_id="") == ("li-x",)
