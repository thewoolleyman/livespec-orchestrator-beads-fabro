"""Shared dispatcher command constants and terminal-failure alarm."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import run_id
from livespec_orchestrator_beads_fabro.commands._dispatcher_merge_wait_handoff import (
    HANDED_OFF_STATUS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_notify import (
    HttpNotifyPoster,
    NotifyPoster,
    notify_terminal,
    terminal_events,
)

__all__: list[str] = [
    "EXIT_BLOCKED",
    "EXIT_FAILURE",
    "EXIT_PRECONDITION_ERROR",
    "EXIT_UNGRADEABLE_CRITERIA",
    "alarm_on_terminal_failure",
    "dispatch_exit_code",
]

EXIT_FAILURE = 1
EXIT_PRECONDITION_ERROR = 3
EXIT_BLOCKED = 4
# The pre-dispatch wall's dedicated code, deliberately DISTINCT from the
# precondition exit 3: an ungradeable item is not a misconfigured invocation,
# and an operator triaging the difference reads it off the exit code alone
# (the dispatcher-exit-code clause of contracts.md).
EXIT_UNGRADEABLE_CRITERIA = 5


# A handed-off merge wait is a SUCCESSFUL dispatch: its pull request is armed and
# going to merge by itself, so the dispatch reports exit 0 under the Dispatcher's
# exit codes and no code is added or redefined.
_EXIT_ZERO_STATUSES = frozenset({"green", "capacity-deferred", HANDED_OFF_STATUS})


def dispatch_exit_code(*, outcomes: list[DispatchOutcome]) -> int:
    if all(outcome.status in _EXIT_ZERO_STATUSES for outcome in outcomes):
        return 0
    if all(outcome.status in {*_EXIT_ZERO_STATUSES, "blocked"} for outcome in outcomes):
        return EXIT_BLOCKED
    return EXIT_FAILURE


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
