"""The per-item dispatch LOCK scope: hold it, dispatch inside it, release the claim.

Split out of `_dispatcher_loop`, which stood at exactly the 250-LLOC hard ceiling,
so the sequence that materializes the run-config overlay could take the one
further argument the projected proof-asset rendering needs. The two modules own
different concerns: this one owns the SCOPE a dispatch runs in -- the factory
target the invocation selected, the per-item dispatch lock, the dispatch id that
names it, and the pre-run claim released on the way out -- while `_dispatcher_loop`
owns the SEQUENCE that runs inside it, from the first pre-run refusal through the
post-run review gate.

The seam is where the coupling is thinnest: everything crossing it is already a
parameter of the sequence, so no context type had to be invented to carry it.
`dispatch_one_locked` is PUBLIC on the other side because only public names may
cross a module boundary; it was private while both halves shared one file.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_id_journal import (
    DispatchJournalIdentity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    dispatch_lock_path,
    live_dispatch_lock,
    release_dispatch_lock,
    write_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop import dispatch_one_locked
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import run_id
from livespec_orchestrator_beads_fabro.commands._dispatcher_pre_run_claim import (
    release_pre_run_claim_if_needed,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "dispatch_one",
]


def dispatch_one(
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    journal: JournalFile,
    janitor: tuple[str, ...] | None,
) -> DispatchOutcome:
    raw_factory_target = getattr(args, "fabro_factory_target", None)
    dispatch_factory = (
        raw_factory_target.name if isinstance(raw_factory_target, FactoryTarget) else None
    )
    if not isinstance(raw_factory_target, FactoryTarget):
        args.fabro_factory_target = FactoryTarget(name="default", server=None, dev_token=None)
    lock = live_dispatch_lock(repo=repo, work_item_id=item.id)
    if lock is None or lock.dispatch_id is None:
        dispatch_id = run_id()
        lock_path = write_dispatch_lock(repo=repo, work_item_id=item.id, dispatch_id=dispatch_id)
    else:
        dispatch_id = lock.dispatch_id
        lock_path = dispatch_lock_path(repo=repo, work_item_id=item.id)
    with ExitStack() as stack:
        _ = stack.callback(lambda: release_dispatch_lock(path=lock_path))
        outcome = dispatch_one_locked(
            args=args,
            repo=repo,
            item=item,
            journal=journal,
            janitor=janitor,
            identity=DispatchJournalIdentity(
                dispatch_id=dispatch_id,
                dispatch_factory=dispatch_factory,
            ),
        )
        release_pre_run_claim_if_needed(repo=repo, item=item, outcome=outcome, journal=journal)
        return outcome
