"""Exactly one class per priority child, by the first rule that matches.

The twelve classes and their order are the idle-slot clause's own ladder in
`SPECIFICATION/contracts.md`.

BLOCKED BEATS STALE-EDGE WHEN THE BLOCKER HAS A LIVE RUN. The journaled script
this surface replaces treated any `active` or `acceptance` blocker as
landed-but-unclosed, so `bd-ib-pe2dxk` read STALE EDGE while its only open
blocker `bd-ib-myvlbl` had an implement run in flight that later succeeded in
117 minutes. `active` means in flight, not landed. A blocker that is `active`
WITH an attributed live row is therefore a real blocker; only an `acceptance`
blocker, or an `active` one with NO attributed live row, is a stale edge. And
STALE-EDGE requires EVERY open blocker to be such an edge: one real blocker
beside a stale one still blocks.

ONE CONSERVATIVE EDGE, STATED. `HOST-ONLY` is decided by `is_host_only_item`
over the item's own materialized fields with NO raw labels, exactly as the
idle-factory fact decides it. An item whose workflow-scope override lives in a
ledger label therefore reads host-only here, so this surface can only ever
WITHHOLD a child from the finding line, never add one falsely.

"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from livespec_runtime.cross_repo.types import LocalDependency

from livespec_orchestrator_beads_fabro.commands._cross_repo import parse_entry
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_only import is_host_only_item
from livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_board import BoardReading
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "BLOCKER_STATUS_ABSENT",
    "CLASS_BLOCKED",
    "CLASS_DISPATCHABLE_NOW",
    "CLASS_HELD",
    "CLASS_HOST_ONLY",
    "CLASS_NEEDS_APPROVAL",
    "CLASS_NEEDS_CAPTURE_OR_ACCEPT",
    "CLASS_PARKED",
    "CLASS_POST_RUN",
    "CLASS_RUNNING",
    "CLASS_STALE_EDGE",
    "CLASS_UNADMITTED",
    "CLASS_UNCLASSIFIED_STATUS",
    "CLOSED_STATUSES",
    "IDLE_SLOT_CLASSES",
    "READY_STATUS",
    "BlockerView",
    "ClassifiedChild",
    "classify_child",
    "open_blockers",
]

READY_STATUS = "ready"
# The two spellings of a resolved record: the livespec `done` lane and the
# beads-native `closed` status the store maps it from. A closed record is
# neither a child nor an open blocker, and both surfaces read that from here
# so they cannot disagree about what "resolved" means.
CLOSED_STATUSES: frozenset[str] = frozenset({"closed", "done"})

CLASS_RUNNING = "RUNNING"
CLASS_POST_RUN = "POST-RUN"
CLASS_NEEDS_CAPTURE_OR_ACCEPT = "NEEDS-CAPTURE-OR-ACCEPT"
CLASS_NEEDS_APPROVAL = "NEEDS-APPROVAL"
CLASS_UNADMITTED = "UNADMITTED"
CLASS_PARKED = "PARKED"
CLASS_HOST_ONLY = "HOST-ONLY"
CLASS_BLOCKED = "BLOCKED"
CLASS_STALE_EDGE = "STALE-EDGE"
CLASS_HELD = "HELD"
CLASS_DISPATCHABLE_NOW = "DISPATCHABLE-NOW"
CLASS_UNCLASSIFIED_STATUS = "UNCLASSIFIED-STATUS"

IDLE_SLOT_CLASSES: tuple[str, ...] = (
    CLASS_RUNNING,
    CLASS_POST_RUN,
    CLASS_NEEDS_CAPTURE_OR_ACCEPT,
    CLASS_NEEDS_APPROVAL,
    CLASS_UNADMITTED,
    CLASS_PARKED,
    CLASS_HOST_ONLY,
    CLASS_BLOCKED,
    CLASS_STALE_EDGE,
    CLASS_HELD,
    CLASS_DISPATCHABLE_NOW,
    CLASS_UNCLASSIFIED_STATUS,
)

# The status a blocker absent from its tenant is SHOWN with. The clause makes
# such a blocker OPEN and requires it to be shown as unresolved, so the absence
# is rendered rather than letting the row read as an unblocked child.
BLOCKER_STATUS_ABSENT = "absent-from-tenant"

_ACCEPTANCE_STATUS = "acceptance"
_ACTIVE_STATUS = "active"

# The clause's status ladder, flattened to the lookup it already is: the six
# non-`ready` arms are disjoint status sets, so a table says exactly what a
# six-branch cascade would and cannot drift out of the clause's order. Both
# beads-native spellings the store normalizes away (`in_progress`, `open`,
# `deferred`) are carried, because the audit reads other tenants' ledgers and
# a tenant mid-normalization still holds them.
_CLASS_BY_STATUS: dict[str, str] = {
    "active": CLASS_POST_RUN,
    "in_progress": CLASS_POST_RUN,
    _ACCEPTANCE_STATUS: CLASS_NEEDS_CAPTURE_OR_ACCEPT,
    "pending-approval": CLASS_NEEDS_APPROVAL,
    "backlog": CLASS_UNADMITTED,
    "open": CLASS_UNADMITTED,
    "blocked": CLASS_PARKED,
    "deferred": CLASS_PARKED,
}


@dataclass(frozen=True, kw_only=True)
class BlockerView:
    """One OPEN `blocks` blocker of a child, with the status it is shown with."""

    id: str
    status: str


@dataclass(frozen=True, kw_only=True)
class ClassifiedChild:
    """One child's single class, its reason where there is one, its blockers."""

    id: str
    status: str
    classification: str
    reason: str | None
    blockers: tuple[BlockerView, ...]


def open_blockers(*, item: WorkItem, statuses: Mapping[str, str]) -> tuple[BlockerView, ...]:
    """The child's OPEN `blocks` blockers, in id order, with their statuses.

    `item.depends_on` is populated from `blocks` edges alone, which is exactly
    the dependency type the clause admits as a blocker — no other type is read.
    A blocker absent from `statuses` is OPEN and is shown as unresolved.
    """
    views = [
        BlockerView(id=blocker_id, status=statuses.get(blocker_id, BLOCKER_STATUS_ABSENT))
        for blocker_id in _blocker_ids(item=item)
    ]
    return tuple(
        sorted(
            (view for view in views if view.status not in CLOSED_STATUSES),
            key=lambda view: view.id,
        )
    )


def classify_child(
    *,
    item: WorkItem,
    blockers: Sequence[BlockerView],
    board: BoardReading,
    hold_reasons: Mapping[str, str],
) -> ClassifiedChild:
    """Assign the FIRST matching class of the clause's ladder, and only that."""
    classification, reason = _class_of(
        item=item, blockers=blockers, board=board, hold_reasons=hold_reasons
    )
    return ClassifiedChild(
        id=item.id,
        status=item.status,
        classification=classification,
        reason=reason,
        blockers=tuple(blockers),
    )


def _class_of(
    *,
    item: WorkItem,
    blockers: Sequence[BlockerView],
    board: BoardReading,
    hold_reasons: Mapping[str, str],
) -> tuple[str, str | None]:
    # The HELD arm reads this map, and it arrives with the shared admission
    # verdict that fills it; until then a ready child with no open blocker is
    # DISPATCHABLE-NOW.
    _ = hold_reasons
    if item.id in board.live_item_ids:
        return CLASS_RUNNING, None
    mapped = _CLASS_BY_STATUS.get(item.status)
    if mapped is not None:
        return mapped, None
    if item.status == READY_STATUS:
        return _ready_class(item=item, blockers=blockers, board=board)
    return CLASS_UNCLASSIFIED_STATUS, item.status


def _ready_class(
    *,
    item: WorkItem,
    blockers: Sequence[BlockerView],
    board: BoardReading,
) -> tuple[str, str | None]:
    if is_host_only_item(item=item):
        return CLASS_HOST_ONLY, None
    if blockers:
        if all(_is_stale_edge(blocker=blocker, board=board) for blocker in blockers):
            return CLASS_STALE_EDGE, None
        return CLASS_BLOCKED, None
    return CLASS_DISPATCHABLE_NOW, None


def _is_stale_edge(*, blocker: BlockerView, board: BoardReading) -> bool:
    """Whether ONE open blocker is a landed-but-unclosed edge rather than live."""
    if blocker.status == _ACCEPTANCE_STATUS:
        return True
    return blocker.status == _ACTIVE_STATUS and blocker.id not in board.live_item_ids


def _blocker_ids(*, item: WorkItem) -> tuple[str, ...]:
    """The LOCAL dependency ids, which is what a `blocks` edge materializes as.

    Dispatched through the shared `parse_entry` rather than a local shape test,
    so this surface and the readiness gate cannot disagree about what a raw
    `depends_on` cell says. A non-local entry is not a `blocks` edge — the
    store reconstructs only `local` entries from edges — so it is not read as
    a blocker here; a cross-tenant sibling dependency is refused one stage
    later, by readiness, and surfaces as `HELD`.
    """
    parsed = (parse_entry(raw=raw) for raw in item.depends_on)
    return tuple(entry.work_item_id for entry in parsed if isinstance(entry, LocalDependency))
