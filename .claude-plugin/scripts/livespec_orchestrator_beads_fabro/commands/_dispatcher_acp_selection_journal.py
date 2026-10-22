"""Journal the per-node candidate selections one dispatch rendered."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._acp_node_selection import (
    SelectedAcpCandidate,
    acp_node_selection_record,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import JournalWriter

__all__: list[str] = ["append_acp_node_selection"]


def append_acp_node_selection(
    *,
    journal: JournalWriter,
    selected: Mapping[str, SelectedAcpCandidate],
    work_item_id: str,
    dispatch_id: str | None,
) -> None:
    """Append the selection record with the immutable launch correlation."""
    journal.append(
        record={
            **acp_node_selection_record(selected=selected, dispatch_id=dispatch_id),
            "work_item_id": work_item_id,
        }
    )
