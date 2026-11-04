"""Read the durable terminal account a needs-human run leaves on its item."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro._store_comments import WorkItemComment
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_cause import (
    NEEDS_HUMAN_CAUSE_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._fabro_needs_human_question import (
    NeedsHumanQuestion,
)

__all__: list[str] = ["needs_human_question_from_ledger_comments"]

_CAUSE_LABELS = ("innermost cause", "agent-reported cause")
_PRESERVED_ON_PREFIX = "the tree was preserved on "
_NOT_PUSHED_PREFIX = "the tree was not pushed to a run-scoped ref"


def needs_human_question_from_ledger_comments(
    *, comments: tuple[WorkItemComment, ...], run_id: str
) -> NeedsHumanQuestion | None:
    """The newest usable terminal account for `run_id`, if the ledger carries one."""
    for comment in reversed(comments):
        question = _question_from_comment(text=comment.text, run_id=run_id)
        if question is not None:
            return question
    return None


def _question_from_comment(*, text: str, run_id: str) -> NeedsHumanQuestion | None:
    lines = tuple(line.strip() for line in text.splitlines() if line.strip())
    if not lines or lines[0] != NEEDS_HUMAN_CAUSE_MARKER:
        return None
    fields = _fields(lines=lines[1:])
    if fields.get("run id") != run_id:
        return None
    preserved_ref, tree_preserved = _preservation(value=fields.get("preservation"))
    return NeedsHumanQuestion(
        prompt=fields.get("terminal reason"),
        reason=fields.get("failure signature"),
        cause=next((fields[label] for label in _CAUSE_LABELS if label in fields), None),
        preserved_ref=preserved_ref,
        tree_preserved=tree_preserved,
    )


def _fields(*, lines: tuple[str, ...]) -> dict[str, str]:
    """The labelled terminal-account fields carried in one comment body."""
    fields: dict[str, str] = {}
    for line in lines:
        label, separator, value = line.partition(":")
        if separator and value.strip():
            fields[label.strip()] = value.strip()
    return fields


def _preservation(*, value: str | None) -> tuple[str | None, bool]:
    """Map the writer's preservation sentence onto the rendered account fields."""
    if value is None:
        return (None, True)
    if value.startswith(_PRESERVED_ON_PREFIX):
        return (value.removeprefix(_PRESERVED_ON_PREFIX).split(" ", 1)[0], True)
    return (None, not value.startswith(_NOT_PUSHED_PREFIX))
