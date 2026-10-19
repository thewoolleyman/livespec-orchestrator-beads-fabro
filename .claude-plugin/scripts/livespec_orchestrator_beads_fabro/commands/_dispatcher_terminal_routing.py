"""Where a NON-GREEN terminal leaves its work-item: the four peer routes.

Split out of `_dispatcher_loop_selection` by cohesion. That module owns the
POST-RUN SEQUENCE -- the acceptance valve, the provider-exhaustion record, the
event projection, the journal row, the preservation reference, the groom draft,
the needs-human pair, the calibration span -- while this owns the one question
those steps do not answer: given a terminal that is not green, what happens to
the slice.

THE THREE ARE PEERS AND ARE MUTUALLY EXCLUSIVE BY PREDICATE, which is why they
belong together and why their order among themselves cannot change which one
fires:

- a NON-CONVERGENCE bounce returns the slice to `backlog`, and fires on a
  `failed` status carrying the non-converged marker;
- a STALL-WATCHDOG cancellation releases the item to `ready` on its first
  cancel and parks it at `blocked / needs-human` on a repeat, and fires on the
  `stalled-no-progress` status;
- a PROVIDER-LIMIT release returns the item to `ready` for the ordinary
  admission valve, and fires on the `provider-limit-release` status.
- an EXTERNAL FABRO cancellation rests the item at `blocked / needs-human`,
  and fires on the `cancelled` status after naming the run and its factory in
  a ledger comment.

Each one is a no-op for every status but its own, so the sequence below is a
declaration of the complete route set rather than a priority order. Keeping
them in one place is what lets a reader see that no non-green terminal is left
with no disposition at all -- the property `_dispatcher_stall_disposition`'s
docstring records as the whole reason the stall arm had to exist once the
bounce stopped claiming cancellations.

DO NOT ADD A GUARD HERE THAT A STATUS ALREADY ENFORCES. The provider-limit
clause forbids a release from consuming rework-cap budget or being surfaced as
a needs-human decision, and that is enforced by its status matching none of the
predicates that would do those things. A guard in this module would suggest
those statuses are insufficient, and the next editor would weaken one.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_completion import (
    bounce_non_convergence_to_backlog,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_external_cancel_disposition import (
    dispose_external_fabro_cancel,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_disposition import (
    dispose_provider_limit_release,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_disposition import (
    dispose_stall_cancel,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["dispose_terminal_routing"]


def dispose_terminal_routing(
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
    now_iso: str,
) -> None:
    """Run every non-green terminal disposition; each declines what is not its own.

    `now_iso` is passed in rather than read here, for the reason the
    provider-exhaustion record takes its own clock from its caller: one
    post-run pass must describe ONE instant, and a second reading taken inside
    a disposition could date a hold a few milliseconds away from the row that
    announces it.
    """
    bounce_non_convergence_to_backlog(repo=repo, item=item, outcome=outcome, journal=journal)
    dispose_stall_cancel(repo=repo, item=item, outcome=outcome, journal=journal)
    dispose_external_fabro_cancel(repo=repo, item=item, outcome=outcome, journal=journal)
    dispose_provider_limit_release(
        repo=repo, item=item, outcome=outcome, journal=journal, now_iso=now_iso
    )
