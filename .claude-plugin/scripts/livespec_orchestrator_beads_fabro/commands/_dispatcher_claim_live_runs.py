"""Which ledger-active claims still hold a factory run slot (bd-ib-rtzhfc).

`dispatcher.wip_cap` bounds the claims that hold a factory run slot. A live
dispatch lock alone does not prove one: a dispatcher keeps its lock through
the post-run legs that follow its factory run, and on 2026-11-05 ~04:15Z the
WIP count read 20/20 while the petri board read 15/16 for exactly that
reason. So a claim holds a slot unless BOTH of these are observed:

- its current dispatch has a stamped run, meaning a `dispatch-run-stamp`
  record newer than its latest `ledger-admit`; and
- the factory that stamp names, read now, does not list the claim's work item
  with a non-terminal run.

Both fallbacks keep the claim counted. A claim with no stamped run since its
admit is still launching. A board nobody could read is `None`, never an empty
set: an empty set would say "no item holds a run here", the one reading that
would release every slot on a factory nobody could reach. The board is the
idle-slot board's own `live_item_ids`, so the two never disagree about what a
live run is. Each factory is read at most once per accounting pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_board import (
    RunLister,
    read_idle_slot_board,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt, parse_json

__all__: list[str] = ["RunSlotBoard", "current_run_factories", "read_live_item_ids"]

_ADMIT_STAGE = "ledger-admit"
_STAMP_STAGE = "dispatch-run-stamp"


def read_live_item_ids(
    *, repo: Path, factory: str, lister: RunLister | None = None
) -> frozenset[str] | None:
    """The work items `factory` lists with a non-terminal run, or `None` if unreadable."""
    reading = read_idle_slot_board(repo=repo, factory=factory, lister=lister)
    return reading.live_item_ids if reading.observable else None


def current_run_factories(*, journal_path: Path) -> dict[str, str]:
    """Each work item whose CURRENT dispatch has a stamped run, mapped to that run's factory.

    An unreadable journal maps nothing, which keeps every claim counted.
    """
    read = attempt(action=lambda: journal_path.read_text(encoding="utf-8"), exceptions=(OSError,))
    text = "" if isinstance(read, AttemptFailure) else read
    factories: dict[str, str] = {}
    for line in text.splitlines():
        item_id, stage, factory = _stamp_fields(record=parse_json(text=line))
        if stage == _ADMIT_STAGE and item_id is not None:
            _ = factories.pop(item_id, None)
        elif stage == _STAMP_STAGE and item_id is not None and factory is not None:
            factories[item_id] = factory
    return factories


@dataclass(kw_only=True)
class RunSlotBoard:
    """One accounting pass's view of which live-lock claims hold a run slot.

    `journal` is read lazily and only through its `path`: some callers hand
    the accounting an in-memory journal writer with no file behind it, and that
    journal maps no stamp, so every claim it carries stays counted.
    """

    repo: Path
    journal: object
    _factories: dict[str, str] | None = None
    _live: dict[str, frozenset[str] | None] = field(default_factory=dict)

    def holds_run_slot(self, *, work_item_id: str) -> bool:
        """False only when the claim's stamped run is observed NOT live on its factory."""
        if self._factories is None:
            path = getattr(self.journal, "path", None)
            self._factories = (
                current_run_factories(journal_path=path) if isinstance(path, Path) else {}
            )
        factory = self._factories.get(work_item_id)
        if factory is None:
            return True
        if factory not in self._live:
            self._live[factory] = read_live_item_ids(repo=self.repo, factory=factory)
        live = self._live[factory]
        return live is None or work_item_id in live


def _stamp_fields(*, record: object) -> tuple[str | None, object, str | None]:
    row = cast("dict[str, object]", record) if isinstance(record, dict) else {}
    item_id = row.get("work_item_id")
    factory = row.get("dispatch_factory")
    return (
        item_id if isinstance(item_id, str) else None,
        row.get("stage"),
        factory if isinstance(factory, str) else None,
    )
