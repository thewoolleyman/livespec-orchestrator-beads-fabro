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
refusal and an exclusion can never disagree about the recorded classification of
the same item.

THE FILTER EXISTS BECAUSE THE ROW ALONE WOULD STOP THE QUEUE. A wave-level
refusal refuses the WHOLE selection, so one held item at the head of the ranking
would refuse every dispatch behind it — and the drain would keep picking it
every pass, reporting a factory that cannot run while the work it could run sat
behind one item waiting on a human to ratify a proposal. That is the same reason
the Definition-of-Done judgement has a filter beside its row.

THE HOLD ITSELF SPENDS NO MODEL CALL, and that is what the ratified "needs no
model" wording buys: it is a read of the recorded classification and of the spec
history, so a provider outage cannot weaken it. What the ROW additionally spends
is the CLASSIFICATION the clause puts on every dispatch path — reuse-capped, so
one per item per specification version — because that is also what releases a
held item once its topic ratifies. The FILTER spends nothing at all: it runs
over every ready item in the tenant, and a classification there would turn one
drain pass into two model calls per ready row.

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

from livespec_orchestrator_beads_fabro.commands._dispatcher_criteria_wall_variant import (
    criteria_wall_variant,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    item_comment_bodies,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_spec_commitments import (
    ratified_proposal_topics,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import SPEC_DIRNAME
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_gate import (
    classify_item_spec_change_tier,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_hold import spec_change_hold
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    STAGE_DISPATCH,
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

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.commands._spec_change_tier_hold import SpecChangeHold
    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "classify_and_hold",
    "spec_change_tier_refusal",
    "spec_change_unrefused_candidates",
]


def classify_and_hold(
    *,
    item: WorkItem,
    repo: Path,
    path: StoreConfig,
    stage: str,
    runner: CommandRunner | None = None,
) -> SpecChangeHold | None:
    """Classify one item at this cadence point, then read the hold that stands.

    The ONE composition both armed cadence points take — the pre-dispatch wall
    row below and the filing-time route of `intake_dor` — because the clause
    puts the classification and the hold at the same positions: "At filing, at
    groom and again on every dispatch path, every implement-kind item MUST be
    classified", and then "The item MUST be held out of `ready` until BOTH
    hold".

    THE ORDER IS LOAD-BEARING AND IS WHAT RELEASES A HELD ITEM. The
    classification is reused only while the specification it was taken against
    is unchanged, so the revision that ratifies the linked topic retires the
    record that held the item; the classification is then re-taken against the
    RATIFIED tree, returns `stated`, and records a `none` tier — at which point
    the hold read below simply finds nothing holding the item. That is the
    clause's "the next intake or drain pass MUST release the hold with no human
    valve", and it needs no release pass of its own: a second mechanism for it
    would be a second authority on when a hold ends.

    Reading the hold FIRST would be the natural ordering and is the one that
    cannot release anything: the record that holds the item is still the newest
    one until the classification replaces it.

    THE HOLD IS THEN READ FROM THE LEDGER, not from the classification's own
    return value, and that is what keeps a did-not-run honest. "When the
    classification cannot run ... route it as it would without the
    classification" — and for an item that ALREADY carries a spec-change-tier
    record, routing as it would without the classification means that record
    still governs, which is exactly what the plan-child-disposition clause's
    "from that recorded classification" asks for. Reading the fresh outcome
    instead reports no tier at all on every provider outage, so one unavailable
    model RELEASES every held item in the tenant and the release reads exactly
    like a ratification. Measured while wiring this row: the wall's own
    unratified-topic case stopped refusing the moment the row began
    classifying, because the fixture has no judge.

    Re-reading costs one comment read per item and buys the ONE rule both
    answers come from — the newest record, which is the fresh one when the
    classification ran and the standing one when it did not.
    """
    _ = classify_item_spec_change_tier(item=item, repo=repo, path=path, stage=stage, runner=runner)
    return _held(
        item=item,
        config=path,
        ratified_topics=ratified_proposal_topics(spec_root=repo / SPEC_DIRNAME),
    )


def spec_change_tier_refusal(
    *, repo: Path, items: Sequence[WorkItem], workflow_name: str | None = None
) -> str | None:
    """The wall's refusal for the FIRST held item of this selection, or `None`.

    The refusal NAMES the topic, as the clause requires, and carries the verdict
    and the generalization target the classification recorded — the two things
    the operator needs to write the proposal, and the two a summary would drop.

    This row CLASSIFIES, which is what makes "again on every dispatch path"
    true of a dispatch rather than of an enumeration: it is scoped to the
    SELECTION this pass would claim, so the spend is one reuse-capped
    classification per item a dispatch is actually about. The drain's filter
    below deliberately classifies NOTHING — it runs over every ready item in the
    tenant, and a filter that could take a classification would turn one drain
    pass into two model calls per ready row.
    """
    if not items:
        return None
    config = _connection(repo=repo)
    if config is None:
        return None
    for item in items:
        if _exempt(repo=repo, item=item, workflow_name=workflow_name):
            continue
        hold = classify_and_hold(item=item, repo=repo, path=config, stage=STAGE_DISPATCH)
        if hold is not None:
            return hold.refusal
    return None


def spec_change_unrefused_candidates(
    *, items: Sequence[WorkItem], repo: Path, workflow_name: str | None = None
) -> list[WorkItem]:
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
        item
        for item in items
        if _exempt(repo=repo, item=item, workflow_name=workflow_name)
        or _held(item=item, config=config, ratified_topics=ratified) is None
    ]


def _exempt(*, repo: Path, item: WorkItem, workflow_name: str | None) -> bool:
    """Whether the tier is out of scope for this item's resolved variant.

    The clause scopes the classification to "every IMPLEMENT-KIND item", and a
    GROOM target is precisely not one: it reaches the groom door BECAUSE it is
    not yet decomposed into slices, and the groom run's own output is what
    produces the behaviour a judgement could be taken about. Classifying it
    would spend two model calls to judge an item whose asked-for behaviour is
    "decompose me", and the honest answer — a feature whose behaviour the spec
    does not state — would hold the groom door shut on the one run that could
    open it. Measured while wiring this row: a groom-pinned dispatch took the
    judgement and its own exemption test reported one call where none is owed.

    The resolution is the SHARED one, so this row and the two criteria rows
    above it exempt the same set — and an unresolvable variant reads as
    `implement`, the ARMED side, for the reason `criteria_wall_variant`'s own
    docstring gives: answering `groom` for an environment fault would let a
    directory or ledger fault promote an item past the tier.

    Both surfaces honour it, exactly as the Definition-of-Done judgement's pair
    does: a verdict recorded by an earlier build outlives the dispatch that
    wrote it, and the one change that would retire it is the decomposition the
    groom run has not been allowed to produce.
    """
    return criteria_wall_variant(
        repo=repo, work_item_id=item.id, workflow_name=workflow_name
    ).exempt


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
