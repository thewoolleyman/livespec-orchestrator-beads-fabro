"""The `driver-dispatch:<id>` door — the journaled dispatch for host-only work.

`SPECIFICATION/contracts.md` names this one of the two doors into `active`, and
binds the pairing: `active` is entered ONLY by a journaled dispatch or by a
rework return from `acceptance`. The factory dispatch refuses exactly the
host-only set (the admission valve's host-only refusal, which tells the operator
to host-route the item instead), so for an item carrying a non-null
`factory_safety` this is the only forward door there is. Without it the attended
host-only work still happens, but it happens off the journaled doors and the
item's state cannot say it is in progress.

It is routed on its own prefix straight from `drive.py` rather than through the
`_drive_valves` router because that module documents itself as holding "the
valves that do nothing but write the ledger", and because it sits at its own
file-size ceiling. The payload builders are the shared ones either way, so a
console consuming drive results sees the same shape it sees for every other
operator verb in the `ready` lane's vocabulary.

THE ELIGIBILITY PREDICATE IS A SAFETY PROPERTY, NOT A CONVENIENCE FILTER. The
spec says so outright: because the eligible set is precisely the set the
Dispatcher refuses, no dispatcher/driver race is possible and no claim mechanism
is required — and "widening `driver-dispatch` to any `ready` item WOULD require a
claim mechanism, and MUST NOT be done without one". Both halves of
`status == "ready" AND factory_safety is not None` therefore stand in for the
claim mechanism this door does not have; relaxing either one reintroduces the
race silently, because a widened door looks exactly like a working one.

The journal write routes through `JournalFile`, the single append layer, so the
acting identity is stamped there once and this writer cannot forge it. That
durable record is what makes the door journaled — the `journal` key the result
payload also carries is transient and unattributable the moment the invocation
returns, which is precisely why the door rules refuse to count one as a journal
record.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro import store
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_lifecycle_writes import (
    write_work_item_status_and_reconcile,
)
from livespec_orchestrator_beads_fabro.commands._drive_valve_result import (
    invalid_source_state,
    valve_refusal,
    valve_success,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "DRIVER_DISPATCH_PREFIX",
    "DRIVER_DISPATCH_STAGE",
    "driver_session_reference",
    "is_driver_dispatch_action",
    "run_driver_dispatch",
]

DRIVER_DISPATCH_PREFIX = "driver-dispatch:"
DRIVER_DISPATCH_STAGE = "human-valve-driver-dispatch"

_SOURCE_STATUS = "ready"
_TARGET_STATUS = "active"

# The one journal the Dispatcher and the drive valves already append to, so a
# driver dispatch and a factory dispatch of the same item are readable from one
# file in one pass.
_JOURNAL_RELATIVE_PATH = Path("tmp") / "fabro-dispatch-journal.jsonl"

_NOT_HOST_ONLY_REFUSAL = (
    "driver-dispatch requires a ready item whose factory_safety is non-null -- "
    "exactly the host-only set the factory admission valve refuses. A factory-safe "
    "item is dispatched through the factory ('impl:<id>'); widening this door to "
    "any ready item would require a claim mechanism it does not have."
)


def is_driver_dispatch_action(*, action_id: str) -> bool:
    """Does `action_id` select the driver-dispatch door?"""
    return action_id.startswith(DRIVER_DISPATCH_PREFIX)


def driver_session_reference(*, driver_session: str | None, identity: InvokerIdentity) -> str:
    """Resolve the reference to the session that will drive this item.

    An explicitly asserted `--driver-session` wins; otherwise the reference is
    the invocation's own resolved invoker, because the session that presses this
    door is normally the session that then drives the item. Falling back rather
    than refusing is what keeps the SPECIFIED action-id grammar whole: the spec
    gives `driver-dispatch` exactly two fields, so a third one cannot be made
    mandatory here without contradicting it.

    A blank assertion is treated as no assertion, for the reason
    `resolve_invoker` treats one that way: an empty string is not a reference,
    and letting it through would journal a driver session nobody can find.
    """
    asserted = None if driver_session is None else driver_session.strip()
    return asserted or identity.invoker


def run_driver_dispatch(
    *,
    repo: Path,
    action_id: str,
    identity: InvokerIdentity,
    driver_session: str | None = None,
) -> dict[str, Any]:
    """Open the driver-dispatch door for the work-item `action_id` names.

    ORDER IS LOAD-BEARING in the same way `resolve_blocked_item`'s is, but the
    other way round: every refusal is decided BEFORE anything is written, so an
    ineligible press leaves the item exactly where it was and the operator can
    re-run the identical action once the item qualifies.
    """
    item_id = action_id.removeprefix(DRIVER_DISPATCH_PREFIX)
    config = resolve_store_config(cwd=repo, work_items_arg=None)
    item = _find_item(items=list(store.read_work_items(path=config)), item_id=item_id)
    if item is None:
        return valve_refusal(
            aid=action_id,
            err="work-item-not-found",
            msg=f"work-item not found: {item_id}",
        )
    refusal = _eligibility_refusal(item=item, aid=action_id)
    if refusal is not None:
        return refusal
    session = driver_session_reference(driver_session=driver_session, identity=identity)
    write_work_item_status_and_reconcile(path=config, item_id=item.id, status=_TARGET_STATUS)
    record = _journal_driver_dispatch(repo=repo, identity=identity, item=item, session=session)
    return valve_success(
        aid=action_id,
        wid=item.id,
        stage=DRIVER_DISPATCH_STAGE,
        status=_TARGET_STATUS,
        assignee=None,
        msg=(
            f"Driver-dispatched {item.id}: {_SOURCE_STATUS} -> {_TARGET_STATUS}; "
            f"driver session {session}. Park the result at acceptance."
        ),
    ) | {"journal": record}


def _find_item(*, items: list[WorkItem], item_id: str) -> WorkItem | None:
    return next((item for item in items if item.id == item_id), None)


def _eligibility_refusal(*, item: WorkItem, aid: str) -> dict[str, Any] | None:
    """Refuse a press outside the eligible set, or `None` to open the door.

    The two guards are the whole safety property; see this module's header for
    why neither may be relaxed on its own.
    """
    if item.status != _SOURCE_STATUS:
        return invalid_source_state(aid=aid, item=item, expected=_SOURCE_STATUS)
    if item.factory_safety is None:
        return valve_refusal(
            aid=aid,
            wid=item.id,
            err="not-host-only",
            msg=_NOT_HOST_ONLY_REFUSAL,
        )
    return None


def _journal_driver_dispatch(
    *, repo: Path, identity: InvokerIdentity, item: WorkItem, session: str
) -> dict[str, object]:
    """Append the durable record for this door and return what was written.

    The record carries the driver-session reference and the transition's two
    ends; the ACTOR is stamped by the append layer, which is the only place the
    attribution contract lets it come from. It is returned so the result payload
    republishes the SAME object rather than a second, hand-built description of
    it that could drift from the record on disk.
    """
    record: dict[str, object] = {
        "actor": "operator",
        "stage": DRIVER_DISPATCH_STAGE,
        "work_item_id": item.id,
        "driver_session": session,
        "factory_safety": item.factory_safety,
        "from_status": _SOURCE_STATUS,
        "to_status": _TARGET_STATUS,
    }
    JournalFile(path=repo / _JOURNAL_RELATIVE_PATH, identity=identity).append(record=record)
    return record
