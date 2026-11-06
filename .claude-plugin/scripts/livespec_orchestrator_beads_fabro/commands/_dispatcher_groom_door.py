"""The groom door: the one route by which a `backlog` item enters `active`.

`SPECIFICATION/contracts.md` section "Grooming and slice-size calibration" ->
"Consensus-gated automated groom cut" ratifies the groom dispatch as a DOOR
rather than as a new admission rule, and the distinction is the whole design.
The defined `admit` verb stays `ready -> active`; the Dispatcher's drain still
selects only `ready` and rework-pending items and MUST NOT admit a `backlog`
item on its own initiative; and the `groom` front-end's OPERATOR is what opens
this door for one item at a time. So the mechanism lives here, beside the
admission valve rather than inside it: a rule added to
`_dispatcher_admission` would fire on every unattended drain tick, which is
exactly the autonomy the contract withholds.

WHY IT WRITES THE PIN BEFORE THE STATUS. An item that reached `active`
carrying no `dispatch_workflow` pin is indistinguishable from an ordinary
admitted item, so the drain would dispatch it under
`dispatcher.default_workflow` — the implement graph, against a `backlog` epic,
with nothing in the record to say a groom was intended. Pinning first means the
only half-applied state this function can leave behind is a pinned item still
resting in `backlog`, which the operator can simply re-open the door on.

WITH `dispatcher.claim_tokens` TRUE THE DOOR IS ONE WRITE. Opening the door
changes the item's status and its assignee, so it is a claim-changing write
(`SPECIFICATION/contracts.md`, "Claim tokens") and lands only after the door
has won the item's current claim token. A writer that does not win must write
nothing to the item, so the pin cannot go first as it does before the cutover:
it rides the ONE write that moves the item to `active` and names the successor
token. A single write leaves no pinless `active` row either, which is the
property the pin-first order exists for. A door the protocol refused wrote
nothing and is reported as the `claim-refused` cause.

WHY THE KIND IS CHECKED HERE AND AGAIN AT DISPATCH. This door refuses a variant
whose declared kind is not `groom`, and `_dispatcher_workflow_variant` refuses
the APPLY dispatch of an approved draft under a non-groom variant. They are not
redundant: the pin can be changed, cleared, or overridden by an explicit
`--workflow-name` between the two moments, so a check at the door alone would
guard only the first of the two dispatches the ratified two-phase cut makes.

WHY THE READ-BACK PREDICATE LIVES HERE TOO. `groom_door_claimed` recognises
what `groom_dispatch` wrote, and the two halves are one fact: change the claim
the door leaves and the reader that finds it must change with it. Splitting
them across modules is how a door would come to write a claim no launch path
recognises — which is precisely the gap this predicate closes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro._store_dispatch_workflow import (
    dispatch_workflow_for,
    dispatch_workflow_metadata,
    record_dispatch_workflow,
)
from livespec_orchestrator_beads_fabro._store_factory_size_gate import (
    route_factory_size_decomposition,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_self_update as selfup
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_guard import (
    guarded_status_write,
    status_is,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_writes import (
    WRITER_ADMISSION,
    settle_claim_write,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    DispatchLock,
    live_dispatch_lock,
    recorded_dispatch_lock,
    write_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import JournalWriter
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_size_gate import (
    record_factory_size_admission_decision,
    resolved_stored_factory_size_decision,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_size_route import (
    route_size_decomposition,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import resolve_assignee
from livespec_orchestrator_beads_fabro.commands._workflow_variant_kind import groom_variant_names
from livespec_orchestrator_beads_fabro.store import update_work_item_status
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "GROOM_DISPATCH_STAGE",
    "GROOM_DOOR_CLAIM_REFUSED",
    "GROOM_DOOR_NOT_A_GROOM_VARIANT",
    "GROOM_DOOR_NOT_BACKLOG",
    "GROOM_DOOR_REFUSED_STAGE",
    "GROOM_DOOR_SIZE_DECOMPOSITION",
    "GroomDispatch",
    "GroomDoorRefusal",
    "groom_dispatch",
    "groom_door_claimed",
]

# Two stages, never one. A reader counting how many groom dispatches a
# repository has made must not have to filter refusals out of the same stage,
# and a refusal that shared the success stage would inflate that count.
GROOM_DISPATCH_STAGE = "groom-dispatch"
GROOM_DOOR_REFUSED_STAGE = "groom-dispatch-refused"

# The causes the door can refuse for, named rather than numbered so the
# journal row says what was wrong without a reader parsing the detail back out.
GROOM_DOOR_NOT_BACKLOG = "not-backlog"
GROOM_DOOR_NOT_A_GROOM_VARIANT = "not-a-groom-variant"
GROOM_DOOR_SIZE_DECOMPOSITION = "size-decomposition"
GROOM_DOOR_CLAIM_REFUSED = "claim-refused"

_BACKLOG_STATUS = "backlog"
_ACTIVE_STATUS = "active"
_DOOR_INTENT = "groom-door"


@dataclass(frozen=True, kw_only=True)
class GroomDispatch:
    """What the door wrote, reported back to the front-end that opened it.

    A REPORT of persisted facts, never the facts themselves: the status, the
    claim and the pin all live in the store and the lock file, and a caller
    verifying the door worked reads them from there.
    """

    work_item_id: str
    workflow_name: str
    assignee: str | None
    dispatch_id: str


@dataclass(frozen=True, kw_only=True)
class GroomDoorRefusal:
    """A door that did not open, and why — with nothing written."""

    cause: str
    detail: str


def groom_dispatch(
    *,
    repo: Path,
    item: WorkItem,
    variant: str,
    journal: JournalWriter,
) -> GroomDispatch | GroomDoorRefusal:
    """Take one `backlog` item to `active` under a claim and a groom-variant pin.

    Returns the report of what was written, or a refusal that wrote NOTHING —
    not the pin, not the status, not the claim — so the operator can correct
    the variant or the item and re-run the identical call. A door the
    claim-token protocol refused is one of those refusals.
    """
    refusal = _refusal(repo=repo, item=item, variant=variant)
    if refusal is None:
        size_result = resolved_stored_factory_size_decision(
            cwd=repo,
            path_factory=lambda: store_config(repo=repo),
            item=item,
        )
        if not is_successful(size_result):
            failure = unsafe_perform_io(size_result.failure())
            refusal = GroomDoorRefusal(
                cause="configuration",
                detail=failure.detail,
            )
        else:
            size = unsafe_perform_io(size_result.unwrap())
            record_factory_size_admission_decision(
                journal=journal,
                item=item,
                decision=size,
            )
            if size.disposition == "decompose":
                reason = cast("str", size.reason)
                unrouted = route_size_decomposition(
                    repo=repo,
                    path=store_config(repo=repo),
                    work_item_id=item.id,
                    status=item.status,
                    reason=reason,
                    journal=journal,
                    route=route_factory_size_decomposition,
                )
                refusal = GroomDoorRefusal(
                    cause=GROOM_DOOR_SIZE_DECOMPOSITION,
                    detail=reason if unrouted is None else _unrouted(reason=reason, by=unrouted),
                )
    assignee = resolve_assignee(item=item)
    if refusal is None:
        refusal = _claim_refusal(
            repo=repo, item=item, variant=variant, assignee=assignee, journal=journal
        )
    if refusal is not None:
        journal.append(
            record={
                "stage": GROOM_DOOR_REFUSED_STAGE,
                "work_item_id": item.id,
                "workflow_name": variant,
                "cause": refusal.cause,
                "detail": refusal.detail,
            }
        )
        return refusal
    dispatch_id = selfup.run_id()
    _ = write_dispatch_lock(repo=repo, work_item_id=item.id, dispatch_id=dispatch_id)
    journal.append(
        record={
            "stage": GROOM_DISPATCH_STAGE,
            "work_item_id": item.id,
            "workflow_name": variant,
            "from_status": _BACKLOG_STATUS,
            "assignee": assignee,
            "dispatch_id": dispatch_id,
        }
    )
    return GroomDispatch(
        work_item_id=item.id,
        workflow_name=variant,
        assignee=assignee,
        dispatch_id=dispatch_id,
    )


def _claim_refusal(
    *, repo: Path, item: WorkItem, variant: str, assignee: str | None, journal: JournalWriter
) -> GroomDoorRefusal | None:
    """Write the pin and the claim; `None` when the item is `active` under both."""
    config = store_config(repo=repo)
    outcome = settle_claim_write(
        repo=repo,
        item_id=item.id,
        writer=WRITER_ADMISSION,
        intent=_DOOR_INTENT,
        journal=journal,
        unguarded=lambda: _open_unguarded(
            config=config, item=item, variant=variant, assignee=assignee
        ),
        guarded=lambda: guarded_status_write(
            path=config,
            item_id=item.id,
            status=_ACTIVE_STATUS,
            intent=_DOOR_INTENT,
            writer=WRITER_ADMISSION,
            assignee=assignee,
            metadata=dispatch_workflow_metadata(workflow=variant),
            # The door opens from `backlog` only, and `_refusal` checked it there.
            still_as_decided=status_is(status=_BACKLOG_STATUS),
        ),
    )
    if outcome is None:
        return None
    return GroomDoorRefusal(
        cause=GROOM_DOOR_CLAIM_REFUSED,
        detail=(
            f"work-item {item.id} was not claimed because the claim-token protocol "
            f"reported {outcome}; nothing was written to the item"
        ),
    )


def _unrouted(*, reason: str, by: str) -> str:
    """The size refusal of an item whose route to `backlog` the protocol refused."""
    return (
        f"{reason}; the item was not routed to backlog because the claim-token "
        f"protocol reported {by}, and nothing was written to it"
    )


def _open_unguarded(
    *, config: StoreConfig, item: WorkItem, variant: str, assignee: str | None
) -> None:
    """The pin BEFORE the status, in the door's own two writes."""
    record_dispatch_workflow(path=config, work_item_id=item.id, workflow=variant)
    update_work_item_status(path=config, item_id=item.id, status="active", assignee=assignee)


def groom_door_claimed(*, repo: Path, item: WorkItem) -> bool:
    """Is this `active` row the door's OWN claim, still waiting to be launched?

    The three facts `groom_dispatch` wrote, read back in the order that costs
    least: the status, then the claim (one local file), then the pin (a store
    read). An ordinary `active` row fails at the claim and never pays for the
    store read, which matters because the drain asks this of every row it sees.

    A CLAIM HELD BY A DIFFERENT LIVE PROCESS IS NOT THE DOOR'S CLAIM. That is a
    groom dispatch already in flight, and answering True for it would let a
    second drain launch the same row again. A claim held by THIS process is the
    door's, opened moments ago; a claim whose holder has exited is also the
    door's, because the door writes and returns — the measured field case, and
    the one a liveness-only reading refuses. So liveness alone answers neither
    question: the discriminator is WHOSE process, not whether one is running.

    THE DISPATCH ID IS LOAD-BEARING, not decoration. The door stamps one on
    every claim it writes; a lock payload carrying none was not written by a
    dispatching path this predicate should hand to a launch.
    """
    if item.status != _ACTIVE_STATUS:
        return False
    lock = recorded_dispatch_lock(repo=repo, work_item_id=item.id)
    if lock is None or lock.dispatch_id is None:
        return False
    if _held_by_another_live_process(repo=repo, lock=lock):
        return False
    pin = dispatch_workflow_for(path=store_config(repo=repo), work_item_id=item.id)
    return pin in groom_variant_names(repo=repo)


def _held_by_another_live_process(*, repo: Path, lock: DispatchLock) -> bool:
    if lock.pid == os.getpid():
        return False
    return live_dispatch_lock(repo=repo, work_item_id=lock.work_item_id) is not None


def _refusal(*, repo: Path, item: WorkItem, variant: str) -> GroomDoorRefusal | None:
    """Both causes, checked before any write, so a refusal is total."""
    if item.status != _BACKLOG_STATUS:
        return GroomDoorRefusal(
            cause=GROOM_DOOR_NOT_BACKLOG,
            detail=(
                f"work-item {item.id} is {item.status!r}, and the groom door opens from "
                f"{_BACKLOG_STATUS!r} only; the admit verb is ready -> active"
            ),
        )
    registered = groom_variant_names(repo=repo)
    if variant in registered:
        return None
    return GroomDoorRefusal(
        cause=GROOM_DOOR_NOT_A_GROOM_VARIANT,
        detail=(
            f"workflow variant {variant!r} is not a registered groom variant "
            f"(groom variants: {', '.join(registered) if registered != () else 'none'})"
        ),
    )
