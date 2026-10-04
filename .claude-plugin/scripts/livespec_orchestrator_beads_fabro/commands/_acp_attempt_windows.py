"""Each candidate attempt's own window on the timeline, from one run's events.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Cost follows every attempt in a successful fallback run": "Token
use and elapsed time MUST be attributed and summed per candidate attempt,
including failed attempts before the successful fallback."

BOTH EVENT FIELDS ARE LOAD-BEARING AND NEITHER IS SUFFICIENT.
`agent.acp.started` says which candidate began a node visit and when;
`agent.acp.failover`'s `attempted_durations_ms` says how long each attempted
candidate actually ran. Bounding an attempt at the NEXT attempt's start instead
would fold the engine's teardown gap into the attempt, so the elapsed time the
contract requires per attempt would be a derived guess rather than the engine's
own measurement. Using only the durations would leave every attempt unplaced,
because a duration says nothing about when its attempt began.

THE SUCCESSFUL ATTEMPT IS UNBOUNDED, and this is the decision most likely to be
"tidied" into a defect. No failover event measures the attempt that SUCCEEDED --
there was no transition away from it to record one -- so its window has no end.
Closing it at `chain_deadline_epoch_ms` would look tidier and would silently
drop every token the winning candidate spent after that instant: the deadline
bounds when a NEW candidate may start, not when the winner must finish.
Under-reporting a cost is the expensive direction, so the deadline rides the
window as reported context and never truncates it.

AN UNPLACEABLE START YIELDS NO WINDOW, rather than a window at a substituted
instant. A substitute would attribute every observation in the node to whichever
candidate happened to get the earlier substitute -- a confident wrong
attribution, where an absent window is a gap the caller can see and report.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_fallback_event_types import (
    AcpEventScan,
    AcpFallbackEvent,
    AcpNodeStart,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_records import parse_hold_instant

__all__: list[str] = [
    "AcpAttemptWindow",
    "attempt_windows",
]

_MS_PER_SECOND = 1000


@dataclass(frozen=True, kw_only=True)
class AcpAttemptWindow:
    """One candidate attempt of one node visit, positioned on the timeline.

    `elapsed_ms` is the engine's OWN measurement of this attempt, present only
    when a failover event reported a duration for this candidate index. It is
    the "elapsed time" half of what the contract requires attributed per
    attempt, so it is deliberately not back-filled from the window's own
    boundaries: a derived number read back as a measurement is the thing this
    field exists to avoid.

    `ended_at_ms` is the attempt's close: its measured end when a duration was
    reported, else the next attempt's start (evidence that this one had
    finished), else `None` for an attempt nothing bounded -- which the
    successful final attempt of every chain is.
    """

    node: str
    node_visit: int
    candidate_index: int
    started_at_ms: int
    ended_at_ms: int | None
    elapsed_ms: int | None
    chain_deadline_epoch_ms: int | None


def attempt_windows(*, scan: AcpEventScan) -> tuple[AcpAttemptWindow, ...]:
    """Every placeable candidate attempt in one run's stream, in a stable order.

    Ordered by node, then node visit, then candidate index, so one run's
    windows are the same sequence however the stream delivered its events --
    which is what makes a cost derived from them reproducible.
    """
    placed = _placed_starts(starts=scan.starts)
    durations = _durations_by_visit(events=scan.events)
    windows = [
        _window(start=start, visit_starts=placed[visit], durations=durations.get(visit, ()))
        for visit in sorted(placed)
        for start in placed[visit]
    ]
    return tuple(windows)


def _placed_starts(
    *, starts: tuple[AcpNodeStart, ...]
) -> Mapping[tuple[str, int], tuple[tuple[AcpNodeStart, int], ...]]:
    """Every start that can be positioned, grouped by node visit and ordered.

    A candidate that started twice in one visit -- the event stream is
    at-least-once -- keeps its EARLIEST instant. A later duplicate would
    shorten the window and orphan every observation before it, which
    under-reports that attempt's usage.
    """
    earliest: dict[tuple[str, int], dict[int, tuple[AcpNodeStart, int]]] = {}
    for start in starts:
        moment = _epoch_ms(occurred_at=start.occurred_at)
        if moment is None:
            continue
        visit = earliest.setdefault((start.node, start.node_visit), {})
        held = visit.get(start.candidate_index)
        if held is None or moment < held[1]:
            visit[start.candidate_index] = (start, moment)
    return {key: tuple(visit[index] for index in sorted(visit)) for key, visit in earliest.items()}


def _durations_by_visit(
    *, events: tuple[AcpFallbackEvent, ...]
) -> Mapping[tuple[str, int], tuple[int, ...]]:
    """The fullest per-candidate duration list each node visit reported.

    A visit that failed over twice emits two events, and the earlier one knows
    only the earlier attempts' durations. Taking the LONGEST list keeps the
    most complete record; taking the first encountered would leave a measured
    attempt reading as unmeasured.
    """
    fullest: dict[tuple[str, int], tuple[int, ...]] = {}
    for event in events:
        key = (event.node, event.node_visit)
        if len(event.attempted_durations_ms) > len(fullest.get(key, ())):
            fullest[key] = event.attempted_durations_ms
    return fullest


def _window(
    *,
    start: tuple[AcpNodeStart, int],
    visit_starts: tuple[tuple[AcpNodeStart, int], ...],
    durations: tuple[int, ...],
) -> AcpAttemptWindow:
    """One attempt's window, from its own start plus its visit's other evidence."""
    record, started_at_ms = start
    index = record.candidate_index
    elapsed_ms = durations[index] if index < len(durations) else None
    return AcpAttemptWindow(
        node=record.node,
        node_visit=record.node_visit,
        candidate_index=index,
        started_at_ms=started_at_ms,
        ended_at_ms=_ended_at_ms(
            started_at_ms=started_at_ms,
            elapsed_ms=elapsed_ms,
            next_start_ms=_next_start_ms(index=index, visit_starts=visit_starts),
        ),
        elapsed_ms=elapsed_ms,
        chain_deadline_epoch_ms=record.chain_deadline_epoch_ms,
    )


def _ended_at_ms(
    *, started_at_ms: int, elapsed_ms: int | None, next_start_ms: int | None
) -> int | None:
    """The attempt's close, preferring its measurement over its successor's start."""
    if elapsed_ms is not None:
        return started_at_ms + elapsed_ms
    return next_start_ms


def _next_start_ms(*, index: int, visit_starts: tuple[tuple[AcpNodeStart, int], ...]) -> int | None:
    """When the next candidate of THIS node visit began, or None if none did.

    Scoped to the one visit on purpose: a later node's start, or a second visit
    to the same node, is not evidence about when this attempt finished.
    """
    for record, moment in visit_starts:
        if record.candidate_index > index:
            return moment
    return None


def _epoch_ms(*, occurred_at: str) -> int | None:
    """One ISO-8601 occurrence time as epoch milliseconds, or None when unreadable.

    Milliseconds rather than seconds because the engine reports attempt
    durations in milliseconds, and mixing the two units is how a boundary ends
    up a thousand times away from where the events put it.
    """
    moment = parse_hold_instant(text=occurred_at)
    if moment is None:
        return None
    return round(moment.timestamp() * _MS_PER_SECOND)
