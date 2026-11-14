"""Comment-copying rules for a contaminated-item successor."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro._store_comments import WorkItemComment

__all__: list[str] = [
    "copy_instruction_comments",
]


def copy_instruction_comments(
    *,
    client: BeadsClient,
    original_id: str,
    successor_id: str,
    comments: tuple[WorkItemComment, ...],
) -> tuple[str, ...]:
    """Copy instruction riders in order, retaining machine receipts on the original."""
    record_ids: list[str] = []
    for comment in comments:
        if comment.text.startswith("livespec-"):
            if comment.comment_id is not None:
                record_ids.append(comment.comment_id)
            continue
        client.add_comment(
            issue_id=successor_id,
            body=_copied_comment_body(
                original_id=original_id,
                comment_id=comment.comment_id,
                created_at=comment.created_at,
                text=comment.text,
            ),
        )
    return tuple(record_ids)


def _copied_comment_body(
    *, original_id: str, comment_id: str | None, created_at: str | None, text: str
) -> str:
    """Attach provenance without displacing a stage-scoped rider's first line."""
    provenance = (
        f"Superseded from {original_id} comment {comment_id or 'unknown'} "
        f"created {created_at or 'unknown'}."
    )
    lines = text.splitlines()
    if lines and lines[0].startswith("FOR ") and lines[0].endswith(" ONLY:"):
        return "\n".join((lines[0], provenance, _sanitize(text="\n".join(lines[1:]))))
    return "\n".join((provenance, _sanitize(text=text)))


def _sanitize(*, text: str) -> str:
    """Use the goal renderer's bracket form for every copied template opener."""
    return text.replace("{{", "⟦⟦").replace("{%", "⟦%").replace("{#", "⟦#")
