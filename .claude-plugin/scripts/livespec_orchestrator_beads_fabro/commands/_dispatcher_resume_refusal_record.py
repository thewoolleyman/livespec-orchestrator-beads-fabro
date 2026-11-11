"""Ledger record of an automatic overtaken-arming resume the ladder refused.

Split from `_dispatcher_base_advance_record` to keep that module under the file
LLOC ceiling. The refusal reuses its marker, its detector-guarded fail-soft
comment writer and its rendering helpers, so the refused-resume comment reads
as the same overtaken-arming record with the named refusals appended.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance import (
    BASE_ADVANCED_AFTER_ARMING,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance_record import (
    BASE_ADVANCED_MARKER,
    UNREPORTED,
    pr_number_line,
    write_comment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_correlation import (
    is_identifier_shaped,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile

__all__: list[str] = [
    "record_resume_refusal",
    "resume_refusal_comment_body",
]


def record_resume_refusal(
    *,
    repo: Path,
    work_item_id: str,
    pr_number: int | None,
    pr_head: str | None,
    refusals: tuple[str, ...],
    journal: JournalFile,
) -> None:
    """Append the durable record of an automatic resume the ladder refused, once.

    The contract requires "the ledger comment and the outcome detail" of a
    refused automatic resume to name the refusal. The ending's ordinary comment
    is written by the post-run dispositions, which an admitted-or-refused resume
    returns past, so the refusal writes its own under the same marker and on the
    same fail-soft terms: it MUST NOT prevent the blocked transition.
    """
    write_comment(
        repo=repo,
        work_item_id=work_item_id,
        body=resume_refusal_comment_body(
            work_item_id=work_item_id,
            pr_number=pr_number,
            pr_head=pr_head,
            refusals=refusals,
        ),
        pr_number=pr_number,
        journal=journal,
        cause=BASE_ADVANCED_AFTER_ARMING,
    )


def resume_refusal_comment_body(
    *,
    work_item_id: str,
    pr_number: int | None,
    pr_head: str | None,
    refusals: tuple[str, ...],
) -> str:
    """Render the refused-resume record: the overtaken-arming marker plus each refusal."""
    head = (
        f"pull request head: {pr_head}"
        if pr_head is not None and is_identifier_shaped(value=pr_head)
        else f"pull request head: {UNREPORTED}"
    )
    return "\n".join(
        [
            BASE_ADVANCED_MARKER,
            "",
            f"work-item: {work_item_id}",
            f"pull request: {pr_number_line(pr_number=pr_number)}",
            head,
            "",
            "automatic resume refused:",
            *(f"- {one}" for one in refusals),
            "",
            _REFUSED_DECISION,
        ]
    )


# The refused automatic resume's reading: the arming is still overtaken, and the
# resume the Dispatcher offered was refused, so the hand-driven chain applies once
# the named refusal is cleared.
_REFUSED_DECISION = (
    "decision: the automatic resume of the overtaken arming was refused for the reasons "
    "above, and no agent asked anything, so no answer is owed. The pull request is left "
    "armed and standing — do NOT disarm, close or rebase it by hand. Clear the refusal, "
    "release the item with `resolve-blocked:<work-item>:ready`, then `resume --item "
    "<work-item>`, substituting the work-item named above."
)
