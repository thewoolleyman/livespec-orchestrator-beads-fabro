"""Dispatch-target and run-stamp metadata for beads work-items.

Two facts about a dispatch live here because they share one metadata key's
fate. `dispatch_factory` names WHICH factory an item is pinned to, and it is
written twice per dispatch from two different moments: `record_dispatch_factory`
pins the target while the plan is being built, before any run exists, and
`record_dispatch_run` re-writes it with the resolved server url once the run id
is known. Splitting the two writers across modules would let the pinned factory
and the factory a run actually went to drift apart with nothing to notice.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsRecord
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "backfill_dispatch_factory_metadata",
    "dispatch_factories_for",
    "dispatch_factory_for",
    "dispatch_factory_from_record",
    "dispatch_run_id_from_record",
    "dispatch_run_ids_for",
    "read_dispatch_factories",
    "record_dispatch_factory",
    "record_dispatch_run",
]

_MARKER_PREFIX = "livespec-dispatch-factory: "
_META_DISPATCH_FACTORY = "dispatch_factory"
_META_DISPATCH_RUN_ID = "dispatch_fabro_run_id"
_FACTORY_NAME_KEY = "name"
_FACTORY_SERVER_KEY = "server"
_BEADS_CLOSED = "closed"


def dispatch_factory_for(*, path: StoreConfig, work_item_id: str) -> str | None:
    """Return the persisted factory marker for a work-item, if present."""
    client = make_beads_client(config=path)
    record = client.show_issue(issue_id=work_item_id)
    factory = dispatch_factory_from_record(record=record)
    if factory is not None:
        return factory
    return _latest_comment_marker(path=path, work_item_id=work_item_id)


def read_dispatch_factories(*, path: StoreConfig) -> dict[str, str]:
    """Every item's stamped dispatch factory, read from ONE `bd list` of the tenant.

    The narrow-raw-read shape `read_merge_held_work_item_ids` uses: the marker rides
    each record's metadata, which the list already returns, so a snapshot that needs
    the factory for many items reads it here once instead of `dispatch_factory_for`'s
    one `bd show` (plus a `bd comments` fallback) per item. Measured 2026-10-25 on the
    orchestrator tenant (bd-ib-tzbdd3): needs-attention issued 60 such shows at
    1.6-4.6 s each. An item whose record carries no marker is simply absent, and
    the caller falls back to the configured default factory as it always has.
    """
    client = make_beads_client(config=path)
    factories: dict[str, str] = {}
    for record in client.list_issues():
        issue_id = record.get("id")
        factory = dispatch_factory_from_record(record=record)
        if isinstance(issue_id, str) and factory is not None:
            factories[issue_id] = factory
    return factories


def dispatch_factory_from_record(*, record: BeadsRecord) -> str | None:
    """Return the dispatch-factory NAME carried by an issue record.

    TWO shapes are read for the one key, and the reason is a write-ordering
    fact rather than indecision. The bare-string shape is what
    `record_dispatch_factory` pins while the plan is built — at that moment
    there is no run, so there is no resolved server url to record beside the
    name. The `{"name", "server"}` shape is what `record_dispatch_run` stamps
    once the run exists. Both answer "which factory", so both are read here: a
    reader that understood only the bare string would report NO pinned factory
    for every already-stamped item and silently re-resolve the default, which
    is precisely the wrong-pool failure the stamp exists to prevent.
    """
    return _factory_name(raw=_metadata_of(record=record).get(_META_DISPATCH_FACTORY))


def dispatch_factories_for(*, path: StoreConfig) -> dict[str, str | None]:
    """Return metadata-carried dispatch factories from one issue-list payload."""
    client = make_beads_client(config=path)
    return {
        issue_id: dispatch_factory_from_record(record=record)
        for record in client.list_issues()
        if isinstance((issue_id := record.get("id")), str)
    }


def backfill_dispatch_factory_metadata(*, path: StoreConfig) -> int:
    """Backfill open issue metadata from legacy comment-borne markers."""
    client = make_beads_client(config=path)
    changed = 0
    for record in client.list_issues():
        issue_id = record.get("id")
        if not isinstance(issue_id, str) or record.get("status") == _BEADS_CLOSED:
            continue
        if dispatch_factory_from_record(record=record) is not None:
            continue
        factory = _latest_comment_marker(path=path, work_item_id=issue_id)
        if factory is None:
            continue
        client.update_issue(
            issue_id=issue_id,
            metadata=_metadata_with_dispatch_factory(record=record, factory=factory),
        )
        changed += 1
    return changed


def _latest_comment_marker(*, path: StoreConfig, work_item_id: str) -> str | None:
    factory: str | None = None
    for comment in read_work_item_comments(path=path, work_item_id=work_item_id):
        if comment.text.startswith(_MARKER_PREFIX):
            candidate = comment.text.removeprefix(_MARKER_PREFIX).strip()
            if candidate != "":
                factory = candidate
    return factory


def record_dispatch_factory(*, path: StoreConfig, work_item_id: str, factory: str) -> None:
    """Persist the dispatch-factory marker and keep a comment audit trail."""
    client = make_beads_client(config=path)
    record = client.show_issue(issue_id=work_item_id)
    if dispatch_factory_from_record(record=record) == factory:
        return
    client.update_issue(
        issue_id=work_item_id,
        metadata=_metadata_with_dispatch_factory(record=record, factory=factory),
    )
    client.add_comment(issue_id=work_item_id, body=f"{_MARKER_PREFIX}{factory}")


def record_dispatch_run(
    *,
    path: StoreConfig,
    work_item_id: str,
    run_id: str,
    factory_name: str,
    factory_server: str | None,
) -> None:
    """Stamp the newest Fabro run id and its factory target onto the item.

    Both keys land at the metadata TOP LEVEL on purpose. `bd update --metadata`
    MERGES top-level keys but REPLACES a nested object wholesale, so a key
    tucked under an existing object would destroy every sibling sub-key this
    payload did not happen to resend. The whole existing metadata mapping is
    read back and re-sent for the same reason: what survives a write is exactly
    what the payload carries.

    The NEWEST run wins — a re-dispatch overwrites `dispatch_fabro_run_id`
    outright. The superseded id is not lost: the dispatch journal keeps every
    run id it has recorded for the item, which is the leg
    `_run_attribution.newest_journaled_run_id` reads.
    """
    client = make_beads_client(config=path)
    metadata = _metadata_of(record=client.show_issue(issue_id=work_item_id))
    metadata[_META_DISPATCH_RUN_ID] = run_id
    metadata[_META_DISPATCH_FACTORY] = {
        _FACTORY_NAME_KEY: factory_name,
        _FACTORY_SERVER_KEY: factory_server,
    }
    client.update_issue(issue_id=work_item_id, metadata=metadata)


def dispatch_run_id_from_record(*, record: BeadsRecord) -> str | None:
    """Return the newest Fabro run id stamped on an issue record."""
    raw = _metadata_of(record=record).get(_META_DISPATCH_RUN_ID)
    if isinstance(raw, str) and raw.strip() != "":
        return raw.strip()
    return None


def dispatch_run_ids_for(*, path: StoreConfig) -> dict[str, str]:
    """Map each stamped Fabro run id to the work-item that dispatched it.

    Keyed by RUN id rather than by item id because that is the direction
    run-to-item attribution needs, and because it is the direction that stays
    single-valued: one item accumulates many runs over its life, while a run
    belongs to exactly one item.
    """
    client = make_beads_client(config=path)
    mapped: dict[str, str] = {}
    for record in client.list_issues():
        issue_id = record.get("id")
        run_id = dispatch_run_id_from_record(record=record)
        if isinstance(issue_id, str) and run_id is not None:
            mapped[run_id] = issue_id
    return mapped


def _factory_name(*, raw: object) -> str | None:
    """Read a factory name off either stored shape, or None if it holds none."""
    named = cast("dict[str, Any]", raw).get(_FACTORY_NAME_KEY) if isinstance(raw, dict) else raw
    if isinstance(named, str) and named.strip() != "":
        return named.strip()
    return None


def _metadata_with_dispatch_factory(*, record: BeadsRecord, factory: str) -> dict[str, Any]:
    metadata = _metadata_of(record=record)
    metadata[_META_DISPATCH_FACTORY] = factory
    return metadata


def _metadata_of(*, record: BeadsRecord) -> dict[str, Any]:
    raw = record.get("metadata")
    if isinstance(raw, dict):
        return dict(cast("dict[str, Any]", raw))
    return {}
