"""Mutation primitives for the beads-backed work-item store."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._beads_client import (
    EDGE_BLOCKS,
    EDGE_SUPERSEDES,
    IssueDraft,
    make_beads_client,
)
from livespec_orchestrator_beads_fabro.types import AuditRecord, DependsOnRaw, WorkItem

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "append_work_item",
    "create_work_item",
    "register_custom_statuses",
    "update_work_item_policy",
    "update_work_item_rank",
    "update_work_item_status",
]

_LABEL_ORIGIN = "origin:"
_LABEL_GAP_ID = "gap-id:"
_LABEL_RESOLUTION = "resolution:"
_LABEL_ADMISSION = "admission:"
_LABEL_ACCEPTANCE = "acceptance:"
_LABEL_BLOCKED_REASON = "blocked-reason:"

_META_AUDIT = "audit"
_META_ACCEPTANCE_CRITERIA = "acceptance_criteria"
_META_NON_LOCAL_DEPENDS_ON = "non_local_depends_on"
_META_NOTES = "notes"
_META_RANK = "rank"

_LIVESPEC_DONE = "done"
_BEADS_CLOSED = "closed"


def _beads_status_for(*, status: str) -> str:
    return _BEADS_CLOSED if status == _LIVESPEC_DONE else status


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
    client.update_issue(issue_id=item.id, metadata=_work_item_metadata(item=item))


def update_work_item_status(
    *,
    path: StoreConfig,
    item_id: str,
    status: str,
    assignee: str | None = None,
) -> None:
    """Transition an existing item's `status` (and optional `assignee`) IN PLACE.

    The Dispatcher's non-terminal lifecycle write seam — the `ready -> active`
    admit (which also sets the `assignee`), the `active -> acceptance`
    complete, the `acceptance -> active`/`backlog` reject routing, and the
    non-convergence bounce to `backlog`. Unlike `append_work_item` (which
    CREATES a fresh issue or CLOSES one in place) this mutates an EXISTING
    non-`done` issue's status without re-creating it, mirroring
    `update_work_item_rank`'s in-place shape. The `done` terminal is NOT
    routed here — a `done` transition carries `resolution` + the
    `AuditRecord` and goes through `append_work_item`'s close-in-place path;
    so the livespec status maps straight onto its beads name (no `done`
    arm is reachable here).
    """
    client = make_beads_client(config=path)
    client.update_issue(
        issue_id=item_id,
        status=_beads_status_for(status=status),
        assignee=assignee,
    )


def update_work_item_policy(
    *,
    path: StoreConfig,
    item_id: str,
    admission_policy: str | None = None,
    acceptance_policy: str | None = None,
) -> None:
    """Edit policy labels on an existing item without changing its status.

    The operator policy-edit seam behind `drive --action`
    `set-admission:<id>:...` / `set-acceptance:<id>:...`. The write is
    label-only: it removes the previous label for each named policy field,
    adds the replacement label, and deliberately sends no status or assignee
    mutation so a policy edit cannot surprise-transition the item.
    """
    remove_labels: list[str] = []
    add_labels: list[str] = []
    if admission_policy is not None:
        remove_labels.extend(f"{_LABEL_ADMISSION}{value}" for value in ("auto", "manual"))
        add_labels.append(f"{_LABEL_ADMISSION}{admission_policy}")
    if acceptance_policy is not None:
        remove_labels.extend(
            f"{_LABEL_ACCEPTANCE}{value}" for value in ("ai-only", "human-only", "ai-then-human")
        )
        add_labels.append(f"{_LABEL_ACCEPTANCE}{acceptance_policy}")
    client = make_beads_client(config=path)
    if remove_labels:
        client.update_issue(issue_id=item_id, remove_labels=remove_labels)
    if add_labels:
        client.update_issue(issue_id=item_id, add_labels=add_labels)


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
            metadata=_work_item_metadata(item=item),
            spec_id=item.spec_commitment_hint,
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
        client.update_issue(issue_id=item.id, status=_beads_status_for(status=item.status))


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
    """Close an existing issue: bd close + resolution label + audit metadata."""
    client.close_issue(issue_id=item.id, reason=item.reason)
    add_labels: list[str] = []
    if item.resolution is not None:
        add_labels.append(f"{_LABEL_RESOLUTION}{item.resolution}")
    metadata = _work_item_metadata(item=item)
    client.update_issue(
        issue_id=item.id,
        add_labels=add_labels if add_labels else None,
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
        labels.append(f"{_LABEL_BLOCKED_REASON}{item.blocked_reason}")
    return labels


def _work_item_metadata(*, item: WorkItem) -> dict[str, Any]:
    """Build the metadata JSON object: rank + the full AuditRecord + non-local depends_on.

    `rank` is the sole ordering authority and a strictly-required non-null
    field, so it is ALWAYS written into `metadata.rank` (both on create and
    on the in-place close, which re-writes metadata).
    """
    metadata: dict[str, Any] = {_META_RANK: item.rank}
    if item.audit is not None:
        metadata[_META_AUDIT] = _audit_to_dict(audit=item.audit)
    if item.acceptance_criteria is not None:
        metadata[_META_ACCEPTANCE_CRITERIA] = item.acceptance_criteria
    if item.notes is not None:
        metadata[_META_NOTES] = item.notes
    non_local = _non_local_depends_on_list(depends_on=item.depends_on)
    if non_local:
        metadata[_META_NON_LOCAL_DEPENDS_ON] = non_local
    return metadata


def _non_local_depends_on_list(*, depends_on: tuple[DependsOnRaw, ...]) -> list[dict[str, Any]]:
    """Collect non-local depends_on entries for metadata storage.

    Local entries (bare strings or {"kind": "local", ...} dicts) are stored as
    beads blocks edges. Non-local dict entries have no edge home and ride in
    metadata so cross-repo DAGs survive the round-trip.
    """
    result: list[dict[str, Any]] = []
    for raw in depends_on:
        if isinstance(raw, dict) and raw.get("kind") != "local":
            result.append(dict(raw))
    return result


def _audit_to_dict(*, audit: AuditRecord) -> dict[str, Any]:
    return {
        "verification_timestamp": audit.verification_timestamp,
        "commits": list(audit.commits),
        "files_changed": list(audit.files_changed),
        "merge_sha": audit.merge_sha,
        "pr_number": audit.pr_number,
    }


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
