"""Recover preserved-tree seeds from the durable work-item comment sidecar.

The dispatch journal belongs to the host that wrote it, while a
``livespec-preserved-tree`` comment follows its work item to every later
Dispatcher host.  Recovery therefore projects well-formed preservation comments
onto the same row shape the local journal already supplies to the recovery
reader.  The comment is written only after the publisher created the ref and
records both immutable commits needed to start the next sandbox.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_record import (
    PRESERVED_TREE_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import RecoverySeed
from livespec_orchestrator_beads_fabro.store import WorkItemComment

__all__: list[str] = ["preserved_tree_comment_names_run", "preserved_tree_comment_seed"]


def preserved_tree_comment_seed(
    *, comments: tuple[WorkItemComment, ...], work_item_id: str
) -> RecoverySeed | None:
    """Return the newest complete preservation seed named by this item's comments.

    A malformed marked comment remains harmless: it cannot name a seed.  The
    writer's success comment supplies every named field, including the base
    commit rather than the hookless preservation commit.
    """
    for comment in reversed(comments):
        fields = _fields(text=comment.text)
        if not _matches(comment=comment, fields=fields, work_item_id=work_item_id):
            continue
        return RecoverySeed(
            source_run_id=fields["run id"],
            remote="origin",
            commit_sha=fields["base commit"],
            preservation_ref=fields["preservation ref"],
        )
    return None


def preserved_tree_comment_names_run(*, comments: tuple[WorkItemComment, ...], run_id: str) -> bool:
    """Whether a marked preserved-tree comment, success or failure, names this run."""
    return any(
        comment.text.startswith(PRESERVED_TREE_MARKER)
        and _fields(text=comment.text).get("run id") == run_id
        for comment in comments
    )


def _fields(*, text: str) -> dict[str, str]:
    """Read the simple ``key: value`` lines emitted by the record writer."""
    return dict(line.split(": ", maxsplit=1) for line in text.splitlines() if ": " in line)


def _matches(*, comment: WorkItemComment, fields: dict[str, str], work_item_id: str) -> bool:
    """Whether a comment has the complete, item-owned successful-record shape."""
    required = ("run id", "factory", "preservation ref", "commit id", "base commit")
    return (
        comment.text.startswith(PRESERVED_TREE_MARKER)
        and fields.get("work-item") == work_item_id
        and all(fields.get(key, "").strip() for key in required)
    )
