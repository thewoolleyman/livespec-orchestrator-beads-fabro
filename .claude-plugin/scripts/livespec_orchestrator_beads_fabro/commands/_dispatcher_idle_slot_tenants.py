"""Each named tenant's ledger, and the children one priority entry names.

THE CHILD UNION IS THE WHOLE POINT OF THIS MODULE, and it is the one place a
hand-rolled filter is reliably wrong. Beads links a child to its epic two
ways, and each single-arm reading is blind to one of them: an explicit
`parent-child` / `tracks` edge populates the dependency surface, while the
implicit dotted-id hierarchy does not — `bd` honours it and REFUSES to add a
redundant edge for such a record, so a hierarchy-only child cannot be given
one. `plan_child_ids_from_dependencies` and `plan_child_ids_from_id_hierarchy`
are therefore UNIONED, exactly as the plan archive gate unions them.

The union's THIRD arm — records that BLOCK the epic — is deliberately
EXCLUDED, because the idle-slot clause excludes it: a record that blocks a
priority epic is not a child of it, and counting it would put unrelated work
into the priority set.

WHY A TENANT IS READ TWICE. The materialized `WorkItem` carries `depends_on`
populated from `blocks` edges alone, which is the right blocker surface and
the wrong child surface — it has no parent field at all. The raw records carry
the edges. Both readings are taken through the SAME resolved tenant config in
one call so a caller cannot pair one tenant's items with another's edges.

An unreadable tenant is `None` and is REPORTED as unreadable by the audit
rather than omitted: a tenant silently dropped from a priority set reads as a
tenant with no dispatchable work, which is the one reading that lets the
finding line fire while the evidence for it was never collected.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from livespec_runtime.work_items.reduce import materialize_work_items

from livespec_orchestrator_beads_fabro._beads_client import BeadsRecord, make_beads_client
from livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_classify import (
    CLOSED_STATUSES,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_config import (
    PriorityEntry,
    priority_entry_root,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._plan_child_edges import (
    plan_child_ids_from_dependencies,
    plan_child_ids_from_id_hierarchy,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)
from livespec_orchestrator_beads_fabro.store import read_work_items
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "EntryChildren",
    "TenantReader",
    "TenantReading",
    "entry_children",
    "load_tenant",
    "read_tenant",
]

# The EXPECTED-error surface one tenant read can raise. Catching exactly this
# set — never a blanket `except` — keeps an unreachable, unconfigured or
# malformed tenant REPORTABLE rather than crashing the whole audit.
_TENANT_READ_ERRORS: tuple[type[Exception], ...] = (
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
    BeadsCredentialMissingError,
    BeadsConnectionError,
    BeadsTenantMissingError,
    BeadsCommandError,
    BeadsMappingError,
)


@dataclass(frozen=True, kw_only=True)
class TenantReading:
    """One tenant's ledger in both shapes the audit needs, read in one call."""

    items: tuple[WorkItem, ...]
    records: tuple[BeadsRecord, ...]


TenantReader = Callable[..., TenantReading | None]


@dataclass(frozen=True, kw_only=True)
class EntryChildren:
    """One priority entry's resolved children, plus what could not be read.

    `tenant` is `None` exactly when the tenant could not be read, in which
    case `children` and `missing_ids` are empty — an unreadable tenant yields
    no findings about its contents, only the report that nobody looked.
    """

    entry: PriorityEntry
    root: Path
    tenant: TenantReading | None
    children: tuple[WorkItem, ...]
    missing_ids: tuple[str, ...]


def read_tenant(
    *, repo: Path, load: Callable[..., TenantReading] | None = None
) -> TenantReading | None:
    """Read one tenant through its own checkout, or `None` when unreadable."""
    if not repo.is_dir():
        return None
    loader = load_tenant if load is None else load
    read = attempt(action=lambda: loader(repo=repo), exceptions=_TENANT_READ_ERRORS)
    if isinstance(read, AttemptFailure):
        return None
    return read


def load_tenant(*, repo: Path) -> TenantReading:
    """Both readings of one tenant, through that tenant's own committed config."""
    config = store_config(repo=repo)
    items = materialize_work_items(records=read_work_items(path=config.work_items_path))
    records = tuple(make_beads_client(config=config).list_issues())
    return TenantReading(items=tuple(items.values()), records=records)


def entry_children(
    *,
    project_root: Path,
    entry: PriorityEntry,
    reader: TenantReader = read_tenant,
) -> EntryChildren:
    """Resolve one priority entry against its tenant's own checkout."""
    root = priority_entry_root(project_root=project_root, entry=entry)
    tenant = reader(repo=root)
    if tenant is None:
        return EntryChildren(entry=entry, root=root, tenant=None, children=(), missing_ids=())
    if entry.epic is not None:
        return EntryChildren(
            entry=entry,
            root=root,
            tenant=tenant,
            children=_epic_children(tenant=tenant, epic_id=entry.epic),
            missing_ids=(),
        )
    named = _named_children(tenant=tenant, item_ids=entry.items)
    return EntryChildren(
        entry=entry, root=root, tenant=tenant, children=named[0], missing_ids=named[1]
    )


def _epic_children(*, tenant: TenantReading, epic_id: str) -> tuple[WorkItem, ...]:
    """Every non-closed child of one epic, through BOTH linkage arms."""
    records = list(tenant.records)
    linked = plan_child_ids_from_dependencies(
        records=records, epic_id=epic_id
    ) | plan_child_ids_from_id_hierarchy(records=records, epic_id=epic_id)
    return tuple(
        sorted(
            (item for item in tenant.items if item.id in linked and _is_open(item=item)),
            key=lambda item: item.id,
        )
    )


def _named_children(
    *,
    tenant: TenantReading,
    item_ids: Sequence[str],
) -> tuple[tuple[WorkItem, ...], tuple[str, ...]]:
    """The named non-closed records, in configuration order, plus absent ids."""
    index = {item.id: item for item in tenant.items}
    children = [
        item
        for item_id in item_ids
        if (item := index.get(item_id)) is not None and _is_open(item=item)
    ]
    missing = [item_id for item_id in item_ids if item_id not in index]
    return tuple(children), tuple(missing)


def _is_open(*, item: WorkItem) -> bool:
    return item.status not in CLOSED_STATUSES
