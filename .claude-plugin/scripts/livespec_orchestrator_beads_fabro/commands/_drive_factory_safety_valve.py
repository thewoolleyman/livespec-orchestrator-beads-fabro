"""The `set-factory-safety:<id>:<reason>` valve — the attributable opt-out.

`SPECIFICATION/contracts.md` makes this verb the ONLY route out of factory
eligibility: "opting an item out of factory eligibility MUST go through this
verb, so the reason is recorded on the item in the journal, rather than through a
raw `bd label add` that leaves no attributable record". The valve is therefore
where the mandatory rationale is enforced, and the journal append is not a
courtesy — it is half of what the contract asks for.

TWO PROPERTIES ARE LOAD-BEARING AND NEITHER IS INCIDENTAL.

`factory_safety` is an INTRINSIC runnability axis, orthogonal to lifecycle
status, so the verb is valid on an item in ANY lane. It is deliberately NOT
gated to `ready` the way `set-workflow-scope-override` is: the fact that a slice
needs host secrets is true while it is still `backlog`, and a valve that could
only be pressed in one lane would push every earlier press back onto the raw
label edit this verb exists to retire.

And the reason is graded HERE rather than in the action-id grammar. The grammar
could reject an out-of-enum value by simply not recognizing the id, but the
operator would then read "Unsupported human valve action id." — the same message
a typo'd VERB produces, which cannot tell them their verb was right and their
reason was wrong. Contracts.md requires the three canonical values by name, so
the refusal names them.

The write is label-only and the status is echoed back unchanged, because the
contract also binds what this verb must NOT do: it "does NOT change item status
and MUST NOT alter `admission_policy`, the orthogonal human-approval axis".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro._store_label_mutations import (
    FACTORY_SAFETY_REASONS,
    update_work_item_factory_safety,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._drive_valve_result import (
    valve_refusal,
    valve_success,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "FACTORY_SAFETY_ACTION",
    "FACTORY_SAFETY_STAGE",
    "set_factory_safety",
]

FACTORY_SAFETY_ACTION = "set-factory-safety"
FACTORY_SAFETY_STAGE = "human-valve-set-factory-safety"

# The same journal the Dispatcher and the other journaled drive door append to,
# so an opt-out and the host-route it causes are readable from one file in one
# pass (`_drive_driver_dispatch` carries the same constant for the same reason).
_JOURNAL_RELATIVE_PATH = Path("tmp") / "fabro-dispatch-journal.jsonl"


def set_factory_safety(
    *,
    repo: Path,
    config: StoreConfig,
    item: WorkItem,
    aid: str,
    value: str,
    identity: InvokerIdentity,
) -> dict[str, Any]:
    """Record the host-only opt-out reason on `item`, in the store and the journal.

    ORDER IS LOAD-BEARING the way `_drive_driver_dispatch`'s is: the reason is
    graded BEFORE anything is written, so a refused press leaves the item exactly
    factory-eligible and the operator re-runs the identical action with a reason
    the enum admits.
    """
    if value not in FACTORY_SAFETY_REASONS:
        return valve_refusal(
            aid=aid,
            wid=item.id,
            err="invalid-factory-safety-reason",
            msg=(
                f"{FACTORY_SAFETY_ACTION} refused: {value!r} is not a factory_safety "
                f"reason; expected one of {', '.join(FACTORY_SAFETY_REASONS)}."
            ),
        )
    update_work_item_factory_safety(path=config, item_id=item.id, reason=value)
    record = _journal_opt_out(repo=repo, identity=identity, item=item, reason=value)
    return valve_success(
        aid=aid,
        wid=item.id,
        stage=FACTORY_SAFETY_STAGE,
        status=item.status,
        assignee=item.assignee,
        msg=(
            f"Recorded {item.id}: factory_safety -> {value}; status unchanged. "
            "The admission valve now host-routes it; driver-dispatch is the "
            "applicable door."
        ),
    ) | {"journal": record}


def _journal_opt_out(
    *, repo: Path, identity: InvokerIdentity, item: WorkItem, reason: str
) -> dict[str, object]:
    """Append the durable opt-out record and return what was written.

    The ACTOR is stamped by the append layer, which is the only place the
    attribution contract lets it come from. The object is returned so the result
    payload republishes the SAME record rather than a second, hand-built
    description of it that could drift from the line on disk.
    """
    record: dict[str, object] = {
        "actor": "operator",
        "stage": FACTORY_SAFETY_STAGE,
        "work_item_id": item.id,
        "factory_safety": reason,
    }
    JournalFile(path=repo / _JOURNAL_RELATIVE_PATH, identity=identity).append(record=record)
    return record
