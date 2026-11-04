"""Which declared factory an UNPINNED dispatch is placed on, and the record of it.

The factory-overflow-selection clause of `SPECIFICATION/contracts.md` fixes the
ranking: "The Dispatcher MUST place the dispatch on the candidate with a free
slot whose count divided by its `max_concurrent_runs` is smallest; ties go to the
earlier candidate. When no candidate has a free slot, the dispatch MUST be placed
on `dispatcher.default_factory`." `_dispatcher_overflow_factories` owns which
candidates there are and in what order; `_dispatcher_factory_capacity` owns what
each one reported; this owns the choice and the journal record of it.

WHY THE COMPARISON IS A RATIO AND NOT A COUNT, A FREE-SLOT TALLY, OR REMAINING
CAPACITY. Measured 2026-10-19, hp's scheduler reports `max_concurrent_runs` 10
and petri's reports 2, and the ratifying revision records that asymmetry as the
reason the rule exists: on a first-free-slot or most-free-slots rule the smaller
factory would almost never be selected. The ratio is also what makes the
equal-utilization case decidable — 5 of 10 and 1 of 2 are the same utilization
while differing on every absolute measure — and the clause then breaks that tie
toward the earlier candidate, which is the default.

WHY SELECTION NEVER REFUSES, DEFERS OR COUNTS. The clause says so outright:
"Selection MUST NOT refuse, defer, hold, delay or count a dispatch on capacity
grounds", because host concurrency belongs to the Fabro scheduler and a dispatch
placed on a saturated factory queues in that factory's own scheduler. So the
no-candidate arm is a PLACEMENT on the default and not a decision to wait, and
nothing in this module has a refusal to return.

WHY THE RECORD IS ONE ROW PER CANDIDATE RATHER THAN THE CHOSEN NAME. "The record
carries every candidate considered, in order, with the non-terminal run count and
`max_concurrent_runs` its server reported or the reason its read failed." A
record naming only the chosen factory cannot be read back to say WHY: a dispatch
that landed on the default is the ordinary outcome of a healthy ranking, of an
unreachable overflow factory, and of a build that never ranked anything, and
those three have completely different remedies.

WHY THE JOURNAL WRITE LIVES HERE AND THE SELECTION IS CALLED FROM TWO PLACES.
`_dispatcher_factory_ledger` resolves the unpinned target on two paths — the
pre-claim gates, which must leave the ledger exactly as they found it, and the
dispatch resolution, which records the chosen factory. Both rank; only the second
journals, which is what keeps the clause's "one record" one record.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import JournalWriter
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_capacity import (
    CapacityReader,
    FactoryCapacity,
    read_factory_capacity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overflow_factories import (
    overflow_candidates,
)

__all__: list[str] = [
    "OVERFLOW_SELECTION_STAGE",
    "REASON_LEAST_UTILIZED_FREE_SLOT",
    "REASON_NO_CANDIDATE_FREE_DEFAULT",
    "OverflowSelection",
    "journal_overflow_selection",
    "overflow_selection",
    "select_from_capacities",
]

OVERFLOW_SELECTION_STAGE = "overflow-factory-selection"
# The two reasons the clause enumerates, verbatim. They are the whole of what a
# reader needs to tell a ranking that chose from a free slot apart from one that
# found none and fell back.
REASON_LEAST_UTILIZED_FREE_SLOT = "least-utilized-free-slot"
REASON_NO_CANDIDATE_FREE_DEFAULT = "no-candidate-free-default"


@dataclass(frozen=True, kw_only=True)
class OverflowSelection:
    """One overflow selection: the chosen factory, the reason, and the evidence.

    `candidates` preserves CANDIDATE ORDER, which is load-bearing twice over: the
    clause requires the record to list them "in order", and the tie rule is
    stated in terms of which candidate is earlier.
    """

    chosen: str
    reason: str
    candidates: tuple[FactoryCapacity, ...]


def overflow_selection(
    *,
    repo: Path,
    reader: CapacityReader | None = None,
) -> OverflowSelection | None:
    """Rank this repository's candidates, or `None` when overflow does not apply.

    `None` means `dispatcher.overflow_factories` is absent, empty or refused, and
    every caller reads it as "resolve the factory exactly as before" — so a
    repository that configures nothing performs no capacity read at all.
    """
    candidates = overflow_candidates(cwd=repo)
    if not candidates:
        return None
    return select_from_capacities(
        capacities=tuple(
            read_factory_capacity(repo=repo, factory=candidate, reader=reader)
            for candidate in candidates
        )
    )


def select_from_capacities(*, capacities: Sequence[FactoryCapacity]) -> OverflowSelection:
    """The clause's ranking, as a pure function of what each candidate reported.

    The default is `capacities[0]` by construction rather than by name: the
    candidate list is built default-first, so the fallback arm and the tie rule
    both reduce to "the earliest", and there is no second place where which
    factory is the default could be decided differently.
    """
    free = [capacity for capacity in capacities if capacity.free_slot]
    if not free:
        return OverflowSelection(
            chosen=capacities[0].factory,
            reason=REASON_NO_CANDIDATE_FREE_DEFAULT,
            candidates=tuple(capacities),
        )
    # The candidate's POSITION rides the tuple, so the tie rule is stated rather
    # than inherited: `min` would return the first minimal element anyway, but
    # only as a property of this implementation of `min` over this list order,
    # and the clause's "ties go to the earlier candidate" is a requirement.
    # Comparison never reaches the third element, since the index is unique.
    _, _, chosen = min(
        (capacity.ranking_key, index, capacity) for index, capacity in enumerate(free)
    )
    return OverflowSelection(
        chosen=chosen.factory,
        reason=REASON_LEAST_UTILIZED_FREE_SLOT,
        candidates=tuple(capacities),
    )


def journal_overflow_selection(
    *,
    journal: JournalWriter,
    work_item_id: str,
    selection: OverflowSelection,
) -> None:
    """Record ONE overflow selection: every candidate, the choice, and the reason."""
    journal.append(
        record={
            "stage": OVERFLOW_SELECTION_STAGE,
            "work_item_id": work_item_id,
            "chosen": selection.chosen,
            "reason": selection.reason,
            "candidates": [dict(capacity.journal_fields()) for capacity in selection.candidates],
        }
    )
