"""Tests for the host-local OTLP enrich/scrub stage (29f E1 data plane).

Covers `_otel_enrich` — the custom host-local OTLP processor
(telemetry-pipeline-architecture.md §3). Every assertion runs OFFLINE: the
egress path is an injected fake `SpanExporter` (no real Honeycomb call),
and the `HoneycombHttpExporter` transport is exercised with a
monkeypatched `urllib.request.urlopen` (never a real socket). The
load-bearing invariants under test:

- File-tail ingest with a resumable byte cursor (§3.2 (b)); fail-open on a
  missing file / malformed line / truncation.
- Correlation-triple augmentation via the in-memory join map keyed on
  `work.item.id` — backfill the others when a span carries one key (§3.3).
- Fail-CLOSED scrub: a credential-shaped value in an allowlisted attribute
  REJECTS the whole span; a non-allowlisted attribute is DROPPED (§3.4).
- Fail-OPEN toward the pipeline: a forward error never raises out of
  `forward_once` (§3.2).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands._otel_enrich import (
    CorrelationJoin,
    EnrichStage,
    HoneycombHttpExporter,
    correlation_keys_from_attrs,
    enrich_span,
    honeycomb_dataset_for,
    tail_spans,
)

_URLOPEN = "urllib.request.urlopen"
_ENRICH_SLEEP = "livespec_orchestrator_beads_fabro.commands._otel_enrich.time.sleep"


def _no_sleep(_seconds: float) -> None:
    """Drop-in for `time.sleep` so retry tests never actually block."""
    return None


# --------------------------------------------------------------------------
# Fakes + builders (no network, no real fabro)
# --------------------------------------------------------------------------


@dataclass(kw_only=True)
class _FakeExporter:
    """Records every export call; configurable success per call."""

    succeed: bool = True
    calls: list[tuple[tuple[dict[str, object], ...], str]] = field(default_factory=list)

    def export(self, *, spans: tuple[dict[str, object], ...], dataset: str) -> bool:
        self.calls.append((spans, dataset))
        return self.succeed


def _attr_entry(*, key: str, string_value: str) -> dict[str, object]:
    return {"key": key, "value": {"stringValue": string_value}}


def _int_attr_entry(*, key: str, int_value: int) -> dict[str, object]:
    return {"key": key, "value": {"intValue": str(int_value)}}


def _span(*, name: str, attrs: list[dict[str, object]]) -> dict[str, object]:
    return {
        "traceId": "0f47cb389c78d595429094ccc72a4dca",
        "spanId": "0f47cb389c78d595",
        "name": name,
        "kind": 1,
        "startTimeUnixNano": "1",
        "endTimeUnixNano": "2",
        "attributes": attrs,
    }


def _request_line(*, service_name: str, spans: list[dict[str, object]]) -> str:
    request: dict[str, object] = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": service_name}},
                        {
                            "key": "service.namespace",
                            "value": {"stringValue": "livespec-family"},
                        },
                    ]
                },
                "scopeSpans": [{"scope": {"name": "x", "version": "1"}, "spans": spans}],
            }
        ]
    }
    return json.dumps(request, separators=(",", ":"), sort_keys=True)


def _write_lines(*, path: Path, lines: list[str]) -> None:
    _ = path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")


# --------------------------------------------------------------------------
# correlation_keys_from_attrs
# --------------------------------------------------------------------------


def test_correlation_keys_extracts_only_triple_string_values() -> None:
    span = _span(
        name="dispatcher.dispatch",
        attrs=[
            _attr_entry(key="work.item.id", string_value="li-1"),
            _attr_entry(key="livespec.dispatch.id", string_value="d-1"),
            _int_attr_entry(key="pr_number", int_value=7),  # not a triple key
            _attr_entry(key="repo", string_value="livespec"),  # not a triple key
        ],
    )
    assert correlation_keys_from_attrs(span=span) == {
        "work.item.id": "li-1",
        "livespec.dispatch.id": "d-1",
    }


def test_correlation_keys_tolerates_missing_or_malformed_attrs() -> None:
    assert correlation_keys_from_attrs(span={"name": "x"}) == {}
    assert correlation_keys_from_attrs(span={"attributes": "not-a-list"}) == {}
    malformed = {
        "attributes": [
            "not-a-dict",
            {"key": 5, "value": {"stringValue": "v"}},  # non-str key
            {"key": "work.item.id", "value": "not-a-dict"},  # non-dict value
            {"key": "fabro.run_id", "value": {"intValue": "9"}},  # non-string value
        ]
    }
    assert correlation_keys_from_attrs(span=cast("dict[str, object]", malformed)) == {}


# --------------------------------------------------------------------------
# CorrelationJoin
# --------------------------------------------------------------------------


def test_join_backfills_triple_for_later_span_carrying_one_key() -> None:
    join = CorrelationJoin()
    join.observe(
        keys={"work.item.id": "li-1", "livespec.dispatch.id": "d-1", "fabro.run_id": "r-9"}
    )
    # A later span carries only work.item.id; the join backfills the rest.
    backfilled = join.backfill(keys={"work.item.id": "li-1"})
    assert backfilled == {
        "work.item.id": "li-1",
        "livespec.dispatch.id": "d-1",
        "fabro.run_id": "r-9",
    }


def test_join_does_not_clobber_value_the_span_already_carries() -> None:
    join = CorrelationJoin()
    join.observe(keys={"work.item.id": "li-1", "fabro.run_id": "r-old"})
    backfilled = join.backfill(keys={"work.item.id": "li-1", "fabro.run_id": "r-new"})
    assert backfilled["fabro.run_id"] == "r-new"


def test_join_ignores_span_without_work_item_id() -> None:
    join = CorrelationJoin()
    join.observe(keys={"fabro.run_id": "r-9"})  # no anchor key — not learned
    assert join.backfill(keys={"fabro.run_id": "r-9"}) == {"fabro.run_id": "r-9"}


def test_join_merges_triple_pieces_across_observations() -> None:
    join = CorrelationJoin()
    join.observe(keys={"work.item.id": "li-1", "livespec.dispatch.id": "d-1"})
    join.observe(keys={"work.item.id": "li-1", "fabro.run_id": "r-9"})
    assert join.backfill(keys={"work.item.id": "li-1"}) == {
        "work.item.id": "li-1",
        "livespec.dispatch.id": "d-1",
        "fabro.run_id": "r-9",
    }


# --------------------------------------------------------------------------
# enrich_span — allowlist drop + fail-closed reject
# --------------------------------------------------------------------------


def test_enrich_drops_non_allowlisted_attrs_and_stamps_triple() -> None:
    span = _span(
        name="fabro.node",
        attrs=[
            _int_attr_entry(key="cost_usd", int_value=3),  # allowlisted
            _attr_entry(key="agent.acp.stdout", string_value="narrates PAT"),  # dropped
            _attr_entry(key="repo", string_value="livespec"),  # allowlisted
        ],
    )
    enriched = enrich_span(span=span, triple={"work.item.id": "li-1", "fabro.run_id": "r-9"})
    assert enriched is not None
    keys = {a["key"] for a in cast("list[dict[str, object]]", enriched["attributes"])}
    assert "agent.acp.stdout" not in keys  # non-allowlisted dropped
    assert {"cost_usd", "repo", "work.item.id", "fabro.run_id"} <= keys
    # Non-attribute fields are preserved.
    assert enriched["name"] == "fabro.node"
    assert enriched["traceId"] == span["traceId"]


def test_enrich_rejects_span_with_credential_shaped_allowlisted_value() -> None:
    span = _span(
        name="fabro.node",
        attrs=[
            # An allowlisted attribute carrying a credential-shaped value:
            # the WHOLE span is rejected (fail closed), not partially shipped.
            _attr_entry(key="repo", string_value="https://x-access-token:ghp_x@github.com/o/r"),
        ],
    )
    assert enrich_span(span=span, triple={"work.item.id": "li-1"}) is None


def test_enrich_tolerates_span_without_attributes() -> None:
    span: dict[str, object] = {"name": "bare", "traceId": "t", "spanId": "s"}
    enriched = enrich_span(span=span, triple={"work.item.id": "li-1"})
    assert enriched is not None
    keys = {a["key"] for a in cast("list[dict[str, object]]", enriched["attributes"])}
    assert keys == {"work.item.id"}


def test_enrich_skips_malformed_attribute_entries() -> None:
    span = {
        "name": "x",
        "attributes": [
            "not-a-dict",
            {"key": 5, "value": {"stringValue": "v"}},  # non-str key
            _attr_entry(key="repo", string_value="livespec"),
        ],
    }
    enriched = enrich_span(span=cast("dict[str, object]", span), triple={})
    assert enriched is not None
    keys = {a["key"] for a in cast("list[dict[str, object]]", enriched["attributes"])}
    assert keys == {"repo"}


def test_enrich_bool_attribute_round_trips_without_scrub() -> None:
    # exit_code allowlisted; build a bool-valued attribute on the wire shape.
    span = {
        "name": "x",
        "attributes": [{"key": "exit_code", "value": {"boolValue": True}}],
    }
    enriched = enrich_span(span=cast("dict[str, object]", span), triple={})
    assert enriched is not None
    attrs = cast("list[dict[str, object]]", enriched["attributes"])
    assert attrs[0] == {"key": "exit_code", "value": {"boolValue": True}}


def test_enrich_handles_unknown_value_shape_as_empty() -> None:
    span = {
        "name": "x",
        "attributes": [{"key": "repo", "value": {"doubleValue": 1.5}}],
    }
    enriched = enrich_span(span=cast("dict[str, object]", span), triple={})
    assert enriched is not None
    attrs = cast("list[dict[str, object]]", enriched["attributes"])
    assert attrs[0] == {"key": "repo", "value": {"stringValue": ""}}


def test_enrich_handles_non_dict_value_block_as_empty() -> None:
    span = {"name": "x", "attributes": [{"key": "repo", "value": "scalar"}]}
    enriched = enrich_span(span=cast("dict[str, object]", span), triple={})
    assert enriched is not None
    attrs = cast("list[dict[str, object]]", enriched["attributes"])
    assert attrs[0] == {"key": "repo", "value": {"stringValue": ""}}


def test_enrich_handles_non_numeric_int_value_as_zero() -> None:
    span = {
        "name": "x",
        "attributes": [{"key": "pr_number", "value": {"intValue": ["bad"]}}],
    }
    enriched = enrich_span(span=cast("dict[str, object]", span), triple={})
    assert enriched is not None
    attrs = cast("list[dict[str, object]]", enriched["attributes"])
    assert attrs[0] == {"key": "pr_number", "value": {"intValue": "0"}}


# --------------------------------------------------------------------------
# honeycomb_dataset_for
# --------------------------------------------------------------------------


def test_dataset_derives_from_service_name_with_sentinel_fallback() -> None:
    assert honeycomb_dataset_for(resource_attrs={"service.name": "livespec-dispatcher"}) == (
        "livespec-dispatcher"
    )
    assert honeycomb_dataset_for(resource_attrs={}) == "livespec-unknown"


# --------------------------------------------------------------------------
# tail_spans — resumable cursor, fail-open
# --------------------------------------------------------------------------


def test_tail_missing_file_yields_empty_at_same_offset(tmp_path: Path) -> None:
    result = tail_spans(spans_path=tmp_path / "absent.jsonl", offset=42)
    assert result.spans == ()
    assert result.offset == 42


def test_tail_reads_new_lines_and_advances_cursor(tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    line_a = _request_line(service_name="livespec-dispatcher", spans=[_span(name="a", attrs=[])])
    _write_lines(path=path, lines=[line_a])
    first = tail_spans(spans_path=path, offset=0)
    assert len(first.spans) == 1
    assert first.spans[0].resource_attrs["service.name"] == "livespec-dispatcher"
    # A second pass from the advanced cursor sees nothing until more is written.
    second = tail_spans(spans_path=path, offset=first.offset)
    assert second.spans == ()
    assert second.offset == first.offset


def test_tail_resets_when_file_truncated_under_cursor(tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    line = _request_line(service_name="svc", spans=[_span(name="a", attrs=[])])
    _write_lines(path=path, lines=[line])
    # Cursor past EOF (e.g. file rotated): tail restarts from the top.
    result = tail_spans(spans_path=path, offset=10_000)
    assert len(result.spans) == 1


def test_tail_skips_blank_and_malformed_lines(tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    good = _request_line(service_name="svc", spans=[_span(name="a", attrs=[])])
    _write_lines(
        path=path,
        lines=[
            "",
            "{not json",
            "[1, 2, 3]",  # JSON but not an object
            json.dumps({"resourceSpans": "not-a-list"}),
            json.dumps({"resourceSpans": ["not-a-dict"]}),
            json.dumps({"resourceSpans": [{"resource": {}, "scopeSpans": "nope"}]}),
            json.dumps({"resourceSpans": [{"resource": {}, "scopeSpans": ["bad"]}]}),
            json.dumps({"resourceSpans": [{"resource": {}, "scopeSpans": [{"spans": "bad"}]}]}),
            json.dumps({"resourceSpans": [{"resource": {}, "scopeSpans": [{"spans": ["bad"]}]}]}),
            good,
        ],
    )
    result = tail_spans(spans_path=path, offset=0)
    assert len(result.spans) == 1
    assert result.spans[0].span["name"] == "a"


def test_tail_resource_attrs_skip_malformed_and_missing(tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    line = json.dumps(
        {
            "resourceSpans": [
                {
                    "resource": "not-a-dict",
                    "scopeSpans": [{"spans": [_span(name="a", attrs=[])]}],
                }
            ]
        }
    )
    line_b = json.dumps(
        {
            "resourceSpans": [
                {
                    "resource": {"attributes": "not-a-list"},
                    "scopeSpans": [{"spans": [_span(name="b", attrs=[])]}],
                }
            ]
        }
    )
    line_c = json.dumps(
        {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            "bad",
                            {"key": 1, "value": {"stringValue": "x"}},
                            {"key": "service.name", "value": {"intValue": "9"}},
                            {"key": "service.namespace", "value": {"stringValue": "ns"}},
                        ]
                    },
                    "scopeSpans": [{"spans": [_span(name="c", attrs=[])]}],
                }
            ]
        }
    )
    _write_lines(path=path, lines=[line, line_b, line_c])
    result = tail_spans(spans_path=path, offset=0)
    assert {s.span["name"] for s in result.spans} == {"a", "b", "c"}
    # The 'c' line has a non-string service.name (intValue) — skipped; only
    # the string service.namespace survives.
    c_attrs = next(s for s in result.spans if s.span["name"] == "c").resource_attrs
    assert c_attrs == {"service.namespace": "ns"}


# --------------------------------------------------------------------------
# EnrichStage.forward_once — end-to-end, fail-open + fail-closed
# --------------------------------------------------------------------------


def test_forward_once_enriches_scrubs_and_batches_per_dataset(tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    dispatcher_span = _span(
        name="dispatcher.dispatch",
        attrs=[
            _attr_entry(key="work.item.id", string_value="li-1"),
            _attr_entry(key="livespec.dispatch.id", string_value="d-1"),
            _attr_entry(key="fabro.run_id", string_value="r-9"),
        ],
    )
    # A fabro span carrying only work.item.id — backfilled from the dispatcher.
    fabro_span = _span(
        name="fabro.node",
        attrs=[_attr_entry(key="work.item.id", string_value="li-1")],
    )
    _write_lines(
        path=path,
        lines=[
            _request_line(service_name="livespec-dispatcher", spans=[dispatcher_span]),
            _request_line(service_name="fabro-sandbox", spans=[fabro_span]),
        ],
    )
    exporter = _FakeExporter()
    stage = EnrichStage(spans_path=path, exporter=exporter)
    result = stage.forward_once()
    assert result.ingested == 2
    assert result.forwarded == 2
    assert result.rejected == 0
    assert result.exported is True
    # Two datasets, one batch each.
    datasets = {dataset for _, dataset in exporter.calls}
    assert datasets == {"livespec-dispatcher", "fabro-sandbox"}
    # The fabro span got the full triple backfilled.
    fabro_batch = next(spans for spans, ds in exporter.calls if ds == "fabro-sandbox")
    fabro_keys = {a["key"] for a in cast("list[dict[str, object]]", fabro_batch[0]["attributes"])}
    assert {"work.item.id", "livespec.dispatch.id", "fabro.run_id"} <= fabro_keys
    # Cursor advanced; a second pass forwards nothing.
    assert stage.offset == result.offset
    assert stage.forward_once().forwarded == 0


def test_forward_once_rejects_credential_span_and_keeps_clean_ones(tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    clean = _span(name="ok", attrs=[_attr_entry(key="repo", string_value="livespec")])
    dirty = _span(
        name="leak",
        attrs=[_attr_entry(key="repo", string_value="https://u:p@github.com/o/r")],
    )
    _write_lines(path=path, lines=[_request_line(service_name="svc", spans=[clean, dirty])])
    exporter = _FakeExporter()
    stage = EnrichStage(spans_path=path, exporter=exporter)
    result = stage.forward_once()
    assert result.ingested == 2
    assert result.forwarded == 1
    assert result.rejected == 1
    # Only the clean span reached the exporter.
    exported_spans = exporter.calls[0][0]
    assert len(exported_spans) == 1
    assert exported_spans[0]["name"] == "ok"


def test_forward_once_reports_export_failure_without_raising(tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    span = _span(name="a", attrs=[_attr_entry(key="repo", string_value="livespec")])
    _write_lines(path=path, lines=[_request_line(service_name="svc", spans=[span])])
    stage = EnrichStage(spans_path=path, exporter=_FakeExporter(succeed=False))
    result = stage.forward_once()
    assert result.forwarded == 1
    assert result.exported is False


def test_forward_once_is_fail_open_when_a_dependency_raises(tmp_path: Path) -> None:
    # A raising exporter must NOT escape forward_once (fail-open toward the
    # pipeline): a forward error never blocks a dispatch.
    @dataclass(kw_only=True)
    class _BoomExporter:
        def export(self, *, spans: tuple[dict[str, object], ...], dataset: str) -> bool:
            del spans, dataset
            raise RuntimeError("honeycomb exploded")

    path = tmp_path / "spans.jsonl"
    span = _span(name="a", attrs=[_attr_entry(key="repo", string_value="livespec")])
    _write_lines(path=path, lines=[_request_line(service_name="svc", spans=[span])])
    start_offset = 0
    stage = EnrichStage(spans_path=path, exporter=_BoomExporter(), offset=start_offset)
    result = stage.forward_once()  # must not raise
    assert result.exported is False
    assert result.forwarded == 0
    # Cursor unchanged on a fail-open error so the next pass retries.
    assert stage.offset == start_offset


def test_forward_once_no_spans_is_a_clean_noop(tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    _ = path.write_text("", encoding="utf-8")
    exporter = _FakeExporter()
    stage = EnrichStage(spans_path=path, exporter=exporter)
    result = stage.forward_once()
    assert result.ingested == 0
    assert result.forwarded == 0
    assert result.exported is True
    assert exporter.calls == []


# --------------------------------------------------------------------------
# HoneycombHttpExporter — stdlib transport, monkeypatched (no real socket)
# --------------------------------------------------------------------------


@dataclass(kw_only=True)
class _FakeResponse:
    status: int

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def test_http_exporter_posts_with_team_and_dataset_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_urlopen(request: urllib.request.Request, *, timeout: float) -> _FakeResponse:
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        captured["data"] = request.data
        captured["timeout"] = timeout
        return _FakeResponse(status=200)

    monkeypatch.setattr(_URLOPEN, _fake_urlopen)
    exporter = HoneycombHttpExporter(ingest_key="ingest-key-xyz")
    span = _span(name="a", attrs=[_attr_entry(key="repo", string_value="livespec")])
    assert exporter.export(spans=(span,), dataset="livespec-dispatcher") is True
    headers = cast("dict[str, str]", captured["headers"])
    # urllib title-cases header keys.
    assert headers["X-honeycomb-team"] == "ingest-key-xyz"
    assert headers["X-honeycomb-dataset"] == "livespec-dispatcher"
    assert captured["url"] == "https://api.honeycomb.io/v1/traces"
    body = json.loads(cast("bytes", captured["data"]).decode("utf-8"))
    assert body["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["name"] == "a"


def test_http_exporter_empty_batch_is_a_noop_success() -> None:
    # An empty batch short-circuits to a no-op success BEFORE any urlopen
    # (urllib is deliberately NOT monkeypatched here — the early return is
    # what guarantees no network call is attempted on an empty batch).
    exporter = HoneycombHttpExporter(ingest_key="k")
    assert exporter.export(spans=(), dataset="svc") is True


def test_http_exporter_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[int] = []

    def _flaky_urlopen(request: urllib.request.Request, *, timeout: float) -> _FakeResponse:
        del request, timeout
        attempts.append(1)
        if len(attempts) < 2:
            raise urllib.error.URLError("transient")
        return _FakeResponse(status=202)

    monkeypatch.setattr(_URLOPEN, _flaky_urlopen)
    monkeypatch.setattr(_ENRICH_SLEEP, _no_sleep)
    exporter = HoneycombHttpExporter(ingest_key="k")
    span = _span(name="a", attrs=[])
    assert exporter.export(spans=(span,), dataset="svc") is True
    assert len(attempts) == 2


def test_http_exporter_returns_false_after_retries_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[int] = []

    def _always_fail(request: urllib.request.Request, *, timeout: float) -> _FakeResponse:
        del request, timeout
        attempts.append(1)
        raise urllib.error.URLError("down")

    monkeypatch.setattr(_URLOPEN, _always_fail)
    monkeypatch.setattr(_ENRICH_SLEEP, _no_sleep)
    exporter = HoneycombHttpExporter(ingest_key="k", max_retries=2)
    span = _span(name="a", attrs=[])
    assert exporter.export(spans=(span,), dataset="svc") is False
    assert len(attempts) == 2


def test_http_exporter_treats_5xx_as_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _serverdown(request: urllib.request.Request, *, timeout: float) -> _FakeResponse:
        del request, timeout
        return _FakeResponse(status=503)

    monkeypatch.setattr(_URLOPEN, _serverdown)
    monkeypatch.setattr(_ENRICH_SLEEP, _no_sleep)
    exporter = HoneycombHttpExporter(ingest_key="k", max_retries=1)
    span = _span(name="a", attrs=[])
    assert exporter.export(spans=(span,), dataset="svc") is False
