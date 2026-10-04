"""Each candidate attempt's own window, from the run's own event stream.

Binds the attribution half of `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority" -> "Cost follows every attempt in
a successful fallback run": "Token use and elapsed time MUST be attributed and
summed per candidate attempt, including failed attempts before the successful
fallback."

THE TWO NAMED EVENT FIELDS ARE BOTH LOAD-BEARING, so the fixtures here make them
disagree with any shortcut. `agent.acp.started` says WHICH candidate began a
node visit and WHEN (`candidate_index`, `occurred_at`, and the additive
`chain_deadline_epoch_ms`); `agent.acp.failover` says HOW LONG each attempted
candidate ran (`attempted_durations_ms`). A reader that used only the starts
would place every boundary at the next start, so the gap between one attempt
ending and the next beginning would vanish -- and the elapsed time the contract
requires per attempt would be a derived guess rather than the engine's own
measurement.

THE SUCCESSFUL ATTEMPT IS DELIBERATELY UNBOUNDED, which is the case most likely
to be "fixed" into a bug. No failover event records the duration of the attempt
that SUCCEEDED -- there was no transition away from it -- so its window has no
end. Closing it at the chain deadline instead would silently drop every token
the winning candidate spent after that instant, and the chain deadline bounds
when a NEW candidate may start, not when the winner must finish. Dropping usage
is the expensive direction: it under-reports a cost.
"""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_fallback_event_types import AcpEventScan
from livespec_orchestrator_beads_fabro.commands._acp_fallback_events import scan_acp_events

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_MODULE = "_acp_attempt_windows"
_MODULE_PATH = _COMMANDS / f"{_MODULE}.py"

# One base instant, with its epoch-millisecond form DERIVED from it rather than
# transcribed, so every expected boundary below is an offset from the same fact
# the fixtures are built from. A second hand-written timestamp is the shape that
# drifts.
_BASE = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)
_BASE_MS = int(_BASE.timestamp() * 1000)
_DEADLINE_MS = _BASE_MS + 600_000


def _instant(*, offset_ms: int) -> str:
    """An ISO-8601 instant `offset_ms` after the base, in the event wire format."""
    moment = _BASE + timedelta(milliseconds=offset_ms)
    return moment.isoformat().replace("+00:00", "Z")


def _identity(*, index: int, key: str) -> dict[str, Any]:
    return {
        "candidate_index": index,
        "display_name": f"display {key}",
        "candidate_key": key,
        "availability_key": "codex",
    }


def _start(*, index: int, offset_ms: int, **overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "type": "agent.acp.started",
        "node": "implement",
        "node_visit": 1,
        "candidate_index": index,
        "occurred_at": _instant(offset_ms=offset_ms),
        "primary_generation": "gen-a",
        "chain_deadline_epoch_ms": _DEADLINE_MS,
    }
    record.update(overrides)
    return record


def _failover(*, durations_ms: object, **overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "type": "agent.acp.failover",
        "schema_version": 1,
        "event_id": "ev-1",
        "occurred_at": _instant(offset_ms=0),
        "node": "implement",
        "node_visit": 1,
        "engine_attempt": 1,
        "from": _identity(index=0, key="claude-opus-5"),
        "to": _identity(index=1, key="gpt-5-5"),
        "hold_key": "codex",
        "cause": "quota",
        "scope": "availability-domain",
        "primary_generation": "gen-a",
        "full_chain": "chain-1",
        "attempted_durations_ms": durations_ms,
    }
    record.update(overrides)
    return record


def _scan(*, payload: list[dict[str, Any]]) -> AcpEventScan:
    scan = scan_acp_events(payload=payload)
    assert isinstance(scan, AcpEventScan), scan
    return scan


def _windows(*, payload: list[dict[str, Any]]) -> tuple[Any, ...]:
    """The attempt windows for one event payload, through an in-body import."""
    assert _MODULE_PATH.is_file(), _MODULE_PATH
    module = importlib.import_module(f"livespec_orchestrator_beads_fabro.commands.{_MODULE}")
    return module.attempt_windows(scan=_scan(payload=payload))  # pyright: ignore[reportAttributeAccessIssue]


def test_a_two_candidate_visit_yields_one_window_per_attempt() -> None:
    """Both the failed primary and the successful fallback get a window.

    "including failed attempts before the successful fallback" -- the failed
    attempt is the one a cost path is most likely to omit, because the run
    reports no result for it.
    """
    windows = _windows(
        payload=[
            _start(index=0, offset_ms=0),
            _failover(durations_ms=[120_000]),
            _start(index=1, offset_ms=125_000),
        ]
    )

    assert tuple(window.candidate_index for window in windows) == (0, 1)
    assert all(window.node == "implement" for window in windows)
    assert all(window.node_visit == 1 for window in windows)


def test_a_failed_attempt_is_bounded_by_its_reported_duration() -> None:
    """The failed attempt's end comes from `attempted_durations_ms`, not the next start.

    The fixture puts a 5-second gap between the primary's measured end and the
    fallback's start, so a reader that bounded the window at the next start
    would report 125_000 ms of elapsed time for an attempt the engine measured
    at 120_000.
    """
    windows = _windows(
        payload=[
            _start(index=0, offset_ms=0),
            _failover(durations_ms=[120_000]),
            _start(index=1, offset_ms=125_000),
        ]
    )

    primary = windows[0]
    assert primary.started_at_ms == _BASE_MS
    assert primary.elapsed_ms == 120_000
    assert primary.ended_at_ms == _BASE_MS + 120_000


def test_the_successful_attempt_is_unbounded_and_has_no_measured_elapsed_time() -> None:
    """No failover measured the winner, so its window has no end and no duration."""
    windows = _windows(
        payload=[
            _start(index=0, offset_ms=0),
            _failover(durations_ms=[120_000]),
            _start(index=1, offset_ms=125_000),
        ]
    )

    winner = windows[1]
    assert winner.started_at_ms == _BASE_MS + 125_000
    assert winner.elapsed_ms is None
    assert winner.ended_at_ms is None


def test_the_chain_deadline_is_carried_but_does_not_close_the_winner() -> None:
    """The deadline rides the window as reported context, never as a truncation.

    The deadline here is 600_000 ms after the base while the winner started at
    125_000 -- so a reader that closed the winner at the deadline would produce
    a plausible non-None end, and would drop every token the winner spent after
    it.
    """
    windows = _windows(
        payload=[
            _start(index=0, offset_ms=0),
            _failover(durations_ms=[120_000]),
            _start(index=1, offset_ms=125_000),
        ]
    )

    assert windows[1].chain_deadline_epoch_ms == _DEADLINE_MS
    assert windows[1].ended_at_ms is None


def test_an_attempt_with_no_recorded_duration_is_bounded_by_the_next_start() -> None:
    """A short durations list still bounds every attempt that HAS a successor.

    The engine reported one duration for a visit that ran three candidates, so
    index 1 has no measurement of its own. Its end comes from index 2's start,
    which is evidence rather than a guess -- the attempt had demonstrably
    finished by the time the next one began.
    """
    windows = _windows(
        payload=[
            _start(index=0, offset_ms=0),
            _failover(durations_ms=[120_000]),
            _start(index=1, offset_ms=125_000),
            _start(index=2, offset_ms=300_000),
        ]
    )

    middle = windows[1]
    assert middle.elapsed_ms is None
    assert middle.ended_at_ms == _BASE_MS + 300_000
    assert windows[2].ended_at_ms is None


def test_the_most_complete_durations_record_of_a_visit_is_used() -> None:
    """Two failovers in one visit: the longer list is the fuller record.

    The first failover knows only the primary's duration; the second knows both.
    Reading the first event encountered would leave the second attempt
    unmeasured even though the stream reported its duration.
    """
    windows = _windows(
        payload=[
            _start(index=0, offset_ms=0),
            _failover(durations_ms=[120_000], event_id="ev-1"),
            _start(index=1, offset_ms=125_000),
            _failover(durations_ms=[120_000, 60_000], event_id="ev-2"),
            _start(index=2, offset_ms=190_000),
        ]
    )

    assert windows[0].elapsed_ms == 120_000
    assert windows[1].elapsed_ms == 60_000
    assert windows[2].elapsed_ms is None


def test_each_node_visit_keeps_its_own_durations() -> None:
    """A second visit to the same node does not inherit the first visit's measurements."""
    windows = _windows(
        payload=[
            _start(index=0, offset_ms=0),
            _failover(durations_ms=[120_000], event_id="ev-1"),
            _start(index=1, offset_ms=125_000),
            _start(index=0, offset_ms=400_000, node_visit=2),
            _failover(durations_ms=[30_000], event_id="ev-2", node_visit=2),
            _start(index=1, offset_ms=440_000, node_visit=2),
        ]
    )

    by_visit = {(window.node_visit, window.candidate_index): window for window in windows}
    assert by_visit[(1, 0)].elapsed_ms == 120_000
    assert by_visit[(2, 0)].elapsed_ms == 30_000
    assert by_visit[(1, 1)].elapsed_ms is None
    assert by_visit[(2, 1)].elapsed_ms is None


def test_windows_from_separate_nodes_do_not_bound_each_other() -> None:
    """A later node's start is not the previous node's attempt boundary."""
    windows = _windows(
        payload=[
            _start(index=0, offset_ms=0),
            _start(index=0, offset_ms=500_000, node="review"),
        ]
    )

    by_node = {window.node: window for window in windows}
    assert by_node["implement"].ended_at_ms is None
    assert by_node["review"].ended_at_ms is None


def test_a_single_candidate_visit_yields_one_unbounded_window() -> None:
    """The ordinary non-fallback run: one attempt, from its start, open-ended.

    This is the shape every dispatch in this fleet produces today, and the
    contract keeps it priced "exactly as before": one window spanning the whole
    node means every observation lands on candidate zero.
    """
    windows = _windows(payload=[_start(index=0, offset_ms=0)])

    assert len(windows) == 1
    assert windows[0].candidate_index == 0
    assert windows[0].started_at_ms == _BASE_MS
    assert windows[0].ended_at_ms is None


def test_a_stream_with_no_started_events_yields_no_windows() -> None:
    """Durations alone cannot place an attempt, so an unstarted stream is empty."""
    assert _windows(payload=[_failover(durations_ms=[120_000])]) == ()


def test_an_unparseable_occurrence_time_places_no_window() -> None:
    """A start whose instant cannot be read cannot be positioned on the timeline.

    Returning a window anchored at some substitute instant would attribute
    every observation in the node to whichever candidate got the earlier
    substitute -- a confident wrong attribution rather than a visible gap.
    """
    assert _windows(payload=[_start(index=0, offset_ms=0, occurred_at="the other day")]) == ()


def test_an_unreadable_durations_field_leaves_every_attempt_unmeasured() -> None:
    """A malformed `attempted_durations_ms` costs the measurements, not the windows.

    Each variant below is a shape a future engine version could emit. The
    windows still exist -- the starts are readable -- so attribution continues
    on start order while elapsed time is honestly absent.
    """
    for durations in ("120000", [120_000, "fast"], [-5], [True], 120_000, None):
        windows = _windows(
            payload=[
                _start(index=0, offset_ms=0),
                _failover(durations_ms=durations),
                _start(index=1, offset_ms=125_000),
            ]
        )
        assert windows[0].elapsed_ms is None, durations
        assert windows[0].ended_at_ms == _BASE_MS + 125_000, durations


def test_an_unreadable_chain_deadline_is_absent_rather_than_zero() -> None:
    """A malformed deadline reads as None; zero would be a real instant in 1970."""
    for deadline in ("soon", True, -1, None, 1.5):
        windows = _windows(payload=[_start(index=0, offset_ms=0, chain_deadline_epoch_ms=deadline)])
        assert windows[0].chain_deadline_epoch_ms is None, deadline


def test_windows_are_ordered_by_node_visit_and_candidate_index() -> None:
    """A deterministic order, whatever order the stream delivered the starts in."""
    windows = _windows(
        payload=[
            _start(index=1, offset_ms=125_000),
            _start(index=0, offset_ms=400_000, node_visit=2),
            _start(index=0, offset_ms=0),
            _start(index=0, offset_ms=500_000, node="review"),
        ]
    )

    assert tuple((w.node, w.node_visit, w.candidate_index) for w in windows) == (
        ("implement", 1, 0),
        ("implement", 1, 1),
        ("implement", 2, 0),
        ("review", 1, 0),
    )


def test_a_duplicate_start_for_one_candidate_keeps_the_earliest_instant() -> None:
    """A re-delivered start does not mint a second attempt for the same candidate.

    The event stream is at-least-once, and the earliest instant is the one the
    attempt actually began at -- a later duplicate would shorten the window and
    orphan every observation before it.
    """
    windows = _windows(
        payload=[
            _start(index=0, offset_ms=0),
            _start(index=0, offset_ms=4_000),
        ]
    )

    assert len(windows) == 1
    assert windows[0].started_at_ms == _BASE_MS
