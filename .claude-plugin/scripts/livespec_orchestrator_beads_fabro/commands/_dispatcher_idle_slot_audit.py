"""The priority-epic idle-slot audit: one read-only pass, one finding line.

The audit exists because idle capacity beside dispatchable work is the
quietest failure a factory has. On 2026-10-16 nine hp slots sat idle for about
five hours while four priority-set items were dispatchable, because three
successive driver sessions repeated a handoff's "nothing can use the slots"
instead of measuring the queue. This is that measurement, shipped.

THERE IS NO SLOT CEILING AND NO FREE-SLOT COUNT anywhere in this module, and
there will not be one: host concurrency belongs to the Fabro scheduler, so
this surface reads the board's own counts and derives no available capacity
from them.

WHY THIS WRITES NOTHING. The audit reads tenants, reads one board, and
returns. No ledger, no dispatch journal, no factory, no credential probe, no
availability confirmation turn — which is what lets it be run from a snapshot
surface without two invocations against an unchanged store disagreeing.

The three collaborators are SEAMS rather than direct calls because each one is
a different substrate — a tenant's beads store, a factory's run board, and the
shared admission verdict — and a test that had to stand all three up at once
could not isolate any of them. The parameter defaults are the real readers.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_board import (
    UNOBSERVABLE_BOARD,
    BoardReading,
    read_idle_slot_board,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_classify import (
    READY_STATUS,
    ClassifiedChild,
    classify_child,
    open_blockers,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_config import (
    PriorityEntry,
    resolve_idle_slot_audit,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_holds import (
    tenant_hold_reasons,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_tenants import (
    EntryChildren,
    TenantReader,
    entry_children,
    read_tenant,
)

__all__: list[str] = [
    "BoardLister",
    "EntryAudit",
    "HoldReader",
    "IdleSlotAuditResult",
    "idle_slot_audit",
]

BoardLister = Callable[..., BoardReading]
HoldReader = Callable[..., "dict[str, str]"]


@dataclass(frozen=True, kw_only=True)
class EntryAudit:
    """One priority entry's classified children, and what could not be read."""

    repo: str
    root: str
    epic: str | None
    item_ids: tuple[str, ...]
    unreadable: bool
    children: tuple[ClassifiedChild, ...]
    missing_ids: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class IdleSlotAuditResult:
    """The whole audit: configuration state, board, per-entry rows, finding.

    `configured` is False with `configuration_finding` None exactly when the
    object is absent, which is an answer rather than a fault. A malformed
    object is `configured` False WITH a finding — the two absences are
    deliberately distinguishable, because one composes a refusal and the other
    composes nothing.
    """

    configured: bool
    configuration_finding: str | None
    factory: str | None
    board: BoardReading
    entries: tuple[EntryAudit, ...]


@dataclass(frozen=True, kw_only=True)
class _Readers:
    """The resolved substrate readers for one audit pass."""

    tenant: TenantReader
    board: BoardLister
    holds: HoldReader


def idle_slot_audit(
    *,
    project_root: Path,
    tenant_reader: TenantReader | None = None,
    board_reader: BoardLister | None = None,
    hold_reader: HoldReader | None = None,
) -> IdleSlotAuditResult:
    """Run the read-only audit over the committed priority sets and one board.

    Each reader defaults to the production one, resolved INSIDE the call rather
    than as a parameter default: a default evaluated at definition time binds
    the function object itself, so a test could no longer substitute the
    production reader by name and would have to thread a seam through every
    caller to reach it.
    """
    resolved = resolve_idle_slot_audit(cwd=project_root)
    if resolved is None:
        return _unconfigured(finding=None)
    if isinstance(resolved, str):
        return _unconfigured(finding=resolved)
    readers = _Readers(
        tenant=read_tenant if tenant_reader is None else tenant_reader,
        board=read_idle_slot_board if board_reader is None else board_reader,
        holds=tenant_hold_reasons if hold_reader is None else hold_reader,
    )
    board = readers.board(repo=project_root, factory=resolved.factory)
    entries = tuple(
        _entry_audit(project_root=project_root, entry=entry, board=board, readers=readers)
        for entry in resolved.priority
    )
    return IdleSlotAuditResult(
        configured=True,
        configuration_finding=None,
        factory=resolved.factory,
        board=board,
        entries=entries,
    )


def _unconfigured(*, finding: str | None) -> IdleSlotAuditResult:
    return IdleSlotAuditResult(
        configured=False,
        configuration_finding=finding,
        factory=None,
        board=UNOBSERVABLE_BOARD,
        entries=(),
    )


def _entry_audit(
    *,
    project_root: Path,
    entry: PriorityEntry,
    board: BoardReading,
    readers: _Readers,
) -> EntryAudit:
    resolved = entry_children(project_root=project_root, entry=entry, reader=readers.tenant)
    return EntryAudit(
        repo=entry.repo,
        root=str(resolved.root),
        epic=entry.epic,
        item_ids=entry.items,
        unreadable=resolved.tenant is None,
        children=_classified(resolved=resolved, board=board, readers=readers),
        missing_ids=resolved.missing_ids,
    )


def _classified(
    *,
    resolved: EntryChildren,
    board: BoardReading,
    readers: _Readers,
) -> tuple[ClassifiedChild, ...]:
    tenant = resolved.tenant
    if tenant is None:
        return ()
    statuses = {item.id: item.status for item in tenant.items}
    # ONE hold evaluation per entry, and only when a `ready` child could
    # consume it: the shared verdict reads the tenant's whole ready set plus
    # its spec tree, so running it per child would re-read both once per row
    # to reach the identical answer.
    holds = (
        readers.holds(repo=resolved.root, items=list(tenant.items))
        if any(item.status == READY_STATUS for item in resolved.children)
        else {}
    )
    return tuple(
        classify_child(
            item=item,
            blockers=open_blockers(item=item, statuses=statuses),
            board=board,
            hold_reasons=holds,
        )
        for item in resolved.children
    )
