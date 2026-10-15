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

The `fabro events` stream is the SOLE liveness source: the former
`fabro inspect` / `updated_at` fallback is removed (bd-ib-tec5sz), which
`test_wall_clock_probe_reads_only_the_event_stream_never_fabro_inspect`
pins from both ends — the probe never issues `fabro inspect`, and
`parse_last_event_epoch` no longer accepts an inspect payload. That case
is driven against the PROBE rather than the launcher, because the launcher
now does issue `fabro inspect` — to observe its bound RUN, which is a
different question from how it measures PROGRESS (bd-ib-6pdigz).
"""

from __future__ import annotations

import itertools
import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from inspect import signature
from pathlib import Path
from types import SimpleNamespace

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_io_fabro_launcher
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
    DispatchOutcome,
    FabroRunResult,
    JournalWriter,
    PollPolicy,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import WatchedFabroLauncher
from livespec_orchestrator_beads_fabro.commands._dispatcher_io_liveness_probe import (
    liveness_sample,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    build_plan,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_window import (
    DEFAULT_STALL_WINDOW,
    StallWindow,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import (
    LivenessSample,
    OpenCommandNode,
    StallVerdict,
    decide_stall,
    parse_last_event_epoch,
    quiet_window_seconds,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroRunSummary,
    fabro_port_for_plan,
    fabro_run_summaries_from_stdout,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import REPOSITORY_LAYER

# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------


def _plan(*, repo: Path, stall_seconds: float | None = None) -> DispatchPlan:
    """A dispatch plan, optionally carrying a tight stall window.

    `stall_seconds` stands in for a dispatch target that configured
    `dispatcher.stall_timeout_seconds`: the window the watch loop grades
    against rides the plan (bd-ib-3ugnfr), so a test that needs a window
    tighter than the 7200-second default declares it here rather than
    through the environment.
    """
    window = (
        DEFAULT_STALL_WINDOW
        if stall_seconds is None
        else StallWindow(seconds=stall_seconds, layer=REPOSITORY_LAYER)
    )
    return build_plan(
        repo=repo,
        work_item_id="livespec-impl-beads-oyg",
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        stall_window=window,
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


def test_parse_last_event_epoch_returns_none_on_no_signal() -> None:
    # A transient probe error / empty shapes land here — the fail-safe
    # "no signal" result the caller must NOT treat as a stall. With the
    # `updated_at` fallback removed there is no second source to consult.
    assert parse_last_event_epoch(events_json="not json") is None
    assert parse_last_event_epoch(events_json="[]") is None
    assert parse_last_event_epoch(events_json='[{"noskey": 1}]') is None


def test_parse_last_event_epoch_skips_unusable_event_shapes() -> None:
    # Non-dict events, dict events with no timestamp keys, and an
    # unparseable timestamp string are all skipped; a later numeric `ts`
    # still resolves.
    events = '["not-a-dict", {"other": 1}, {"timestamp": "garbage"}, {"ts": 1750000123}]'
    assert parse_last_event_epoch(events_json=events) == 1750000123.0


def test_parse_last_event_epoch_envelope_with_non_list_events_is_no_signal() -> None:
    # `{"events": <not a list>}` -> no usable events -> no signal.
    assert parse_last_event_epoch(events_json='{"events": "nope"}') is None


def test_parse_last_event_epoch_top_level_scalar_is_no_signal() -> None:
    # A bare JSON scalar (neither array nor object) -> no usable events.
    assert parse_last_event_epoch(events_json="42") is None
    assert parse_last_event_epoch(events_json='"a string"') is None


def test_parse_last_event_epoch_handles_naive_and_offset_timestamps() -> None:
    # A naive timestamp is treated as UTC; an explicit +00:00 offset
    # parses to the same instant as the trailing-Z form.
    naive = parse_last_event_epoch(events_json='[{"timestamp": "2026-06-13T08:00:00"}]')
    zulu = parse_last_event_epoch(events_json='[{"timestamp": "2026-06-13T08:00:00Z"}]')
    offset = parse_last_event_epoch(events_json='[{"timestamp": "2026-06-13T08:00:00+00:00"}]')
    assert naive == zulu == offset


# ---------------------------------------------------------------------------
# FabroPort run summaries (fabro ps -a --json)
# ---------------------------------------------------------------------------


def test_fabro_run_summaries_match_running_run_for_work_item() -> None:
    ps = (
        '[{"run_id": "01OTHER", "goal": "Work-item: other-1", "status": {"kind": "running"}},'
        ' {"run_id": "01MINE", "goal": "Work-item: oyg-1 ...", "status": {"kind": "running"}}]'
    )
    assert _running_run_id(ps_json=ps, work_item_id="oyg-1") == "01MINE"


def test_fabro_run_summaries_skip_non_running_and_wrong_item() -> None:
    # succeeded run for my item -> not it; running run for another item -> not it.
    ps = (
        '[{"run_id": "01DONE", "goal": "Work-item: oyg-1", "status": {"kind": "succeeded"}},'
        ' {"run_id": "01OTHER", "goal": "Work-item: zzz", "status": "running"}]'
    )
    assert _running_run_id(ps_json=ps, work_item_id="oyg-1") is None


def test_fabro_run_summaries_accept_envelope_and_plain_string_status() -> None:
    ps = '{"runs": [{"run_id": "01ENV", "goal": "Work-item: oyg-1", "status": "running"}]}'
    assert _running_run_id(ps_json=ps, work_item_id="oyg-1") == "01ENV"


def test_fabro_run_summaries_return_none_on_malformed() -> None:
    assert _running_run_id(ps_json="not json", work_item_id="oyg-1") is None
    assert _running_run_id(ps_json="[]", work_item_id="oyg-1") is None
    assert _running_run_id(ps_json='[{"no": "fields"}]', work_item_id="oyg-1") is None


def test_fabro_run_summaries_handle_unusable_top_level_and_entries() -> None:
    # Top-level scalar and a dict without a `runs` list -> empty run set.
    assert _running_run_id(ps_json="42", work_item_id="oyg-1") is None
    assert _running_run_id(ps_json='{"runs": "nope"}', work_item_id="oyg-1") is None
    # A non-dict entry in the list is skipped.
    assert _running_run_id(ps_json='["not-a-dict"]', work_item_id="oyg-1") is None


def test_fabro_run_summaries_skip_unusable_status_shapes() -> None:
    # A numeric status (neither string nor `{"kind": ...}`) and a status
    # dict with no string `kind` are both treated as not-running.
    numeric_status = '[{"run_id": "01N", "goal": "Work-item: oyg-1", "status": 7}]'
    no_kind = '[{"run_id": "01K", "goal": "Work-item: oyg-1", "status": {"phase": "x"}}]'
    assert _running_run_id(ps_json=numeric_status, work_item_id="oyg-1") is None
    assert _running_run_id(ps_json=no_kind, work_item_id="oyg-1") is None


def test_fabro_run_summaries_require_a_nonempty_run_id() -> None:
    # A running, matching run with a missing/empty run_id -> no usable id.
    missing = '[{"goal": "Work-item: oyg-1", "status": "running"}]'
    empty = '[{"run_id": "", "goal": "Work-item: oyg-1", "status": "running"}]'
    assert _running_run_id(ps_json=missing, work_item_id="oyg-1") is None
    assert _running_run_id(ps_json=empty, work_item_id="oyg-1") is None


def test_fabro_run_summaries_match_runnable_or_running_run_for_work_item() -> None:
    ps = (
        '[{"run_id": "01OTHER", "goal": "Work-item: other-1", "status": "runnable"},'
        ' {"run_id": "01QUEUED", "goal": "Work-item: oyg-1",'
        ' "status": {"kind": "runnable"}},'
        ' {"run_id": "01RUNNING", "goal": "Work-item: oyg-1", "status": "running"}]'
    )
    run = _watchable_run(ps_json=ps, work_item_id="oyg-1")

    assert run is not None
    assert run.run_id == "01QUEUED"
    assert run.status_kind == "runnable"


def test_fabro_run_summaries_skip_unwatchable_and_malformed_entries() -> None:
    assert _watchable_run(ps_json="not-json", work_item_id="oyg-1") is None
    assert _watchable_run(ps_json='{"runs": "nope"}', work_item_id="oyg-1") is None
    ps = (
        '["bad", {"run_id": "01DONE", "goal": "Work-item: oyg-1",'
        ' "status": {"kind": "succeeded"}},'
        ' {"run_id": "", "goal": "Work-item: oyg-1", "status": "runnable"},'
        ' {"run_id": "01NOGOAL", "status": "runnable"},'
        ' {"run_id": "01NOSTATUS", "goal": "Work-item: oyg-1", "status": 7}]'
    )
    assert _watchable_run(ps_json=ps, work_item_id="oyg-1") is None


def _running_run_id(*, ps_json: str, work_item_id: str) -> str | None:
    run = _watchable_run(ps_json=ps_json, work_item_id=work_item_id)
    return run.run_id if run is not None and run.status_kind == "running" else None


def _watchable_run(*, ps_json: str, work_item_id: str) -> FabroRunSummary | None:
    for run in fabro_run_summaries_from_stdout(stdout=ps_json):
        if run.work_item_id == work_item_id and run.status_kind in {"runnable", "running"}:
            return run
    return None


# ---------------------------------------------------------------------------
# decide_stall — the load-bearing fail-safety matrix
# ---------------------------------------------------------------------------


def _sample(
    *,
    epoch: float | None,
    observed_at: float,
    open_command_node: OpenCommandNode | None = None,
) -> LivenessSample:
    return LivenessSample(
        last_event_epoch=epoch,
        observed_at=observed_at,
        open_command_node=open_command_node,
    )


# The janitor as the graph's own `dispatcher.node_timeouts` default resolves
# it: 1800 seconds, longer than the tight 1500-second window these tests
# declare, which is what makes the two bounds distinguishable.
_OPEN_JANITOR = OpenCommandNode(node="janitor", timeout_seconds=1800.0)


def test_decide_stall_continues_when_progress_is_made() -> None:
    assert StallVerdict.CONTINUE.value == "continue"
    assert StallVerdict.STALLED.value == "stalled-no-progress"
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


def test_quiet_window_seconds_is_unmeasured_without_two_timestamped_readings() -> None:
    # The window the cancellation record carries is UNMEASURED, not zero,
    # when fewer than two readings carried a timestamp: a zero would read as
    # a window that was measured and found empty, which is what would let a
    # probe outage look like a run that had just reported progress. Asserted
    # on the public surface the launcher journals from, because the number in
    # that record is the only evidence a cancellation leaves behind.
    assert quiet_window_seconds(samples=()) is None
    assert quiet_window_seconds(samples=(_sample(epoch=100.0, observed_at=0.0),)) is None
    assert (
        quiet_window_seconds(
            samples=(
                _sample(epoch=None, observed_at=0.0),
                _sample(epoch=100.0, observed_at=900.0),
            )
        )
        is None
    )
    # And it IS a measurement once two readings agree, so the None above is
    # a measurement that could not be taken rather than one this function
    # never takes.
    measured = (
        _sample(epoch=100.0, observed_at=0.0),
        _sample(epoch=100.0, observed_at=900.0),
    )
    assert quiet_window_seconds(samples=measured) == 900.0


def test_decide_stall_waits_for_an_open_command_nodes_own_timeout() -> None:
    """An open COMMAND node is graded against ITS timeout, not the window (bd-ib-qsk4o5).

    A command node emits a start event and a completion event and nothing
    between them, so BOTH liveness layers are flat for its whole duration
    however healthy the run is — the heartbeat because it beats only while an
    agent turn runs, the event stream because there is no further event. A
    sandbox `just check` measured 21 minutes on 2026-10-12, so the stall
    window is routinely the SHORTER of the two bounds, and grading against it
    cancelled runs whose work was already green.

    The bound is the MAXIMUM of the two rather than the node's alone, so a
    repository that shortens `dispatcher.stall_timeout_seconds` below a node's
    timeout does not thereby make the watchdog cancel inside that node.
    """
    opened = (
        _sample(epoch=100.0, observed_at=0.0, open_command_node=_OPEN_JANITOR),
        _sample(epoch=100.0, observed_at=900.0, open_command_node=_OPEN_JANITOR),
        _sample(epoch=100.0, observed_at=1500.0, open_command_node=_OPEN_JANITOR),
    )
    # Past the 1500s window but inside the janitor's own 1800s timeout.
    assert decide_stall(samples=opened, stall_seconds=1500.0) is StallVerdict.CONTINUE
    # And once that node's own timeout HAS elapsed, the stall is confirmed:
    # the node's bound relaxes the watchdog, it does not disarm it.
    elapsed = (*opened, _sample(epoch=100.0, observed_at=1800.0, open_command_node=_OPEN_JANITOR))
    assert decide_stall(samples=elapsed, stall_seconds=1500.0) is StallVerdict.STALLED


def test_decide_stall_keeps_an_open_command_nodes_bound_across_the_whole_window() -> None:
    """The bound is taken across the quiet window, not from the newest reading.

    A command node cannot complete without emitting a completion event, and
    that event advances the last-event timestamp — which opens a NEW quiet
    window. So WITHIN one quiet window, a node once observed open is still
    open, and a later reading that does not report it has failed to observe
    it rather than watched it finish: the `fabro events` reader tolerates a
    stream truncated mid-record by a probe timeout, so it can parse a
    timestamp from the records before the cut while missing the start event
    behind it.

    Reading the bound off the newest sample alone would therefore let one
    truncated read collapse the window back to the shorter bound and cancel
    the run — the failure this watchdog must never commit.
    """
    window = (
        _sample(epoch=100.0, observed_at=0.0, open_command_node=_OPEN_JANITOR),
        _sample(epoch=100.0, observed_at=900.0),
        _sample(epoch=100.0, observed_at=1500.0),
    )
    assert decide_stall(samples=window, stall_seconds=1500.0) is StallVerdict.CONTINUE


def test_decide_stall_drops_an_open_command_nodes_bound_once_the_window_restarts() -> None:
    """A node open in an EARLIER window does not widen the current one.

    The launcher retains every sample for the life of the run, so a bound
    taken over the whole sample list would be inherited by every later window
    — one long janitor early in a run would widen the watchdog for the rest of
    it, which is the standing-relaxation failure the window scoping exists to
    prevent. Fresh progress ends the window and the bound with it.
    """
    samples = (
        _sample(epoch=100.0, observed_at=0.0, open_command_node=_OPEN_JANITOR),
        _sample(epoch=200.0, observed_at=100.0),
        _sample(epoch=200.0, observed_at=1600.0),
    )
    assert decide_stall(samples=samples, stall_seconds=1500.0) is StallVerdict.STALLED


def test_decide_stall_confirms_a_stall_when_no_command_node_is_open() -> None:
    """A full frozen window with NO command node open is still a stall (bd-ib-qsk4o5).

    Every observation records which COMMAND node of the phase graph the run
    was inside when it was taken, so that a run genuinely sitting inside
    `janitor` or `publish_draft` is graded against that node's own timeout
    rather than against the shorter stall window. This is the arm that keeps
    the relaxation honest: when NO observation in the quiet window reports an
    open command node, the configured stall window governs alone and the run
    is still cancelled as `stalled-no-progress`.

    The default is what makes that arm the common one, so it is asserted here
    rather than assumed: a sample built with no observation of its own carries
    None, not a bound that would quietly widen every window in the fleet.
    """
    samples = (
        _sample(epoch=100.0, observed_at=0.0),
        _sample(epoch=100.0, observed_at=900.0),
        _sample(epoch=100.0, observed_at=1500.0),
    )
    assert [sample.open_command_node for sample in samples] == [None, None, None]
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


def test_decide_stall_confirms_a_quiet_window_after_earlier_observed_progress() -> None:
    """A full quiet window AFTER the most recent progress is a stall (bd-ib-n44n4e).

    The watchdog used to compare only the OLDEST and NEWEST observed event
    epochs, so one early advance made `last_event > first_event` true for
    the rest of the run and suppressed every later confirmed stall — the
    advertised backstop could never fire again. Observed 2026-10-09 on run
    01M4EX8SNQMVNZBPB1WGKGMET1 (hp): the last tool completion and dispatch
    heartbeat sat unchanged past 30 minutes while discovery kept reporting
    `running`, and no cancellation ever came.

    The quiet window is therefore measured from the MOST RECENT observed
    progress, not from the first observation of the run.
    """
    # The 2026-10-09 reproduction, verbatim: one advance, then silence
    # well past the 1500s window.
    reproduction = (
        _sample(epoch=100.0, observed_at=100.0),
        _sample(epoch=200.0, observed_at=200.0),
        _sample(epoch=200.0, observed_at=1801.0),
    )
    assert decide_stall(samples=reproduction, stall_seconds=1500.0) is StallVerdict.STALLED
    # And at the production 30s poll cadence the frozen tail is dozens of
    # samples long, so a decision reading only the final PAIR of readings
    # would miss it too (each adjacent pair spans one poll interval).
    cadence = (
        _sample(epoch=100.0, observed_at=0.0),
        _sample(epoch=200.0, observed_at=30.0),
        *(_sample(epoch=200.0, observed_at=float(t)) for t in range(60, 1891, 30)),
    )
    assert decide_stall(samples=cadence, stall_seconds=1500.0) is StallVerdict.STALLED


def test_decide_stall_restarts_the_quiet_window_on_fresh_progress() -> None:
    """Fresh progress opens a NEW window; unavailable readings stay fail-safe.

    The window is the CURRENT one, not the widest one in the run's
    history. The launcher retains every sample for the life of the run, so
    a run that went quiet for longer than a window and then RESUMED still
    carries that old silence in its sample list — and holding it against a
    run that is emitting now would kill healthy work, which is the one
    direction this watchdog must never fail in.
    """
    # Quiet for more than a full window, then emitting again.
    resumed = (
        _sample(epoch=100.0, observed_at=0.0),
        _sample(epoch=100.0, observed_at=1800.0),
        _sample(epoch=300.0, observed_at=1830.0),
        _sample(epoch=300.0, observed_at=1860.0),
    )
    assert decide_stall(samples=resumed, stall_seconds=1500.0) is StallVerdict.CONTINUE
    # ... and the RESTARTED window still confirms a stall once IT elapses,
    # so resuming once does not buy permanent immunity.
    resumed_then_quiet = (*resumed, _sample(epoch=300.0, observed_at=3400.0))
    assert decide_stall(samples=resumed_then_quiet, stall_seconds=1500.0) is StallVerdict.STALLED
    # Unavailable observations preserve the existing fail-safe behaviour: a
    # long burst of no-signal probes after fresh progress cannot manufacture
    # a stall, because the window is anchored on the last OBSERVED progress
    # and a no-signal reading observes nothing.
    unavailable = (
        _sample(epoch=100.0, observed_at=0.0),
        _sample(epoch=300.0, observed_at=100.0),
        *(_sample(epoch=None, observed_at=float(t)) for t in range(130, 3700, 30)),
    )
    assert decide_stall(samples=unavailable, stall_seconds=1500.0) is StallVerdict.CONTINUE


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
    assert "dispatcher.stall_timeout_seconds" in outcome.detail
    # The runner was never touched -> the PR flow was never entered (the
    # engine short-circuited on the stall).
    assert runner.calls == []
    stages = [record.get("stage") for record in journal.records]
    assert stages == ["fabro-run"]


def test_run_dispatch_reports_stale_run_reap_and_skips_pr_flow(tmp_path: Path) -> None:
    result = FabroRunResult(
        command=CommandResult(exit_code=1, stdout="", stderr="cancelled by stale item reaper"),
        abandoned_run_id="01RUNSTALE",
        abandoned_item_status="done",
    )
    outcome, journal, runner = _dispatch_with_launcher(repo=tmp_path, result=result)

    assert outcome.status == "failed"
    assert outcome.stage == "stale-run-reap"
    assert outcome.fabro_run_id == "01RUNSTALE"
    assert "livespec-impl-beads-oyg status is done" in outcome.detail
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
# What `fabro inspect 01RUN --json` answers once the watch loop has BOUND the
# run, as a one-element list (the shape the pinned build returns). The
# listing above is only reachable on the FIRST poll now, so a runner that
# scripted no inspect would stall the loop at its second poll rather than
# exercise it. The status is a knob so a case can send the bound run
# TERMINAL mid-dispatch, which the listing could express only by dropping
# the row.
_INSPECT_RECORD = '[{{"run_id": "01RUN", "status": {{"kind": "{status}"}}}}]'

# The janitor's own start and completion events, in the shape the engine
# emits them (`node_id` at the top level beside the envelope's timestamp),
# so a frozen stream can model a run INSIDE that command node and a run
# that has already left it. Both carry the SAME timestamp, so the quiet
# window the two fixtures produce is identical and the only thing that
# differs between them is whether a command node is open.
_JANITOR_STARTED_EVENT = (
    '{"event": "stage.started", "node_id": "janitor", "timestamp": "2026-06-13T08:00:00Z"}'
)
_JANITOR_COMPLETED_EVENT = (
    '{"event": "stage.completed", "node_id": "janitor", "timestamp": "2026-06-13T08:00:00Z"}'
)
_JANITOR_STARTED_JSON = f"[{_JANITOR_STARTED_EVENT}]"


@dataclass(kw_only=True)
class _ScriptedFabroRunner:
    """A CommandRunner scripting fabro's run/ps/inspect/events/rm subprocesses.

    `fabro run` BLOCKS on `run_done` so the background thread stays alive
    while the foreground watch loop runs (mirroring a real long run);
    `fabro rm` sets `run_done` (fabro killing the run makes `fabro run`
    return). `events_jsons` is the per-poll sequence of event-stream JSON
    the watch loop reads — a frozen value across polls models a stall, an
    advancing value models progress. `ps_exit` / `events_exit` flip a
    probe to a non-zero error so the no-signal / probe-failure branches
    are exercised. Every verb the launcher issues is recorded in `verbs`,
    so a test can assert WHICH probe each poll spent. NEVER launches a
    real process.
    """

    events_jsons: list[str]
    inspect_status: str = "running"
    ps_exit: int = 0
    inspect_exit: int = 0
    inspect_stderr: str = "boom"
    events_exit: int = 0
    run_done: threading.Event = field(default_factory=threading.Event)
    run_returned: threading.Event = field(default_factory=threading.Event)
    rm_calls: list[str] = field(default_factory=list)
    verbs: list[str] = field(default_factory=list)
    _poll: int = 0

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        _ = (cwd, timeout_seconds)
        verb = argv[1] if len(argv) > 1 else ""
        self.verbs.append(verb)
        dispatch = {
            "run": self._run,
            "ps": self._ps,
            "inspect": self._inspect,
            "events": self._events,
            "rm": lambda: self._rm(run_id=argv[-1]),
        }
        handler = dispatch.get(verb)
        if handler is None:
            return CommandResult(exit_code=1, stdout="", stderr=f"unexpected argv {argv}")
        return handler()

    def _run(self) -> CommandResult:
        # Block until the watchdog cancels (or a healthy run completes —
        # the healthy-path tests set run_done during or before polling).
        _ = self.run_done.wait(timeout=10.0)
        self.run_returned.set()
        return CommandResult(exit_code=0, stdout="    Run: 01RUN\n", stderr="")

    def _ps(self) -> CommandResult:
        return CommandResult(exit_code=self.ps_exit, stdout=_PS_RUNNING, stderr="boom")

    def _inspect(self) -> CommandResult:
        return CommandResult(
            exit_code=self.inspect_exit,
            stdout="" if self.inspect_exit else _INSPECT_RECORD.format(status=self.inspect_status),
            stderr=self.inspect_stderr,
        )

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
    # Unbounded: a finite iterator raised StopIteration out of `launch`
    # whenever the watch loop out-polled the run thread's return.
    ticks = itertools.count(0.0, 600.0)
    return lambda: next(ticks)


def test_scripted_runner_rejects_unknown_verb(tmp_path: Path) -> None:
    # Exercise the fake's defensive fallback (the launcher only ever
    # issues run/ps/inspect/events/rm).
    runner = _ScriptedFabroRunner(events_jsons=["[]"])
    out = runner.run(argv=["fabro", "bogus"], cwd=tmp_path, timeout_seconds=1.0)
    assert out.exit_code == 1


def test_wall_clock_probe_reads_only_the_event_stream_never_fabro_inspect(
    tmp_path: Path,
) -> None:
    """bd-ib-tec5sz: the `updated_at` fallback is REMOVED, not repointed.

    The pinned fabro build never emits that field, and the only
    running-run candidate (`checkpoint.timestamp`) advances per NODE rather
    than per event, so it cannot be a wall-clock liveness signal. Pinned
    from both ends: the production probe issues `fabro events` and NEVER
    `fabro inspect`, and the parser accepts no inspect payload.

    Aimed at the PROBE and not at the launcher. The launcher reads its bound
    run with `fabro inspect` since bd-ib-6pdigz, so a launcher-level
    "inspect was never issued" assertion can no longer separate the
    liveness question from the observation question — it would simply fail
    on a probe that is still correct. The exact verb list is what makes this
    a measurement rather than a containment check.
    """
    runner = _ScriptedFabroRunner(events_jsons=['[{"timestamp": "2026-06-13T08:00:00Z"}]'])
    port = fabro_port_for_plan(plan=_plan(repo=tmp_path, stall_seconds=1000.0), runner=runner)

    sample = liveness_sample(
        plan=_plan(repo=tmp_path, stall_seconds=1000.0),
        port=port,
        run_id="01RUN",
        heartbeat_path=None,
        dispatch_id=None,
        observed_at=0.0,
    )

    assert sample.last_event_epoch is not None
    assert runner.verbs == ["events"]
    assert "inspect_json" not in signature(parse_last_event_epoch).parameters


def test_the_cancel_record_locates_the_run_before_the_rm_destroys_it(tmp_path: Path) -> None:
    """`bd-ib-nfbyot`: the production launcher journals the run's own half too.

    The two readings this adds — the executing stage and the publication — are
    available ONLY while the run exists, so the case asserts the verb ORDER as
    well as the fields: a reading taken after `fabro rm -f` would still succeed
    and would report every cancelled run as a run with no publication. Both the
    stage and the head come from the SAME scripted stream, because a fixture
    supplying one and not the other cannot tell a reader that located the run
    from one that happened to find a marker.
    """
    head = "d" * 40
    frozen = json.dumps(
        [
            {"timestamp": "2026-06-13T08:00:00Z", "event": "fabro.stage.started"},
            {"event": "fabro.stage.started", "node_id": "publish_draft"},
            {"event": "fabro.stage.completed", "node_id": "publish_draft"},
            {
                "event": "fabro.edge.selected",
                "properties": {"from_node": "publish_draft", "to_node": "proof_capture"},
            },
            {"event": "fabro.stage.started", "node_id": "proof_capture"},
            {
                "event": "fabro.agent.log",
                "properties": {
                    "text": (
                        "LIVESPEC_PUBLISH_DRAFT_PUBLISHED: publish_branch=feat/x "
                        f"head={head} pull_request=#2612"
                    )
                },
            },
        ]
    )
    runner = _ScriptedFabroRunner(events_jsons=[frozen])
    journal = _RecordingJournal()
    launcher = WatchedFabroLauncher(sleep=lambda _s: None, clock=_advancing_clock())

    result = launcher.launch(
        plan=_plan(repo=tmp_path, stall_seconds=1000.0), runner=runner, journal=journal
    )

    assert result.stalled_run_id == "01RUN"
    cancels = [r for r in journal.records if r.get("stage") == "watchdog-stall-cancel"]
    assert len(cancels) == 1
    # This launcher is wired with no dispatch id, so the key is present and
    # NULL rather than absent: an absent key is what a record from a build
    # predating the field looks like, and a reader could not tell the two
    # apart. The populated case is asserted on the renderer, which is the only
    # layer that can be handed one without the correlation wiring this fake
    # runner does not model.
    assert cancels[0]["dispatch_id"] is None
    assert cancels[0]["factory"] == "default"
    assert cancels[0]["executing_stage"] == "proof_capture"
    assert cancels[0]["pull_request"] == 2612
    assert cancels[0]["published_head"] == head
    # The reading precedes the destruction: `events` and `inspect` both appear
    # before the `rm` that makes them unanswerable.
    assert runner.verbs.index("rm") > runner.verbs.index("inspect")


def test_watched_launcher_cancels_a_confirmed_stall(tmp_path: Path) -> None:
    # A frozen event timestamp across every poll -> the watch loop
    # confirms a stall within the (tight, test-set) window and `fabro rm
    # -f`-es the run. Injected clock advances 600s/sample; window 1000s.
    frozen = '[{"timestamp": "2026-06-13T08:00:00Z"}]'
    runner = _ScriptedFabroRunner(events_jsons=[frozen])
    journal = _RecordingJournal()
    launcher = WatchedFabroLauncher(sleep=lambda _s: None, clock=_advancing_clock())
    result = launcher.launch(
        plan=_plan(repo=tmp_path, stall_seconds=1000.0), runner=runner, journal=journal
    )
    assert result.stalled_run_id == "01RUN"
    assert runner.rm_calls == ["01RUN"]
    stages = [record.get("stage") for record in journal.records]
    assert "watchdog-stall-cancel" in stages


def test_watched_launcher_cancels_after_progress_then_a_confirmed_quiet_window(
    tmp_path: Path,
) -> None:
    """The production shape of bd-ib-n44n4e, driven through the real watch loop.

    The run emits for a couple of polls and then goes silent while `fabro
    ps` keeps reporting it `running` — the 2026-10-09 incident exactly.
    The CONFIGURED stall interval is what governs the cancellation of that
    discovered running target, so the cancel record names the interval
    that governed it alongside the quiet window actually confirmed. The
    incident had to be reconstructed by hand from a run's event stream
    because the journal recorded a cancel with neither figure in it.
    """
    # Two advancing readings, then the scripted runner clamps to the last
    # one: progress, then silence. The injected clock advances 600s per
    # sample, so the quiet window reaches 1200s at the fourth poll.
    progress_then_silence = [
        '[{"timestamp": "2026-06-13T08:00:00Z"}]',
        '[{"timestamp": "2026-06-13T08:10:00Z"}]',
    ]
    runner = _ScriptedFabroRunner(events_jsons=progress_then_silence)
    journal = _RecordingJournal()
    launcher = WatchedFabroLauncher(sleep=lambda _s: None, clock=_advancing_clock())
    result = launcher.launch(
        plan=_plan(repo=tmp_path, stall_seconds=1000.0), runner=runner, journal=journal
    )

    assert result.stalled_run_id == "01RUN"
    assert runner.rm_calls == ["01RUN"]
    cancels = [r for r in journal.records if r.get("stage") == "watchdog-stall-cancel"]
    assert [record.get("stall_seconds") for record in cancels] == [1000.0]
    assert [record.get("quiet_seconds") for record in cancels] == [1200.0]


def test_a_stall_is_still_confirmed_while_the_bound_run_is_polled_by_id(
    tmp_path: Path,
) -> None:
    """bd-ib-6pdigz: binding the run must not cost the watchdog its stall detection.

    ONE listing to find the run, then per-run reads for the rest of the
    dispatch — and the cancel still fires on the confirmed quiet window. The
    verb tally is asserted beside the cancel because the cancel alone passes
    equally well on a build that never stopped listing, which is the thing
    being removed.
    """
    runner = _ScriptedFabroRunner(events_jsons=['[{"timestamp": "2026-06-13T08:00:00Z"}]'])
    launcher = WatchedFabroLauncher(sleep=lambda _s: None, clock=_advancing_clock())

    result = launcher.launch(
        plan=_plan(repo=tmp_path, stall_seconds=1000.0),
        runner=runner,
        journal=_RecordingJournal(),
    )

    assert result.stalled_run_id == "01RUN"
    assert runner.rm_calls == ["01RUN"]
    assert runner.verbs.count("ps") == 1
    assert runner.verbs.count("inspect") >= 1


def test_a_bound_run_that_goes_terminal_is_observed_and_never_stall_cancelled(
    tmp_path: Path,
) -> None:
    """The other half of bd-ib-6pdigz's detection claim: a terminal bound run.

    The event stream is FROZEN and the window is tight, so a watchdog that
    could no longer tell a terminal run from a running one would cancel here.
    It does not, and each per-run read says why — which is the record a
    listing-based poll could only express by the row disappearing.
    """
    runner = _ScriptedFabroRunner(
        events_jsons=['[{"timestamp": "2026-06-13T08:00:00Z"}]'],
        inspect_status="succeeded",
    )
    polls = {"n": 0}

    def _sleep_then_finish(_seconds: float) -> None:
        polls["n"] += 1
        if polls["n"] >= 4:
            runner.run_done.set()
            assert runner.run_returned.wait(timeout=1.0)

    journal = _RecordingJournal()
    launcher = WatchedFabroLauncher(sleep=_sleep_then_finish, clock=_advancing_clock())

    result = launcher.launch(
        plan=_plan(repo=tmp_path, stall_seconds=1000.0), runner=runner, journal=journal
    )

    bound = [r for r in journal.records if r.get("stage") == "watchdog-bound-poll"]
    assert result.stalled_run_id is None
    assert runner.rm_calls == []
    assert len(bound) >= 2
    assert {record.get("reason") for record in bound} == {"status-kind-not-running"}
    assert {record.get("status_kind") for record in bound} == {"succeeded"}


def test_a_failed_per_run_read_leaves_a_record_and_cancels_nothing(
    tmp_path: Path,
) -> None:
    """A per-run read that FAILED observed nothing, so it decides nothing.

    The event stream is frozen and the window is tight, so a watchdog that
    read a failed probe as an observation about the run would cancel here.
    The reason NAME is deliberately not pinned — only that the poll is
    recorded, saw nothing, and does not claim the factory stopped holding
    the run, which is the claim a failed read cannot support.
    """
    runner = _ScriptedFabroRunner(
        events_jsons=['[{"timestamp": "2026-06-13T08:00:00Z"}]'],
        inspect_exit=1,
        inspect_stderr="error: connection refused",
    )
    polls = {"n": 0}

    def _sleep_then_finish(_seconds: float) -> None:
        polls["n"] += 1
        if polls["n"] >= 4:
            runner.run_done.set()
            assert runner.run_returned.wait(timeout=1.0)

    journal = _RecordingJournal()
    launcher = WatchedFabroLauncher(sleep=_sleep_then_finish, clock=_advancing_clock())

    result = launcher.launch(
        plan=_plan(repo=tmp_path, stall_seconds=1000.0), runner=runner, journal=journal
    )

    bound = [r for r in journal.records if r.get("stage") == "watchdog-bound-poll"]
    assert result.stalled_run_id is None
    assert runner.rm_calls == []
    assert len(bound) >= 2
    assert {record.get("matched") for record in bound} == {False}
    assert "run-not-held" not in {record.get("reason") for record in bound}


def test_watched_launcher_does_not_cancel_while_a_command_node_is_open(tmp_path: Path) -> None:
    """End to end: a run inside `janitor` survives past the stall window.

    The event stream carries ONE record — the janitor's own start event — so
    both liveness layers are flat from the moment that node began, which is
    exactly what a healthy long `just check` looks like from the host. The
    quiet window reaches 1200 seconds here, past the 1000-second window this
    plan declares, and the run must still not be cancelled because the
    janitor's own resolved timeout (1800 seconds, the graph default) has not
    elapsed.

    The negative control is the sibling below: the SAME frozen stream with the
    janitor's completion event in it carries no open node, so the window
    governs alone and the run IS cancelled.
    """
    runner = _ScriptedFabroRunner(events_jsons=[_JANITOR_STARTED_JSON])
    polls = {"n": 0}

    def _sleep_then_finish(_seconds: float) -> None:
        polls["n"] += 1
        if polls["n"] >= 4:
            runner.run_done.set()
            assert runner.run_returned.wait(timeout=1.0)

    journal = _RecordingJournal()
    launcher = WatchedFabroLauncher(sleep=_sleep_then_finish, clock=_advancing_clock())
    result = launcher.launch(
        plan=_plan(repo=tmp_path, stall_seconds=1000.0), runner=runner, journal=journal
    )
    assert result.stalled_run_id is None
    assert runner.rm_calls == []


def test_watched_launcher_cancels_once_the_open_command_node_has_completed(
    tmp_path: Path,
) -> None:
    # The negative control for the test above. The same frozen stream, plus
    # the janitor's completion event: nothing is open, so the configured
    # stall window governs alone and the silent run is cancelled. Without
    # this, a watchdog that simply stopped cancelling whenever the stream
    # mentioned a command node would satisfy the test above.
    frozen_and_completed = [f"[{_JANITOR_STARTED_EVENT}, {_JANITOR_COMPLETED_EVENT}]"]
    runner = _ScriptedFabroRunner(events_jsons=frozen_and_completed)
    journal = _RecordingJournal()
    launcher = WatchedFabroLauncher(sleep=lambda _s: None, clock=_advancing_clock())
    result = launcher.launch(
        plan=_plan(repo=tmp_path, stall_seconds=1000.0), runner=runner, journal=journal
    )
    assert result.stalled_run_id == "01RUN"
    assert runner.rm_calls == ["01RUN"]


def test_watched_launcher_lets_a_healthy_run_complete(tmp_path: Path) -> None:
    # The run completes on its own during the watch sleep before the
    # would-be deciding sample. The background thread is alive at the top
    # of the watch iteration, but the launcher must notice completion
    # after the sleep boundary and return the real CommandResult without
    # probing/canceling the finished run.
    runner = _ScriptedFabroRunner(events_jsons=['[{"timestamp": "2026-06-13T08:00:00Z"}]'])
    polls = {"n": 0}

    def _sleep_then_finish(_seconds: float) -> None:
        polls["n"] += 1
        if polls["n"] >= 3:
            runner.run_done.set()
            assert runner.run_returned.wait(timeout=1.0)

    journal = _RecordingJournal()
    launcher = WatchedFabroLauncher(sleep=_sleep_then_finish, clock=_advancing_clock())
    result = launcher.launch(
        plan=_plan(repo=tmp_path, stall_seconds=1000.0), runner=runner, journal=journal
    )
    assert result.stalled_run_id is None
    assert result.command.exit_code == 0
    assert runner.rm_calls == []


def test_watched_launcher_takes_no_sample_once_the_fabro_run_call_has_returned(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """bd-ib-qhyxqs: the run's own RETURN ends the watch, not the thread's exit.

    `fabro run` returns from INSIDE the run thread, and the interpreter tears
    that thread down afterwards — a lag that widens under load. A watch loop
    keyed on `is_alive` therefore resumed after the run had finished, took one
    more liveness sample of a run that was already over, and cancelled it: the
    event stream froze when the run ended, so the sample reads exactly like a
    stall. Measured in the sandbox of run 01M4WWQNRN2J at hp load ~23, where
    the sibling healthy-completion case above failed with a stalled result.

    The condition is pinned by WRAPPING the thread target: the wrapper runs the
    launcher's own target to completion — so this dispatch's `fabro run` call
    HAS returned — then signals this test and lingers, so the thread is still
    alive when the loop resumes. No sleep-ordering guess is involved, which is
    what the fixture it repairs could not avoid.

    The negative control is `test_watched_launcher_cancels_a_confirmed_stall`
    above: there the run's `fabro run` call never returns and liveness stays
    flat for the full stall window, and the run is still cancelled as
    stalled-no-progress. Without it, a launcher that simply stopped sampling
    would satisfy this case.
    """
    runner = _ScriptedFabroRunner(events_jsons=['[{"timestamp": "2026-06-13T08:00:00Z"}]'])
    target_returned = threading.Event()
    real_thread = threading.Thread

    def _lingering_thread(*, target: Callable[[], None], name: str) -> threading.Thread:
        def _linger() -> None:
            target()
            target_returned.set()
            # Outlive the watch loop's completion check, which is the whole
            # condition: a thread that has not yet exited is not a run still
            # running. Bounded, because `launch` joins this thread on its way
            # out and nothing else can release it.
            _ = threading.Event().wait(timeout=0.5)

        return real_thread(target=_linger, name=name)

    polls = {"n": 0}

    def _sleep_then_finish(_seconds: float) -> None:
        polls["n"] += 1
        if polls["n"] >= 3:
            runner.run_done.set()
            assert target_returned.wait(timeout=5.0)

    monkeypatch.setattr(_dispatcher_io_fabro_launcher.threading, "Thread", _lingering_thread)
    journal = _RecordingJournal()
    launcher = WatchedFabroLauncher(sleep=_sleep_then_finish, clock=_advancing_clock())
    result = launcher.launch(
        plan=_plan(repo=tmp_path, stall_seconds=1000.0), runner=runner, journal=journal
    )

    assert result.stalled_run_id is None
    assert result.command.exit_code == 0
    assert runner.rm_calls == []
    # Two polls sampled liveness; the third found the run returned and probed
    # nothing. A third sample would have reached 1200s of frozen stream against
    # the 1000s window this plan declares, which is the cancel being prevented.
    assert runner.verbs.count("events") == 2


def test_watched_launcher_does_not_cancel_when_events_advance(tmp_path: Path) -> None:
    # Advancing event timestamps -> progress -> never stalls. The oldest
    # sample's timestamp stays below the newest, so `decide_stall` returns
    # CONTINUE indefinitely; the test ends the run after a few polls via
    # the injected sleep so launch() returns without a cancel.
    # One advancing entry per poll the watch loop can reach. The scripted
    # runner CLAMPS to the LAST entry once the list is exhausted, so a
    # short list goes frozen partway through the watch and — correctly,
    # since the quiet window is now measured from the most recent progress
    # (bd-ib-n44n4e) — confirms a stall. A fixture for the healthy
    # advancing run must therefore keep advancing for as long as the loop
    # runs, or it stops modelling the run it names.
    advancing = [
        f'[{{"timestamp": "2026-06-13T08:{minute:02d}:00Z"}}]' for minute in range(0, 40, 5)
    ]
    runner = _ScriptedFabroRunner(events_jsons=advancing)
    polls = {"n": 0}

    def _sleep_then_finish(_seconds: float) -> None:
        # Drive the loop deterministically from the (single-threaded under
        # test) sleep hook: after a few polls end the run so launch()
        # returns. No busy-wait, no second thread. The hook WAITS for the
        # background run to return, so the loop stops at a known poll
        # count instead of spinning an unbounded number of extra polls
        # while the OS gets round to scheduling the run thread.
        polls["n"] += 1
        if polls["n"] >= 4:
            runner.run_done.set()
            assert runner.run_returned.wait(timeout=1.0)

    journal = _RecordingJournal()
    launcher = WatchedFabroLauncher(sleep=_sleep_then_finish, clock=_advancing_clock())
    result = launcher.launch(
        plan=_plan(repo=tmp_path, stall_seconds=1000.0), runner=runner, journal=journal
    )
    assert result.stalled_run_id is None
    assert runner.rm_calls == []


def test_watched_launcher_treats_probe_failure_as_no_signal_never_cancels(
    tmp_path: Path,
) -> None:
    # `fabro ps` keeps erroring -> the run id is never discovered -> every
    # sample is no-signal -> decide_stall stays CONTINUE forever, the run
    # is NEVER cancelled (the load-bearing fail-safety property at the
    # production launcher level). The test ends the run after a few polls.
    runner = _ScriptedFabroRunner(
        events_jsons=['[{"timestamp": "2026-06-13T08:00:00Z"}]'], ps_exit=1
    )
    polls = {"n": 0}

    def _sleep_then_finish(_seconds: float) -> None:
        polls["n"] += 1
        if polls["n"] >= 5:
            runner.run_done.set()
            assert runner.run_returned.wait(timeout=1.0)

    journal = _RecordingJournal()
    launcher = WatchedFabroLauncher(sleep=_sleep_then_finish, clock=_advancing_clock())
    result = launcher.launch(
        plan=_plan(repo=tmp_path, stall_seconds=1000.0), runner=runner, journal=journal
    )
    assert result.stalled_run_id is None
    assert runner.rm_calls == []


def test_watched_launcher_continues_when_discovered_run_item_is_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _ = tmp_path.joinpath(".livespec.jsonc").write_text(
        """
        {
          "livespec-orchestrator-beads-fabro": {
            "connection": {
              "prefix": "bd-ib",
              "tenant": "test-tenant",
              "fake": true
            }
          }
        }
        """,
        encoding="utf-8",
    )

    def _no_items(*, path: object) -> list[object]:
        _ = path
        return [
            SimpleNamespace(id="bd-ib-other-1", status="done"),
            SimpleNamespace(id="bd-ib-other-2", status="done"),
        ]

    runner = _ScriptedFabroRunner(events_jsons=['[{"timestamp": "2026-06-13T08:00:00Z"}]'])
    polls = {"n": 0}

    def _sleep_then_finish(_seconds: float) -> None:
        polls["n"] += 1
        if polls["n"] >= 3:
            runner.run_done.set()
            assert runner.run_returned.wait(timeout=1.0)

    monkeypatch.setattr(_dispatcher_io_fabro_launcher, "read_work_items", _no_items)
    journal = _RecordingJournal()
    launcher = WatchedFabroLauncher(sleep=_sleep_then_finish, clock=_advancing_clock())
    result = launcher.launch(
        plan=_plan(repo=tmp_path, stall_seconds=1000.0), runner=runner, journal=journal
    )

    assert result.abandoned_run_id is None
    assert runner.rm_calls == []


def test_watched_launcher_events_probe_error_is_no_signal_never_cancels(
    tmp_path: Path,
) -> None:
    # The run id resolves (ps ok) but `fabro events` keeps erroring, and
    # there is no second source to consult -> no usable timestamp ->
    # no-signal -> never stalls. Proves an events-probe outage degrades to
    # no detection, not a false kill.
    runner = _ScriptedFabroRunner(events_jsons=["whatever"], events_exit=1)
    polls = {"n": 0}

    def _sleep_then_finish(_seconds: float) -> None:
        polls["n"] += 1
        if polls["n"] >= 5:
            runner.run_done.set()
            assert runner.run_returned.wait(timeout=1.0)

    journal = _RecordingJournal()
    launcher = WatchedFabroLauncher(sleep=_sleep_then_finish, clock=_advancing_clock())
    result = launcher.launch(
        plan=_plan(repo=tmp_path, stall_seconds=1000.0), runner=runner, journal=journal
    )
    assert result.stalled_run_id is None
    assert runner.rm_calls == []
