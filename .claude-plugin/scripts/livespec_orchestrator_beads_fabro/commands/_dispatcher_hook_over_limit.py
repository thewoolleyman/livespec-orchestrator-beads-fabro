"""A git commit or push ended by a limit while its repository hook still ran.

WHAT THE EVENT IS, AND WHY IT NEEDS A NAME OF ITS OWN.
`SPECIFICATION/contracts.md` section "ACP node timeouts" -> "Repository hooks
that outlive a limit" defines a `hook-over-limit` event as a git commit or push
ended by one of two limits -- an agent's per-tool-call limit, or the resolved
timeout of a command node that commits or pushes -- WHILE a hook run it started
was still executing. The discrimination is the whole point: a push ended by a
limit BEFORE its hook started, or AFTER its hook finished, is not this event and
"keeps its existing failure classification". Without the distinction every
publication timeout reads as one undifferentiated stall, and the remedy differs
-- a hook that needs more budget is a configuration decision, while a push that
timed out with no hook running is a network or forge fault.

WHY THE GRAMMAR LIVES HERE AND IS SPELLED ONCE. The event is OBSERVED inside the
sandbox, by the materialized program `_dispatcher_hook_limit_program` lands
there, and CONSUMED on the host, by the journal row and the needs-human cause
below. Those are two processes that never share an import, so the sentinel is the
only thing holding them together. It is declared here and SUBSTITUTED into the
program's source, for the same reason `_dispatcher_publication_head` substitutes
its label rather than typing it twice: a sentinel spelled independently at both
ends drifts silently, and the failure is an event that is observed, reported, and
then read by nothing.

WHY THE ROW IS WRITTEN WHETHER OR NOT THE RUN RECOVERS. The clause says so in as
many words -- "For every `hook-over-limit` event the run MUST record a
`hook-over-limit` row ... whether or not the run later recovers". A row written
only for a run that then died would make the journal an account of outcomes
rather than of observations, and the recovered events are exactly the ones that
show a budget running out before it bites.

AND WHY THE CAUSE LINES ARE SEPARATE FROM THE ROW. A recovered event MUST NOT be
named as the cause of a later needs-human ending that has a different cause, so
the row and the cause are written at different moments by different deciders: the
row records that the event happened, and the cause is rendered only where the
ending is attributed to it. Collapsing them into one renderer is what would make
every run that ever saw a slow hook report that hook as its reason for stopping.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import (
        JournalWriter,
    )

__all__: list[str] = [
    "HOOK_OVER_LIMIT_JOURNAL_STAGE",
    "HOOK_OVER_LIMIT_SENTINEL",
    "HookOverLimit",
    "hook_over_limit_cause_lines",
    "hook_over_limit_from_text",
    "journal_hook_over_limit",
]

# The sentinel the in-sandbox observer prints and this module reads. One
# spelling, substituted into the observer's source -- see the module docstring.
HOOK_OVER_LIMIT_SENTINEL = "LIVESPEC_HOOK_OVER_LIMIT"

# The journal row's stage name, which is the word the contract uses.
HOOK_OVER_LIMIT_JOURNAL_STAGE = "hook-over-limit"

# The four facts the clause requires the row to name, in the order the observer
# prints them. `node` and `operation` are bounded words rather than `\S+` so a
# line of ordinary stage output that happens to carry the sentinel cannot be read
# as an event; the two integers are what the clause asks for in seconds and
# milliseconds respectively.
_EVENT_PATTERN = re.compile(
    "".join(
        (
            re.escape(HOOK_OVER_LIMIT_SENTINEL),
            r": node=(?P<node>[a-z_]+) ",
            r"operation=(?P<operation>commit|push) ",
            r"limit_seconds=(?P<limit_seconds>\d+) ",
            r"hook_elapsed_ms=(?P<hook_elapsed_ms>\d+)",
        )
    )
)


@dataclass(frozen=True, kw_only=True)
class HookOverLimit:
    """One observed `hook-over-limit` event, as the sandbox reported it.

    `hook_elapsed_ms` is the hook RUN's elapsed time at the moment the limit
    ended the operation, not the operation's own duration. The two differ
    whenever the hook started late, which is the ordinary case for a push: the
    hook does not begin until git has reached the remote.
    """

    node: str
    operation: str
    limit_seconds: int
    hook_elapsed_ms: int


def hook_over_limit_from_text(*, text: str) -> HookOverLimit | None:
    """The event one run's output reports, or None when it reports none.

    None is the ordinary answer and is NOT a failure to read: the overwhelming
    majority of runs never approach a publication limit, and a run whose push
    timed out with no hook running is required to report nothing here.
    """
    match = _EVENT_PATTERN.search(text)
    if match is None:
        return None
    return HookOverLimit(
        node=match.group("node"),
        operation=match.group("operation"),
        limit_seconds=int(match.group("limit_seconds")),
        hook_elapsed_ms=int(match.group("hook_elapsed_ms")),
    )


def journal_hook_over_limit(
    *,
    journal: JournalWriter,
    work_item_id: str,
    event: HookOverLimit | None,
) -> None:
    """Record the event in the dispatch journal, if one was observed.

    Takes the ALREADY-PARSED event rather than the run text, because the
    needs-human cause needs the same event and a second parse of the same output
    is a second reading nothing could prove agrees with the first.

    The `JournalWriter` Protocol is imported under TYPE_CHECKING, the way
    `_dispatcher_engine_journal` imports it: `_dispatcher_engine_types` imports
    this module at runtime for the outcome's own field, so a runtime import
    back would close a cycle.
    There is deliberately no defensive `getattr` around `append` -- the sole
    caller is the engine, whose writer always has one, and a branch no test can
    reach is dead code rather than safety.
    """
    if event is None:
        return
    journal.append(
        record={
            "work_item_id": work_item_id,
            "stage": HOOK_OVER_LIMIT_JOURNAL_STAGE,
            "node": event.node,
            "operation": event.operation,
            "limit_seconds": event.limit_seconds,
            "hook_elapsed_ms": event.hook_elapsed_ms,
        }
    )


def hook_over_limit_cause_lines(*, event: HookOverLimit | None) -> tuple[str, ...]:
    """The needs-human cause's account of this ending, when it caused one.

    Rendered ONLY where the ending is attributed to the event -- see the module
    docstring on why this is not the row's renderer. The first line names the
    classification, the node and the operation, which are the three things the
    clause requires "so that the stop is not presented as an agent's decision";
    the second says outright that no question is pending, because a needs-human
    record a reader scans for a question is exactly where this ending gets
    mistaken for one.
    """
    if event is None:
        return ()
    return (
        f"transport fault: {HOOK_OVER_LIMIT_JOURNAL_STAGE}",
        (
            f"classification: the {event.node} node's {event.operation} was ended by its "
            f"resolved {event.limit_seconds}s limit while a repository hook run it started "
            f"was still executing, {event.hook_elapsed_ms}ms in; no agent asked anything"
        ),
    )
