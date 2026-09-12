"""Establishing one dispatch's identity and the lock that makes it exclusive.

Split out of `_dispatcher_loop` because "who is this dispatch, and does it already own a
lock" is settled BEFORE any dispatch work begins and is never revisited afterwards. The
loop's own concern starts once the answer exists.

THE LOCK DECIDES THE IDENTITY, NOT THE OTHER WAY AROUND. A live lock carrying a dispatch
id means this work-item is already mid-dispatch under that id, so the identity is ADOPTED
from the lock rather than minted afresh — minting a second id for an item already holding
one would split its journal across two identities and make the run unqueryable by either.
A fresh id is minted only when no live lock names one.

THE FACTORY-TARGET DEFAULT IS APPLIED TO `args` IN PLACE, DELIBERATELY. Downstream seams
read the resolved target off the namespace rather than being handed it, so a default
returned instead of installed would leave every one of them reading `None`. The recorded
`dispatch_factory` is None in exactly that defaulted case, because "no factory was named"
and "the `default` placeholder was named" are different facts and only the first belongs
on a journal row.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_id_journal import (
    DispatchJournalIdentity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    dispatch_lock_path,
    live_dispatch_lock,
    write_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import run_id

__all__: list[str] = [
    "DispatchLease",
    "resolve_dispatch_lease",
]


@dataclass(frozen=True, kw_only=True)
class DispatchLease:
    """One dispatch's journal identity and the lock path its release must target."""

    identity: DispatchJournalIdentity
    lock_path: Path


def resolve_dispatch_lease(
    *,
    args: argparse.Namespace,
    repo: Path,
    work_item_id: str,
) -> DispatchLease:
    """Adopt this item's live dispatch lock, or take a fresh one under a new id."""
    raw_factory_target = getattr(args, "fabro_factory_target", None)
    dispatch_factory = (
        raw_factory_target.name if isinstance(raw_factory_target, FactoryTarget) else None
    )
    if not isinstance(raw_factory_target, FactoryTarget):
        args.fabro_factory_target = FactoryTarget(name="default", server=None, dev_token=None)
    lock = live_dispatch_lock(repo=repo, work_item_id=work_item_id)
    if lock is None or lock.dispatch_id is None:
        dispatch_id = run_id()
        lock_path = write_dispatch_lock(
            repo=repo, work_item_id=work_item_id, dispatch_id=dispatch_id
        )
    else:
        dispatch_id = lock.dispatch_id
        lock_path = dispatch_lock_path(repo=repo, work_item_id=work_item_id)
    return DispatchLease(
        identity=DispatchJournalIdentity(
            dispatch_id=dispatch_id,
            dispatch_factory=dispatch_factory,
        ),
        lock_path=lock_path,
    )
