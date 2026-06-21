"""Tests for the 29f.6 metrics-heartbeat LivenessProbe (oyg OTEL upgrade).

The watchdog's DEFERRED-PRIMARY liveness signal: a `LivenessProbe` that
reads the metrics-heartbeat (last metric-emit timestamp for the
run/session) written by the 29f.7 `HeartbeatSink` to a journal-sibling
JSON file, feeding the EXISTING `decide_stall`. The wall-clock /
`fabro inspect` backstop oyg already shipped STAYS as the permanent
defense-in-depth layer: if the observability pipeline has an outage, the
watchdog degrades to coarse event-stream detection, NEVER to NO
detection (design §4.4).

Every test is hermetic per the self-machinery hang-guard: synthetic
heartbeat JSON is written to a `tmp_path`, the probe is pointed at it,
and NO real fabro run launches, NO receiver binds, NO network call is
made. `monkeypatch`/`tmp_path` isolate any path/cwd default so no test
pollutes the repo.

Covered:
* `heartbeat_lookup_keys` derives the scrubbed candidate keys (work-item
  id always; the resolved fabro run id when present) — matching how
  `HeartbeatSink.beat` stores them (most-specific first).
* fresh heartbeat -> the probe reports the last-emit epoch (alive signal,
  feeds `decide_stall`).
* a frozen heartbeat across the full window -> `decide_stall` confirms a
  STALL from the probe's samples (the finer 7us.6 detection).
* stale/absent heartbeat -> the layered probe falls through to the
  wall-clock backstop (degrade, never to no detection).
* malformed/missing file -> the probe is fail-safe: it returns no signal
  rather than crashing the watchdog, so the backstop still runs.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_heartbeat_probe import (
    HeartbeatLivenessProbe,
    LayeredLivenessProbe,
    heartbeat_lookup_keys,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import WatchedFabroLauncher
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import (
    LivenessSample,
    StallVerdict,
    decide_stall,
)
from livespec_orchestrator_beads_fabro.commands._otel_receive import HeartbeatSink

# ---------------------------------------------------------------------------
# Shared fakes / helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class _ScriptedProbe:
    """A LivenessProbe returning a scripted epoch (the wall-clock fallback fake)."""

    epoch: float | None

    def sample(self, *, observed_at: float) -> LivenessSample:
        return LivenessSample(last_event_epoch=self.epoch, observed_at=observed_at)


def _sink_with(*, path: Path, beats: dict[str, float]) -> HeartbeatSink:
    sink = HeartbeatSink(path=path)
    for key, at in beats.items():
        sink.beat(key=key, at=at)
    return sink


# ---------------------------------------------------------------------------
# heartbeat_lookup_keys
# ---------------------------------------------------------------------------


def test_lookup_keys_use_work_item_id_when_no_run_id() -> None:
    # Before `fabro ps` resolves a run id, the work-item id is the only
    # always-available key (it is known at plan time).
    keys = heartbeat_lookup_keys(work_item_id="livespec-impl-beads-29f.6", run_id=None)
    assert keys == ("livespec-impl-beads-29f.6",)


def test_lookup_keys_prefer_run_id_then_work_item_id() -> None:
    # Once the fabro run id is known it is the most-specific key
    # (`fabro.run_id` is first in the sink's key preference), but the
    # work-item id stays as a fallback the receiver may have keyed on.
    keys = heartbeat_lookup_keys(work_item_id="oyg-1", run_id="01RUN")
    assert keys == ("01RUN", "oyg-1")


def test_lookup_keys_are_scrubbed_to_match_the_sink() -> None:
    # The sink stores keys AFTER `scrub`, so a credential-shaped id is
    # stored as the redaction marker; the probe must look it up the same
    # way or it would never match.
    keys = heartbeat_lookup_keys(
        work_item_id="https://x-access-token:SECRET@github.com/a/b",
        run_id=None,
    )
    assert keys == ("[redacted-credential-shaped-value]",)


def test_lookup_keys_drop_an_empty_run_id() -> None:
    # An empty run id is not a usable candidate (it can never key a beat);
    # only the work-item id survives.
    keys = heartbeat_lookup_keys(work_item_id="oyg-1", run_id="")
    assert keys == ("oyg-1",)


def test_lookup_keys_dedupe_when_run_id_equals_work_item_id() -> None:
    # If the resolved run id and the work-item id scrub to the same value,
    # the candidate is listed once (no redundant lookup).
    keys = heartbeat_lookup_keys(work_item_id="same-id", run_id="same-id")
    assert keys == ("same-id",)


# ---------------------------------------------------------------------------
# HeartbeatLivenessProbe — fresh / frozen / absent / malformed
# ---------------------------------------------------------------------------


def test_probe_reports_fresh_heartbeat_epoch(tmp_path: Path) -> None:
    # A heartbeat present for the work-item id -> the probe reports that
    # last-emit epoch as the liveness signal.
    path = tmp_path / "j-otel-heartbeat.json"
    sink = _sink_with(path=path, beats={"oyg-1": 1_750_000_500.0})
    probe = HeartbeatLivenessProbe(sink=sink, keys=("oyg-1",))
    sample = probe.sample(observed_at=42.0)
    assert sample == LivenessSample(last_event_epoch=1_750_000_500.0, observed_at=42.0)


def test_probe_takes_the_freshest_across_candidate_keys(tmp_path: Path) -> None:
    # The receiver may have keyed the SAME run under both its fabro run id
    # and its work-item id; the probe takes the MOST RECENT beat across
    # the candidates (liveness is the latest activity, like the wall-clock
    # layer's max-timestamp rule).
    path = tmp_path / "j-otel-heartbeat.json"
    sink = _sink_with(path=path, beats={"01RUN": 1_750_000_100.0, "oyg-1": 1_750_000_900.0})
    probe = HeartbeatLivenessProbe(sink=sink, keys=("01RUN", "oyg-1"))
    assert probe.sample(observed_at=1.0).last_event_epoch == 1_750_000_900.0


def test_probe_is_no_signal_when_key_absent(tmp_path: Path) -> None:
    # A heartbeat file that exists but has never beaten THIS run's key ->
    # no signal (None), which `decide_stall` skips. The layered probe then
    # degrades to the wall-clock backstop, never to no detection.
    path = tmp_path / "j-otel-heartbeat.json"
    sink = _sink_with(path=path, beats={"someone-else": 1_750_000_000.0})
    probe = HeartbeatLivenessProbe(sink=sink, keys=("oyg-1",))
    assert probe.sample(observed_at=7.0).last_event_epoch is None


def test_probe_is_no_signal_when_file_missing(tmp_path: Path) -> None:
    # No heartbeat file at all (the pipeline never wrote one — outage /
    # not-yet-started) -> no signal, fail-safe (no crash).
    path = tmp_path / "does-not-exist-otel-heartbeat.json"
    probe = HeartbeatLivenessProbe(sink=HeartbeatSink(path=path), keys=("oyg-1",))
    assert probe.sample(observed_at=7.0).last_event_epoch is None


def test_probe_is_fail_safe_on_malformed_file(tmp_path: Path) -> None:
    # A corrupt / non-JSON heartbeat file must NOT crash the watchdog: the
    # probe reads it as no signal (the sink's own fail-open read), so the
    # backstop layer still runs. This is the load-bearing degrade-not-die
    # property.
    path = tmp_path / "j-otel-heartbeat.json"
    _ = path.write_text("{ this is not json", encoding="utf-8")
    probe = HeartbeatLivenessProbe(sink=HeartbeatSink(path=path), keys=("oyg-1",))
    assert probe.sample(observed_at=9.0).last_event_epoch is None


def test_frozen_heartbeat_confirms_a_stall_through_decide_stall(tmp_path: Path) -> None:
    # The finer 7us.6 detection: a heartbeat that stops advancing across
    # the full stall window is a confirmed deadlock. The probe samples the
    # SAME frozen epoch repeatedly; `decide_stall` (UNCHANGED policy)
    # confirms STALLED once the observed span reaches the window.
    path = tmp_path / "j-otel-heartbeat.json"
    sink = _sink_with(path=path, beats={"oyg-1": 1_750_000_000.0})
    probe = HeartbeatLivenessProbe(sink=sink, keys=("oyg-1",))
    samples = (
        probe.sample(observed_at=0.0),
        probe.sample(observed_at=900.0),
        probe.sample(observed_at=1500.0),
    )
    assert decide_stall(samples=samples, stall_seconds=1500.0) is StallVerdict.STALLED


def test_advancing_heartbeat_is_continue_through_decide_stall(tmp_path: Path) -> None:
    # A live run: each metric export advances the heartbeat. The probe
    # reports a strictly-greater epoch over the window -> CONTINUE (the
    # run is healthy, finer + earlier than the coarse event stream).
    path = tmp_path / "j-otel-heartbeat.json"
    sink = HeartbeatSink(path=path)
    probe = HeartbeatLivenessProbe(sink=sink, keys=("oyg-1",))
    sink.beat(key="oyg-1", at=1_750_000_000.0)
    first = probe.sample(observed_at=0.0)
    sink.beat(key="oyg-1", at=1_750_000_300.0)
    second = probe.sample(observed_at=2000.0)
    assert decide_stall(samples=(first, second), stall_seconds=1500.0) is StallVerdict.CONTINUE


# ---------------------------------------------------------------------------
# LayeredLivenessProbe — heartbeat PRIMARY, wall-clock FALLBACK
# ---------------------------------------------------------------------------


def test_layered_prefers_the_heartbeat_when_present(tmp_path: Path) -> None:
    # The deferred-PRIMARY signal wins when the heartbeat is present: the
    # finer heartbeat epoch is reported, NOT the coarse fallback.
    path = tmp_path / "j-otel-heartbeat.json"
    sink = _sink_with(path=path, beats={"oyg-1": 1_750_000_500.0})
    primary = HeartbeatLivenessProbe(sink=sink, keys=("oyg-1",))
    fallback = _ScriptedProbe(epoch=111.0)
    layered = LayeredLivenessProbe(primary=primary, fallback=fallback)
    assert layered.sample(observed_at=5.0).last_event_epoch == 1_750_000_500.0


def test_layered_falls_through_to_wall_clock_when_heartbeat_absent(tmp_path: Path) -> None:
    # Pipeline outage / no heartbeat for this run -> the layered probe
    # degrades to the coarse wall-clock backstop, NEVER to no detection.
    path = tmp_path / "j-otel-heartbeat.json"
    sink = _sink_with(path=path, beats={"other": 1_750_000_000.0})
    primary = HeartbeatLivenessProbe(sink=sink, keys=("oyg-1",))
    fallback = _ScriptedProbe(epoch=1_750_000_777.0)
    layered = LayeredLivenessProbe(primary=primary, fallback=fallback)
    sample = layered.sample(observed_at=5.0)
    assert sample.last_event_epoch == 1_750_000_777.0


def test_layered_is_no_signal_only_when_both_layers_are(tmp_path: Path) -> None:
    # Both the heartbeat AND the wall-clock probe are blind (a total
    # observability outage): the layered sample is no-signal, which
    # `decide_stall` treats as "keep waiting" (a probe outage can never
    # kill a healthy run).
    path = tmp_path / "missing-otel-heartbeat.json"
    primary = HeartbeatLivenessProbe(sink=HeartbeatSink(path=path), keys=("oyg-1",))
    fallback = _ScriptedProbe(epoch=None)
    layered = LayeredLivenessProbe(primary=primary, fallback=fallback)
    assert layered.sample(observed_at=5.0).last_event_epoch is None


# ---------------------------------------------------------------------------
# WatchedFabroLauncher wiring: the heartbeat is the PRIMARY signal in the
# running watchdog, with the wall-clock layer as the fallback. Hermetic —
# a scripted CommandRunner + a controllable clock + a synthetic heartbeat
# file; NO real fabro run, NO receiver, NO network.
# ---------------------------------------------------------------------------


_PS_RUNNING = (
    '[{"run_id": "01RUN", "goal": "Work-item: livespec-impl-beads-oyg",'
    ' "status": {"kind": "running"}}]'
)
_HEARTBEAT_WORK_ITEM_ID = "livespec-impl-beads-oyg"


def _watchdog_plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id=_HEARTBEAT_WORK_ITEM_ID,
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
    )


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _ScriptedFabroRunner:
    """Scripts fabro run/ps/events/inspect/rm; `events_jsons` per-poll feed.

    `fabro run` BLOCKS on `run_done` so the foreground watch loop runs;
    `fabro rm` sets `run_done`. The wall-clock event reading is whatever
    `events_jsons` supplies — but with a heartbeat present the launcher's
    PRIMARY layer is the heartbeat file, not these events.
    """

    events_jsons: list[str]
    run_done: threading.Event = field(default_factory=threading.Event)
    rm_calls: list[str] = field(default_factory=list)
    _poll: int = 0

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        _ = (cwd, timeout_seconds)
        verb = argv[1] if len(argv) > 1 else ""
        if verb == "run":
            _ = self.run_done.wait(timeout=10.0)
            return CommandResult(exit_code=0, stdout="    Run: 01RUN\n", stderr="")
        if verb == "ps":
            return CommandResult(exit_code=0, stdout=_PS_RUNNING, stderr="")
        if verb == "events":
            index = min(self._poll, len(self.events_jsons) - 1)
            self._poll += 1
            return CommandResult(exit_code=0, stdout=self.events_jsons[index], stderr="")
        if verb == "inspect":
            return CommandResult(exit_code=0, stdout="{}", stderr="")
        if verb == "rm":
            self.rm_calls.append(argv[-1])
            self.run_done.set()
            return CommandResult(exit_code=0, stdout="", stderr="")
        return CommandResult(exit_code=1, stdout="", stderr=f"unexpected argv {argv}")


def _advancing_clock() -> object:
    """A monotonic clock that jumps 600s per call (3 samples span 1200s)."""
    ticks = iter(float(t) for t in range(0, 6_000_000, 600))
    return lambda: next(ticks)


def test_scripted_runner_rejects_unknown_verb(tmp_path: Path) -> None:
    # Exercise the fake's defensive fallback (the launcher only ever issues
    # run/ps/events/inspect/rm).
    runner = _ScriptedFabroRunner(events_jsons=["[]"])
    out = runner.run(argv=["fabro", "bogus"], cwd=tmp_path, timeout_seconds=1.0)
    assert out.exit_code == 1


def test_launcher_cancels_on_a_frozen_heartbeat_even_when_events_advance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The heartbeat is the PRIMARY signal: even though the coarse
    # `fabro events` stream ADVANCES every poll (which the wall-clock
    # backstop alone would read as healthy), a FROZEN heartbeat for this
    # run confirms the finer 7us.6 stall and the watchdog `fabro rm -f`-es
    # the run. Proves the heartbeat wins over the wall-clock layer.
    monkeypatch.setenv("LIVESPEC_DISPATCH_STALL_SECONDS", "1000")
    heartbeat_path = tmp_path / "j-otel-heartbeat.json"
    _ = _sink_with(path=heartbeat_path, beats={_HEARTBEAT_WORK_ITEM_ID: 1_750_000_000.0})
    advancing = [
        '[{"timestamp": "2026-06-13T08:00:00Z"}]',
        '[{"timestamp": "2026-06-13T08:10:00Z"}]',
        '[{"timestamp": "2026-06-13T08:20:00Z"}]',
    ]
    runner = _ScriptedFabroRunner(events_jsons=advancing)
    journal = _RecordingJournal()
    launcher = WatchedFabroLauncher(
        sleep=lambda _s: None,
        clock=_advancing_clock(),
        heartbeat_path=heartbeat_path,
    )
    result = launcher.launch(plan=_watchdog_plan(repo=tmp_path), runner=runner, journal=journal)
    assert result.stalled_run_id == "01RUN"
    assert runner.rm_calls == ["01RUN"]


def test_launcher_falls_through_to_wall_clock_when_heartbeat_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # No heartbeat for this run (pipeline outage / not-yet-started) but the
    # coarse `fabro events` stream is FROZEN: the layered probe degrades to
    # the wall-clock backstop, which still confirms the stall and cancels.
    # Degrade to coarse detection — never to NO detection.
    monkeypatch.setenv("LIVESPEC_DISPATCH_STALL_SECONDS", "1000")
    heartbeat_path = tmp_path / "j-otel-heartbeat.json"
    _ = _sink_with(path=heartbeat_path, beats={"some-other-run": 1_750_000_000.0})
    frozen = ['[{"timestamp": "2026-06-13T08:00:00Z"}]']
    runner = _ScriptedFabroRunner(events_jsons=frozen)
    journal = _RecordingJournal()
    launcher = WatchedFabroLauncher(
        sleep=lambda _s: None,
        clock=_advancing_clock(),
        heartbeat_path=heartbeat_path,
    )
    result = launcher.launch(plan=_watchdog_plan(repo=tmp_path), runner=runner, journal=journal)
    assert result.stalled_run_id == "01RUN"
    assert runner.rm_calls == ["01RUN"]


def test_launcher_with_fresh_advancing_heartbeat_never_cancels(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A live run whose heartbeat ADVANCES each poll -> the PRIMARY layer
    # reports progress -> the watchdog never stalls even though the same
    # frozen wall-clock events would (the heartbeat is the finer truth).
    monkeypatch.setenv("LIVESPEC_DISPATCH_STALL_SECONDS", "1000")
    heartbeat_path = tmp_path / "j-otel-heartbeat.json"
    sink = HeartbeatSink(path=heartbeat_path)
    sink.beat(key=_HEARTBEAT_WORK_ITEM_ID, at=1_750_000_000.0)
    runner = _ScriptedFabroRunner(events_jsons=['[{"timestamp": "2026-06-13T08:00:00Z"}]'])
    polls = {"n": 0}

    def _advance_heartbeat_then_finish(_seconds: float) -> None:
        # Each poll the live run exports a fresh metric -> the heartbeat
        # advances; after a few polls end the run so launch() returns.
        polls["n"] += 1
        sink.beat(key=_HEARTBEAT_WORK_ITEM_ID, at=1_750_000_000.0 + polls["n"] * 600.0)
        if polls["n"] >= 4:
            runner.run_done.set()

    journal = _RecordingJournal()
    launcher = WatchedFabroLauncher(
        sleep=_advance_heartbeat_then_finish,
        clock=_advancing_clock(),
        heartbeat_path=heartbeat_path,
    )
    result = launcher.launch(plan=_watchdog_plan(repo=tmp_path), runner=runner, journal=journal)
    assert result.stalled_run_id is None
    assert runner.rm_calls == []
