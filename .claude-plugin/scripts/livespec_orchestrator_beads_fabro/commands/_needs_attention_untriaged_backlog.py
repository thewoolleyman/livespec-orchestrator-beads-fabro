"""The un-triaged-backlog attention lane.

A sibling of `_needs_attention_work_items` rather than a section of it: this
lane is the only one that reads `IntakeTriageRecord` (the narrow raw read)
instead of the materialized `WorkItem`, so it shares neither inputs nor
helpers with the host-only / human-valve / impl-next lanes there.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef

from livespec_orchestrator_beads_fabro.commands._needs_attention_handoffs import (
    untriaged_backlog_command,
    untriaged_backlog_summary_command,
)
from livespec_orchestrator_beads_fabro.store import IntakeTriageRecord

__all__: list[str] = ["untriaged_backlog_items"]

_BACKLOG_STATUS = "backlog"
# Beads-native priority is ascending-urgent: 0 is P0, 1 is P1. Items at or
# below this ceiling get one attention item EACH; everything else collapses
# into a single summary item.
_PER_ITEM_PRIORITY_CEILING = 1
# Sort position for a record carrying no usable native priority: after every
# real priority tier, so it never displaces a genuinely-urgent record.
_UNPRIORITIZED_SORT_POSITION = _PER_ITEM_PRIORITY_CEILING + 1000


def untriaged_backlog_items(
    *,
    project_root: Path,
    repo: str,
    records: Sequence[IntakeTriageRecord],
) -> list[AttentionItem]:
    """Surface backlog work-items the intake Definition-of-Ready gate never saw.

    A `backlog` item is admitted by no dispatch surface and, before this
    lane, was reported by none either — so an item filed with a raw
    `bd create` (which never runs the intake gate) silently disappeared,
    looking exactly like an epic the gate deliberately parked. The
    `intake:triaged` marker is the discriminator: this lane reports backlog
    items that lack it.

    Noise control is part of the contract, not a refinement of it. A
    repository can carry hundreds of un-triaged backlog items; emitting one
    attention item each would drown the list and get the lane switched off.
    So each item at or above the P0/P1 urgency tier — the filed-and-forgotten
    high-priority risk this lane exists to catch — gets its own item, and the
    whole remainder collapses into ONE summary item.
    """
    untriaged = sorted(
        (record for record in records if record.status == _BACKLOG_STATUS and not record.triaged),
        key=_untriaged_sort_key,
    )
    per_item = [record for record in untriaged if _is_per_item_priority(record=record)]
    items = [
        _untriaged_backlog_item(project_root=project_root, repo=repo, record=record)
        for record in per_item
    ]
    remainder = len(untriaged) - len(per_item)
    if remainder > 0:
        items.append(
            _remainder_item(project_root=project_root, repo=repo, count=remainder),
        )
    return items


def _untriaged_sort_key(record: IntakeTriageRecord) -> tuple[int, str]:
    """Order by urgency tier, then by id so the lane is deterministic."""
    priority = record.priority
    position = _UNPRIORITIZED_SORT_POSITION if priority is None else priority
    return (position, record.id)


def _is_per_item_priority(*, record: IntakeTriageRecord) -> bool:
    priority = record.priority
    return priority is not None and priority <= _PER_ITEM_PRIORITY_CEILING


def _untriaged_backlog_item(
    *,
    project_root: Path,
    repo: str,
    record: IntakeTriageRecord,
) -> AttentionItem:
    return AttentionItem(
        id=f"hygiene:untriaged-backlog:{record.id}",
        kind="hygiene",
        urgency="high",
        summary=(
            f"Un-triaged backlog work-item {record.id} at P{record.priority}: "
            f"{record.title}. The intake Definition-of-Ready gate never ran on it, "
            "so no dispatch surface admits it and nothing else reports it."
        ),
        source_ref=SourceRef(repo=repo, work_item=record.id),
        handoff=Handoff(
            kind="shell",
            command=untriaged_backlog_command(project_root=project_root, work_item=record.id),
        ),
    )


def _remainder_item(*, project_root: Path, repo: str, count: int) -> AttentionItem:
    return AttentionItem(
        id="hygiene:untriaged-backlog-remainder:count",
        kind="hygiene",
        urgency="low",
        summary=(
            f"{count} un-triaged backlog work-items at P2 or lower (or carrying no "
            "priority) were filed without the intake Definition-of-Ready gate. "
            "Triage them, or label each deliberately-parked one intake:triaged."
        ),
        source_ref=SourceRef(repo=repo),
        handoff=Handoff(
            kind="shell",
            command=untriaged_backlog_summary_command(project_root=project_root),
        ),
    )
