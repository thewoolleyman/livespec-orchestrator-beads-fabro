"""Tests for the coarse wall-clock progress watchdog (livespec-impl-beads-oyg).

The watchdog is the host-side backstop for the 7us.6 silent-deadlock
class: a fabro run wedged in `status=running` emitting ZERO events for
152 minutes that no Fabro-internal machinery cancelled. These tests cover
the PURE decision + parsing layer (`_dispatcher_watchdog`) and the
ENGINE integration (`run_dispatch` short-circuits to a distinct
`stalled-no-progress` outcome when an injected launcher reports a stall).

Every test is hermetic: it injects a fake clock / event-stream / launcher
and NEVER launches a real fabro run, per the self-machinery hang-guard.

The load-bearing fail-safety property — a probe FAILURE ("no signal") is
NOT a stall, so a flaky probe can never kill a healthy run — is proven by
`test_probe_failure_is_not_a_stall` and the no-signal `decide_stall`
cases.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_impl_beads.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
    DispatchOutcome,
    FabroRunResult,
    JournalWriter,
    PollPolicy,
    run_dispatch,
)
from livespec_impl_beads.commands._dispatcher_io import WatchedFabroLauncher
from livespec_impl_beads.commands._dispatcher_plan import (
    DispatchPlan,
    build_plan,
    parse_running_run_id,
)
from livespec_impl_beads.commands._dispatcher_watchdog import (
    DEFAULT_STALL_SECONDS,
    STALL_SECONDS_ENV_VAR,
    LivenessSample,
    StallVerdict,
    decide_stall,
    parse_last_event_epoch,
    resolve_stall_seconds,
)

# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------


def _plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id="livespec-impl-beads-oyg",
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
class _RecordingRunner:
    """A CommandRunner that records calls; the stall path never invokes it."""

    calls: list[list[str]] = field(default_factory=list)

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        _ = (cwd, timeout_seconds)
        self.calls.append(argv)
        return CommandResult(exit_code=0, stdout="", stderr="")


@dataclass(kw_only=True)
class _FakeLauncher:
    """A FabroLauncher returning a scripted FabroRunResult (no real run)."""

    result: FabroRunResult

    def launch(
        self,
        *,
        plan: DispatchPlan,
        runner: CommandRunner,
        journal: JournalWriter,
    ) -> FabroRunResult:
        _ = (plan, runner, journal)
        return self.result


# ---------------------------------------------------------------------------
# resolve_stall_seconds
# ---------------------------------------------------------------------------


def test_resolve_stall_seconds_defaults_when_unset() -> None:
    assert resolve_stall_seconds(environ={}) == DEFAULT_STALL_SECONDS


def test_resolve_stall_seconds_reads_env_override() -> None:
    assert resolve_stall_seconds(environ={STALL_SECONDS_ENV_VAR: "600"}) == 600.0


def test_resolve_stall_seconds_falls_back_on_garbage_or_nonpositive() -> None:
    # A misconfigured window must never DISABLE the backstop or set a
    # zero/negative window that fires instantly.
    assert resolve_stall_seconds(environ={STALL_SECONDS_ENV_VAR: "nope"}) == DEFAULT_STALL_SECONDS
    assert resolve_stall_seconds(environ={STALL_SECONDS_ENV_VAR: "0"}) == DEFAULT_STALL_SECONDS
    assert resolve_stall_seconds(environ={STALL_SECONDS_ENV_VAR: "-5"}) == DEFAULT_STALL_SECONDS
    assert resolve_stall_seconds(environ={STALL_SECONDS_ENV_VAR: ""}) == DEFAULT_STALL_SECONDS


# ---------------------------------------------------------------------------
# parse_last_event_epoch
# ---------------------------------------------------------------------------


def test_parse_last_event_epoch_takes_max_timestamp_across_events() -> None:
    events = (
        '[{"timestamp": "2026-06-13T08:00:00Z"},'
        ' {"timestamp": "2026-06-13T08:05:00Z"},'
        ' {"timestamp": "2026-06-13T08:02:00Z"}]'
    )
    epoch = parse_last_event_epoch(events_json=events)
    assert epoch is not None
    # 08:05:00Z is the max; compare against the same parse of that instant.
    latest = parse_last_event_epoch(events_json='[{"timestamp": "2026-06-13T08:05:00Z"}]')
    assert epoch == latest


def test_parse_last_event_epoch_accepts_envelope_and_numeric_and_alt_keys() -> None:
    enveloped = parse_last_event_epoch(events_json='{"events": [{"ts": "2026-06-13T08:00:00Z"}]}')
    assert enveloped is not None
    numeric = parse_last_event_epoch(events_json='[{"at": 1750000000}]')
    assert numeric == 1750000000.0


def test_parse_last_event_epoch_falls_back_to_inspect_updated_at() -> None:
    # Empty/unparseable events but inspect still reports a fresh update.
    epoch = parse_last_event_epoch(
        events_json="[]",
        inspect_json='{"updated_at": "2026-06-13T09:00:00Z"}',
    )
    assert epoch is not None


def test_parse_last_event_epoch_returns_none_on_no_signal() -> None:
    # A transient probe error / empty shapes land here — the fail-safe
    # "no signal" result the caller must NOT treat as a stall.
    assert parse_last_event_epoch(events_json="not json", inspect_json="") is None
    assert parse_last_event_epoch(events_json="[]", inspect_json="{}") is None
    assert parse_last_event_epoch(events_json='[{"noskey": 1}]', inspect_json="garbage") is None


def test_parse_last_event_epoch_skips_unusable_event_shapes() -> None:
    # Non-dict events, dict events with no timestamp keys, and an
    # unparseable timestamp string are all skipped; a later numeric `ts`
    # still resolves.
    events = '["not-a-dict", {"other": 1}, {"timestamp": "garbage"}, {"ts": 1750000123}]'
    assert parse_last_event_epoch(events_json=events) == 1750000123.0


def test_parse_last_event_epoch_envelope_with_non_list_events_is_no_signal() -> None:
    # `{"events": <not a list>}` -> no usable events -> falls through.
    assert parse_last_event_epoch(events_json='{"events": "nope"}', inspect_json="{}") is None


def test_parse_last_event_epoch_top_level_scalar_is_no_signal() -> None:
    # A bare JSON scalar (neither array nor object) -> no usable events.
    assert parse_last_event_epoch(events_json="42", inspect_json="{}") is None
    assert parse_last_event_epoch(events_json='"a string"', inspect_json="{}") is None


def test_parse_last_event_epoch_inspect_numeric_updated_at() -> None:
    assert parse_last_event_epoch(events_json="[]", inspect_json='{"updated_at": 1750000200}') == (
        1750000200.0
    )


def test_parse_last_event_epoch_inspect_non_timestamp_updated_at_is_no_signal() -> None:
    # A boolean (which is an int subclass) and a non-scalar updated_at are
    # both rejected -> no signal.
    assert parse_last_event_epoch(events_json="[]", inspect_json='{"updated_at": true}') is None
    assert parse_last_event_epoch(events_json="[]", inspect_json='{"updated_at": [1]}') is None
    assert parse_last_event_epoch(events_json="[]", inspect_json="[1, 2, 3]") is None


def test_parse_last_event_epoch_handles_naive_and_offset_timestamps() -> None:
    # A naive timestamp is treated as UTC; an explicit +00:00 offset
    # parses to the same instant as the trailing-Z form.
    naive = parse_last_event_epoch(events_json='[{"timestamp": "2026-06-13T08:00:00"}]')
    zulu = parse_last_event_epoch(events_json='[{"timestamp": "2026-06-13T08:00:00Z"}]')
    offset = parse_last_event_epoch(events_json='[{"timestamp": "2026-06-13T08:00:00+00:00"}]')
    assert naive == zulu == offset


# ---------------------------------------------------------------------------
# parse_running_run_id (fabro ps -a --json)
# ---------------------------------------------------------------------------


def test_parse_running_run_id_matches_running_run_for_work_item() -> None:
    ps = (
        '[{"run_id": "01OTHER", "goal": "Work-item: other-1", "status": {"kind": "running"}},'
        ' {"run_id": "01MINE", "goal": "Work-item: oyg-1 ...", "status": {"kind": "running"}}]'
    )
    assert parse_running_run_id(ps_json=ps, work_item_id="oyg-1") == "01MINE"


def test_parse_running_run_id_skips_non_running_and_wrong_item() -> None:
    # succeeded run for my item -> not it; running run for another item -> not it.
    ps = (
        '[{"run_id": "01DONE", "goal": "Work-item: oyg-1", "status": {"kind": "succeeded"}},'
        ' {"run_id": "01OTHER", "goal": "Work-item: zzz", "status": "running"}]'
    )
    assert parse_running_run_id(ps_json=ps, work_item_id="oyg-1") is None


def test_parse_running_run_id_accepts_envelope_and_plain_string_status() -> None:
    ps = '{"runs": [{"run_id": "01ENV", "goal": "Work-item: oyg-1", "status": "running"}]}'
    assert parse_running_run_id(ps_json=ps, work_item_id="oyg-1") == "01ENV"


def test_parse_running_run_id_returns_none_on_malformed() -> None:
    assert parse_running_run_id(ps_json="not json", work_item_id="oyg-1") is None
    assert parse_running_run_id(ps_json="[]", work_item_id="oyg-1") is None
    assert parse_running_run_id(ps_json='[{"no": "fields"}]', work_item_id="oyg-1") is None


def test_parse_running_run_id_handles_unusable_top_level_and_entries() -> None:
    # Top-level scalar and a dict without a `runs` list -> empty run set.
    assert parse_running_run_id(ps_json="42", work_item_id="oyg-1") is None
    assert parse_running_run_id(ps_json='{"runs": "nope"}', work_item_id="oyg-1") is None
    # A non-dict entry in the list is skipped.
    assert parse_running_run_id(ps_json='["not-a-dict"]', work_item_id="oyg-1") is None


def test_parse_running_run_id_skips_unusable_status_shapes() -> None:
    # A numeric status (neither string nor `{"kind": ...}`) and a status
    # dict with no string `kind` are both treated as not-running.
    numeric_status = '[{"run_id": "01N", "goal": "Work-item: oyg-1", "status": 7}]'
    no_kind = '[{"run_id": "01K", "goal": "Work-item: oyg-1", "status": {"phase": "x"}}]'
    assert parse_running_run_id(ps_json=numeric_status, work_item_id="oyg-1") is None
    assert parse_running_run_id(ps_json=no_kind, work_item_id="oyg-1") is None


def test_parse_running_run_id_requires_a_nonempty_run_id() -> None:
    # A running, matching run with a missing/empty run_id -> no usable id.
    missing = '[{"goal": "Work-item: oyg-1", "status": "running"}]'
    empty = '[{"run_id": "", "goal": "Work-item: oyg-1", "status": "running"}]'
    assert parse_running_run_id(ps_json=missing, work_item_id="oyg-1") is None
    assert parse_running_run_id(ps_json=empty, work_item_id="oyg-1") is None


# ---------------------------------------------------------------------------
# decide_stall — the load-bearing fail-safety matrix
# ---------------------------------------------------------------------------


def _sample(*, epoch: float | None, observed_at: float) -> LivenessSample:
    return LivenessSample(last_event_epoch=epoch, observed_at=observed_at)


def test_decide_stall_continues_when_progress_is_made() -> None:
    # The event timestamp advanced across the window -> healthy -> CONTINUE.
    samples = (
        _sample(epoch=100.0, observed_at=0.0),
        _sample(epoch=200.0, observed_at=2000.0),
    )
    assert decide_stall(samples=samples, stall_seconds=1500.0) is StallVerdict.CONTINUE


def test_decide_stall_confirms_stall_on_full_window_of_frozen_timestamp() -> None:
    # Same last-event timestamp across a span >= the window -> STALLED.
    samples = (
        _sample(epoch=100.0, observed_at=0.0),
        _sample(epoch=100.0, observed_at=900.0),
        _sample(epoch=100.0, observed_at=1500.0),
    )
    assert decide_stall(samples=samples, stall_seconds=1500.0) is StallVerdict.STALLED


def test_decide_stall_waits_when_frozen_but_window_not_yet_elapsed() -> None:
    # Frozen timestamp but the observed span is still under the window.
    samples = (
        _sample(epoch=100.0, observed_at=0.0),
        _sample(epoch=100.0, observed_at=600.0),
    )
    assert decide_stall(samples=samples, stall_seconds=1500.0) is StallVerdict.CONTINUE


def test_decide_stall_never_stalls_with_no_timestamped_signal() -> None:
    # PROBE-FAILURE != STALL (load-bearing): every sample is "no signal"
    # spanning far more than the window -> still CONTINUE. A flaky /
    # unreachable probe can never kill a healthy run.
    samples = tuple(_sample(epoch=None, observed_at=float(t)) for t in (0, 500, 1000, 2000, 9000))
    assert decide_stall(samples=samples, stall_seconds=1500.0) is StallVerdict.CONTINUE


def test_decide_stall_skips_intermittent_probe_failures_between_progress() -> None:
    # Real timestamps that ADVANCE, with no-signal probe failures
    # interleaved: the no-signal samples are skipped, the real ones show
    # progress -> CONTINUE (a probe-failure burst cannot manufacture a
    # false stall on a run that is actually emitting events).
    samples = (
        _sample(epoch=100.0, observed_at=0.0),
        _sample(epoch=None, observed_at=600.0),
        _sample(epoch=None, observed_at=1200.0),
        _sample(epoch=250.0, observed_at=2000.0),
    )
    assert decide_stall(samples=samples, stall_seconds=1500.0) is StallVerdict.CONTINUE


def test_decide_stall_single_reading_is_inconclusive() -> None:
    samples = (_sample(epoch=100.0, observed_at=0.0),)
    assert decide_stall(samples=samples, stall_seconds=1500.0) is StallVerdict.CONTINUE


# ---------------------------------------------------------------------------
# Engine integration: a launcher-reported stall -> stalled-no-progress
# ---------------------------------------------------------------------------


def _dispatch_with_launcher(
    *,
    repo: Path,
    result: FabroRunResult,
) -> tuple[DispatchOutcome, _RecordingJournal, _RecordingRunner]:
    journal = _RecordingJournal()
    runner = _RecordingRunner()
    outcome = run_dispatch(
        plan=_plan(repo=repo),
        runner=runner,
        journal=journal,
        sleep=lambda _seconds: None,
        poll=PollPolicy(attempts=3, interval_seconds=0.5),
        fabro_launcher=_FakeLauncher(result=result),
    )
    return outcome, journal, runner


def test_recording_runner_returns_for_a_direct_call(tmp_path: Path) -> None:
    # Exercise the shared fake runner's body directly (the dispatch tests
    # below assert it is NEVER called on the short-circuit paths).
    runner = _RecordingRunner()
    out = runner.run(argv=["x"], cwd=tmp_path, timeout_seconds=1.0)
    assert (out.exit_code, runner.calls) == (0, [["x"]])


def test_run_dispatch_reports_stalled_no_progress_and_skips_pr_flow(tmp_path: Path) -> None:
    result = FabroRunResult(
        command=CommandResult(exit_code=124, stdout="", stderr="cancelled by stall watchdog"),
        stalled_run_id="01RUNSTALLED",
    )
    outcome, journal, runner = _dispatch_with_launcher(repo=tmp_path, result=result)
    # Distinct fail-CLOSED terminal class (never silently green); no PR.
    assert outcome.status == "stalled-no-progress"
    assert outcome.stage == "fabro-run"
    assert outcome.pr_number is None
    assert "01RUNSTALLED" in outcome.detail
    assert STALL_SECONDS_ENV_VAR in outcome.detail
    # The runner was never touched -> the PR flow was never entered (the
    # engine short-circuited on the stall).
    assert runner.calls == []
    stages = [record.get("stage") for record in journal.records]
    assert stages == ["fabro-run"]


def test_run_dispatch_with_healthy_launcher_proceeds_normally(tmp_path: Path) -> None:
    # No stall reported -> the engine routes on the exit code exactly as
    # before. A non-zero fabro-run with no run line is a plain failed
    # outcome; the blocked-detection inspect then runs through the runner.
    result = FabroRunResult(
        command=CommandResult(exit_code=1, stdout="", stderr="hard crash, no run line"),
        stalled_run_id=None,
    )
    outcome, _, _ = _dispatch_with_launcher(repo=tmp_path, result=result)
    assert (outcome.status, outcome.stage) == ("failed", "fabro-run")


def test_probe_failure_is_not_a_stall(tmp_path: Path) -> None:
    """End-to-end fail-safety proof: a probe that only ever errors ('no
    signal') must NOT produce a stall, so the run is NOT killed.

    This mirrors the production watchdog's behavior: the launcher samples
    liveness, every probe yields no usable timestamp (transient errors /
    unreachable fabro), `decide_stall` returns CONTINUE for the entire
    span, and the launcher therefore reports `stalled_run_id=None` — the
    run lives. We assert the decision directly over a window of pure
    no-signal samples far exceeding the stall window, which is the exact
    condition the launcher feeds `decide_stall`.
    """
    _ = tmp_path
    # A 2-hour span of nothing-but-probe-failures, window 25 min.
    no_signal = tuple(_sample(epoch=None, observed_at=float(t)) for t in range(0, 7200, 30))
    assert decide_stall(samples=no_signal, stall_seconds=1500.0) is StallVerdict.CONTINUE
    # And the engine, handed a launcher that reports no stall (the
    # no-signal outcome), proceeds rather than reporting a stall.
    result = FabroRunResult(
        command=CommandResult(exit_code=1, stdout="", stderr="probe never resolved a signal"),
        stalled_run_id=None,
    )
    outcome, _, _ = _dispatch_with_launcher(repo=Path("/nonexistent"), result=result)
    assert outcome.status != "stalled-no-progress"


# ---------------------------------------------------------------------------
# WatchedFabroLauncher — the production threading seam, hermetically driven
# (NO real fabro: a scripted CommandRunner + a controllable clock).
# ---------------------------------------------------------------------------


_PS_RUNNING = (
    '[{"run_id": "01RUN", "goal": "Work-item: livespec-impl-beads-oyg",'
    ' "status": {"kind": "running"}}]'
)


@dataclass(kw_only=True)
class _ScriptedFabroRunner:
    """A CommandRunner scripting fabro's run/ps/events/inspect/rm subprocesses.

    `fabro run` BLOCKS on `run_done` so the background thread stays alive
    while the foreground watch loop runs (mirroring a real long run);
    `fabro rm` sets `run_done` (fabro killing the run makes `fabro run`
    return). `events_jsons` is the per-poll sequence of event-stream JSON
    the watch loop reads — a frozen value across polls models a stall, an
    advancing value models progress. `ps_exit` / `events_exit` flip a
    probe to a non-zero error so the no-signal / probe-failure branches
    are exercised. NEVER launches a real process.
    """

    events_jsons: list[str]
    ps_exit: int = 0
    events_exit: int = 0
    run_done: threading.Event = field(default_factory=threading.Event)
    rm_calls: list[str] = field(default_factory=list)
    _poll: int = 0

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        _ = (cwd, timeout_seconds)
        verb = argv[1] if len(argv) > 1 else ""
        dispatch = {
            "run": self._run,
            "ps": self._ps,
            "events": self._events,
            "inspect": lambda: CommandResult(exit_code=0, stdout="{}", stderr=""),
            "rm": lambda: self._rm(run_id=argv[-1]),
        }
        handler = dispatch.get(verb)
        if handler is None:
            return CommandResult(exit_code=1, stdout="", stderr=f"unexpected argv {argv}")
        return handler()

    def _run(self) -> CommandResult:
        # Block until the watchdog cancels (or a healthy run completes —
        # the test sets run_done up front for the healthy path).
        _ = self.run_done.wait(timeout=10.0)
        return CommandResult(exit_code=0, stdout="    Run: 01RUN\n", stderr="")

    def _ps(self) -> CommandResult:
        return CommandResult(exit_code=self.ps_exit, stdout=_PS_RUNNING, stderr="boom")

    def _events(self) -> CommandResult:
        index = min(self._poll, len(self.events_jsons) - 1)
        self._poll += 1
        return CommandResult(
            exit_code=self.events_exit, stdout=self.events_jsons[index], stderr="x"
        )

    def _rm(self, *, run_id: str) -> CommandResult:
        self.rm_calls.append(run_id)
        self.run_done.set()
        return CommandResult(exit_code=0, stdout="", stderr="")


def _advancing_clock() -> object:
    """A monotonic clock that jumps 600s per call (3 samples span 1200s)."""
    ticks = iter(float(t) for t in range(0, 6_000_000, 600))
    return lambda: next(ticks)


def test_scripted_runner_rejects_unknown_verb(tmp_path: Path) -> None:
    # Exercise the fake's defensive fallback (the launcher only ever
    # issues run/ps/events/inspect/rm).
    runner = _ScriptedFabroRunner(events_jsons=["[]"])
    out = runner.run(argv=["fabro", "bogus"], cwd=tmp_path, timeout_seconds=1.0)
    assert out.exit_code == 1


def test_watched_launcher_cancels_a_confirmed_stall(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A frozen event timestamp across every poll -> the watch loop
    # confirms a stall within the (tight, test-set) window and `fabro rm
    # -f`-es the run. Injected clock advances 600s/sample; window 1000s.
    monkeypatch.setenv(STALL_SECONDS_ENV_VAR, "1000")
    frozen = '[{"timestamp": "2026-06-13T08:00:00Z"}]'
    runner = _ScriptedFabroRunner(events_jsons=[frozen])
    journal = _RecordingJournal()
    launcher = WatchedFabroLauncher(sleep=lambda _s: None, clock=_advancing_clock())
    result = launcher.launch(plan=_plan(repo=tmp_path), runner=runner, journal=journal)
    assert result.stalled_run_id == "01RUN"
    assert runner.rm_calls == ["01RUN"]
    stages = [record.get("stage") for record in journal.records]
    assert "watchdog-stall-cancel" in stages


def test_watched_launcher_lets_a_healthy_run_complete(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The run completes on its own (run_done pre-set) before the watch
    # loop ever confirms a stall -> no cancellation, the real
    # CommandResult flows back.
    monkeypatch.setenv(STALL_SECONDS_ENV_VAR, "1000")
    runner = _ScriptedFabroRunner(events_jsons=['[{"timestamp": "2026-06-13T08:00:00Z"}]'])
    runner.run_done.set()  # the run is already finished when the loop checks
    journal = _RecordingJournal()
    launcher = WatchedFabroLauncher(sleep=lambda _s: None, clock=_advancing_clock())
    result = launcher.launch(plan=_plan(repo=tmp_path), runner=runner, journal=journal)
    assert result.stalled_run_id is None
    assert result.command.exit_code == 0
    assert runner.rm_calls == []


def test_watched_launcher_does_not_cancel_when_events_advance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Advancing event timestamps -> progress -> never stalls. The oldest
    # sample's timestamp stays below the newest, so `decide_stall` returns
    # CONTINUE indefinitely; the test ends the run after a few polls via
    # the injected sleep so launch() returns without a cancel.
    monkeypatch.setenv(STALL_SECONDS_ENV_VAR, "1000")
    advancing = [
        '[{"timestamp": "2026-06-13T08:00:00Z"}]',
        '[{"timestamp": "2026-06-13T08:10:00Z"}]',
        '[{"timestamp": "2026-06-13T08:20:00Z"}]',
    ]
    runner = _ScriptedFabroRunner(events_jsons=advancing)
    polls = {"n": 0}

    def _sleep_then_finish(_seconds: float) -> None:
        # Drive the loop deterministically from the (single-threaded under
        # test) sleep hook: after a few polls end the run so launch()
        # returns. No busy-wait, no second thread.
        polls["n"] += 1
        if polls["n"] >= 4:
            runner.run_done.set()

    journal = _RecordingJournal()
    launcher = WatchedFabroLauncher(sleep=_sleep_then_finish, clock=_advancing_clock())
    result = launcher.launch(plan=_plan(repo=tmp_path), runner=runner, journal=journal)
    assert result.stalled_run_id is None
    assert runner.rm_calls == []


def test_watched_launcher_treats_probe_failure_as_no_signal_never_cancels(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # `fabro ps` keeps erroring -> the run id is never discovered -> every
    # sample is no-signal -> decide_stall stays CONTINUE forever, the run
    # is NEVER cancelled (the load-bearing fail-safety property at the
    # production launcher level). The test ends the run after a few polls.
    monkeypatch.setenv(STALL_SECONDS_ENV_VAR, "1000")
    runner = _ScriptedFabroRunner(
        events_jsons=['[{"timestamp": "2026-06-13T08:00:00Z"}]'], ps_exit=1
    )
    polls = {"n": 0}

    def _sleep_then_finish(_seconds: float) -> None:
        polls["n"] += 1
        if polls["n"] >= 5:
            runner.run_done.set()

    journal = _RecordingJournal()
    launcher = WatchedFabroLauncher(sleep=_sleep_then_finish, clock=_advancing_clock())
    result = launcher.launch(plan=_plan(repo=tmp_path), runner=runner, journal=journal)
    assert result.stalled_run_id is None
    assert runner.rm_calls == []


def test_watched_launcher_events_probe_error_is_no_signal_never_cancels(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The run id resolves (ps ok) but `fabro events` keeps erroring and
    # `fabro inspect` returns "{}" -> no usable timestamp -> no-signal ->
    # never stalls. Proves an events-probe outage degrades to no
    # detection, not a false kill.
    monkeypatch.setenv(STALL_SECONDS_ENV_VAR, "1000")
    runner = _ScriptedFabroRunner(events_jsons=["whatever"], events_exit=1)
    polls = {"n": 0}

    def _sleep_then_finish(_seconds: float) -> None:
        polls["n"] += 1
        if polls["n"] >= 5:
            runner.run_done.set()

    journal = _RecordingJournal()
    launcher = WatchedFabroLauncher(sleep=_sleep_then_finish, clock=_advancing_clock())
    result = launcher.launch(plan=_plan(repo=tmp_path), runner=runner, journal=journal)
    assert result.stalled_run_id is None
    assert runner.rm_calls == []
