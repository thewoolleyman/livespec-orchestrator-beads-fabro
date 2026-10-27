"""Render the durable ledger account for a needs-human valve without a factory read."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro._store_comments import WorkItemComment
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_cause import (
    NEEDS_HUMAN_CAUSE_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserve_reference_body import (
    PRESERVE_POINTER_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserve_reference_check import (
    parse_preserved_pointer,
)
from livespec_orchestrator_beads_fabro.commands._fabro_needs_human_question import (
    NEEDS_HUMAN_NODE_ID,
)

__all__: list[str] = ["needs_human_comment_summary"]

_NO_REASON = (
    "the implementer reported a needs-human ending; the engine recorded no "
    "loop failure signature"
)


def needs_human_comment_summary(
    *,
    comments: tuple[WorkItemComment, ...],
    default_summary: str,
    factory_name: str,
    factory_server_url: str,
    item_id: str,
    run_id: str,
) -> str | None:
    """The newest durable account for this run, or None when factory fallback is owed."""
    cause = _newest_cause_comment(comments=comments, run_id=run_id)
    if cause is None:
        return None
    lines = cause.splitlines()
    reason = _field(lines=lines, name="terminal reason") or _NO_REASON
    cause_clause = "".join(
        f"Innermost cause: {value}. "
        for line in lines
        if line.startswith("innermost cause")
        for value in (line.partition(": ")[2],)
        if value
    )
    return (
        f"{default_summary}; fabro run {run_id} on factory {factory_name} "
        f"({factory_server_url}) terminated at the {NEEDS_HUMAN_NODE_ID} node and "
        f"routed the decision to this valve. Why: {reason}. {cause_clause}"
        f"{_preservation(comments=comments, run_id=run_id)} "
        f"Available actions: resolve-blocked:{item_id}:ready, "
        f"resolve-blocked:{item_id}:backlog, or leave the item blocked."
    )


def _newest_cause_comment(*, comments: tuple[WorkItemComment, ...], run_id: str) -> str | None:
    for comment in reversed(comments):
        lines = comment.text.splitlines()
        if (
            lines
            and lines[0] == NEEDS_HUMAN_CAUSE_MARKER
            and _field(lines=lines, name="run id") == run_id
        ):
            return comment.text
    return None


def _field(*, lines: list[str], name: str) -> str | None:
    prefix = f"{name}: "
    return next((line[len(prefix) :] for line in lines if line.startswith(prefix)), None)


def _preservation(*, comments: tuple[WorkItemComment, ...], run_id: str) -> str:
    for comment in reversed(comments):
        pointer = parse_preserved_pointer(body=comment.text)
        if pointer is not None and pointer.run_id == run_id:
            return (
                "The preserved work reference is the "
                f"{PRESERVE_POINTER_MARKER} comment for run {run_id}."
            )
    return ""
