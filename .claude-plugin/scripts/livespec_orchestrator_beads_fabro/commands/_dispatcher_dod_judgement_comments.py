"""Read one work item's ledger comment bodies for a Definition-of-Done judgement.

Split out of `_dispatcher_dod_judgement_gate` by cohesion: the gate decides what a
judgement does with the comments it is handed, while this owns only the READ that
produces them, so the gate stays under its file LLOC ceiling.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = ["item_comment_bodies"]


def item_comment_bodies(*, path: StoreConfig, work_item_id: str) -> tuple[str, ...] | None:
    """One item's comment bodies oldest-first, or `None` when they cannot be read.

    `None` and the empty tuple are deliberately different answers: an item with
    no comments has no recorded verdict and must be judged, while an item whose
    sidecar could not be read is one nothing can be concluded about.
    """
    read = attempt(
        action=lambda: read_work_item_comments(path=path, work_item_id=work_item_id),
        exceptions=(
            BeadsCommandError,
            BeadsConnectionError,
            BeadsMappingError,
            BeadsTenantMissingError,
        ),
    )
    if isinstance(read, AttemptFailure):
        return None
    return tuple(comment.text for comment in read)
