"""The read-only hygiene fact for input-bound host Definition-of-Done takings.

The fact is deliberately computed from receipts the host already appended.  A
snapshot must not retry a model judgement or alter an item's lifecycle merely to
report that every candidate could not preflight its oversized subject.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef

from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_comments import (
    item_comment_bodies,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_markers import (
    JUDGEMENT_COMMENT_MARKER,
    UNAVAILABLE_COMMENT_MARKER,
    comment_marker,
)
from livespec_orchestrator_beads_fabro.commands._dod_unavailable_record import (
    STAGE_PRE_ADMISSION,
    STAGE_PRE_DISPATCH,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "latest_input_bound_measurement",
    "unpreflightable_definition_of_done_items",
]

_HOST_TAKING_STAGES = frozenset({STAGE_PRE_ADMISSION, STAGE_PRE_DISPATCH})
_INPUT_BOUND_CAUSE = "input-limit-reached"
_FIELD_SEPARATOR = ": "


def unpreflightable_definition_of_done_items(
    *, project_root: Path, repo: str, items: list[WorkItem]
) -> list[AttentionItem]:
    """One hygiene fact per item whose latest host taking reached the input bound."""
    resolved = attempt(
        action=lambda: resolve_store_config(cwd=project_root, work_items_arg=None),
        exceptions=(ConnectionPrefixMissingError, LivespecConfigUnreadableError),
    )
    if isinstance(resolved, AttemptFailure):
        return []
    return [
        _unpreflightable_item(
            project_root=project_root,
            repo=repo,
            item=item,
            subject_characters=measurement[0],
            carried_rider_count=measurement[1],
        )
        for item in items
        for comments in (item_comment_bodies(path=resolved, work_item_id=item.id),)
        if comments is not None
        for measurement in (latest_input_bound_measurement(comments=comments),)
        if measurement is not None
    ]


def latest_input_bound_measurement(*, comments: tuple[str, ...]) -> tuple[int, int] | None:
    """The latest host receipt's input-bound measurements, if it has both."""
    for body in reversed(comments):
        marker = comment_marker(body=body)
        fields = _record_fields(body=body)
        if fields.get("stage") not in _HOST_TAKING_STAGES:
            continue
        if marker == UNAVAILABLE_COMMENT_MARKER and (
            fields.get("judgement-unavailable-cause") == _INPUT_BOUND_CAUSE
        ):
            attempted_candidates = _candidate_ids(body=body)
            bound_ended_candidates = _field_values(body=body, name="bound-ended-candidate")
            if not attempted_candidates or set(bound_ended_candidates) != set(attempted_candidates):
                return None
            subject_characters = _integer_field(fields=fields, name="subject-size-characters")
            carried_rider_count = _integer_field(fields=fields, name="carried-rider-count")
            if subject_characters is not None and carried_rider_count is not None:
                return subject_characters, carried_rider_count
        if marker in {JUDGEMENT_COMMENT_MARKER, UNAVAILABLE_COMMENT_MARKER}:
            return None
    return None


def _record_fields(*, body: str) -> dict[str, str]:
    """The single-valued fields a host receipt records."""
    fields: dict[str, str] = {}
    for raw in body.splitlines():
        key, separator, value = raw.strip().partition(_FIELD_SEPARATOR)
        if separator:
            fields[key] = value
    return fields


def _integer_field(*, fields: dict[str, str], name: str) -> int | None:
    """A non-negative decimal receipt field, rejecting malformed evidence."""
    value = fields.get(name)
    return int(value) if value is not None and value.isdecimal() else None


def _field_values(*, body: str, name: str) -> tuple[str, ...]:
    """Every repeated receipt value carrying one field name."""
    prefix = f"{name}{_FIELD_SEPARATOR}"
    return tuple(raw[len(prefix) :] for raw in body.splitlines() if raw.startswith(prefix))


def _candidate_ids(*, body: str) -> tuple[str, ...]:
    """The resolved agent:model identifier of every candidate the receipt ran."""
    identifiers: list[str] = []
    for value in _field_values(body=body, name="candidate"):
        fields: dict[str, str] = {}
        for part in value.split():
            key, separator, field_value = part.partition("=")
            if separator:
                fields[key] = field_value
        agent = fields.get("agent")
        model = fields.get("model")
        if agent is None or model is None:
            return ()
        identifiers.append(f"{agent}:{model}")
    return tuple(identifiers)


def _unpreflightable_item(
    *,
    project_root: Path,
    repo: str,
    item: WorkItem,
    subject_characters: int,
    carried_rider_count: int,
) -> AttentionItem:
    return ConformanceContext(project_root=project_root, repo=repo).candidate(
        id=f"hygiene:unpreflightable-definition-of-done:{item.id}",
        kind="hygiene",
        urgency="medium",
        summary=(
            f"Work-item {item.id}'s latest host Definition-of-Done taking exhausted"
            f" its input bound at {subject_characters} characters with"
            f" {carried_rider_count} carried riders."
        ),
        source_ref=SourceRef(repo=repo, work_item=item.id),
        handoff=Handoff(
            kind="shell", command=_context_command(project_root=project_root, item=item)
        ),
    )


def _context_command(*, project_root: Path, item: WorkItem) -> str:
    """Return the item's own record without spending a sandbox on a dispatch."""
    wrapper = Path(__file__).parents[2] / "bin" / "context.py"
    return (
        f"python3 {shlex.quote(str(wrapper))} "
        f"--project-root {shlex.quote(str(project_root))} {shlex.quote(item.id)} --json"
    )
