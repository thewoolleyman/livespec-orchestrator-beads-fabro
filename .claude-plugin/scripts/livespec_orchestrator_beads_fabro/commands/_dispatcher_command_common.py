"""Shared dispatcher command constants and terminal-failure alarm."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import run_id
from livespec_orchestrator_beads_fabro.commands._dispatcher_notify import (
    HttpNotifyPoster,
    NotifyPoster,
    notify_terminal,
    terminal_events,
)

__all__: list[str] = [
    "EXIT_FAILURE",
    "EXIT_PRECONDITION_ERROR",
    "alarm_on_terminal_failure",
]

EXIT_FAILURE = 1
EXIT_PRECONDITION_ERROR = 3


def alarm_on_terminal_failure(
    *,
    outcomes: list[DispatchOutcome],
    include_loop_summary: bool,
    journal: JournalFile,
    poster: NotifyPoster | None = None,
) -> None:
    """Fire the fail-open ntfy alarm for any terminal failure (0jxs gate).

    Called AFTER the verdict / exit code is computed, so it can never
    change it. Derives the leak-free alarm events (one per non-green
    outcome — `failed`/`blocked`, covering uvd's `host-only-refused` —
    plus a `non-green-loop` summary for the loop command), then posts them
    fail-open: a missing topic, an unreachable server, or any POST error
    is journaled and swallowed, never raised. A fully-green wave fires
    nothing. `poster` is injectable for the hermetic test tier; production
    is the real `HttpNotifyPoster`.
    """
    events = terminal_events(
        outcomes=tuple(outcomes),
        include_loop_summary=include_loop_summary,
    )
    notify_terminal(
        events=events,
        run_id=run_id(),
        poster=poster if poster is not None else HttpNotifyPoster(),
        journal=journal,
    )
