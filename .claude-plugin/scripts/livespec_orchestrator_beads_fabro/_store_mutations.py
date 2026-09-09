"""Mutation primitives for the beads-backed work-item store.

The write seams here CREATE, CLOSE, or TRANSITION an item. The label-only
edits that deliberately change no status live in the sibling modules
`_store_label_mutations` (policy + scope-override), `_store_cap_mutations`
(per-item cap overrides), and `_store_rework_mutations` (the `rework:pending`
marker), which this module consults for the marker removals every transition
out of `active` must carry. `_store_blocked_mutations` is the same arrangement
for the `blocked-reason:` vocabulary: it owns the removals every transition out
of `blocked` must carry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._beads_client import (
    EDGE_BLOCKS,
    EDGE_SUPERSEDES,
    IssueDraft,
    make_beads_client,
)
from livespec_orchestrator_beads_fabro._store_blocked_mutations import (
    LABEL_BLOCKED_REASON_PREFIX,
    blocked_reason_label_removals,
)
from livespec_orchestrator_beads_fabro._store_metadata import (
    metadata_with_rank,
    work_item_metadata,
    work_item_metadata_preserving_existing,
)
from livespec_orchestrator_beads_fabro._store_ready_dwell import (
    read_ready_dwell_instants,
    ready_transition_metadata,
)
from livespec_orchestrator_beads_fabro._store_ready_dwell import (
    utc_now_iso as _utc_now_iso,
)
from livespec_orchestrator_beads_fabro._store_rework_mutations import (
    rework_pending_label_removals,
)
from livespec_orchestrator_beads_fabro._store_statuses import beads_status_for
from livespec_orchestrator_beads_fabro.types import WorkItem

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "append_work_item",
    "create_work_item",
    "read_ready_dwell_instants",
    "register_custom_statuses",
    "update_work_item_rank",
    "update_work_item_status",
]

_LABEL_ORIGIN = "origin:"
_LABEL_GAP_ID = "gap-id:"
_LABEL_RESOLUTION = "resolution:"
_LABEL_ADMISSION = "admission:"
_LABEL_ACCEPTANCE = "acceptance:"
_LABEL_FACTORY_SAFETY = "factory-safety:"
_LABEL_AWAITS_SCOPE_OVERRIDE = "awaits-scope-override"

_LIVESPEC_DONE = "done"


def append_work_item(*, path: StoreConfig, item: WorkItem) -> None:
    """Create a new issue, or close an existing one in place.

    A closure in the JSONL world was a SECOND appended record carrying
    the same id with `status="done"`. Here that becomes an IN-PLACE
    mutation: when `item.status == "done"` AND an issue with `item.id`
    already exists in the tenant, we do NOT create a second issue.
    Instead we:

    1. `bd close <id> --reason <reason>` (sets beads `closed` ≡ livespec
       `done`, plus `close_reason`),
    2. `bd update <id>` to add the `resolution:<enum>` label, and
    3. write the full `AuditRecord` (lossless) into the metadata JSON
       column.

    Every other append is a fresh 2-step `bd create` (lands `open`) +
    `bd update --status <state>` (the custom livespec status), followed by
    `bd dep add` edges for `depends_on` (blocks) and `superseded_by`
    (supersedes). This whole semantic shift is contained here; the
    command/skill layer is unaffected.
    """
    client = make_beads_client(config=path)
    if item.status == _LIVESPEC_DONE and client.exists(issue_id=item.id):
        _close_in_place(client=client, item=item)
        return
    create_work_item(client=client, item=item)


def update_work_item_rank(*, path: StoreConfig, item: WorkItem) -> None:
    """Re-key an existing item's `rank` IN PLACE (metadata.rank).

    The bulk `rebalance-ranks` re-key path: unlike `append_work_item`
    (which CREATES a fresh issue, or closes one in place), this mutates an
    EXISTING issue's `metadata.rank` without re-creating it. It rewrites
    the FULL metadata object reconstructed from `item` (rank PLUS any
    `AuditRecord`), so a re-key never drops the audit a closed-then-reopened
    or evidence-carrying issue holds. The status/labels/edges are untouched.
    """
    client = make_beads_client(config=path)
    client.update_issue(
        issue_id=item.id,
        metadata=work_item_metadata_preserving_existing(
            existing_metadata=_existing_metadata(client=client, issue_id=item.id),
            item=item,
        ),
    )


def update_work_item_status(
    *,
    path: StoreConfig,
    item_id: str,
    status: str,
    assignee: str | None = None,
    clear_assignee: bool = False,
    rank: str | None = None,
) -> None:
    """Transition an existing item's `status` (and optional `assignee`) IN PLACE.

    The Dispatcher's non-terminal lifecycle write seam — the `ready -> active`
    admit (which also sets the `assignee`), the `active -> acceptance`
    complete, the `acceptance -> active`/`backlog` reject routing, and the
    non-convergence bounce to `backlog`. `assignee=None` preserves the existing
    assignee; `clear_assignee=True` is the explicit clear affordance for
    operator moves to statuses no runner claims. Unlike `append_work_item` (which
    CREATES a fresh issue or CLOSES one in place) this mutates an EXISTING
    non-`done` issue's status without re-creating it, mirroring
    `update_work_item_rank`'s in-place shape. The `done` terminal is NOT
    routed here — a `done` transition carries `resolution` + the
    `AuditRecord` and goes through `append_work_item`'s close-in-place path;
    so the livespec status maps straight onto its beads name (no `done`
    arm is reachable here).

    A transition to any status other than `active` also clears the
    `rework:pending` marker in the SAME mutation, which is what makes the
    "an item leaving `active` has the label cleared" invariant structural
    rather than something each disposition has to remember. A transition to
    any status other than `blocked` clears the `blocked-reason:` label the
    same way, so an operator valve move out of `blocked` cannot leave the
    item advertising a human gate it no longer has.

    A non-null `rank` assigns `metadata.rank` in the SAME mutation as the
    status. That is the ledger normalization's adoption insert (the beads-native
    `open` -> `backlog` / `in_progress` -> `active` self-heal): an adopted row
    reading back through the bottom sentinel gets a real key here, so status and
    rank land together rather than leaving a window in which the row is a live
    head with no real rank.
    """
    client = make_beads_client(config=path)
    metadata = _transition_metadata(client=client, item_id=item_id, status=status, rank=rank)
    client.update_issue(
        issue_id=item_id,
        status=beads_status_for(status=status),
        assignee=assignee,
        clear_assignee=clear_assignee,
        metadata=metadata,
        remove_labels=(
            rework_pending_label_removals(status=status)
            + blocked_reason_label_removals(status=status)
        )
        or None,
    )


def _transition_metadata(
    *,
    client: BeadsClient,
    item_id: str,
    status: str,
    rank: str | None,
) -> dict[str, Any] | None:
    """The metadata one status transition writes, or `None` when it writes none.

    Both overlays read the CURRENT metadata ONCE and preserve every other key,
    so an adoption insert never drops the `audit` a closed-then-reopened issue
    holds nor the `ready_since` a prior ready transition stamped — and a
    transition needing neither overlay still writes no metadata at all.
    """
    if status != "ready" and rank is None:
        return None
    metadata = _existing_metadata(client=client, issue_id=item_id)
    if status == "ready":
        metadata = ready_transition_metadata(existing_metadata=metadata, now_iso=_utc_now_iso())
    if rank is not None:
        metadata = metadata_with_rank(existing_metadata=metadata, rank=rank)
    return metadata


def register_custom_statuses(*, path: StoreConfig) -> None:
    """Provision the tenant's five custom livespec statuses (idempotent).

    A per-tenant bootstrap step: `bd create` cannot land directly in a
    custom status, so the 2-step `append_work_item` path depends on the
    custom statuses already being registered on the tenant. Delegates to
    the client seam's `register_custom_statuses` verb (a real
    `bd config set status.custom` against the live tenant; a recorded no-op
    against the in-memory fake).
    """
    client = make_beads_client(config=path)
    client.register_custom_statuses()


def create_work_item(*, client: BeadsClient, item: WorkItem) -> None:
    metadata = work_item_metadata(item=item)
    if item.status == "ready":
        metadata = ready_transition_metadata(
            existing_metadata=metadata,
            now_iso=_utc_now_iso(),
        )
    _ = client.create_issue(
        draft=IssueDraft(
            issue_id=item.id,
            issue_type=item.type,
            title=item.title,
            description=item.description,
            # `priority` is the beads-native column only; the logical model
            # dropped it for `rank` (persisted in metadata), so the draft
            # uses IssueDraft's neutral default rather than sourcing it here.
            assignee=item.assignee,
            created_at=item.captured_at,
            labels=_work_item_labels(item=item),
            metadata=metadata,
            spec_id=item.spec_commitment_hint,
            acceptance_criteria=item.acceptance_criteria,
            notes=item.notes,
            # epic linkage is expressed via the depends_on/supersedes edges
            # below; no create-time --parent is emitted by this bridge.
            parent_id=None,
        )
    )
    _add_dependency_edges(client=client, item=item)
    # `bd create` cannot land directly in a custom status, so every initial
    # write is 2-step: the create above lands `open`, then the status is set
    # to the real livespec state. A record born already-`done` takes the
    # in-place close path instead (which sets beads `closed`).
    if item.status == _LIVESPEC_DONE:
        _close_in_place(client=client, item=item)
    else:
        client.update_issue(issue_id=item.id, status=beads_status_for(status=item.status))


def _add_dependency_edges(*, client: BeadsClient, item: WorkItem) -> None:
    """Add `blocks` edges for depends_on and a `supersedes` edge if set.

    Each local `depends_on` entry becomes `bd dep add <this> <dep>
    --type blocks` (this issue is blocked by <dep>). A non-null
    `superseded_by` becomes `bd dep add <superseding> <this>
    --type supersedes` (the superseding issue is the edge source, per
    the verified direction in schema-mapping.md item 6).
    """
    for raw in item.depends_on:
        dep_id = _local_depends_on_id(raw=raw)
        if dep_id is not None:
            client.add_dependency(from_id=item.id, to_id=dep_id, edge_type=EDGE_BLOCKS)
    if item.superseded_by is not None:
        client.add_dependency(
            from_id=item.superseded_by,
            to_id=item.id,
            edge_type=EDGE_SUPERSEDES,
        )


def _close_in_place(*, client: BeadsClient, item: WorkItem) -> None:
    """Close an existing issue: bd close + resolution label + audit metadata.

    The terminal close is a transition OUT of `active`, so it carries the same
    `rework:pending` removal the other lifecycle write seams do — and, since a
    closed item is not `blocked`, the same `blocked-reason:` removal, so an
    item closed straight out of `blocked` stops advertising a human gate.
    """
    existing_metadata = _existing_metadata(client=client, issue_id=item.id)
    client.close_issue(issue_id=item.id, reason=item.reason)
    add_labels: list[str] = []
    if item.resolution is not None:
        add_labels.append(f"{_LABEL_RESOLUTION}{item.resolution}")
    metadata = work_item_metadata_preserving_existing(
        existing_metadata=existing_metadata,
        item=item,
    )
    client.update_issue(
        issue_id=item.id,
        add_labels=add_labels if add_labels else None,
        remove_labels=(
            rework_pending_label_removals(status=item.status)
            + blocked_reason_label_removals(status=item.status)
        )
        or None,
        metadata=metadata,
    )


def _work_item_labels(*, item: WorkItem) -> list[str]:
    """Build the label set carrying origin / gap-id / resolution / policy fields.

    The `admission_policy` / `acceptance_policy` / `blocked_reason` fields
    follow the blessed optional-on-read pattern: a `None` value writes NO
    label (it reads back `None` = inherit / system default), so only a set
    policy materializes a `admission:` / `acceptance:` / `blocked-reason:`
    label.
    """
    labels: list[str] = [f"{_LABEL_ORIGIN}{item.origin}"]
    if item.gap_id is not None:
        labels.append(f"{_LABEL_GAP_ID}{item.gap_id}")
    if item.resolution is not None:
        labels.append(f"{_LABEL_RESOLUTION}{item.resolution}")
    if item.admission_policy is not None:
        labels.append(f"{_LABEL_ADMISSION}{item.admission_policy}")
    if item.acceptance_policy is not None:
        labels.append(f"{_LABEL_ACCEPTANCE}{item.acceptance_policy}")
    if item.blocked_reason is not None:
        labels.append(f"{LABEL_BLOCKED_REASON_PREFIX}{item.blocked_reason}")
    if item.factory_safety is not None:
        labels.append(f"{_LABEL_FACTORY_SAFETY}{item.factory_safety}")
    if item.awaits_scope_override:
        labels.append(_LABEL_AWAITS_SCOPE_OVERRIDE)
    return labels


def _existing_metadata(*, client: BeadsClient, issue_id: str) -> dict[str, Any]:
    raw = client.show_issue(issue_id=issue_id).get("metadata")
    metadata = cast("dict[str, Any] | None", raw)
    return dict(metadata or {})


def _local_depends_on_id(*, raw: object) -> str | None:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        entry = cast("dict[str, Any]", raw)
        if entry.get("kind") == "local":
            work_item_id = entry.get("work_item_id")
            if isinstance(work_item_id, str):
                return work_item_id
    return None
