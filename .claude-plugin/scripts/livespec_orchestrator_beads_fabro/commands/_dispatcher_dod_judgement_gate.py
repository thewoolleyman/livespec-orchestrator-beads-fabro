"""The ONE composed Definition-of-Done judgement decision, for both call sites.

"Judged before admission" and "Judged again before dispatch" describe the same
judgement in two positions, and the second paragraph makes the SHARING
load-bearing: the verdict a dispatch reuses may be "the pre-admission verdict or
an earlier pre-dispatch verdict". Two implementations could not share a record
they digest differently, so the decision is one function and the positions
differ only in the `stage` the record names.

THE ORDER IS REUSE, THEN TAKE, THEN RECORD, and it is the cheap-first order the
clause's own caps imply. The reuse read is a ledger read the drain already pays
for; taking the judgement is a model call; recording is a write that can never
be taken back, because beads comments are append-only. Putting the reuse read
anywhere but first spends a model call per item per pass on items nothing about
has changed.

WHY `held_judgement` IS A SEPARATE, JUDGEMENT-FREE READ. Two surfaces need to
know whether a refusing verdict stands WITHOUT taking one: drain candidate
enumeration, which must exclude a refused item "until its effective criteria or
referenced headings change", and the `needs-attention` hygiene listing. Both run
over every item in the tenant, so a read that could take a judgement would turn
a listing into a fleet of model calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._store_comments import (
    append_work_item_comment,
    read_work_item_comments,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_HELD,
    JUDGEMENT_UNAVAILABLE,
    first_remedy,
    judgement_subject_digest,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    RecordedJudgement,
    did_not_run_comment,
    recorded_did_not_run_causes,
    reusable_verdict,
    verdict_comment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    run_dod_judgement,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "DodJudgementDecision",
    "held_judgement",
    "item_comment_bodies",
    "judge_definition_of_done",
    "judge_item_definition_of_done",
]


@dataclass(frozen=True, kw_only=True)
class DodJudgementDecision:
    """What one call site learned, and whether anything was spent learning it.

    `reused` is reported rather than inferred from `findings`, because a reused
    verdict and a freshly-taken identical one are indistinguishable by outcome —
    and the two caps the clause states are about the SPEND, not the answer.
    """

    work_item_id: str
    outcome: str
    findings: tuple[str, ...] = ()
    reused: bool = False

    @property
    def holds(self) -> bool:
        """Whether this decision rests the item at needs-human."""
        return self.outcome == JUDGEMENT_HELD

    @property
    def first_remedy(self) -> str | None:
        """The remedy a refusal and a hygiene fact name."""
        return first_remedy(findings=self.findings)


def judge_definition_of_done(  # noqa: PLR0913 - each argument is an independent seam input.
    *,
    item: WorkItem,
    repo: Path,
    stage: str,
    comments: Sequence[str],
    append: Callable[..., None],
    runner: CommandRunner | None = None,
    payload_root: Path | None = None,
) -> DodJudgementDecision:
    """Reuse the recorded verdict, else take the judgement and record it."""
    digest = judgement_subject_digest(item=item, cwd=repo)
    reused = reusable_verdict(comments=comments, digest=digest)
    if reused is not None:
        return DodJudgementDecision(
            work_item_id=item.id, outcome=reused.outcome, findings=reused.findings, reused=True
        )
    verdict = run_dod_judgement(item=item, cwd=repo, runner=runner, payload_root=payload_root)
    if verdict.outcome == JUDGEMENT_UNAVAILABLE:
        _record_did_not_run(
            item=item,
            stage=stage,
            digest=digest,
            cause=verdict.cause,
            comments=comments,
            append=append,
        )
        return DodJudgementDecision(work_item_id=item.id, outcome=verdict.outcome)
    append(body=verdict_comment(item_id=item.id, stage=stage, digest=digest, judgement=verdict))
    return DodJudgementDecision(
        work_item_id=item.id, outcome=verdict.outcome, findings=verdict.findings
    )


def judge_item_definition_of_done(
    *,
    item: WorkItem,
    repo: Path,
    path: StoreConfig,
    stage: str,
    runner: CommandRunner | None = None,
    payload_root: Path | None = None,
) -> DodJudgementDecision:
    """The decision above, bound to this item's own ledger comment sidecar."""

    def append(*, body: str) -> None:
        append_work_item_comment(path=path, work_item_id=item.id, body=body)

    return judge_definition_of_done(
        item=item,
        repo=repo,
        stage=stage,
        comments=item_comment_bodies(path=path, work_item_id=item.id),
        append=append,
        runner=runner,
        payload_root=payload_root,
    )


def item_comment_bodies(*, path: StoreConfig, work_item_id: str) -> tuple[str, ...]:
    """One item's comment bodies, oldest-first, as every reader here wants them."""
    return tuple(
        comment.text for comment in read_work_item_comments(path=path, work_item_id=work_item_id)
    )


def held_judgement(
    *, item: WorkItem, repo: Path, comments: Sequence[str]
) -> RecordedJudgement | None:
    """The standing refusing verdict for this item, taking no judgement at all.

    `None` both when no verdict is recorded against the item's current bytes and
    when the recorded one admitted it — the two are the same fact for every
    caller, which is that nothing is holding this item back.
    """
    recorded = reusable_verdict(
        comments=comments, digest=judgement_subject_digest(item=item, cwd=repo)
    )
    if recorded is None or recorded.outcome != JUDGEMENT_HELD:
        return None
    return recorded


def _record_did_not_run(
    *,
    item: WorkItem,
    stage: str,
    digest: str,
    cause: str | None,
    comments: Sequence[str],
    append: Callable[..., None],
) -> None:
    """Record that the judgement did not run, unless this cause already stands.

    `cause` is typed optional because `DodJudgement` carries it only on the
    unavailable outcome; an unavailable verdict with no cause would be a bug in
    the layer above, and recording "it did not run, reason unstated" is worse
    than recording nothing — it is a row an operator cannot act on.
    """
    if cause is None or cause in recorded_did_not_run_causes(comments=comments):
        return
    append(body=did_not_run_comment(item_id=item.id, stage=stage, digest=digest, cause=cause))
