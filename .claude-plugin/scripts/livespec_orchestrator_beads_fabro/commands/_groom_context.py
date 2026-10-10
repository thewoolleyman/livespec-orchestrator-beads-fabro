"""Read-only context for drafting a backlog decomposition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro import regroom
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsRecord
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "GroomContext",
    "load_groom_context",
]


@dataclass(frozen=True, kw_only=True)
class GroomContext:
    """The read-only scoping context a groom draft is grounded in.

    Returned by `load_groom_context` after confirming the target is in
    `backlog`. Carries only what the draft needs; the front-end's dialogue
    reads the spec / scenarios / ledger separately (read-only).
    """

    item_id: str
    title: str
    description: str


def load_groom_context(*, path: StoreConfig, item_id: str) -> GroomContext:
    """Read the backlog target read-only, refusing any other lifecycle state.

    The READ-ONLY entry point: it confirms `item_id` is present and currently
    in `backlog`. Mutates nothing; the draft stays read-only until
    `file_approved_slices` is called on approval.
    """
    regroom.require_backlog_target(path=path, item_id=item_id)
    record = make_beads_client(config=path).show_issue(issue_id=item_id)
    return GroomContext(
        item_id=item_id,
        title=_record_str(record=record, key="title"),
        description=_record_str(record=record, key="description"),
    )


def _record_str(*, record: BeadsRecord, key: str) -> str:
    value = record.get(key)
    return value if isinstance(value, str) else ""
