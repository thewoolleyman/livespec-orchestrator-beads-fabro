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

from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_governing_reuse import (
    governing_heading_subject_digest,
    reusable_governing_heading_verdict,
    with_governing_findings,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    JUDGEMENT_HELD,
    JUDGEMENT_UNAVAILABLE,
    first_remedy,
    judgement_subject_digest,
    rubric_digest,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_comments import (
    item_comment_bodies,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    GoverningHeadingReceipt,
    RecordedJudgement,
    did_not_run_comment,
    recorded_did_not_run_causes,
    reusable_verdict,
    verdict_comment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    CAUSE_PROMPT_UNREADABLE,
    judgement_rubric,
    run_dod_judgement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_spec_identity import (
    SpecIdentity,
    spec_identity_for_governing,
    whole_tree_identity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading_judge import (
    GoverningHeadingReader,
    host_governing_heading_reader,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_candidate_attempt import (
        CandidateAttempt,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "UNREADABLE_RUBRIC_DIGEST",
    "DodJudgementDecision",
    "held_judgement",
    "judge_definition_of_done",
    "judge_item_definition_of_done",
]


# What a did-not-run record names where the rubric itself could not be read. It
# is a SELF-DESCRIBING word rather than an empty value or a digest of nothing,
# because the record is what an operator reads to find out why the judgement
# stopped: a digest-shaped placeholder would read as a rubric that exists, and an
# empty field as a field the writer forgot.
UNREADABLE_RUBRIC_DIGEST = "unreadable"


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
    spec_identity: SpecIdentity | None = None

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
    governing_heading: GoverningHeadingReader | None = None,
    release_of_held_spec_tier: bool = False,
) -> DodJudgementDecision:
    """Reuse the recorded verdict, else take the judgement and record it.

    `comments` is spent TWICE and on one reading: the subject carries the riders
    among them, and the record scan reads the receipts among them. One read is
    what makes the digest this decision compares the digest of the subject it
    would grade — a second read taken for the subject alone could see a rider the
    scan did not.

    THE RUBRIC IS READ FIRST, and once. Its digest is half the reuse condition,
    so there is nothing to compare until it is in hand; and the SAME bytes are
    then handed to the judge, so the rubric a verdict names is the rubric the
    judge graded by rather than whatever the file held on a second read. An
    unreadable rubric records a did-not-run with that cause and takes no
    judgement, which is the behaviour this module had when it read the file one
    layer down.

    THE GOVERNING-HEADING VERDICT IS ESTABLISHED BEFORE THE SUBJECT DIGEST, because
    the digest's SPEC IDENTITY is the clause provenance of that verdict. A recorded
    verdict the component's own reuse rule still allows is read off the ledger and
    spends no model; only the verdicts that rule rejects are taken. The enclosing
    judgement's record is then looked up against the digest the identity produced,
    so a revision that leaves every governing clause unchanged reuses it with no
    judge run at all. `governing_heading` defaults to this host's own reader
    rather than to the absent one, because a gate that silently took no
    spec-stated judgement would report a clean citation for an item whose
    reference line governs nothing.

    `release_of_held_spec_tier` is the judgement that decides whether a held
    spec-change-tier item is released: it always keys on the whole-tree identity,
    because that judgement never reuses a verdict taken before the latest
    revision.
    """
    rubric = judgement_rubric(payload_root=payload_root)
    rubric_bytes_digest = (
        UNREADABLE_RUBRIC_DIGEST if rubric is None else rubric_digest(rubric=rubric)
    )
    if rubric is None:
        return _unavailable(
            item=item,
            stage=stage,
            digest=judgement_subject_digest(item=item, cwd=repo, comments=comments),
            rubric=rubric_bytes_digest,
            cause=CAUSE_PROMPT_UNREADABLE,
            comments=comments,
            append=append,
        )
    governing = reusable_governing_heading_verdict(item=item, repo=repo, comments=comments)
    if governing is None:
        reader = (
            host_governing_heading_reader(runner=ShellCommandRunner() if runner is None else runner)
            if governing_heading is None
            else governing_heading
        )
        governing = reader(item=item, repo=repo)
    identity = (
        whole_tree_identity(cwd=repo)
        if release_of_held_spec_tier
        else spec_identity_for_governing(item=item, cwd=repo, governing=governing)
    )
    digest = judgement_subject_digest(
        item=item, cwd=repo, comments=comments, spec_identity=identity.value
    )
    reused = reusable_verdict(comments=comments, digest=digest, rubric_digest=rubric_bytes_digest)
    if reused is not None:
        return DodJudgementDecision(
            work_item_id=item.id,
            outcome=reused.outcome,
            findings=reused.findings,
            reused=True,
            spec_identity=identity,
        )
    verdict = with_governing_findings(
        item=item,
        verdict=run_dod_judgement(
            item=item,
            cwd=repo,
            comments=comments,
            rubric=rubric,
            runner=runner,
            payload_root=payload_root,
            governing=governing,
        ),
        governing=governing,
    )
    if verdict.outcome == JUDGEMENT_UNAVAILABLE:
        return _unavailable(
            item=item,
            stage=stage,
            digest=digest,
            rubric=rubric_bytes_digest,
            cause=verdict.cause,
            comments=comments,
            append=append,
            bound_ended_candidates=verdict.bound_ended_candidates,
            attempts=verdict.attempts,
        )
    append(
        body=verdict_comment(
            item_id=item.id,
            stage=stage,
            digest=digest,
            rubric_digest=rubric_bytes_digest,
            judgement=verdict,
            spec_identity=identity,
            governing=(
                GoverningHeadingReceipt(
                    verdict=governing,
                    subject_digest=governing_heading_subject_digest(item=item, comments=comments),
                )
                if governing is not None
                else None
            ),
        )
    )
    return DodJudgementDecision(
        work_item_id=item.id,
        outcome=verdict.outcome,
        findings=verdict.findings,
        spec_identity=identity,
    )


def judge_item_definition_of_done(  # noqa: PLR0913 - each argument is an independent seam input.
    *,
    item: WorkItem,
    repo: Path,
    path: StoreConfig,
    stage: str,
    runner: CommandRunner | None = None,
    payload_root: Path | None = None,
    governing_heading: GoverningHeadingReader | None = None,
) -> DodJudgementDecision:
    """The decision above, bound to this item's own ledger comment sidecar.

    An UNREADABLE sidecar reports `did-not-run` and records NOTHING, which is
    the only honest answer available: the comments are both where a reusable
    verdict is read from and where the once-per-cause cap is read from, so a
    judgement taken without them would re-comment on every pass — and the
    write that would say so is the one that cannot be deduplicated. The item
    then routes exactly as it would without the judgement, which is what the
    clause asks of every condition under which it cannot run.
    """

    def append(*, body: str) -> None:
        append_work_item_comment(path=path, work_item_id=item.id, body=body)

    bodies = item_comment_bodies(path=path, work_item_id=item.id)
    if bodies is None:
        return DodJudgementDecision(work_item_id=item.id, outcome=JUDGEMENT_UNAVAILABLE)
    return judge_definition_of_done(
        item=item,
        repo=repo,
        stage=stage,
        comments=bodies,
        append=append,
        runner=runner,
        payload_root=payload_root,
        governing_heading=governing_heading,
    )


def held_judgement(
    *, item: WorkItem, repo: Path, comments: Sequence[str], payload_root: Path | None = None
) -> RecordedJudgement | None:
    """The standing refusing verdict for this item, taking no judgement at all.

    `None` both when no verdict is recorded against the item's current digests
    and when the recorded one admitted it — the two are the same fact for every
    caller, which is that nothing is holding this item back.

    An UNREADABLE rubric answers `None` too, and that is the fail-open direction
    this read already takes for an unreadable sidecar: a drain filter and a
    hygiene listing both read "nothing is holding this item back" as the absence
    of evidence, and the pre-dispatch wall is where a refusal is made. Holding an
    item on a rubric nobody could read would empty the queue on an environment
    fault, and the emptiness reads exactly like a factory with no work.

    THIS READ IS NOT A TAKING, so it takes no governing-heading verdict. It uses
    only a recorded verdict the component's reuse rule still allows. When none
    exists the identity it compares is the whole-tree one, which differs from every
    clause-form record and from every tree-form record taken against another
    revision, so after a revision the item reads as not held and nothing here ever
    spends a model.
    """
    rubric = judgement_rubric(payload_root=payload_root)
    if rubric is None:
        return None
    governing = reusable_governing_heading_verdict(item=item, repo=repo, comments=comments)
    identity = spec_identity_for_governing(item=item, cwd=repo, governing=governing)
    recorded = reusable_verdict(
        comments=comments,
        digest=judgement_subject_digest(
            item=item, cwd=repo, comments=comments, spec_identity=identity.value
        ),
        rubric_digest=rubric_digest(rubric=rubric),
    )
    if recorded is None or recorded.outcome != JUDGEMENT_HELD:
        return None
    return recorded


def _unavailable(  # noqa: PLR0913 - each argument is one field of the record it writes.
    *,
    item: WorkItem,
    stage: str,
    digest: str,
    rubric: str,
    cause: str | None,
    comments: Sequence[str],
    append: Callable[..., None],
    bound_ended_candidates: Sequence[str] = (),
    attempts: Sequence[CandidateAttempt] = (),
) -> DodJudgementDecision:
    """Record that the judgement did not run, unless this cause already stands.

    `cause` is typed optional because `DodJudgement` carries it only on the
    unavailable outcome; an unavailable verdict with no cause would be a bug in
    the layer above, and recording "it did not run, reason unstated" is worse
    than recording nothing — it is a row an operator cannot act on.

    It returns the DECISION as well as writing, because both of the gate's two
    unavailable arms owe the identical answer and one of them is reached before
    any rubric exists. Two call sites each composing the write and the return was
    how the second arm came to record nothing at all.
    """
    if cause is not None and cause not in recorded_did_not_run_causes(comments=comments):
        append(
            body=did_not_run_comment(
                item_id=item.id,
                stage=stage,
                digest=digest,
                rubric_digest=rubric,
                cause=cause,
                bound_ended_candidates=bound_ended_candidates,
                attempts=attempts,
            )
        )
    return DodJudgementDecision(work_item_id=item.id, outcome=JUDGEMENT_UNAVAILABLE)
