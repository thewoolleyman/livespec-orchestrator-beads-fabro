"""The ONE composed spec-change-tier classification, for every cadence point.

The autonomy-tier bullet of `SPECIFICATION/contracts.md` puts the classification
at three positions — "At filing, at groom and again on every dispatch path,
every implement-kind item MUST be classified" — and this is the one function all
three call. Two implementations could not share a record they digest
differently, so the decision is one function and the positions differ only in
the `stage` the record names.

THE ORDER IS REUSE, THEN CLASSIFY, THEN JUDGE, THEN RECORD, and it is the
cheap-first order the clause's own economy implies. The reuse read is a ledger
read the drain already pays for; the classification and the judgement are a
model call each; recording is a write that can never be taken back, because
beads comments are append-only. Putting the reuse read anywhere but first spends
two model calls per item per pass on items nothing about has changed.

THE CLASSIFICATION RUNS BEFORE THE JUDGEMENT, and the saving is the point rather
than a nicety: three of the four classes are exempt outright ("An item
classified `bug`, `chore` or `non_functional` is never spec-change tier"), so a
`bug` never pays for the judgement at all — and the judgement is the expensive
call, because its prompt carries the condensed ratified tree while the
classification's carries one item's title and description.

A JUDGEMENT THAT CANNOT RUN RECORDS THAT IT DID NOT, AND ROUTES AS BEFORE. The
clause is explicit: "When the classification cannot run (no eligible model, a
timeout, or an unparseable verdict), intake MUST record that on the item and
route it as it would without the classification; the `dod_gate` node, which runs
the same judgement in-run, remains the backstop that refuses an unstated feature
before any implementation spend." So an unavailable classifier yields NO
recorded tier — not a `none` tier, which would read as a classification that ran
and found the item free, and which the hold read would then treat as a release.

THE DID-NOT-RUN RECORD IS CAPPED AT ONE PER DISTINCT CAUSE, read back off the
item exactly as the Definition-of-Done judgement caps its own. Without the cap a
provider outage writes one comment per item per pass, which on a drain that
runs every ten minutes buries the item's real history under its own alarm.

WHAT THE REUSE CONDITION IS, AND WHY IT IS THE STATEMENT AND NOT THE GOAL. A
verdict is reusable while "its input and the spec identity it was taken against
are both unchanged", and the input of both calls here is the ASKED-FOR BEHAVIOUR
— the statement the judgement is handed and the title and description the
classifier weighs. The rendered GOAL additionally carries every ledger comment
the item has accumulated, and digesting that would be self-defeating in the most
literal way: this gate's own record is one of those comments, so every
classification would invalidate itself and the next pass would re-judge for
ever. Rider-driven invalidation of the Definition-of-Done judgement's own
verdicts is that judgement's concern and is owned separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_runtime import spec_stated
from returns.pipeline import is_successful

from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    item_comment_bodies,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._drift_run_judge import drift_judge
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    FEATURE_CLASS,
    SPEC_DIRNAME,
    asked_for_behaviour,
    behaviour_digest,
    decide_spec_change_tier,
    exempt_decision,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    classification_did_not_run_comment,
    recorded_did_not_run_causes,
    recorded_spec_change_tier,
    reusable_spec_change_tier,
    spec_change_tier_comment,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import (
    judge_within_ceiling,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.spec_reader import read_current_specification

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
        SpecChangeTierDecision,
    )
    from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
        RecordedSpecChangeTier,
    )
    from livespec_orchestrator_beads_fabro.types import SpecSnapshot, StoreConfig, WorkItem

__all__: list[str] = [
    "CAUSE_CLASSIFICATION_UNREADABLE",
    "CAUSE_LEDGER_UNREADABLE",
    "CAUSE_SPEC_TREE_UNREADABLE",
    "CAUSE_VERDICT_UNREADABLE",
    "SpecChangeTierOutcome",
    "classify_item_spec_change_tier",
    "classify_spec_change_tier",
]

# The four conditions under which the classification does not run, as
# self-describing words rather than a shared "unavailable": the record is what
# an operator reads to find out why the tier is missing, and each of these sends
# them somewhere different — a provider fault, a model answering outside its own
# vocabulary, a spec tree nobody could read, or a ledger nobody could read.
CAUSE_CLASSIFICATION_UNREADABLE = "classification-answer-unreadable"
CAUSE_VERDICT_UNREADABLE = "spec-stated-verdict-unreadable"
CAUSE_SPEC_TREE_UNREADABLE = "spec-tree-unreadable"
CAUSE_LEDGER_UNREADABLE = "ledger-comments-unreadable"


@dataclass(frozen=True, kw_only=True)
class SpecChangeTierOutcome:
    """What one cadence point learned, and whether anything was spent learning it.

    `recorded` is the classification that NOW STANDS against the item, which is
    `None` exactly when the classification did not run — and `cause` then names
    why. The two are reported together rather than as one optional, because a
    caller routing the item needs both: the tier to route by, and the cause to
    say in its own record that it routed without one.

    `reused` is reported rather than inferred from `recorded`, because a reused
    classification and a freshly-taken identical one are indistinguishable by
    value — and the cap the clause's economy rests on is about the SPEND, not the
    answer.
    """

    work_item_id: str
    recorded: RecordedSpecChangeTier | None
    cause: str | None = None
    reused: bool = False

    @property
    def is_spec_change(self) -> bool:
        """Whether the standing classification puts the item in the tier.

        `False` for an item whose classification did not run, which is the
        route-as-before direction the clause requires — not a claim that the
        item is free, which is what `recorded is None` says and what a caller
        records.
        """
        return self.recorded is not None and self.recorded.is_spec_change


def classify_spec_change_tier(
    *,
    item: WorkItem,
    repo: Path,
    stage: str,
    comments: Sequence[str],
    append: Callable[..., None],
    runner: CommandRunner | None = None,
) -> SpecChangeTierOutcome:
    """Reuse the recorded classification, else take it and record it.

    `comments` is read ONCE by the caller and spent twice here: the reuse scan
    reads the recorded classification among them, and the did-not-run cap reads
    the causes among them. One read is what makes the record this decision
    compares the record it would replace — a second read could see a comment the
    first did not.

    The SPEC IDENTITY is read first, and once. It is half the reuse condition, so
    there is nothing to compare until it is in hand; and the SAME tree is then
    handed to the judgement, so the specification a record names is the
    specification the judge read rather than whatever the directory held on a
    second read.
    """
    snapshot = _specification(repo=repo)
    digest = behaviour_digest(item=item)
    if snapshot is None:
        return _did_not_run(
            item=item,
            stage=stage,
            spec_version="",
            digest=digest,
            cause=CAUSE_SPEC_TREE_UNREADABLE,
            comments=comments,
            append=append,
        )
    spec_version = str(snapshot.version)
    reused = reusable_spec_change_tier(comments=comments, spec_version=spec_version, digest=digest)
    if reused is not None:
        return SpecChangeTierOutcome(work_item_id=item.id, recorded=reused, reused=True)
    run_model = drift_judge(project_root=repo, runner=runner or ShellCommandRunner())
    statement = asked_for_behaviour(item=item)
    classification = spec_stated.classify(
        title=item.title,
        description=item.description,
        item_type=item.type,
        run_model=run_model,
    )
    if not is_successful(classification):
        return _did_not_run(
            item=item,
            stage=stage,
            spec_version=spec_version,
            digest=digest,
            cause=CAUSE_CLASSIFICATION_UNREADABLE,
            comments=comments,
            append=append,
        )
    item_class = classification.unwrap()
    if item_class != FEATURE_CLASS:
        return _recorded(
            item=item,
            stage=stage,
            decision=exempt_decision(classification=item_class),
            spec_version=spec_version,
            digest=digest,
            append=append,
        )
    verdict = judge_within_ceiling(
        spec_tree=snapshot.files, statement=statement, run_model=run_model
    )
    if not is_successful(verdict):
        return _did_not_run(
            item=item,
            stage=stage,
            spec_version=spec_version,
            digest=digest,
            cause=CAUSE_VERDICT_UNREADABLE,
            comments=comments,
            append=append,
        )
    standing = recorded_spec_change_tier(comments=comments)
    return _recorded(
        item=item,
        stage=stage,
        decision=decide_spec_change_tier(
            item=item,
            classification=item_class,
            verdict=verdict.unwrap(),
            linked_proposal_topic=None if standing is None else standing.linked_proposal_topic,
        ),
        spec_version=spec_version,
        digest=digest,
        append=append,
    )


def classify_item_spec_change_tier(
    *,
    item: WorkItem,
    repo: Path,
    path: StoreConfig,
    stage: str,
    runner: CommandRunner | None = None,
) -> SpecChangeTierOutcome:
    """The decision above, bound to this item's own ledger comment sidecar.

    An UNREADABLE sidecar reports that the classification did not run and
    records NOTHING, which is the only honest answer available: the comments are
    both where a reusable classification is read from and where the
    once-per-cause cap is read from, so a classification taken without them
    would re-comment on every pass — and the write that would say so is the one
    that cannot be deduplicated.
    """

    def append(*, body: str) -> None:
        append_work_item_comment(path=path, work_item_id=item.id, body=body)

    bodies = item_comment_bodies(path=path, work_item_id=item.id)
    if bodies is None:
        return SpecChangeTierOutcome(
            work_item_id=item.id, recorded=None, cause=CAUSE_LEDGER_UNREADABLE
        )
    return classify_spec_change_tier(
        item=item,
        repo=repo,
        stage=stage,
        comments=bodies,
        append=append,
        runner=runner,
    )


def _specification(*, repo: Path) -> SpecSnapshot | None:
    """This repository's live spec snapshot, or `None` when there is none to judge.

    A dispatch target whose spec tree is absent or unreadable is one no
    judgement can be taken against, and the clause's route-as-before direction
    is what that must produce rather than an exception from inside an intake
    pass.

    AN EMPTY TREE IS AS UNUSABLE AS AN UNREADABLE ONE, and that is the arm most
    easily left out — because the reader does not fail on it. `rglob` over an
    absent directory yields nothing and `current_specification_version` answers
    0 for an absent history, so a missing spec tree reads back as a perfectly
    well-formed snapshot carrying no files at all. A judgement taken against it
    is a judgement against NO governing clause, which can only answer `unstated`
    — so every feature in such a repository would be held for a proposal against
    a specification that does not exist, and the hold would look exactly like a
    correct one.
    """
    read = attempt(
        action=lambda: read_current_specification(spec_root=repo / SPEC_DIRNAME),
        exceptions=(OSError,),
    )
    if isinstance(read, AttemptFailure) or not read.files:
        return None
    return read


def _recorded(
    *,
    item: WorkItem,
    stage: str,
    decision: SpecChangeTierDecision,
    spec_version: str,
    digest: str,
    append: Callable[..., None],
) -> SpecChangeTierOutcome:
    """Write one decision's record and report the classification it leaves standing.

    The outcome's `recorded` is read back out of the body just written rather
    than assembled beside it, so the classification a caller routes by is the
    one the record carries — a second construction is how the two come to differ
    while both look right.
    """
    body = spec_change_tier_comment(
        item_id=item.id,
        stage=stage,
        decision=decision,
        spec_version=spec_version,
        digest=digest,
    )
    append(body=body)
    return SpecChangeTierOutcome(
        work_item_id=item.id, recorded=recorded_spec_change_tier(comments=(body,))
    )


def _did_not_run(  # noqa: PLR0913 - each argument is one field of the record it writes.
    *,
    item: WorkItem,
    stage: str,
    spec_version: str,
    digest: str,
    cause: str,
    comments: Sequence[str],
    append: Callable[..., None],
) -> SpecChangeTierOutcome:
    """Record that the classification did not run, unless this cause already stands."""
    if cause not in recorded_did_not_run_causes(comments=comments):
        append(
            body=classification_did_not_run_comment(
                item_id=item.id,
                stage=stage,
                spec_version=spec_version,
                digest=digest,
                cause=cause,
            )
        )
    return SpecChangeTierOutcome(work_item_id=item.id, recorded=None, cause=cause)
