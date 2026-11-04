"""Which confirmation turns an admission evaluation may run, and what performs them.

Split from `_dispatcher_acp_confirmation_seam` because this is the one module
that names the REAL performing half (`run_availability_probe`), and that half
cannot be imported from inside the preflight's own import closure -- see the
seam module's docstring for the cycle. Only the admission valve imports this.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._acp_availability_probe_run import (
    run_availability_probe,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_confirmation_seam import (
    ConfirmationTurns,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_file import JournalFile
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "confirmation_for",
]


def confirmation_for(
    *, journal: JournalFile, evaluated: tuple[WorkItem, ...]
) -> ConfirmationTurns | None:
    """The turns an admission evaluation of these items may run, or `None` for none.

    The FIRST evaluated item is the one charged: a turn establishes availability
    every peer then benefits from, and the attempt-cost record names only the item
    that spent it. An evaluation of no items has nothing to charge and so runs no
    turn.
    """
    if not evaluated:
        return None
    return ConfirmationTurns(
        perform=run_availability_probe, journal=journal, work_item_id=evaluated[0].id
    )
