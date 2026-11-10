"""The journal-hold lane and the two idle lanes it corrects, from ONE journal reading.

A hold only the dispatch journal records is invisible to the idle-factory fact
and the idle-slot audit unless they are told about it, and the clause these
lanes realize requires the snapshot's facts to be "composed from one reading of
the journal per snapshot". Composing the three here, from the reading taken at
the top, is what makes that true by construction: no lane re-reads the journal,
so none can see a record another did not. It is also why the unreadable-journal
case is consistent across them — the `hygiene:journal-hold:unobservable` fact,
the absent idle-factory fact and the HELD idle-slot children all follow from the
same single failure to read.
"""

from __future__ import annotations

from pathlib import Path

from livespec_runtime.attention_item import AttentionItem

from livespec_orchestrator_beads_fabro.commands._needs_attention_idle_factory import (
    idle_factory_items,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_idle_slot import (
    idle_slot_items,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_journal_hold import (
    journal_hold_items,
    read_journal_holds,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_model_fallback import (
    dispatch_journal_path_for,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "journal_hold_and_idle_items",
]


def journal_hold_and_idle_items(
    *,
    project_root: Path,
    repo: str,
    items: list[WorkItem],
) -> list[AttentionItem]:
    """The journal-hold facts, then the idle-factory fact, then the idle-slot fact."""
    reading = read_journal_holds(
        journal_path=dispatch_journal_path_for(project_root=project_root), items=items
    )
    return (
        journal_hold_items(project_root=project_root, repo=repo, items=items, reading=reading)
        + idle_factory_items(
            project_root=project_root, repo=repo, items=items, journal_holds=reading
        )
        + idle_slot_items(project_root=project_root, repo=repo, journal_holds=reading)
    )
