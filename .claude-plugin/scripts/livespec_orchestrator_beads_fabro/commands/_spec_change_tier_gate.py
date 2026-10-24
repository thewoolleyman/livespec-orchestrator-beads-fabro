"""The composed spec-change-tier decision for ONE item: classify, then hold.

The autonomy-tier bullet puts TWO readings in one decision and gives them
opposite failure directions, which is the whole reason they are composed here
rather than at each call site. The CLASSIFICATION is a model call and fails
OPEN — "When the classification cannot run ..., intake MUST record that on the
item and route it as it would without the classification". The HOLD is a read
of the recorded classification plus the spec history, needs no model, and fails
CLOSED. A call site that composed them itself would get the directions the
wrong way round in exactly one of the two arms, and both arms produce a
well-formed answer.

THE ORDER IS MECHANICAL-FIRST, AND IT IS A COST RULE AS WELL AS A CORRECTNESS
ONE. An item whose recorded classification holds and whose linked topic has not
ratified is held with NO model call at all, because nothing a fresh judgement
could return would release it: the clause requires BOTH conditions, and one of
them is already false. That is the clause's own "needs no model", and a gate
that re-classified such an item would spend one per held row per pass for an
answer it already had.

A HELD ITEM WHOSE TOPIC HAS RATIFIED IS RE-JUDGED RATHER THAN HELD, and this is
the arm that makes the hold releasable at all. Ratification is only half of the
release; the other half is the judgement returning `stated` against the ratified
specification, and only a fresh taking can answer it. A gate that kept holding
here would make every hold permanent, with the ratification an operator earned
changing nothing.

A CLASSIFICATION THAT COULD NOT RUN FALLS BACK ON THE RECORDED ONE, which is the
precise sense in which the clause's fail-open applies to the CLASSIFICATION and
not to the hold. An UNLABELLED item routes as it would without the judgement —
there is nothing recorded to hold it — while an item already labelled
spec-change tier stays held, because its label is a standing measurement that an
outage in the judging path does not retire.

AN UNREADABLE COMMENT SIDECAR HOLDS NOTHING, which is the same fail-open reading
`_dispatcher_dod_judgement_gate` takes for the same read: the comments are both
where a recorded classification is read from and where a fresh one is written
to, so an item whose sidecar cannot be read is one nothing can be concluded
about — and emptying the queue on a transient ledger fault reads exactly like a
factory with no work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    item_comment_bodies,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading_judge import (
    SPECIFICATION_DIRNAME,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    SpecChangeTierVerdict,
    linked_proposal_topic,
    recorded_spec_change_tier,
    spec_change_tier_comment,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_judge import (
    SpecChangeTierReader,
    host_spec_change_tier_reader,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_ratification import (
    topic_is_ratified,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "SpecChangeHold",
    "spec_change_tier_hold",
    "standing_spec_change_hold",
]

_LEDGER_READ_ERRORS = (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
)
_NO_TOPIC = "no linked proposed-change topic"
_NO_TARGET = "no existing heading to generalize"


@dataclass(frozen=True, kw_only=True)
class SpecChangeHold:
    """One item held out of `ready` by the spec-change tier.

    The topic and the generalization target ride WITH the hold because the
    clause requires the refusal to NAME the unratified topic: a hold carrying
    only the work-item id sends an operator to the item, where nothing they can
    edit clears it, rather than to the proposal that has to ratify.
    """

    work_item_id: str
    linked_proposal_topic: str | None = None
    generalization_target: str | None = None

    @property
    def detail(self) -> str:
        """What a refusal says, naming the topic an operator must get ratified."""
        topic = (
            _NO_TOPIC
            if self.linked_proposal_topic is None
            else f"proposed-change topic {self.linked_proposal_topic!r}"
        )
        target = (
            _NO_TARGET
            if self.generalization_target is None
            else f"generalize {self.generalization_target!r}"
        )
        return (
            f"work-item {self.work_item_id} is spec-change tier: the spec-stated"
            " judgement does not report its asked-for behaviour as stated by the"
            f" ratified specification, and it carries {topic} with a ratifying"
            f" revision record. File or ratify that proposal ({target}); the item"
            " is released with no human valve once the topic carries decision"
            " accept or modify and the judgement returns stated."
        )


def standing_spec_change_hold(
    *, work_item_id: str, repo: Path, comments: Sequence[str]
) -> SpecChangeHold | None:
    """The mechanical hold, taking no judgement at all.

    `None` both when no classification is recorded, when the recorded one does
    not hold, and when the recorded hold's linked topic has since ratified. The
    third is NOT a release — it is the one state in which a fresh judgement can
    still change the answer, so the decision passes to the composed gate rather
    than being made here.
    """
    recorded = _recorded_hold(work_item_id=work_item_id, comments=comments)
    if recorded is None:
        return None
    ratified = topic_is_ratified(
        spec_root=repo / SPECIFICATION_DIRNAME, topic=recorded.linked_proposal_topic
    )
    return None if ratified else recorded


def spec_change_tier_hold(
    *,
    item: WorkItem,
    repo: Path,
    path: StoreConfig,
    stage: str,
    runner: CommandRunner | None = None,
    reader: SpecChangeTierReader | None = None,
) -> SpecChangeHold | None:
    """Classify where the clause requires it, then report the standing hold."""
    comments = item_comment_bodies(path=path, work_item_id=item.id)
    if comments is None:
        return None
    standing = standing_spec_change_hold(work_item_id=item.id, repo=repo, comments=comments)
    if standing is not None:
        return standing
    verdict = _classified(item=item, repo=repo, path=path, runner=runner, reader=reader)
    if verdict is None:
        return _recorded_hold(work_item_id=item.id, comments=comments)
    append_work_item_comment(
        path=path,
        work_item_id=item.id,
        body=spec_change_tier_comment(item_id=item.id, stage=stage, verdict=verdict),
    )
    return _hold_of(item_id=item.id, verdict=verdict)


def _classified(
    *,
    item: WorkItem,
    repo: Path,
    path: StoreConfig,
    runner: CommandRunner | None,
    reader: SpecChangeTierReader | None,
) -> SpecChangeTierVerdict | None:
    """One fresh classification, with the item's own linked topic resolved."""
    topic = _declared_topic(path=path, item=item)
    read = (
        host_spec_change_tier_reader(runner=ShellCommandRunner() if runner is None else runner)
        if reader is None
        else reader
    )
    return read(
        item=item,
        repo=repo,
        linked_topic=topic,
        topic_ratified=topic_is_ratified(spec_root=repo / SPECIFICATION_DIRNAME, topic=topic),
    )


def _declared_topic(*, path: StoreConfig, item: WorkItem) -> str | None:
    """The proposed-change topic this item's labels declare, or `None` for none.

    Read through the CONNECTION THE CALLER ALREADY HOLDS rather than through
    `read_dispatch_labels`, which resolves one from the repository root. Both
    callers reach this with a `StoreConfig` in hand — intake was handed one and
    the wall resolved one before it read a single item — so re-resolving would
    be a second reading of the same configuration that can disagree with the
    first, and it raises outright on a repository whose `connection.prefix` is
    unset, which is a bug-class escape through the intake router.

    Every failure is routed as DATA for the reason the clause gives the
    classification: a failure to read the labels is the same absence an
    unlabelled item presents, so the classification proceeds with no linked
    topic rather than refusing over a transient ledger fault.
    """
    record = attempt(
        action=lambda: make_beads_client(config=path).show_issue(issue_id=item.id),
        exceptions=_LEDGER_READ_ERRORS,
    )
    if isinstance(record, AttemptFailure):
        return None
    labels = record.get("labels")
    if not isinstance(labels, list):
        return None
    raw = cast("list[object]", labels)
    return linked_proposal_topic(raw_labels=[one for one in raw if isinstance(one, str)])


def _recorded_hold(*, work_item_id: str, comments: Sequence[str]) -> SpecChangeHold | None:
    """The hold the item's NEWEST recorded classification stands for, or `None`.

    Keyed on the ID rather than on a whole `WorkItem`, because the id is all a
    hold carries and the plan-child disposition reaches this with a beads
    record rather than a materialized item — a `WorkItem` parameter there would
    be a second materialization taken only to be discarded.
    """
    recorded = recorded_spec_change_tier(comments=comments)
    if recorded is None:
        return None
    return _hold_of(item_id=work_item_id, verdict=recorded)


def _hold_of(*, item_id: str, verdict: SpecChangeTierVerdict) -> SpecChangeHold | None:
    """One verdict as a hold, or `None` when it decides the item is not held."""
    if not verdict.holds:
        return None
    return SpecChangeHold(
        work_item_id=item_id,
        linked_proposal_topic=verdict.linked_proposal_topic,
        generalization_target=verdict.generalization_target,
    )
