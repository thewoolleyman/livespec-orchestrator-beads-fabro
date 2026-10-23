"""The pre-dispatch wall's spec-change-tier row, and the drain's own filter.

The second half of the autonomy-tier bullet of `SPECIFICATION/contracts.md`:
"the pre-dispatch wall MUST refuse a held item with exit code `5` naming the
unratified topic". The exit-code enumeration of the same file names it among
the exit-`5` refusals, so this row shares that code with the two
effective-criteria rows it sits beside rather than claiming one of its own.

WHY THE WALL ROW AND THE DRAIN FILTER ARE TWO SHAPES OF ONE DECISION, exactly as
`_dispatcher_dod_judgement_wall` describes its own pair. The row answers "why may
this NAMED selection not run" and renders the refusal an operator reads; the
filter answers "which rows may this pass advertise" and runs over every ready
item in the tenant. Both consume `_spec_change_tier_hold.spec_change_hold`, so a
refusal and an exclusion can never disagree about the same item.

THE FILTER EXISTS BECAUSE THE ROW ALONE WOULD STOP THE QUEUE. A wave-level
refusal refuses the WHOLE selection, so one held item at the head of the ranking
would refuse every dispatch behind it — and the drain would keep picking it
every pass, reporting a factory that cannot run while the work it could run sat
behind one item waiting on a human to ratify a proposal. That is the same reason
the Definition-of-Done judgement has a filter beside its row.

NEITHER SURFACE SPENDS A MODEL CALL, and that is what the ratified "needs no
model" wording buys. Both read the recorded classification and the spec history,
so the filter costs one ledger read per ready item and the row costs one per
named item — no provider request, no judgement, nothing a provider outage can
take away.

AN UNREADABLE LEDGER REFUSES NOTHING AND DROPS NOTHING. The comment sidecar is
where the recorded classification lives, so a sidecar that could not be read is
the absence of evidence that a hold stands rather than evidence that none does —
and holding there would empty the queue on a transient ledger fault, which reads
exactly like a factory with no work. The plan-child disposition takes the
OPPOSITE direction on the same absence because its own clause requires it; that
asymmetry is deliberate and each half is stated where it is required.

THE ROW REFUSES ON THE FIRST HELD ITEM OF THE SELECTION, which is how every row
of this wall reports: the operator repairs one thing at a time, and a refusal
enumerating a wave's every fault is a refusal nobody reads to the end.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    item_comment_bodies,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_spec_commitments import (
    ratified_proposal_topics,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_hold import spec_change_hold
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    recorded_spec_change_tier,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._spec_change_tier_hold import SpecChangeHold
    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "SPEC_DIRNAME",
    "spec_change_tier_refusal",
    "spec_change_unrefused_candidates",
]

# Where the governed spec tree sits under a dispatch target, spelled as the
# Definition-of-Done judgement's own resolution spells it so the ratification
# read and that judgement cannot disagree about which tree is governing.
SPEC_DIRNAME = "SPECIFICATION"


def spec_change_tier_refusal(*, repo: Path, items: Sequence[WorkItem]) -> str | None:
    """The wall's refusal for the FIRST held item of this selection, or `None`.

    The refusal NAMES the topic, as the clause requires, and carries the verdict
    and the generalization target the classification recorded — the two things
    the operator needs to write the proposal, and the two a summary would drop.
    """
    if not items:
        return None
    config = _connection(repo=repo)
    if config is None:
        return None
    ratified = ratified_proposal_topics(spec_root=repo / SPEC_DIRNAME)
    for item in items:
        hold = _held(item=item, config=config, ratified_topics=ratified)
        if hold is not None:
            return hold.refusal
    return None


def spec_change_unrefused_candidates(*, items: Sequence[WorkItem], repo: Path) -> list[WorkItem]:
    """This enumeration's candidates, with every held row dropped.

    The caller's ORDER is preserved rather than re-sorted, exactly as the two
    filters beside this one preserve it and for the same reason: the canonical
    ranking authority is upstream, and re-ordering here would put a second one
    behind the id a consumer reads off the result.
    """
    if not items:
        return []
    config = _connection(repo=repo)
    if config is None:
        return list(items)
    ratified = ratified_proposal_topics(spec_root=repo / SPEC_DIRNAME)
    return [
        item for item in items if _held(item=item, config=config, ratified_topics=ratified) is None
    ]


def _connection(*, repo: Path) -> StoreConfig | None:
    """This repository's ledger connection, or `None` when it cannot be resolved.

    A repository that declares no `connection.prefix`, or whose
    `.livespec.jsonc` cannot be read, is one no recorded classification can be
    read from — so both surfaces above fail toward the behaviour they had
    without the tier. Unwrapped, that resolution raises from inside the
    pre-dispatch wall, which is a bug-class escape on the path whose whole
    purpose is rendering actionable refusals.
    """
    resolved = attempt(
        action=lambda: store_config(repo=repo),
        exceptions=(ConnectionPrefixMissingError, LivespecConfigUnreadableError),
    )
    return None if isinstance(resolved, AttemptFailure) else resolved


def _held(
    *, item: WorkItem, config: StoreConfig, ratified_topics: Collection[str]
) -> SpecChangeHold | None:
    """This item's standing hold, taking no judgement and reaching no provider.

    `item_comment_bodies` answers `None` for a sidecar it could not read and the
    EMPTY TUPLE for an item carrying no comments, and those are deliberately
    different answers at the surface that WRITES — but for this read they
    coincide exactly, because both reduce to "no classification is recorded" and
    the module docstring's fail-open direction is the answer to both. So the two
    are collapsed HERE rather than branched on: a branch whose two arms return
    the same value is a branch a later editor changes one arm of, and the arm
    that would change is the one nothing in a healthy tenant can reach.
    """
    bodies = item_comment_bodies(path=config, work_item_id=item.id)
    return spec_change_hold(
        work_item_id=item.id,
        recorded=recorded_spec_change_tier(comments=bodies or ()),
        ratified_topics=ratified_topics,
    )
