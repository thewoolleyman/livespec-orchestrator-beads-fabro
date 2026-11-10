"""Whether a pull request's CURRENT head is one a Proof of Done record proved.

Split out of `_drive_merge_hold_arm_guard` by cohesion: the guard owns the two
questions a release must answer before it arms (is a run live, is the head
proved) and the refusals it words, while this owns the second one's
measurement -- reading the pull request's anchoring record, naming the head it
proved, and comparing that with the head the pull request carries. It answers
with VALUES (an unproved-head detail, a message-only move, or nothing) and the
guard words the refusal, so the code a caller routes on stays in one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import (
    read_pull_request_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_head import (
    PROOF_HEAD_ANCHOR_VERDICTS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import published_head
from livespec_orchestrator_beads_fabro.commands._drive_merge_hold_head_lineage import (
    message_only_tree,
)

__all__: list[str] = ["MessageOnlyHeadMove", "UnprovedHead", "head_outcome"]


@dataclass(frozen=True, kw_only=True)
class MessageOnlyHeadMove:
    """A current head that differs from the proved head only in its commit message.

    Carried out of the guard so the release can REPORT it: the clause requires the
    result to name the proved head, the current head and their shared tree, and
    the release is the only party that writes a result.
    """

    proved_head: str
    current_head: str
    tree: str


@dataclass(frozen=True, kw_only=True)
class UnprovedHead:
    """Why the head is not one a record proved, worded as the clause of a refusal."""

    detail: str


def head_outcome(
    *,
    repo: Path,
    work_item_id: str,
    pr_number: int,
    pr_head: str | None,
    runner: CommandRunner,
) -> UnprovedHead | MessageOnlyHeadMove | None:
    """Why the pull request's CURRENT head is not one this release may arm.

    Three absences share one refusal code and are worded apart, because the code
    is what the caller routes on while the prose is the only thing that says which
    reading was missing: the forge could not report the head, it carries no
    anchoring record, or the anchoring record names no single head. A fourth arm
    is the one positive negative -- a head that WAS read and differs. A differing
    head is not yet a refusal: one that moved only in its commit message, on the
    same sole parent and the same tree, keeps the proof, and is reported as such.
    """
    if pr_head is None:
        return UnprovedHead(
            detail=(
                "the forge did not report the pull request's current head, so whether it is "
                "the head a verified or carried_forward record names could not be measured"
            ),
        )
    proved = _proved_anchor(
        repo=repo, work_item_id=work_item_id, pr_number=pr_number, runner=runner
    )
    if isinstance(proved, UnprovedHead):
        return proved
    if proved.head == pr_head:
        return None
    shared_tree = message_only_tree(repo=repo, proved=proved.head, current=pr_head, runner=runner)
    if shared_tree is not None:
        return MessageOnlyHeadMove(proved_head=proved.head, current_head=pr_head, tree=shared_tree)
    return UnprovedHead(
        detail=(
            f"it is at {pr_head} while its latest {proved.verdict} Proof of Done "
            f"record names {proved.head}, so the head it carries is one no record of this "
            "item's latest run proved"
        ),
    )


@dataclass(frozen=True, kw_only=True)
class _ProvedAnchor:
    """The head the latest anchoring Proof of Done record names, and that record's verdict."""

    head: str
    verdict: str


def _proved_anchor(
    *, repo: Path, work_item_id: str, pr_number: int, runner: CommandRunner
) -> _ProvedAnchor | UnprovedHead:
    """The proved head, or the refusal naming which reading of it was missing."""
    records = read_pull_request_records(repo=repo, pr_number=pr_number, runner=runner)
    if records is None:
        return UnprovedHead(
            detail=(
                "the forge could not be asked for the Proof of Done records on it, so the "
                "head the latest verified or carried_forward record names could not be read"
            ),
        )
    anchors = [one for one in records if one.verdict in PROOF_HEAD_ANCHOR_VERDICTS]
    if not anchors:
        return UnprovedHead(
            detail=(
                "it carries no verified or carried_forward Proof of Done record, so no record "
                f"names a head {work_item_id} may be merged at"
            ),
        )
    # The LATEST anchor, by position, is the item's latest run's answer: a
    # `carried_forward` record supersedes the verified record it carries, and a
    # later run's record is appended after an earlier run's, so reading per
    # verdict would let an older run's head win a chain of carry-forwards.
    proved = published_head(body=anchors[-1].body)
    if proved is None:
        return UnprovedHead(
            detail=(
                f"its latest {anchors[-1].verdict} Proof of Done record names no single full "
                "publish-branch head, so the tree it proved cannot be established"
            ),
        )
    return _ProvedAnchor(head=proved, verdict=anchors[-1].verdict)
