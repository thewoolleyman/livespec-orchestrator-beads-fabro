"""Ledger persistence for a work-item's description text.

The ONE write path for the description column. It exists because the Proof of
Done pointer clause of `SPECIFICATION/contracts.md` (v114) makes the description
a thing the Dispatcher WRITES after merge, where every other description write in
this plugin happens at creation time through `create_issue`.

The write is a whole-column replace, which is why the composition of the new text
is NOT this module's job: the pointer splice is pure and lives beside the section
it writes, and this module takes the finished bytes. Splitting it the other way
would put a read-modify-write of markdown behind the store seam, where no test of
the splice could reach it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "update_work_item_description",
]


def update_work_item_description(*, path: StoreConfig, item_id: str, description: str) -> None:
    """Replace one work-item's description with the supplied text."""
    make_beads_client(config=path).update_issue(issue_id=item_id, description=description)
