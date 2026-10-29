"""The workflow-variant name a work-item is pinned to, across retries.

Beside `_store_dispatch_factory` rather than inside it, because the two keys
do NOT share one fate. `dispatch_factory` is written twice per dispatch from
two different moments and therefore carries two stored shapes, which is the
whole reason that module keeps its writers together. `dispatch_workflow` is
one plain name written at one moment -- when the variant resolves, before the
run exists -- so folding it in would file a single-shape key under a docstring
explaining a two-writer invariant it does not have.

It is read through this module directly rather than re-exported from
`store.py`, exactly as `_dispatcher_run_stamp` reads `_store_dispatch_factory`:
the facade carries the broad WorkItem API its many callers share, and one
consumer reaching one store concern does not need to widen it.

WHY THE PIN EXISTS AT ALL. A retry of a work-item must re-run the SAME graph
the first attempt ran: `SPECIFICATION/contracts.md` section "Named workflow
variants" resolves the recorded name ahead of `dispatcher.default_workflow`
precisely so a default changed between attempts cannot silently move a
half-finished item onto a different workflow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsRecord
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "dispatch_workflow_for",
    "dispatch_workflow_from_record",
    "dispatch_workflows_for",
    "record_dispatch_workflow",
]

_META_DISPATCH_WORKFLOW = "dispatch_workflow"


def dispatch_workflow_for(*, path: StoreConfig, work_item_id: str) -> str | None:
    """Return the workflow-variant name a prior dispatch pinned, if any."""
    client = make_beads_client(config=path)
    return dispatch_workflow_from_record(record=client.show_issue(issue_id=work_item_id))


def dispatch_workflows_for(*, path: StoreConfig) -> dict[str, str | None]:
    """Every item's recorded workflow-variant name, from ONE issue-list payload.

    The snapshot peer of `dispatch_workflow_for`, in the shape
    `dispatch_factories_for` already uses: an item with no pin maps to None, so
    a caller can tell "listed, unpinned" from "not in the snapshot".
    """
    client = make_beads_client(config=path)
    return {
        issue_id: dispatch_workflow_from_record(record=record)
        for record in client.list_issues()
        if isinstance((issue_id := record.get("id")), str)
    }


def dispatch_workflow_from_record(*, record: BeadsRecord) -> str | None:
    """Return the pinned workflow-variant name carried by an issue record."""
    raw = _metadata_of(record=record).get(_META_DISPATCH_WORKFLOW)
    if isinstance(raw, str) and raw.strip() != "":
        return raw.strip()
    return None


def record_dispatch_workflow(*, path: StoreConfig, work_item_id: str, workflow: str) -> None:
    """Pin the resolved workflow-variant name onto the work-item.

    The key lands at the metadata TOP LEVEL on purpose, and the whole existing
    mapping is read back and re-sent with it. `bd update --metadata` MERGES
    top-level keys but REPLACES a nested object wholesale, so a key tucked
    under an existing object would destroy every sibling sub-key this payload
    did not happen to resend -- and what survives a write is exactly what the
    payload carries.
    """
    client = make_beads_client(config=path)
    record = client.show_issue(issue_id=work_item_id)
    if dispatch_workflow_from_record(record=record) == workflow:
        return
    metadata = _metadata_of(record=record)
    metadata[_META_DISPATCH_WORKFLOW] = workflow
    client.update_issue(issue_id=work_item_id, metadata=metadata)


def _metadata_of(*, record: BeadsRecord) -> dict[str, Any]:
    raw = record.get("metadata")
    if isinstance(raw, dict):
        return dict(cast("dict[str, Any]", raw))
    return {}
