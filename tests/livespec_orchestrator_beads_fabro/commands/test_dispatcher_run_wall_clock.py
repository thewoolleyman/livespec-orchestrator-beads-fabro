"""The whole-run wall budget's slot-holding clock (bd-ib-sdxfsn).

`SPECIFICATION/contracts.md` section "Dispatcher progress watchdog" -> "The
whole-run wall budget": "The budget clock MUST start at the instant the factory
first reports the run `running`. That instant is read from the run's own record
when the record carries it; otherwise it is the instant of the first watchdog
poll that observed the run `running`. Time a run spends queued before that
instant, including `runnable`, MUST NOT count, because a queued run holds no
slot."

The module import sits INSIDE each test body (the new-module pattern this
repo's decomposition slices use) so the Red commit fails on a genuine
assertion -- the module file's absence -- rather than at collection.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands import _node_timeouts
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget import (
    DEFAULT_RUN_WALL_BUDGET,
    RunWallBudget,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import REPOSITORY_LAYER

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_clock"

# A run submitted at 11:00:00Z that the factory only started running at
# 12:00:00Z: one hour queued, which holds no slot.
_SUBMITTED_EPOCH = 1_760_000_000.0
_FIRST_RUNNING_POLL_EPOCH = _SUBMITTED_EPOCH + 3600.0
_RECORDED_RUNNING_ISO = "2026-10-13T12:00:00Z"
_RECORDED_RUNNING_EPOCH = 1_791_892_800.0


def _module_path() -> Path:
    """Where the clock module lives, beside the node-timeout policy."""
    return Path(str(_node_timeouts.__file__)).with_name("_dispatcher_run_wall_clock.py")


def _clock() -> Any:
    """The clock module, imported inside a test body rather than at top."""
    assert _module_path().is_file(), f"{_module_path()} does not exist"
    return importlib.import_module(_MODULE)


def test_queue_time_before_the_first_running_poll_does_not_count() -> None:
    """A run that waited as `runnable` is measured from when it began running.

    The whole guarantee is STRUCTURAL rather than arithmetic: the start can
    only ever be fixed by a poll that OBSERVED the run running, so there is no
    expression in which a queued stretch could be added to it.
    """
    clock = _clock()
    start = clock.run_wall_start_from(
        recorded_epoch=None, observed_at_epoch=_FIRST_RUNNING_POLL_EPOCH
    )
    budget = RunWallBudget(seconds=3600.0, layer=REPOSITORY_LAYER)
    # One second short of the budget since it began RUNNING, and one second
    # short of twice the budget since it was submitted.
    now = _FIRST_RUNNING_POLL_EPOCH + 3599.0
    elapsed = clock.slot_holding_seconds(start=start, now_epoch=now)
    assert elapsed == 3599.0
    assert now - _SUBMITTED_EPOCH > budget.seconds
    assert clock.budget_exceeded(elapsed_seconds=elapsed, budget=budget) is False


def test_an_unfixed_start_measures_nothing_and_exceeds_nothing() -> None:
    """No running instant and no running poll is UNMEASURED, never zero.

    A zero would read as a run that has just started holding its slot, which
    compares as well within any budget and would hide the measurement failure
    behind a plausible number.
    """
    clock = _clock()
    assert clock.slot_holding_seconds(start=None, now_epoch=_FIRST_RUNNING_POLL_EPOCH) is None
    assert clock.budget_exceeded(elapsed_seconds=None, budget=DEFAULT_RUN_WALL_BUDGET) is False


def test_the_start_comes_from_the_run_record_when_it_carries_one() -> None:
    """A recorded running instant outranks the poll that observed it."""
    clock = _clock()
    start = clock.run_wall_start_from(
        recorded_epoch=_RECORDED_RUNNING_EPOCH,
        observed_at_epoch=_FIRST_RUNNING_POLL_EPOCH,
    )
    assert start.epoch == _RECORDED_RUNNING_EPOCH
    assert start.source == clock.RUN_RECORD_SOURCE
    poll_fixed = clock.run_wall_start_from(
        recorded_epoch=None, observed_at_epoch=_FIRST_RUNNING_POLL_EPOCH
    )
    assert poll_fixed.epoch == _FIRST_RUNNING_POLL_EPOCH
    assert poll_fixed.source == clock.FIRST_RUNNING_POLL_SOURCE
    assert clock.RUN_RECORD_SOURCE != clock.FIRST_RUNNING_POLL_SOURCE


def test_the_recorded_instant_is_read_off_the_runs_own_inspect_record() -> None:
    """The reader searches the record and its nested state sub-objects."""
    clock = _clock()
    assert (
        clock.recorded_running_epoch(payload=[{"running_at": _RECORDED_RUNNING_ISO}])
        == _RECORDED_RUNNING_EPOCH
    )
    assert (
        clock.recorded_running_epoch(payload={"status": {"running_since": _RECORDED_RUNNING_ISO}})
        == _RECORDED_RUNNING_EPOCH
    )
    assert clock.recorded_running_epoch(payload=None) is None
    assert clock.recorded_running_epoch(payload=[{"status": {"kind": "running"}}]) is None


def test_the_submission_instant_is_deliberately_not_a_running_instant() -> None:
    """`start_time` names when the run BEGAN, which includes its queued stretch.

    Reading it would make a run that waited an hour as `runnable` read as an
    hour into its budget the moment it started working -- the exact charge the
    queue-time clause forbids. The key set therefore names only the instant a
    run entered `running`.
    """
    clock = _clock()
    assert "start_time" not in clock.RUNNING_SINCE_KEYS
    assert "start_record" not in clock.RUNNING_SINCE_KEYS
    assert clock.recorded_running_epoch(payload=[{"start_time": _RECORDED_RUNNING_ISO}]) is None


def test_the_budget_is_exceeded_only_past_it() -> None:
    """Equality is not exceeded: the clause says strictly greater."""
    clock = _clock()
    budget = RunWallBudget(seconds=21600.0, layer=REPOSITORY_LAYER)
    assert clock.budget_exceeded(elapsed_seconds=21600.0, budget=budget) is False
    assert clock.budget_exceeded(elapsed_seconds=21600.5, budget=budget) is True


def test_a_start_in_the_future_measures_zero_rather_than_a_negative_span() -> None:
    """Clock skew between this host and the factory cannot run the clock backwards.

    A negative span would compare as comfortably within any budget, which is
    the same silence an unmeasured start would produce while looking like a
    measurement.
    """
    clock = _clock()
    start = clock.run_wall_start_from(
        recorded_epoch=_RECORDED_RUNNING_EPOCH + 120.0,
        observed_at_epoch=_RECORDED_RUNNING_EPOCH,
    )
    assert clock.slot_holding_seconds(start=start, now_epoch=_RECORDED_RUNNING_EPOCH) == 0.0
