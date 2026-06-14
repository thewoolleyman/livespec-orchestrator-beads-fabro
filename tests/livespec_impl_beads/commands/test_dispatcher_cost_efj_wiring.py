"""Tests for the efj CC-token cost cap-wiring (work-item livespec-impl-beads-efj).

The wiring that LIFTS 5v9's fail-closed refusal: the host OTLP receiver
accrues per-API-call token cost into the cost sink; `gate_wave` routes a
DERIVED cost through the OBSERVED-cost path so the autonomous fail-closed
refusal no longer fires and the (previously dormant) y0m `cap_value`
comparison activates; the dispatcher reads the derived cost from the sink
the receiver wrote. Four seams under test:

  * the `_otel_scrub` allowlist now forwards `model` + `request_id` (the
    efj additions the cost sink reads);
  * `OtelReceiver._handle_traces` accrues each token-bearing span into the
    injected cost sink keyed by `work.item.id`;
  * `gate_wave(derived_cost_micros_by_work_item=...)` — the GATE FLIP: a
    run that WOULD have fail-closed (autonomous, no fabro cost) now
    proceeds when the derived cost is within caps, refuses `critical` when
    over a cap, accumulates per-session across runs, and STILL fail-closes
    when NO telemetry arrived;
  * the dispatcher's `_cost_gate_after_verdict` reads the derived cost
    out of the sink the receiver wrote and flips the gate end-to-end.

Hermetic: synthetic OTLP trace dicts, an in-process receiver on an
ephemeral port, temp sink files, an injected `_FakeRunner` / poster. No
real fabro run, CC session, or Honeycomb egress.
"""

from __future__ import annotations

import argparse
import http.client
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_impl_beads.commands._dispatcher_cost import gate_wave
from livespec_impl_beads.commands._dispatcher_cost_sink import CostSink
from livespec_impl_beads.commands._dispatcher_engine import CommandResult, DispatchOutcome
from livespec_impl_beads.commands._otel_receive import (
    HeartbeatSink,
    OtelReceiver,
    ReceiverConfig,
)
from livespec_impl_beads.commands._otel_scrub import is_allowed_attr
from livespec_impl_beads.commands.dispatcher import (
    _cost_gate_after_verdict,  # pyright: ignore[reportPrivateUsage]
    _cost_sink_path,  # pyright: ignore[reportPrivateUsage]
)


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _FakeExporter:
    succeed: bool = True
    calls: list[tuple[tuple[dict[str, object], ...], str]] = field(default_factory=list)

    def export(self, *, spans: tuple[dict[str, object], ...], dataset: str) -> bool:
        self.calls.append((spans, dataset))
        return self.succeed


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
    result: bool = True
    calls: list[dict[str, object]] = field(default_factory=list)

    def post(self, *, url: str, body: str, title: str, timeout_seconds: float) -> bool:
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


def _ps_null(*, run_id: str, work_item_id: str) -> str:
    """A null-cost `fabro ps` record (the dark fabro reality 5v9 fires on)."""
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


def _attr(
    *, key: str, string_value: str | None = None, int_value: int | None = None
) -> dict[str, object]:
    if int_value is not None:
        return {"key": key, "value": {"intValue": str(int_value)}}
    return {"key": key, "value": {"stringValue": string_value if string_value is not None else ""}}


def _trace_request_with_cost_span(
    *,
    work_item_id: str,
    request_id: str,
    input_tokens: int,
    model: str = "claude-opus-4-8",
) -> dict[str, object]:
    """One OTLP trace request with a single CC `llm_request`-shaped cost span."""
    return {
        "resourceSpans": [
            {
                "resource": {"attributes": [_attr(key="service.name", string_value="cc-sandbox")]},
                "scopeSpans": [
                    {
                        "scope": {"name": "claude-code", "version": "1.0"},
                        "spans": [
                            {
                                "name": "claude_code.llm_request",
                                "traceId": "0af7651916cd43dd8448eb211c80319c",
                                "spanId": "b7ad6b7169203331",
                                "attributes": [
                                    _attr(key="work.item.id", string_value=work_item_id),
                                    _attr(key="request_id", string_value=request_id),
                                    _attr(key="model", string_value=model),
                                    _attr(key="input_tokens", int_value=input_tokens),
                                    _attr(key="output_tokens", int_value=0),
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }


def _post_json(*, host: str, port: int, path: str, body: dict[str, object]) -> int:
    conn = http.client.HTTPConnection(host, port, timeout=5.0)
    try:
        payload = json.dumps(body).encode("utf-8")
        conn.request("POST", path, body=payload, headers={"content-length": str(len(payload))})
        return conn.getresponse().status
    finally:
        conn.close()


# --- the scrub allowlist additions ---------------------------------------


def test_scrub_allowlist_includes_model_and_request_id() -> None:
    """`model` + `request_id` are now allowlisted (the efj scrub additions)."""
    assert is_allowed_attr(key="model") is True
    assert is_allowed_attr(key="request_id") is True


# --- the receiver accrues cost into the sink -----------------------------


def test_receiver_accrues_cost_span_into_sink(tmp_path: Path) -> None:
    """A trace POST carrying a cost span advances the receiver's cost sink.

    Drives the live in-process receiver on an ephemeral port with a
    synthetic CC cost span; the derived micro-USD lands in the sink keyed
    by `work.item.id`, ready for the gate to read out of process.
    """
    cost = CostSink(path=tmp_path / "cost.json")
    receiver = OtelReceiver(
        config=ReceiverConfig(host="127.0.0.1", port=0),
        exporter=_FakeExporter(),
        heartbeat=HeartbeatSink(path=tmp_path / "hb.json"),
        cost=cost,
    )
    receiver.start()
    try:
        status = _post_json(
            host="127.0.0.1",
            port=receiver.bound_port,
            path="/v1/traces",
            body=_trace_request_with_cost_span(
                work_item_id="li-efj", request_id="req-1", input_tokens=1_000_000
            ),
        )
    finally:
        receiver.stop()
    assert status == 200
    # 1M opus input tokens == 5_000_000 micro-USD, keyed by work.item.id.
    assert cost.usd_micros(key="li-efj") == 5_000_000


def test_receiver_with_no_cost_sink_does_not_crash(tmp_path: Path) -> None:
    """A receiver built WITHOUT a cost sink (cost=None) still forwards traces."""
    exporter = _FakeExporter()
    receiver = OtelReceiver(
        config=ReceiverConfig(host="127.0.0.1", port=0),
        exporter=exporter,
        heartbeat=HeartbeatSink(path=tmp_path / "hb.json"),
        cost=None,
    )
    receiver.start()
    try:
        status = _post_json(
            host="127.0.0.1",
            port=receiver.bound_port,
            path="/v1/traces",
            body=_trace_request_with_cost_span(
                work_item_id="li-efj", request_id="req-1", input_tokens=1000
            ),
        )
    finally:
        receiver.stop()
    assert status == 200
    assert len(exporter.calls) == 1


# --- gate_wave: the GATE FLIP --------------------------------------------


def test_gate_flip_derived_cost_lifts_autonomous_fail_closed() -> None:
    """The headline efj flip: an autonomous run that WOULD fail-close (fabro
    cost null) now PROCEEDS when the CC-derived cost is within caps.

    Without a derived cost this exact wave refuses (5v9). With the derived
    cost present, the observed-cost path runs `cap_value_decision`, the cost
    is under the caps, and the run proceeds — the fail-closed refusal lifts.
    """
    journal = _RecordingJournal()
    refusals = gate_wave(
        mode="autonomous",
        outcomes=(_green("item-aaa"),),
        ps_json=_ps_null(run_id="01RUNAAA", work_item_id="item-aaa"),
        journal=journal,
        environ={"LIVESPEC_MAX_RUN_USD": "25", "LIVESPEC_MAX_SESSION_USD": "100"},
        derived_cost_micros_by_work_item={"item-aaa": 5_000_000},  # $5, under caps
    )
    assert refusals == ()
    record = next(r for r in journal.records if r.get("stage") == "cost-gate")
    assert record["observable"] is True
    assert record["usd_micros"] == 5_000_000
    assert record["refuse"] is False
    assert record["severity"] == "info"


def test_gate_flip_derived_cost_over_per_run_cap_refuses() -> None:
    """A derived cost OVER the per-run cap → critical refuse (cap-value live)."""
    journal = _RecordingJournal()
    refusals = gate_wave(
        mode="autonomous",
        outcomes=(_green("item-aaa"),),
        ps_json=_ps_null(run_id="01RUNAAA", work_item_id="item-aaa"),
        journal=journal,
        environ={"LIVESPEC_MAX_RUN_USD": "25", "LIVESPEC_MAX_SESSION_USD": "100"},
        derived_cost_micros_by_work_item={"item-aaa": 30_000_000},  # $30, over $25
    )
    assert refusals == ("item-aaa",)
    record = next(r for r in journal.records if r.get("stage") == "cost-gate")
    assert record["observable"] is True
    assert record["refuse"] is True
    assert record["severity"] == "critical"
    assert "per-run cap" in str(record["reason"])


def test_gate_flip_derived_cost_accumulates_per_session() -> None:
    """Per-session accumulation across runs on the DERIVED cost.

    Two derived costs of $40 each, per-run cap $50 (each within), session
    cap $60: the second run pushes the session total to $80 and refuses.
    """
    journal = _RecordingJournal()
    refusals = gate_wave(
        mode="autonomous",
        outcomes=(_green("item-aaa"), _green("item-bbb")),
        ps_json=json.dumps(
            [
                {
                    "run_id": rid,
                    "status": {"kind": "succeeded"},
                    "goal": f"Work-item: {wid}\nRepo: /x",
                    "total_usd_micros": None,
                }
                for rid, wid in (("01RUNAAA", "item-aaa"), ("01RUNBBB", "item-bbb"))
            ]
        ),
        journal=journal,
        environ={"LIVESPEC_MAX_RUN_USD": "50", "LIVESPEC_MAX_SESSION_USD": "60"},
        derived_cost_micros_by_work_item={
            "item-aaa": 40_000_000,
            "item-bbb": 40_000_000,
        },
    )
    assert refusals == ("item-bbb",)
    gate_records = [r for r in journal.records if r.get("stage") == "cost-gate"]
    assert gate_records[0]["refuse"] is False
    assert gate_records[1]["refuse"] is True
    assert gate_records[1]["session_usd_micros"] == 80_000_000


def test_gate_still_fail_closed_when_no_telemetry_arrived() -> None:
    """No derived cost AND null fabro cost → STILL fail-closed (gate not blinded).

    The genuinely-dark condition: when no CC telemetry arrived for the run
    AND fabro's field is null, the autonomous fail-closed refusal still
    fires — efj makes the COMMON path observable, it does not disable the
    safety net.
    """
    journal = _RecordingJournal()
    refusals = gate_wave(
        mode="autonomous",
        outcomes=(_green("item-aaa"),),
        ps_json=_ps_null(run_id="01RUNAAA", work_item_id="item-aaa"),
        journal=journal,
        environ={"LIVESPEC_MAX_RUN_USD": "25", "LIVESPEC_MAX_SESSION_USD": "100"},
        derived_cost_micros_by_work_item={},  # nothing accrued
    )
    assert refusals == ("item-aaa",)
    record = next(r for r in journal.records if r.get("stage") == "cost-gate")
    assert record["observable"] is False
    assert record["refuse"] is True


# --- the dispatcher reads the derived cost out of the sink ---------------


def _args(*, journal_path: Path, mode: str = "autonomous") -> argparse.Namespace:
    return argparse.Namespace(mode=mode, fabro_bin="fabro", journal=str(journal_path))


def test_cost_gate_after_verdict_reads_derived_cost_and_proceeds(tmp_path: Path) -> None:
    """End-to-end: the dispatcher reads the derived cost the receiver wrote and
    PROCEEDS — the gate flip wired through `_cost_gate_after_verdict`.

    fabro reports null cost (dark), but the cost sink the receiver wrote
    carries a within-cap derived cost for the work item, so the autonomous
    gate proceeds with no `spend-cap-breach` alarm.
    """
    journal_path = tmp_path / "journal.jsonl"
    args = _args(journal_path=journal_path, mode="autonomous")
    # Seed the cost sink the receiver would have written, at the path the
    # dispatcher derives from the journal stem.
    sink = CostSink(path=_cost_sink_path(args=args, repo=tmp_path))
    sink.accumulate_span(
        span={
            "name": "claude_code.llm_request",
            "spanId": "s1",
            "attributes": [
                _attr(key="work.item.id", string_value="item-aaa"),
                _attr(key="request_id", string_value="req-1"),
                _attr(key="model", string_value="claude-opus-4-8"),
                _attr(key="input_tokens", int_value=1_000_000),  # $5, under $25
            ],
        }
    )
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
    gate = next(r for r in journal.records if r.get("stage") == "cost-gate")
    assert gate["observable"] is True
    assert gate["usd_micros"] == 5_000_000
    assert gate["refuse"] is False
    assert poster.calls == []


def test_cost_gate_after_verdict_derived_over_cap_fires_alarm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: a derived cost OVER the per-run cap fires the spend-cap alarm.

    The derived cost ($30) exceeds the $25 per-run cap, so the now-LIVE
    cap-value path refuses and the wiring POSTs a `spend-cap-breach` alarm —
    the dormant y0m path is activated by the CC-derived cost.
    """
    monkeypatch.setenv("CLAUDE_NTFY_DISPATCHER_TOPIC", "dispatch-alarms")
    monkeypatch.setenv("LIVESPEC_MAX_RUN_USD", "25")
    journal_path = tmp_path / "journal.jsonl"
    args = _args(journal_path=journal_path, mode="autonomous")
    sink = CostSink(path=_cost_sink_path(args=args, repo=tmp_path))
    sink.accumulate_span(
        span={
            "name": "claude_code.llm_request",
            "spanId": "s1",
            "attributes": [
                _attr(key="work.item.id", string_value="item-aaa"),
                _attr(key="request_id", string_value="req-1"),
                _attr(key="model", string_value="claude-opus-4-8"),
                _attr(key="input_tokens", int_value=6_000_000),  # $30, over $25
            ],
        }
    )
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
    gate = next(r for r in journal.records if r.get("stage") == "cost-gate")
    assert gate["refuse"] is True
    assert gate["usd_micros"] == 30_000_000
    assert len(poster.calls) == 1
    body = poster.calls[0]["body"]
    assert isinstance(body, str)
    assert "item-aaa" in body
    assert "spend-cap-breach" in body


def _failed(work_item_id: str) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=work_item_id,
        status="failed",
        stage="host-only-refused",
        pr_number=None,
        merge_sha=None,
        detail="host-route this item",
    )


def test_cost_gate_after_verdict_skips_non_green_and_unaccrued(tmp_path: Path) -> None:
    """`_derived_costs` skips a non-green outcome and a green one with no accrual.

    Mixed wave: a non-green (host-only) outcome is skipped for cost
    derivation, and a green outcome whose work item NEVER accrued a cost
    yields no derived value — so the gate falls back to 5v9's fail-closed
    path (autonomous + null fabro cost → refuse), proving the omission is
    fail-closed, not silently free.
    """
    journal_path = tmp_path / "journal.jsonl"
    args = _args(journal_path=journal_path, mode="autonomous")
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
    gate = next(r for r in journal.records if r.get("stage") == "cost-gate")
    # No derived cost for item-aaa -> unobservable -> autonomous fail-closed.
    assert gate["observable"] is False
    assert gate["refuse"] is True


def test_cost_gate_after_verdict_is_fail_open_on_missing_journal_attr() -> None:
    """`_derived_costs` is fail-open: an `args` lacking `.journal` degrades to
    no derived cost (the fail-closed path), never crashing the cost gate.

    The minimal `args` shape some callers use omits `journal`; the
    cost-sink read must swallow the resulting error and fall back rather
    than propagate it.
    """
    args = argparse.Namespace(mode="autonomous", fabro_bin="fabro")  # no `journal`
    journal = _RecordingJournal()
    runner = _FakeRunner(stdout=_ps_null(run_id="01RUNAAA", work_item_id="item-aaa"), exit_code=0)
    poster = _RecordingPoster()
    # Must NOT raise; degrades to the fail-closed unobservable gate.
    _cost_gate_after_verdict(
        args=args,
        repo=Path("/x"),
        outcomes=[_green("item-aaa")],
        journal=journal,
        runner=runner,
        poster=poster,
    )
    gate = next(r for r in journal.records if r.get("stage") == "cost-gate")
    assert gate["observable"] is False
    assert gate["refuse"] is True
