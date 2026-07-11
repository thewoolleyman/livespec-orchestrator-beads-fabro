"""Tests for the GATE→REPORTER conversion (LIVESPEC_COST_MODE=report).

The user runs on a SUBSCRIPTION (not API billing) and already sets spend
limits at the provider, so the fail-closed dollar gate is the wrong model.
This suite pins the conversion of the dispatcher's spend-COST machinery
from an ENFORCEMENT GATE into a REPORT-ONLY observability signal:

  * `resolve_cost_mode` — the `LIVESPEC_COST_MODE` lever resolving to
    `report` (the DEFAULT) or `enforce` (opt-in for anyone on API billing);
  * `gate_wave(cost_mode="report")` — ALWAYS derives the cost but NEVER
    refuses / applies caps, even when the cost would exceed the old caps
    and even when the cost is unobservable (the two conditions the OLD gate
    refused on);
  * `CostSink.cost_report` — the richer per-dispatch read (per-category
    token sums + the conservative model-resolved flag) the telemetry
    consumes, plus the legacy bare-int migration tolerance;
  * `_dispatcher_cost_report` — the `cost.report` telemetry span (token /
    USD / model-basis fields, scrubbed) + the stderr summary line, with the
    HONEST model-basis labeling when `model` did not flow off the spans;
  * `_cost_gate` (the dispatcher wiring) in report mode — emits the cost
    telemetry + stderr summary and fires NO `spend-cap-breach` alarm.

The `enforce`-mode regression guard (the old fail-closed behavior stays
intact under `LIVESPEC_COST_MODE=enforce`) lives in the existing
`test_dispatcher_cost_wiring` / `test_dispatcher_spend_cap` /
`test_dispatcher_cost_efj_wiring` suites, which now opt into `enforce`.

Hermetic: synthetic outcomes + spans + sinks, temp files, an injected
runner / poster. No real fabro run, CC session, or Honeycomb egress.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost import (
    COST_MODE_ENFORCE,
    COST_MODE_REPORT,
    gate_wave,
    resolve_cost_mode,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_report import (
    build_cost_report_item,
    cost_report_summary_lines,
    emit_cost_report,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_sink import CostReport, CostSink
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
    cost_report_spans_path,
    cost_sink_path,
)
from livespec_orchestrator_beads_fabro.commands._otel_scrub import is_allowed_attr
from livespec_orchestrator_beads_fabro.commands.dispatcher import (
    _cost_gate_after_verdict,  # pyright: ignore[reportPrivateUsage]
)


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _FakeRunner:
    stdout: str = ""
    exit_code: int = 0
    calls: list[dict[str, object]] = field(default_factory=list)

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        self.calls.append({"argv": argv, "cwd": cwd, "timeout_seconds": timeout_seconds})
        return CommandResult(exit_code=self.exit_code, stdout=self.stdout, stderr="")


@dataclass(kw_only=True)
class _RecordingPoster:
    """A `NotifyPoster` that records POSTs — report mode never posts (so this
    body is `pragma: no cover`); the `poster.calls == []` assertions prove it.
    """

    result: bool = True
    calls: list[dict[str, object]] = field(default_factory=list)

    def post(
        self, *, url: str, body: str, title: str, timeout_seconds: float
    ) -> bool:  # pragma: no cover
        self.calls.append(
            {"url": url, "body": body, "title": title, "timeout_seconds": timeout_seconds}
        )
        return self.result


def _green(work_item_id: str) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=work_item_id,
        status="green",
        stage="done",
        pr_number=7,
        merge_sha="abc123",
        detail="merged",
    )


def _attr(
    *, key: str, string_value: str | None = None, int_value: int | None = None
) -> dict[str, object]:
    if int_value is not None:
        return {"key": key, "value": {"intValue": str(int_value)}}
    return {"key": key, "value": {"stringValue": string_value if string_value is not None else ""}}


def _ps_null(*, run_id: str, work_item_id: str) -> str:
    return json.dumps(
        [
            {
                "run_id": run_id,
                "status": {"kind": "succeeded"},
                "goal": f"Work-item: {work_item_id}\nRepo: /x",
                "total_usd_micros": None,
            }
        ]
    )


def _cc_cost_span(
    *,
    work_item_id: str,
    request_id: str,
    span_id: str = "s1",
    model_attr: bool = True,
    input_tokens: int = 1_000_000,
    output_tokens: int = 0,
) -> dict[str, object]:
    """A synthetic CC `llm_request` cost span; `model_attr=False` omits `model`."""
    attrs: list[dict[str, object]] = [
        _attr(key="work.item.id", string_value=work_item_id),
        _attr(key="request_id", string_value=request_id),
        _attr(key="input_tokens", int_value=input_tokens),
        _attr(key="output_tokens", int_value=output_tokens),
    ]
    if model_attr:
        attrs.append(_attr(key="model", string_value="claude-opus-4-8"))
    return {"name": "claude_code.llm_request", "spanId": span_id, "attributes": attrs}


# --------------------------------------------------------------------------
# resolve_cost_mode — the LIVESPEC_COST_MODE lever
# --------------------------------------------------------------------------


def test_resolve_cost_mode_defaults_to_report() -> None:
    """The subscription-friendly default: unset env resolves to `report`."""
    assert resolve_cost_mode(environ={}) == COST_MODE_REPORT


def test_resolve_cost_mode_enforce_is_opt_in() -> None:
    """An explicit `enforce` value opts into the fail-closed gate."""
    assert resolve_cost_mode(environ={"LIVESPEC_COST_MODE": "enforce"}) == COST_MODE_ENFORCE


def test_resolve_cost_mode_unrecognized_falls_back_to_report() -> None:
    """An unrecognized / garbage value resolves to `report` (always wired)."""
    assert resolve_cost_mode(environ={"LIVESPEC_COST_MODE": "garbage"}) == COST_MODE_REPORT
    assert resolve_cost_mode(environ={"LIVESPEC_COST_MODE": ""}) == COST_MODE_REPORT


# --------------------------------------------------------------------------
# gate_wave(cost_mode="report") — never refuses, never caps
# --------------------------------------------------------------------------


def test_report_mode_never_refuses_when_cost_exceeds_old_caps() -> None:
    """Report mode does NOT refuse even when the derived cost blows the caps.

    The OLD enforce gate refused a $30 run over the $25 per-run cap; report
    mode derives the same cost but returns NO refusals and journals a
    non-refusing `report`-severity record.
    """
    journal = _RecordingJournal()
    refusals = gate_wave(
        mode="autonomous",
        outcomes=(_green("item-aaa"),),
        ps_json=_ps_null(run_id="01RUNAAA", work_item_id="item-aaa"),
        journal=journal,
        environ={"LIVESPEC_MAX_RUN_USD": "25", "LIVESPEC_MAX_SESSION_USD": "100"},
        derived_cost_micros_by_work_item={"item-aaa": 30_000_000},  # $30, over the $25 cap
        cost_mode="report",
    )
    assert refusals == ()
    record = next(r for r in journal.records if r.get("stage") == "cost-gate")
    assert record["refuse"] is False
    assert record["severity"] == "report"
    assert record["observable"] is True
    assert record["usd_micros"] == 30_000_000


def test_report_mode_never_refuses_when_unobservable() -> None:
    """Report mode does NOT refuse even when the cost is unobservable.

    The OLD enforce gate fail-closed (autonomous + dark cost → refuse);
    report mode reports the dark condition and returns no refusals.
    """
    journal = _RecordingJournal()
    refusals = gate_wave(
        mode="autonomous",
        outcomes=(_green("item-aaa"),),
        ps_json=_ps_null(run_id="01RUNAAA", work_item_id="item-aaa"),
        journal=journal,
        environ={"LIVESPEC_MAX_RUN_USD": "25", "LIVESPEC_MAX_SESSION_USD": "100"},
        derived_cost_micros_by_work_item={},  # nothing accrued -> unobservable
        cost_mode="report",
    )
    assert refusals == ()
    record = next(r for r in journal.records if r.get("stage") == "cost-gate")
    assert record["refuse"] is False
    assert record["severity"] == "report"
    assert record["observable"] is False


def test_report_mode_is_the_default_cost_mode() -> None:
    """Omitting `cost_mode` defaults to report (never refuses) — the new default."""
    journal = _RecordingJournal()
    refusals = gate_wave(
        mode="autonomous",
        outcomes=(_green("item-aaa"),),
        ps_json=_ps_null(run_id="01RUNAAA", work_item_id="item-aaa"),
        journal=journal,
        environ={"LIVESPEC_MAX_RUN_USD": "25", "LIVESPEC_MAX_SESSION_USD": "100"},
        derived_cost_micros_by_work_item={"item-aaa": 30_000_000},
    )
    assert refusals == ()
    record = next(r for r in journal.records if r.get("stage") == "cost-gate")
    assert record["severity"] == "report"


# --------------------------------------------------------------------------
# CostSink.cost_report — token sums + conservative model-resolved
# --------------------------------------------------------------------------


def test_cost_report_aggregates_token_sums_and_usd(tmp_path: Path) -> None:
    """The report read sums the per-category tokens + the derived micro-USD."""
    sink = CostSink(path=tmp_path / "cost.json")
    sink.accumulate_span(
        span=_cc_cost_span(
            work_item_id="li-x", request_id="req-a", input_tokens=1_000_000, output_tokens=2_000_000
        )
    )
    report = sink.cost_report(key="li-x")
    assert report is not None
    # opus: 1M input == 5_000_000 micro-USD; 2M output == 50_000_000 -> 55_000_000.
    assert report.usd_micros == 55_000_000
    assert report.input_tokens == 1_000_000
    assert report.output_tokens == 2_000_000
    assert report.model_resolved is True


def test_cost_report_model_unresolved_when_a_span_lacks_model(tmp_path: Path) -> None:
    """`model_resolved` is False when ANY contributing span carried no `model`.

    The real CC reality: `claude_code.llm_request` carries no `model`, so the
    cost is priced at the default model and the report must NOT silently
    claim the model was resolved.
    """
    sink = CostSink(path=tmp_path / "cost.json")
    sink.accumulate_span(
        span=_cc_cost_span(work_item_id="li-x", request_id="req-a", model_attr=True)
    )
    sink.accumulate_span(
        span=_cc_cost_span(work_item_id="li-x", request_id="req-b", model_attr=False)
    )
    report = sink.cost_report(key="li-x")
    assert report is not None
    assert report.model_resolved is False


def test_cost_report_none_for_unaccrued_key(tmp_path: Path) -> None:
    """A key that never accrued reads None (the unobservable condition)."""
    sink = CostSink(path=tmp_path / "cost.json")
    assert sink.cost_report(key="li-never") is None


def test_cost_report_reads_legacy_bare_int_format(tmp_path: Path) -> None:
    """A legacy bare-int sink value still reads (usd_micros only, model unresolved).

    The format migration: an older sink file stored `{key: {dedup: micros}}`
    with a plain int; the new reader treats it as a usd_micros-only record
    so `usd_micros` keeps summing and `cost_report` reports zero token sums
    with `model_resolved=False`.
    """
    path = tmp_path / "cost.json"
    _ = path.write_text(json.dumps({"li-x": {"req-a": 5_000_000}}), encoding="utf-8")
    sink = CostSink(path=path)
    assert sink.usd_micros(key="li-x") == 5_000_000
    report = sink.cost_report(key="li-x")
    assert report is not None
    assert report.usd_micros == 5_000_000
    assert report.input_tokens == 0
    assert report.model_resolved is False


def test_cost_report_round_trips_token_record(tmp_path: Path) -> None:
    """The richer record round-trips through the on-disk file (read out of process)."""
    path = tmp_path / "cost.json"
    CostSink(path=path).accumulate_span(
        span=_cc_cost_span(work_item_id="li-x", request_id="req-a", input_tokens=3, output_tokens=4)
    )
    report = CostSink(path=path).cost_report(key="li-x")
    assert report is not None
    assert report.input_tokens == 3
    assert report.output_tokens == 4


# --------------------------------------------------------------------------
# build_cost_report_item — honest model basis
# --------------------------------------------------------------------------


def test_build_item_observable_resolved_model() -> None:
    """An observable report with a resolved model labels the basis as that model."""
    report = CostReport(
        usd_micros=1_250_000,
        input_tokens=100,
        output_tokens=50,
        cache_write_tokens=0,
        cache_read_tokens=0,
        model_resolved=True,
    )
    item = build_cost_report_item(work_item_id="li-x", report=report)
    assert item.observable is True
    assert item.usd_micros == 1_250_000
    assert item.model_basis == "claude-opus-4-8"
    assert item.model_resolved is True


def test_build_item_unresolved_model_labels_default_basis() -> None:
    """An unresolved model labels the basis `default:<model>` (never silent)."""
    report = CostReport(
        usd_micros=1_250_000,
        input_tokens=100,
        output_tokens=50,
        cache_write_tokens=0,
        cache_read_tokens=0,
        model_resolved=False,
    )
    item = build_cost_report_item(work_item_id="li-x", report=report)
    assert item.model_resolved is False
    assert item.model_basis == "default:claude-opus-4-8"


def test_build_item_none_report_is_unobservable() -> None:
    """No accrued report → an UNOBSERVABLE item (reported, never refused)."""
    item = build_cost_report_item(work_item_id="li-x", report=None)
    assert item.observable is False
    assert item.usd_micros is None
    assert item.model_resolved is False


# --------------------------------------------------------------------------
# cost_report_summary_lines — the stderr human summary
# --------------------------------------------------------------------------


def test_summary_line_renders_dollars_tokens_and_basis() -> None:
    """The summary renders the dollars view, per-category tokens, and basis."""
    report = CostReport(
        usd_micros=120_000,
        input_tokens=1000,
        output_tokens=500,
        cache_write_tokens=0,
        cache_read_tokens=0,
        model_resolved=True,
    )
    item = build_cost_report_item(work_item_id="li-x", report=report)
    lines = cost_report_summary_lines(items=(item,))
    assert len(lines) == 1
    line = lines[0]
    assert "cost (API-equiv estimate)" in line
    assert "$0.12" in line
    assert "in 1000 / out 500 / cache-create 0 / cache-read 0 tokens" in line
    assert "basis: claude-opus-4-8" in line


def test_summary_line_flags_default_model_estimate() -> None:
    """An unresolved-model line is tagged a default-model estimate (honesty)."""
    report = CostReport(
        usd_micros=120_000,
        input_tokens=1000,
        output_tokens=0,
        cache_write_tokens=0,
        cache_read_tokens=0,
        model_resolved=False,
    )
    item = build_cost_report_item(work_item_id="li-x", report=report)
    line = cost_report_summary_lines(items=(item,))[0]
    assert "default:claude-opus-4-8" in line
    assert "opus-default estimate" in line


def test_summary_line_reports_unobservable_plainly() -> None:
    """An unobservable item says so plainly (no fabricated number)."""
    item = build_cost_report_item(work_item_id="li-x", report=None)
    line = cost_report_summary_lines(items=(item,))[0]
    assert "unobservable" in line
    assert "report-only" in line


# --------------------------------------------------------------------------
# emit_cost_report — telemetry span emitted + scrubbed
# --------------------------------------------------------------------------


def _spans_from_file(*, spans_path: Path) -> list[dict[str, object]]:
    spans: list[dict[str, object]] = []
    for line in spans_path.read_text(encoding="utf-8").splitlines():
        request: dict[str, object] = json.loads(line)
        for rs in request.get("resourceSpans", []):  # pyright: ignore[reportAttributeAccessIssue]
            for ss in rs.get("scopeSpans", []):
                spans.extend(ss.get("spans", []))
    return spans


def _attrs_of(*, span: dict[str, object]) -> dict[str, object]:
    out: dict[str, object] = {}
    for entry in span.get("attributes", []):  # pyright: ignore[reportAttributeAccessIssue]
        value = entry["value"]
        if "intValue" in value:
            out[entry["key"]] = int(value["intValue"])
        elif "boolValue" in value:
            out[entry["key"]] = bool(value["boolValue"])
        else:
            out[entry["key"]] = value.get("stringValue")
    return out


def test_emit_cost_report_writes_cost_span_with_token_usd_model_fields(tmp_path: Path) -> None:
    """The emitted `cost.report` span carries the token / USD / model-basis fields."""
    report = CostReport(
        usd_micros=5_000_000,
        input_tokens=1_000_000,
        output_tokens=0,
        cache_write_tokens=0,
        cache_read_tokens=0,
        model_resolved=False,
    )
    item = build_cost_report_item(work_item_id="li-x", report=report)
    spans_path = tmp_path / "cost-spans.jsonl"
    emit_cost_report(items=(item,), dispatch_id=None, spans_path=spans_path)
    spans = _spans_from_file(spans_path=spans_path)
    cost_spans = [s for s in spans if s.get("name") == "cost.report"]
    assert len(cost_spans) == 1
    attrs = _attrs_of(span=cost_spans[0])
    assert attrs["work.item.id"] == "li-x"
    assert attrs["livespec.cost.usd_micros"] == 5_000_000
    assert attrs["livespec.cost.input_tokens"] == 1_000_000
    assert attrs["livespec.cost.model_basis"] == "default:claude-opus-4-8"
    assert attrs["livespec.cost.model_resolved"] is False
    # The wave-root span carries the report mode + the running session total.
    wave = next(s for s in spans if s.get("name") == "cost.report.wave")
    wave_attrs = _attrs_of(span=wave)
    assert wave_attrs["livespec.cost.mode"] == "report"
    assert wave_attrs["livespec.cost.session_usd_micros"] == 5_000_000


def test_emit_cost_report_scrubs_through_shared_otel_attr(tmp_path: Path) -> None:
    """Every cost-span attribute is built through the shared `_otel_scrub.attr`.

    A work-item id shaped like a credential-bearing URL is rejected
    WHOLESALE (the shared fail-closed scrub), proving the cost span rides
    the same scrub discipline as every other export rather than a bespoke
    serializer.
    """
    item = build_cost_report_item(
        work_item_id="scheme://user:secret@host",
        report=CostReport(
            usd_micros=1,
            input_tokens=1,
            output_tokens=0,
            cache_write_tokens=0,
            cache_read_tokens=0,
            model_resolved=True,
        ),
    )
    spans_path = tmp_path / "cost-spans.jsonl"
    emit_cost_report(items=(item,), dispatch_id=None, spans_path=spans_path)
    spans = _spans_from_file(spans_path=spans_path)
    cost_span = next(s for s in spans if s.get("name") == "cost.report")
    attrs = _attrs_of(span=cost_span)
    assert attrs["work.item.id"] == "[redacted-credential-shaped-value]"


def test_emit_cost_report_empty_items_is_noop(tmp_path: Path) -> None:
    """No green run carried a cost → no span file written (no-op)."""
    spans_path = tmp_path / "cost-spans.jsonl"
    emit_cost_report(items=(), dispatch_id=None, spans_path=spans_path)
    assert not spans_path.exists()


def test_emit_cost_report_stamps_dispatch_id_on_wave_span(tmp_path: Path) -> None:
    """A supplied dispatch id is stamped on the wave-root span (correlation key)."""
    item = build_cost_report_item(
        work_item_id="li-x",
        report=CostReport(
            usd_micros=1,
            input_tokens=1,
            output_tokens=0,
            cache_write_tokens=0,
            cache_read_tokens=0,
            model_resolved=True,
        ),
    )
    spans_path = tmp_path / "cost-spans.jsonl"
    emit_cost_report(items=(item,), dispatch_id="dispatch-42", spans_path=spans_path)
    spans = _spans_from_file(spans_path=spans_path)
    wave = next(s for s in spans if s.get("name") == "cost.report.wave")
    assert _attrs_of(span=wave)["livespec.dispatch.id"] == "dispatch-42"


def test_cost_span_attribute_keys_are_enrich_allowlisted() -> None:
    """The `livespec.cost.*` span keys are allowlisted so enrich forwards them.

    The enrich stage drops any non-allowlisted attribute; a cost span key
    not in the allowlist would be silently stripped before Honeycomb, so the
    keys the emitter stamps must be allowlisted.
    """
    for key in (
        "livespec.cost.usd_micros",
        "livespec.cost.input_tokens",
        "livespec.cost.output_tokens",
        "livespec.cost.cache_creation_tokens",
        "livespec.cost.cache_read_tokens",
        "livespec.cost.model_basis",
        "livespec.cost.model_resolved",
        "livespec.cost.mode",
        "livespec.cost.session_usd_micros",
    ):
        assert is_allowed_attr(key=key) is True


# --------------------------------------------------------------------------
# _cost_gate (the dispatcher wiring) in report mode
# --------------------------------------------------------------------------


def _args(*, journal_path: Path, mode: str = "autonomous") -> argparse.Namespace:
    return argparse.Namespace(mode=mode, fabro_bin="fabro", journal=str(journal_path))


def test_cost_gate_report_mode_emits_telemetry_and_fires_no_alarm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Report mode (the default): the dispatcher emits the cost-report span +
    stderr summary and fires NO `spend-cap-breach` alarm — even on a cost
    that would have breached the old caps.

    A derived $30 cost (over the old $25 per-run cap) would have refused +
    alarmed under enforce; in report mode the wiring derives + emits it and
    returns quietly.
    """
    monkeypatch.delenv("LIVESPEC_COST_MODE", raising=False)  # default == report
    monkeypatch.setenv("CLAUDE_NTFY_DISPATCHER_TOPIC", "dispatch-alarms")
    journal_path = tmp_path / "journal.jsonl"
    args = _args(journal_path=journal_path)
    sink = CostSink(path=cost_sink_path(args=args, repo=tmp_path))
    sink.accumulate_span(
        span=_cc_cost_span(work_item_id="item-aaa", request_id="req-1", input_tokens=6_000_000)
    )  # $30, over the old $25 per-run cap
    journal = _RecordingJournal()
    runner = _FakeRunner(stdout=_ps_null(run_id="01RUNAAA", work_item_id="item-aaa"), exit_code=0)
    poster = _RecordingPoster()
    _cost_gate_after_verdict(
        args=args,
        repo=tmp_path,
        outcomes=[_green("item-aaa")],
        journal=journal,
        runner=runner,
        poster=poster,
    )
    # No spend-cap-breach alarm fired (report-only).
    assert poster.calls == []
    # The cost-report telemetry span was written to the sibling spans file.
    spans = _spans_from_file(spans_path=cost_report_spans_path(args=args, repo=tmp_path))
    cost_span = next(s for s in spans if s.get("name") == "cost.report")
    attrs = _attrs_of(span=cost_span)
    assert attrs["work.item.id"] == "item-aaa"
    assert attrs["livespec.cost.usd_micros"] == 30_000_000
    # The gate record is a non-refusing report verdict.
    gate = next(r for r in journal.records if r.get("stage") == "cost-gate")
    assert gate["refuse"] is False
    assert gate["severity"] == "report"


def test_cost_gate_report_mode_reports_unobservable_without_refusing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Report mode reports a dark (no-telemetry) run without refusing / alarming."""
    monkeypatch.delenv("LIVESPEC_COST_MODE", raising=False)
    monkeypatch.setenv("CLAUDE_NTFY_DISPATCHER_TOPIC", "dispatch-alarms")
    journal_path = tmp_path / "journal.jsonl"
    args = _args(journal_path=journal_path)
    journal = _RecordingJournal()
    runner = _FakeRunner(stdout=_ps_null(run_id="01RUNAAA", work_item_id="item-aaa"), exit_code=0)
    poster = _RecordingPoster()
    _cost_gate_after_verdict(
        args=args,
        repo=tmp_path,
        outcomes=[_green("item-aaa")],
        journal=journal,
        runner=runner,
        poster=poster,
    )
    assert poster.calls == []
    spans = _spans_from_file(spans_path=cost_report_spans_path(args=args, repo=tmp_path))
    cost_span = next(s for s in spans if s.get("name") == "cost.report")
    attrs = _attrs_of(span=cost_span)
    assert attrs["livespec.cost.observable"] is False
    gate = next(r for r in journal.records if r.get("stage") == "cost-gate")
    assert gate["refuse"] is False


def _failed(work_item_id: str) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=work_item_id,
        status="failed",
        stage="host-only-refused",
        pr_number=None,
        merge_sha=None,
        detail="host-route this item",
    )


def test_cost_gate_report_mode_skips_non_green_outcomes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mixed wave: report mode derives a cost only for the GREEN outcome.

    The non-green (host-only) outcome never launched a run, so it is skipped
    for cost derivation; only the green item gets a `cost.report` span.
    """
    monkeypatch.delenv("LIVESPEC_COST_MODE", raising=False)
    journal_path = tmp_path / "journal.jsonl"
    args = _args(journal_path=journal_path)
    sink = CostSink(path=cost_sink_path(args=args, repo=tmp_path))
    sink.accumulate_span(
        span=_cc_cost_span(work_item_id="item-aaa", request_id="req-1", input_tokens=1_000_000)
    )
    journal = _RecordingJournal()
    runner = _FakeRunner(stdout=_ps_null(run_id="01RUNAAA", work_item_id="item-aaa"), exit_code=0)
    poster = _RecordingPoster()
    _cost_gate_after_verdict(
        args=args,
        repo=tmp_path,
        outcomes=[_failed("item-host"), _green("item-aaa")],
        journal=journal,
        runner=runner,
        poster=poster,
    )
    assert poster.calls == []
    spans = _spans_from_file(spans_path=cost_report_spans_path(args=args, repo=tmp_path))
    cost_spans = [s for s in spans if s.get("name") == "cost.report"]
    # Exactly one cost.report span — for the green item only.
    assert len(cost_spans) == 1
    assert _attrs_of(span=cost_spans[0])["work.item.id"] == "item-aaa"
