"""WorkItemStore protocol facade for the beads-backed store."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from livespec_runtime.work_items.store import WorkItemStore

from livespec_orchestrator_beads_fabro._store_mutations import append_work_item
from livespec_orchestrator_beads_fabro.types import WorkItem

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = ["BeadsWorkItemStore"]


class BeadsWorkItemStore:
    """Thin `WorkItemStore` conformance facade over the store free functions."""

    def __init__(self, *, config: StoreConfig) -> None:
        self._config = config

    def read_work_items(self) -> Iterator[WorkItem]:
        """Stream every WorkItem in the tenant (delegates to the free function)."""
        from livespec_orchestrator_beads_fabro.store import read_work_items

        return read_work_items(path=self._config)

    def append_work_item(self, *, item: WorkItem) -> None:
        """Add one WorkItem to the tenant (delegates to the free function)."""
        append_work_item(path=self._config, item=item)


_: type[WorkItemStore] = BeadsWorkItemStore
