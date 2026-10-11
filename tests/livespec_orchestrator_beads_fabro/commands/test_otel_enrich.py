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
- Expected ingest misses stay fail-open; exporter implementation exceptions
  propagate instead of being hidden by a blanket catch.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands._otel_enrich import (
    CorrelationJoin,
    EnrichStage,
    correlation_keys_from_attrs,
    enrich_span,
    tail_spans,
)
from livespec_orchestrator_beads_fabro.commands._otel_scrub import ATTR_MAX_LEN, REDACTION_MARKER

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


def _event(*, name: str, attrs: list[dict[str, object]]) -> dict[str, object]:
    return {"name": name, "attributes": attrs}


def _attrs_by_key(*, span: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        str(entry["key"]): cast("dict[str, object]", entry["value"])
        for entry in cast("list[dict[str, object]]", span["attributes"])
        if isinstance(entry, dict) and isinstance(entry.get("key"), str)
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


def test_correlation_keys_extracts_fabro_run_id_from_workflow_started_event() -> None:
    span = _span(name="run", attrs=[])
    span["events"] = [
        _event(
            name="Workflow run started",
            attrs=[_attr_entry(key="run_id", string_value="01RUNWORKFLOW")],
        )
    ]

    assert correlation_keys_from_attrs(span=span) == {"fabro.run_id": "01RUNWORKFLOW"}


def test_correlation_keys_extracts_fabro_run_id_from_sandbox_event_id_fallback() -> None:
    span = _span(name="run", attrs=[])
    span["events"] = [
        _event(
            name="Sandbox initialized",
            attrs=[_attr_entry(key="id", string_value="01RUNSANDBOX")],
        )
    ]

    assert correlation_keys_from_attrs(span=span) == {"fabro.run_id": "01RUNSANDBOX"}


def test_correlation_keys_prefers_event_run_id_over_event_id() -> None:
    span = _span(name="run", attrs=[])
    span["events"] = [
        _event(
            name="Sandbox initialized",
            attrs=[_attr_entry(key="id", string_value="01RUNSANDBOX")],
        ),
        _event(
            name="Workflow run started",
            attrs=[_attr_entry(key="run_id", string_value="01RUNWORKFLOW")],
        ),
    ]

    assert correlation_keys_from_attrs(span=span) == {"fabro.run_id": "01RUNWORKFLOW"}


def test_correlation_keys_keep_explicit_fabro_run_id_over_event_value() -> None:
    span = _span(
        name="run",
        attrs=[_attr_entry(key="fabro.run_id", string_value="01RUNEXPLICIT")],
    )
    span["events"] = [
        _event(
            name="Workflow run started",
            attrs=[_attr_entry(key="run_id", string_value="01RUNEVENT")],
        )
    ]

    assert correlation_keys_from_attrs(span=span) == {"fabro.run_id": "01RUNEXPLICIT"}


def test_correlation_keys_ignore_malformed_event_run_id_values() -> None:
    span = _span(name="run", attrs=[])
    span["events"] = [
        "not-a-dict",
        {"name": "Workflow run started", "attributes": "not-a-list"},
        {
            "name": "Workflow run started",
            "attributes": [
                "not-a-dict",
                {"key": "other", "value": {"stringValue": "not-the-run-id"}},
                {"key": "run_id", "value": {"intValue": "9"}},
            ],
        },
        {"name": "Sandbox initialized", "attributes": [{"key": "id", "value": "not-a-dict"}]},
    ]

    assert correlation_keys_from_attrs(span=span) == {}


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


def test_join_backfills_work_item_and_dispatch_ids_from_fabro_run_id() -> None:
    join = CorrelationJoin()
    join.observe(
        keys={"work.item.id": "li-1", "livespec.dispatch.id": "d-1", "fabro.run_id": "r-9"}
    )
    backfilled = join.backfill(keys={"fabro.run_id": "r-9"})
    assert backfilled == {
        "work.item.id": "li-1",
        "livespec.dispatch.id": "d-1",
        "fabro.run_id": "r-9",
    }


def test_join_does_not_clobber_value_the_span_already_carries() -> None:
    join = CorrelationJoin()
    join.observe(
        keys={"work.item.id": "li-1", "livespec.dispatch.id": "d-old", "fabro.run_id": "r-9"}
    )
    backfilled = join.backfill(keys={"livespec.dispatch.id": "d-new", "fabro.run_id": "r-9"})
    assert backfilled["work.item.id"] == "li-1"
    assert backfilled["fabro.run_id"] == "r-9"
    assert backfilled["livespec.dispatch.id"] == "d-new"


def test_join_keeps_existing_work_item_keyed_value_precedence() -> None:
    join = CorrelationJoin()
    join.observe(keys={"work.item.id": "li-1", "fabro.run_id": "r-old"})
    backfilled = join.backfill(keys={"work.item.id": "li-1", "fabro.run_id": "r-new"})
    assert backfilled["fabro.run_id"] == "r-new"


def test_join_leaves_unknown_fabro_run_id_unchanged() -> None:
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


def test_tail_public_api_skips_non_dict_resource_value(tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    line = json.dumps(
        {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": "scalar"},
                            {"key": "service.namespace", "value": {"stringValue": "ns"}},
                        ]
                    },
                    "scopeSpans": [{"spans": [_span(name="a", attrs=[])]}],
                }
            ]
        }
    )
    _write_lines(path=path, lines=[line])
    result = tail_spans(spans_path=path, offset=0)
    assert result.spans[0].resource_attrs == {"service.namespace": "ns"}


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
    # A fabro span carrying only fabro.run_id — backfilled from the dispatcher.
    fabro_span = _span(
        name="fabro.node",
        attrs=[_attr_entry(key="fabro.run_id", string_value="r-9")],
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


def test_forward_once_propagates_unexpected_exporter_error(tmp_path: Path) -> None:
    # Exporters report retry-exhausted delivery by returning False; raising is
    # an unexpected implementation error.
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
    with pytest.raises(RuntimeError, match="honeycomb exploded"):
        stage.forward_once()

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


def test_forward_once_stamps_event_derived_fabro_run_id_under_allowlisted_name(
    tmp_path: Path,
) -> None:
    path = tmp_path / "spans.jsonl"
    span = _span(name="run", attrs=[])
    span["events"] = [
        _event(
            name="Workflow run started",
            attrs=[_attr_entry(key="run_id", string_value="01RUNWORKFLOW")],
        )
    ]
    _write_lines(path=path, lines=[_request_line(service_name="fabro", spans=[span])])
    exporter = _FakeExporter()
    stage = EnrichStage(spans_path=path, exporter=exporter)

    result = stage.forward_once()

    assert result.forwarded == 1
    exported = exporter.calls[0][0][0]
    attrs = _attrs_by_key(span=exported)
    assert attrs["fabro.run_id"] == {"stringValue": "01RUNWORKFLOW"}
    assert "run_id" not in attrs
    assert "id" not in attrs


def test_forward_once_event_derived_run_id_uses_scrub_attr_rules(tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    span = _span(name="run", attrs=[])
    long_run_id = "r" * (ATTR_MAX_LEN + 10)
    span["events"] = [
        _event(
            name="Workflow run started",
            attrs=[_attr_entry(key="run_id", string_value=long_run_id)],
        )
    ]
    _write_lines(path=path, lines=[_request_line(service_name="fabro", spans=[span])])
    exporter = _FakeExporter()

    result = EnrichStage(spans_path=path, exporter=exporter).forward_once()

    assert result.forwarded == 1
    exported = exporter.calls[0][0][0]
    attrs = _attrs_by_key(span=exported)
    assert attrs["fabro.run_id"] == {"stringValue": long_run_id[:ATTR_MAX_LEN]}


def test_forward_once_event_derived_credential_run_id_is_redacted(tmp_path: Path) -> None:
    path = tmp_path / "spans.jsonl"
    span = _span(name="run", attrs=[])
    span["events"] = [
        _event(
            name="Workflow run started",
            attrs=[_attr_entry(key="run_id", string_value="https://u:p@host/run")],
        )
    ]
    _write_lines(path=path, lines=[_request_line(service_name="fabro", spans=[span])])
    exporter = _FakeExporter()

    result = EnrichStage(spans_path=path, exporter=exporter).forward_once()

    assert result.forwarded == 1
    exported = exporter.calls[0][0][0]
    attrs = _attrs_by_key(span=exported)
    assert attrs["fabro.run_id"] == {"stringValue": REDACTION_MARKER}


# --------------------------------------------------------------------------
# Petri-era run-identity join (the `fabro.run_id` span ATTRIBUTE)
# --------------------------------------------------------------------------


def test_forward_once_joins_run_identity_from_the_attribute_and_from_legacy_events(
    tmp_path: Path,
) -> None:
    """Both engine eras' `run_turn` spans reach the reflector under one key set.

    A PETRI-era span carries `fabro.run_id` as a span ATTRIBUTE and emits
    NEITHER `Workflow run started` NOR `Sandbox initialized`; a 0.254-era span
    carries no such attribute and emits only the legacy event. Both are in one
    pass here deliberately — the two halves are each other's control, because a
    join that read only the events would strand the Petri span with no
    work-item id and a join that read only the attribute would strand the 0.254
    one, and each failure looks exactly like a correlation miss at the
    reflector rather than like a missing span.
    """
    path = tmp_path / "spans.jsonl"
    dispatcher_span = _span(
        name="dispatcher.dispatch",
        attrs=[
            _attr_entry(key="work.item.id", string_value="bd-ib-demo"),
            _attr_entry(key="livespec.dispatch.id", string_value="disp-1"),
            _attr_entry(key="fabro.run_id", string_value="01RUNPETRI"),
        ],
    )
    petri_span = _span(
        name="run_turn",
        attrs=[_attr_entry(key="fabro.run_id", string_value="01RUNPETRI")],
    )
    legacy_span = _span(name="run", attrs=[])
    legacy_span["events"] = [
        _event(
            name="Workflow run started",
            attrs=[_attr_entry(key="run_id", string_value="01RUNPETRI")],
        )
    ]
    assert "events" not in petri_span
    _write_lines(
        path=path,
        lines=[
            _request_line(service_name="livespec-dispatcher", spans=[dispatcher_span]),
            _request_line(service_name="fabro", spans=[petri_span, legacy_span]),
        ],
    )
    exporter = _FakeExporter()

    result = EnrichStage(spans_path=path, exporter=exporter).forward_once()

    assert result.forwarded == 3
    exported = {
        str(span["name"]): _attrs_by_key(span=span)
        for spans, _dataset in exporter.calls
        for span in spans
    }
    expected = {
        "fabro.run_id": {"stringValue": "01RUNPETRI"},
        "work.item.id": {"stringValue": "bd-ib-demo"},
        "livespec.dispatch.id": {"stringValue": "disp-1"},
    }
    assert {key: exported["run_turn"][key] for key in expected} == expected
    assert {key: exported["run"][key] for key in expected} == expected
