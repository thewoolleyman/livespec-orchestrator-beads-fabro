"""The EXCLUSION one claim recovery runs inside: the PRIMARY checkout's lock.

A reconciliation pass runs from whichever checkout invoked it, and a tenant
owns no shared directory — a worktree, a janitor checkout and a fresh clone
share an origin and a beads tenant but never a filesystem root
(`_dispatcher_tenant_checkouts` records the measurement). So a lock taken under
the invoking `--repo` excludes that checkout's own callers and NOTHING else:
two passes in two checkouts of one tenant would each find the claim stranded
and each recover it, writing two journal rows, two ledger comments and two
status transitions for one claim.

THE PRIMARY CHECKOUT IS THE ONE PLACE EVERY CHECKOUT CAN AGREE ON. Every
checkout of a tenant resolves the same `livespec.primaryPath`, so a lock there
is a lock every sibling pass contends for. That is why the contract names the
primary checkout specifically rather than "a lock": the location IS the
exclusion, and taking the same lock in the wrong place provides none.

IT REUSES THE DISPATCH LOCK RATHER THAN INVENTING A SECOND ONE, and that is
load-bearing in both directions. A recovery that held a private lock would be
invisible to the WIP-cap accounting and to a sibling pass's own owner-liveness
reading, which is exactly the reading that must see it: a second pass measuring
`observe_owner_liveness` while this one holds the lock reads `dispatch-live`
and holds its claim, which is the hold the clause already defines. So the
exclusion needs no new reason of its own — it arrives through a measurement
that already exists.

A LOCK THAT CANNOT BE TAKEN IS `effect-unobservable`, never a release. The
caller grades it so, and the reading is honest in both of the two ways this
can fail: a live holder means another recovery or dispatch owns the item right
now, and an IO fault means nothing here can be established. Both say the same
thing to a recovery — the effect cannot be established, so write nothing and
let the next pass measure again. Note that `dispatch-live` is deliberately NOT
re-derived here: the ladder graded owner liveness moments ago from EVERY
checkout's lock, and a second, narrower reading taken at one location would
report a different condition for the same fact.

THE RELEASE IS IN A `finally`, because every return path inside the recovery —
the holds, the convergent skips, the terminal delegation that reaches the
Dispatcher's own dispositions — must drop the lock. A lock left behind makes
the item read as permanently owned to every later pass, which converts one
failed recovery into a claim nothing can ever release.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    release_dispatch_lock,
    write_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_gate import (
    resolve_primary_repository,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "RECOVERY_LOCK_DISPATCH_PREFIX",
    "claim_recovery_fence",
]

# What the lock's `dispatch_id` names, so an operator reading a lock file can
# tell a RECOVERY's fence from a dispatch's own claim. The run id follows, which
# is what says WHICH stranded claim is being recovered.
RECOVERY_LOCK_DISPATCH_PREFIX = "stranded-claim-recovery"


@contextmanager
def claim_recovery_fence(*, repo: Path, work_item_id: str, run_id: str) -> Iterator[bool]:
    """Hold the primary checkout's dispatch lock for one claim recovery.

    Yields whether the lock was taken. A `False` is the caller's signal to
    write nothing at all — not a suggestion to proceed carefully — because
    every durable effect below it would then be racing a holder this pass
    could not see.
    """
    primary = _primary_checkout(repo=repo)
    if primary is None:
        yield False
        return
    taken = attempt(
        action=lambda: write_dispatch_lock(
            repo=primary,
            work_item_id=work_item_id,
            dispatch_id=f"{RECOVERY_LOCK_DISPATCH_PREFIX}:{run_id}",
        ),
        exceptions=(OSError,),
    )
    if isinstance(taken, AttemptFailure):
        yield False
        return
    try:
        yield True
    finally:
        release_dispatch_lock(path=taken)


def _primary_checkout(*, repo: Path) -> Path | None:
    """This tenant's primary checkout, or None when it could not be resolved.

    `resolve_primary_repository` asks git for `livespec.primaryPath` and falls
    back to the invoking checkout when the key is unset, which is the right
    answer for a single-checkout clone. `None` is reserved for the case where
    the QUESTION could not be put — no `git` to ask — because a recovery that
    cannot locate the one agreed lock location has no exclusion to take.
    """
    resolved = attempt(
        action=lambda: resolve_primary_repository(repository=repo),
        exceptions=(OSError,),
    )
    return None if isinstance(resolved, AttemptFailure) else resolved
