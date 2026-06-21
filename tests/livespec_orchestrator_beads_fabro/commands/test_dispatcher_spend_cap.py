"""Tests for the live fail-closed spend cap (work-item livespec-impl-beads-y0m).

The third / final piece of the 0jxs operability trio (notification h1p,
watchdog oyg, this spend-cap), a USER-RATIFIED HARD requirement before the
W6 dark-factory cutover (epic livespec-4moata). It builds on 5v9's
cost-observability seam (`_dispatcher_cost`) and h1p's notifier
(`_dispatcher_notify`).

Two layers under test:

  * `cap_value_decision` + `gate_wave(environ=...)` — the per-run +
    per-session USD cap-VALUE comparison (the part 5v9 deferred). When cost
    is OBSERVED, each run's cost is compared to the per-run cap and the
    cumulative session total to the per-session cap; exceeding EITHER is a
    fail-closed `critical` refuse. Within both ⇒ proceed. This path is
    DORMANT in the current fabro version (cost null on every run) but is
    correct + unit-tested here (forward-compat for livespec-impl-beads-efj).
    The fail-closed-when-unobservable behavior 5v9 built STAYS: an
    autonomous-mode null cost still refuses even with caps resolved.

  * `_cost_gate_after_verdict` (the dispatcher wiring) — the post-verdict,
    FAIL-OPEN stage that runs `fabro ps -a --json` once, hands it to
    `gate_wave`, and turns each refusal into a `spend-cap-breach`-class
    `NotifyEvent` through `notify_terminal`. Fail-open is load-bearing: a
    `fabro ps` failure / any exception is journaled as `cost-gate-error`
    and swallowed, never changing the (already-final) verdict.

No test launches a real fabro run: the cost signal is injected as canned
`fabro ps -a --json` text (populated AND null costs), and the dispatcher
seam is exercised with an injected `CommandRunner` + `NotifyPoster`.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost import (
    CostGateDecision,
    cap_value_decision,
    gate_wave,
    usd_micros_to_usd,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)

# Importing the module-private wiring helper directly (the test tier
# verifies the alarm wiring); importing it avoids the SLF001
# attribute-access ban while keeping the name addressable, the same
# pattern test_dispatcher_notify uses for the alarm internals.
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
    """A `CommandRunner` returning a canned `fabro ps -a --json` result.

    Never touches a subprocess — the cost signal is injected text. With
    `raises` set it raises instead, to drive the fail-open supervisor.
    """

    stdout: str = ""
    exit_code: int = 0
    raises: Exception | None = None
    calls: list[dict[str, object]] = field(default_factory=list)

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        self.calls.append({"argv": argv, "cwd": cwd, "timeout_seconds": timeout_seconds})
        if self.raises is not None:
            raise self.raises
        return CommandResult(exit_code=self.exit_code, stdout=self.stdout, stderr="")


@dataclass(kw_only=True)
class _RecordingPoster:
    """A `NotifyPoster` that records every POST and never touches the network."""

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
        detail="merged, post-merge janitor green",
    )


def _host_only_refused(work_item_id: str) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=work_item_id,
        status="failed",
        stage="host-only-refused",
        pr_number=None,
        merge_sha=None,
        detail="host-route this item",
    )


def _ps_json_observed(*, run_id: str, work_item_id: str, usd_micros: int) -> str:
    """One `fabro ps -a --json` record with a POPULATED cost (forward-compat)."""
    return json.dumps(
        [
            {
                "run_id": run_id,
                "status": {"kind": "succeeded"},
                "goal": f"Work-item: {work_item_id}\nRepo: /x",
                "total_usd_micros": usd_micros,
            }
        ]
    )


# A two-run `fabro ps` array, each goal embeds a distinct work-item id, both
# costs POPULATED — the forward-compat shape the cap-value path consumes.
def _ps_json_two_observed(
    *,
    first: tuple[str, str, int],
    second: tuple[str, str, int],
) -> str:
    return json.dumps(
        [
            {
                "run_id": run_id,
                "status": {"kind": "succeeded"},
                "goal": f"Work-item: {work_item_id}\nRepo: /x",
                "total_usd_micros": usd_micros,
            }
            for run_id, work_item_id, usd_micros in (first, second)
        ]
    )


# A null-cost record (the current fabro reality the 5v9 gate fires on).
_PS_JSON_NULL = (
    '[{"run_id": "01RUNNULL", "status": {"kind": "succeeded"}, '
    '"goal": "Work-item: item-aaa\\nRepo: /x", "total_usd_micros": null}]'
)


# --------------------------------------------------------------------------
# usd_micros_to_usd — the unit boundary
# --------------------------------------------------------------------------


def test_usd_micros_to_usd_converts_millionths() -> None:
    assert usd_micros_to_usd(usd_micros=1_250_000) == 1.25
    assert usd_micros_to_usd(usd_micros=0) == 0.0


# --------------------------------------------------------------------------
# cap_value_decision — the per-run + per-session cap-VALUE gate
# --------------------------------------------------------------------------


def test_cap_value_refuses_when_per_run_cost_exceeds_cap() -> None:
    """Fail-closed: a single run over the per-run cap → critical refuse."""
    decision = cap_value_decision(
        run_id="01RUNAAA",
        usd_micros=30_000_000,  # $30
        per_run_cap_usd=25.0,
        session_usd_micros_after=30_000_000,
        per_session_cap_usd=100.0,
    )
    assert decision == CostGateDecision(
        refuse=True,
        severity="critical",
        reason=decision.reason,
    )
    assert "per-run cap" in decision.reason
    assert "01RUNAAA" in decision.reason


def test_cap_value_refuses_when_session_total_exceeds_cap() -> None:
    """Fail-closed: the cumulative session total over the per-session cap → refuse.

    The single run is UNDER the per-run cap, but it pushes the running
    session total past the per-session ceiling — the per-session breach
    must refuse too.
    """
    decision = cap_value_decision(
        run_id="01RUNBBB",
        usd_micros=10_000_000,  # $10, under the $25 per-run cap
        per_run_cap_usd=25.0,
        session_usd_micros_after=105_000_000,  # $105 cumulative, over $100
        per_session_cap_usd=100.0,
    )
    assert decision.refuse is True
    assert decision.severity == "critical"
    assert "per-session cap" in decision.reason


def test_cap_value_proceeds_when_within_both_caps() -> None:
    """Within both ceilings → info, the loop proceeds (no refusal)."""
    decision = cap_value_decision(
        run_id="01RUNCCC",
        usd_micros=1_250_000,  # $1.25
        per_run_cap_usd=25.0,
        session_usd_micros_after=5_000_000,  # $5 cumulative
        per_session_cap_usd=100.0,
    )
    assert decision.refuse is False
    assert decision.severity == "info"


# --------------------------------------------------------------------------
# gate_wave(environ=...) — observed-cost cap comparison + session accumulation
# --------------------------------------------------------------------------


def test_gate_wave_refuses_observed_run_over_per_run_cap() -> None:
    """An observed cost over the per-run cap → a refusal + a cost-gate record."""
    journal = _RecordingJournal()
    refusals = gate_wave(
        mode="autonomous",
        outcomes=(_green("item-aaa"),),
        ps_json=_ps_json_observed(
            run_id="01RUNAAA", work_item_id="item-aaa", usd_micros=30_000_000
        ),
        journal=journal,
        environ={"LIVESPEC_MAX_RUN_USD": "25", "LIVESPEC_MAX_SESSION_USD": "100"},
        cost_mode="enforce",
    )
    assert refusals == ("item-aaa",)
    record = next(r for r in journal.records if r.get("stage") == "cost-gate")
    assert record["observable"] is True
    assert record["usd_micros"] == 30_000_000
    assert record["refuse"] is True
    assert record["severity"] == "critical"


def test_gate_wave_proceeds_observed_run_under_caps() -> None:
    """An observed cost under both caps → no refusal, an info cost-gate record."""
    journal = _RecordingJournal()
    refusals = gate_wave(
        mode="autonomous",
        outcomes=(_green("item-aaa"),),
        ps_json=_ps_json_observed(run_id="01RUNAAA", work_item_id="item-aaa", usd_micros=1_250_000),
        journal=journal,
        environ={"LIVESPEC_MAX_RUN_USD": "25", "LIVESPEC_MAX_SESSION_USD": "100"},
        cost_mode="enforce",
    )
    assert refusals == ()
    record = next(r for r in journal.records if r.get("stage") == "cost-gate")
    assert record["observable"] is True
    assert record["refuse"] is False
    assert record["severity"] == "info"


def test_gate_wave_accumulates_per_session_cost_across_runs() -> None:
    """Per-session cap: two runs each under the per-run cap but together over
    the session cap → the SECOND run refuses on the cumulative total.

    Each run costs $40 (under a $50 per-run cap) but the session cap is $60,
    so the running total crosses it on the second run. Proves the loop's
    per-session cumulative spend is tracked across the wave, not just
    per-run.
    """
    journal = _RecordingJournal()
    refusals = gate_wave(
        mode="autonomous",
        outcomes=(_green("item-aaa"), _green("item-bbb")),
        ps_json=_ps_json_two_observed(
            first=("01RUNAAA", "item-aaa", 40_000_000),
            second=("01RUNBBB", "item-bbb", 40_000_000),
        ),
        journal=journal,
        environ={"LIVESPEC_MAX_RUN_USD": "50", "LIVESPEC_MAX_SESSION_USD": "60"},
        cost_mode="enforce",
    )
    # The first run ($40) is within both caps; the second pushes the
    # session total to $80, over the $60 session cap → it alone refuses.
    assert refusals == ("item-bbb",)
    gate_records = [r for r in journal.records if r.get("stage") == "cost-gate"]
    assert gate_records[0]["refuse"] is False
    assert gate_records[0]["session_usd_micros"] == 40_000_000
    assert gate_records[1]["refuse"] is True
    assert gate_records[1]["session_usd_micros"] == 80_000_000


def test_gate_wave_still_refuses_unobservable_in_autonomous_with_caps() -> None:
    """The 5v9 fail-closed-when-unobservable behavior STAYS under y0m's caps.

    Caps are resolved (environ supplied), but the cost is null, so the
    unobservable gate fires: autonomous mode refuses cost-blind, exactly as
    5v9 built it — the cap-value layer only governs OBSERVED costs.
    """
    journal = _RecordingJournal()
    refusals = gate_wave(
        mode="autonomous",
        outcomes=(_green("item-aaa"),),
        ps_json=_PS_JSON_NULL,
        journal=journal,
        environ={"LIVESPEC_MAX_RUN_USD": "25", "LIVESPEC_MAX_SESSION_USD": "100"},
        cost_mode="enforce",
    )
    assert refusals == ("item-aaa",)
    record = next(r for r in journal.records if r.get("stage") == "cost-gate")
    assert record["observable"] is False
    assert record["refuse"] is True
    assert "unobservable" in str(record["reason"]).lower()


# --------------------------------------------------------------------------
# _cost_gate_after_verdict — the dispatcher wiring (fail-closed + fail-open)
# --------------------------------------------------------------------------


def _args(*, mode: str = "autonomous", fabro_bin: str = "fabro") -> argparse.Namespace:
    return argparse.Namespace(mode=mode, fabro_bin=fabro_bin)


def test_cost_gate_after_verdict_no_green_outcome_runs_no_probe() -> None:
    """No launched run in the wave → no `fabro ps` probe, nothing journaled.

    A host-only refusal never reached a fabro run, so there is no cost to
    gate and the probe is skipped entirely.
    """
    journal = _RecordingJournal()
    runner = _FakeRunner()
    poster = _RecordingPoster()
    _cost_gate_after_verdict(
        args=_args(),
        repo=Path("/x"),
        outcomes=[_host_only_refused("item-bbb")],
        journal=journal,
        runner=runner,
        poster=poster,
    )
    assert runner.calls == []
    assert journal.records == []
    assert poster.calls == []


def test_cost_gate_after_verdict_refusal_fires_spend_cap_breach_alarm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail-CLOSED end-to-end: autonomous + unobservable cost → a refusal that
    POSTs a `spend-cap-breach`-class alarm through the notifier seam.

    The injected `fabro ps` returns the null-cost (dark) shape, so the
    autonomous-mode unobservable gate refuses, and the wiring turns the
    refusal into a `spend-cap-breach` `NotifyEvent`. With a dispatcher topic
    set, the leak-free body carries the item id + the class + a run id only.
    (Opt into `enforce`, since the `report` default never refuses.)
    """
    monkeypatch.setenv("LIVESPEC_COST_MODE", "enforce")
    monkeypatch.setenv("CLAUDE_NTFY_DISPATCHER_TOPIC", "dispatch-alarms")
    journal = _RecordingJournal()
    runner = _FakeRunner(stdout=_PS_JSON_NULL, exit_code=0)
    poster = _RecordingPoster()
    _cost_gate_after_verdict(
        args=_args(mode="autonomous"),
        repo=Path("/x"),
        outcomes=[_green("item-aaa")],
        journal=journal,
        runner=runner,
        poster=poster,
    )
    # The probe ran exactly once with the `fabro ps -a --json` argv.
    assert len(runner.calls) == 1
    assert runner.calls[0]["argv"] == ["fabro", "ps", "-a", "--json"]
    # The refusal was journaled as a critical cost-gate refuse.
    gate = next(r for r in journal.records if r.get("stage") == "cost-gate")
    assert gate["refuse"] is True
    # The spend-cap-breach alarm POSTed a leak-free body.
    assert len(poster.calls) == 1
    body = poster.calls[0]["body"]
    assert isinstance(body, str)
    assert "item-aaa" in body
    assert "spend-cap-breach" in body
    assert "notify-sent" in [r.get("stage") for r in journal.records]


def test_cost_gate_after_verdict_is_fail_open_on_runner_exception() -> None:
    """The 0jxs load-bearing invariant: a cost-gate error NEVER changes the
    verdict. A `fabro ps` runner that raises is caught, journaled as
    `cost-gate-error`, and swallowed — no exception escapes, no alarm fires.

    The verdict / exit code is already computed by the caller before this
    stage; this proves the stage cannot crash the dispatcher or flip it.
    """
    journal = _RecordingJournal()
    runner = _FakeRunner(raises=RuntimeError("fabro ps blew up"))
    poster = _RecordingPoster()
    # Must NOT raise.
    _cost_gate_after_verdict(
        args=_args(),
        repo=Path("/x"),
        outcomes=[_green("item-aaa")],
        journal=journal,
        runner=runner,
        poster=poster,
    )
    stages = [r.get("stage") for r in journal.records]
    assert stages == ["cost-gate-error"]
    assert poster.calls == []


def test_cost_gate_after_verdict_observed_under_caps_fires_no_alarm() -> None:
    """A green wave whose observed cost is within both caps → no refusal, no
    alarm: the wiring journals an `info` cost-gate and returns quietly.

    This is the forward-compat happy path (dormant until fabro reports
    cost): the gate ran, the cost was within the committed ceilings, so the
    loop proceeds with no `spend-cap-breach` alarm.
    """
    journal = _RecordingJournal()
    runner = _FakeRunner(
        stdout=_ps_json_observed(run_id="01RUNAAA", work_item_id="item-aaa", usd_micros=1_250_000),
        exit_code=0,
    )
    poster = _RecordingPoster()
    _cost_gate_after_verdict(
        args=_args(mode="autonomous"),
        repo=Path("/x"),
        outcomes=[_green("item-aaa")],
        journal=journal,
        runner=runner,
        poster=poster,
    )
    gate = next(r for r in journal.records if r.get("stage") == "cost-gate")
    assert gate["refuse"] is False
    assert gate["observable"] is True
    assert poster.calls == []


def test_cost_gate_after_verdict_treats_nonzero_ps_exit_as_no_signal() -> None:
    """A non-zero `fabro ps` exit yields empty cost text → the run id cannot be
    resolved → `cost-gate-skipped`, no refusal, no alarm (fail-open).

    A failed probe is "no signal", not a refusal: the verdict is already
    final, so an unresolvable run is journaled and skipped rather than
    crashing or spuriously refusing.
    """
    journal = _RecordingJournal()
    runner = _FakeRunner(stdout="", exit_code=1)
    poster = _RecordingPoster()
    _cost_gate_after_verdict(
        args=_args(mode="autonomous"),
        repo=Path("/x"),
        outcomes=[_green("item-aaa")],
        journal=journal,
        runner=runner,
        poster=poster,
    )
    stages = [r.get("stage") for r in journal.records]
    assert "cost-gate-skipped" in stages
    assert "cost-gate" not in stages
    assert poster.calls == []
