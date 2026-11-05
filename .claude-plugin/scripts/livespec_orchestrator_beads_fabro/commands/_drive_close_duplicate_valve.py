"""The `close-duplicate:<id>:<successor>` human valve.

A duplicate is a disposition, not a release from a spec-change hold.  The
successor already carries the commitment, so this valve may close a held item
in any non-terminal lane without revisiting tier classification or intake.
Every refusal is decided before the first ledger or journal write.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from livespec_orchestrator_beads_fabro import store
from livespec_orchestrator_beads_fabro._beads_client import EDGE_SUPERSEDES, make_beads_client
from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    LOCK_ABSENT,
    observe_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._drive_merge_hold_arm_guard import (
    observe_item_run_liveness,
)
from livespec_orchestrator_beads_fabro.commands._drive_valve_result import (
    valve_refusal,
    valve_success,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
    from livespec_orchestrator_beads_fabro.commands._drive_reject_valve import HumanValveRunner
    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = ["CLOSE_DUPLICATE_ACTION", "CLOSE_DUPLICATE_STAGE", "close_duplicate"]

CLOSE_DUPLICATE_ACTION = "close-duplicate"
CLOSE_DUPLICATE_STAGE = "human-valve-close-duplicate"
_JOURNAL_RELATIVE_PATH = Path("tmp") / "fabro-dispatch-journal.jsonl"


def close_duplicate(  # noqa: PLR0913 - each keyword is an independent action input.
    *,
    repo: Path,
    config: StoreConfig,
    item: WorkItem,
    aid: str,
    successor_id: str,
    identity: InvokerIdentity,
    runner: HumanValveRunner | None,
) -> dict[str, Any]:
    """Close `item` as a duplicate of the readable `successor_id` item."""
    refusal = _eligibility_refusal(
        repo=repo,
        config=config,
        item=item,
        aid=aid,
        successor_id=successor_id,
        runner=runner,
    )
    if refusal is not None:
        return refusal

    # A supersedes edge points from the successor to the duplicate.  This is
    # the store's durable representation of the duplicate's `superseded_by`.
    make_beads_client(config=config).add_dependency(
        from_id=successor_id,
        to_id=item.id,
        edge_type=EDGE_SUPERSEDES,
    )
    append_work_item_comment(
        path=config,
        work_item_id=item.id,
        body=_comment(successor_id=successor_id, invoker=identity.invoker),
    )
    record = _journal(repo=repo, identity=identity, item=item, successor_id=successor_id)
    store.append_work_item(path=config, item=_closed_item(item=item, successor_id=successor_id))
    return valve_success(
        aid=aid,
        wid=item.id,
        stage=CLOSE_DUPLICATE_STAGE,
        status="done",
        assignee=None,
        msg=f"Closed {item.id} as a duplicate of {successor_id}.",
    ) | {"journal": record, "successor": successor_id}


def _eligibility_refusal(  # noqa: PLR0911 - one refusal per ordered guard.
    *,
    repo: Path,
    config: StoreConfig,
    item: WorkItem,
    aid: str,
    successor_id: str,
    runner: HumanValveRunner | None,
) -> dict[str, Any] | None:
    """Return the first no-write reason this duplicate cannot be closed."""
    successor = next(
        (
            candidate
            for candidate in store.read_work_items(path=config)
            if candidate.id == successor_id
        ),
        None,
    )
    if successor is None:
        return valve_refusal(
            aid=aid,
            wid=item.id,
            err="successor-not-found",
            msg=(
                f"{CLOSE_DUPLICATE_ACTION} refused: successor {successor_id} does not resolve "
                "to a work item the Dispatcher can read."
            ),
        )
    if successor.id == item.id:
        return valve_refusal(
            aid=aid,
            wid=item.id,
            err="self-successor",
            msg=f"{CLOSE_DUPLICATE_ACTION} refused: {item.id} cannot supersede itself.",
        )
    if item.status == "done":
        return valve_refusal(
            aid=aid,
            wid=item.id,
            err="already-closed",
            msg=f"{CLOSE_DUPLICATE_ACTION} refused: {item.id} is already closed.",
        )
    liveness = observe_item_run_liveness(repo=repo, work_item_id=item.id, runner=runner)
    if not liveness.observed:
        return valve_refusal(
            aid=aid,
            wid=item.id,
            err="live-run",
            msg=(
                f"{CLOSE_DUPLICATE_ACTION} refused: whether a run of {item.id} is live could "
                "not be established because the configured factory did not answer with a run "
                "inventory."
            ),
        )
    if liveness.live_run_ids:
        return valve_refusal(
            aid=aid,
            wid=item.id,
            err="live-run",
            msg=(
                f"{CLOSE_DUPLICATE_ACTION} refused: {', '.join(liveness.live_run_ids)} is "
                f"still non-terminal, so a run of {item.id} is live."
            ),
        )
    if observe_dispatch_lock(repo=repo, work_item_id=item.id) != LOCK_ABSENT:
        return valve_refusal(
            aid=aid,
            wid=item.id,
            err="dispatch-lock-held",
            msg=(
                f"{CLOSE_DUPLICATE_ACTION} refused: {item.id} has an unreleased "
                "dispatch-scoped ownership claim."
            ),
        )
    return None


def _closed_item(*, item: WorkItem, successor_id: str) -> WorkItem:
    """Return the terminal duplicate record consumed by the store close seam."""
    from dataclasses import replace

    return replace(
        item,
        status="done",
        assignee=None,
        reason=f"Duplicate of {successor_id}.",
        superseded_by=successor_id,
    )


def _comment(*, successor_id: str, invoker: str) -> str:
    return "\n".join(
        (
            CLOSE_DUPLICATE_ACTION,
            "",
            f"successor: {successor_id}",
            f"invoker: {invoker}",
        )
    )


def _journal(
    *, repo: Path, identity: InvokerIdentity, item: WorkItem, successor_id: str
) -> dict[str, object]:
    record: dict[str, object] = {
        "actor": "operator",
        "stage": CLOSE_DUPLICATE_STAGE,
        "work_item_id": item.id,
        "successor": successor_id,
    }
    JournalFile(path=repo / _JOURNAL_RELATIVE_PATH, identity=identity).append(record=record)
    return record
