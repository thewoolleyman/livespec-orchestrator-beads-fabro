"""`orchestrator gap-capture` subcommand — write detected gaps to the Ledger.

Per livespec/SPECIFICATION/contracts.md §"Orchestrator CLI contract —
the three named CLIs", gap-capture is a CAPTURE interface: detection
(mechanical / LLM / human) happens upstream at the orchestrator's
private choice — usually LLM-driven — and the resulting gap findings
arrive here as a JSON payload. This subcommand writes each finding as
a gap-tied work-item into the beads-backed work-items store
(the Ledger). LiveSpec never sees the gaps or the store.

The spec-reader CLI is injected as a reference (`--spec-reader-cli`);
it resolves the current spec version, which is stamped onto every
captured work-item's description for provenance. Without the flag the
in-package Spec Reader is used (the same orchestrator owns both
sides, so the internal API is a legitimate private interface).

Payload wire shape (orchestrator-private):

    {"gaps": [{"gap_id": "<id>", "title": "<title>",
               "description": "<prose>", "priority": <0-4>}]}

`description` defaults to the empty string; `priority` defaults to 2.
Findings whose `gap_id` already has a non-closed work-item in the
store are skipped (idempotent re-capture), as are duplicate `gap_id`s
within one payload.
"""

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast

from livespec_impl_beads._ids import new_work_item_id
from livespec_impl_beads.commands._config import resolve_store_config
from livespec_impl_beads.commands._orchestrator_shared import (
    CliContext,
    PayloadInvalidError,
    load_payload,
    require_str,
    resolve_spec_version,
)
from livespec_impl_beads.store import append_work_item, materialize_work_items, read_work_items
from livespec_impl_beads.types import StoreConfig, WorkItem

__all__: list[str] = ["GapFinding", "run_gap_capture", "validate_gaps"]

_DEFAULT_PRIORITY = 2


@dataclass(frozen=True, kw_only=True)
class GapFinding:
    """One validated gap finding from the inbound payload."""

    gap_id: str
    title: str
    description: str
    priority: int


def run_gap_capture(
    *,
    gaps_json: str,
    context: CliContext,
    spec_reader_cli: list[str] | None,
    dry_run: bool,
    as_json: bool,
) -> int:
    """Run the gap-capture subcommand: validate, dedupe, append, report."""
    gaps = validate_gaps(payload=load_payload(source=gaps_json))
    spec_version = resolve_spec_version(spec_reader_cli=spec_reader_cli, context=context)
    config = resolve_store_config(cwd=context.project_root, work_items_arg=None, memos_arg=None)
    seen = _open_gap_ids(config=config)
    created: list[dict[str, str]] = []
    skipped: list[str] = []
    for gap in gaps:
        if gap.gap_id in seen:
            skipped.append(gap.gap_id)
            continue
        seen.add(gap.gap_id)
        item = _work_item_for(gap=gap, config=config, spec_version=spec_version)
        if not dry_run:
            append_work_item(path=config, item=item)
        created.append({"id": item.id, "gap_id": gap.gap_id})
    _emit(
        spec_version=spec_version,
        dry_run=dry_run,
        created=created,
        skipped=skipped,
        as_json=as_json,
    )
    return 0


def validate_gaps(*, payload: object) -> list[GapFinding]:
    """Validate the inbound payload shape into `GapFinding`s (or raise)."""
    if not isinstance(payload, dict):
        raise PayloadInvalidError(detail="payload must be a JSON object")
    root = cast("dict[str, Any]", payload)
    raw_gaps: object = root.get("gaps")
    if not isinstance(raw_gaps, list):
        raise PayloadInvalidError(detail="payload.gaps must be a list")
    entries = cast("list[Any]", raw_gaps)
    return [_validate_gap(entry=entry, index=index) for index, entry in enumerate(entries)]


def _validate_gap(*, entry: object, index: int) -> GapFinding:
    where = f"payload.gaps[{index}]"
    if not isinstance(entry, dict):
        raise PayloadInvalidError(detail=f"{where} must be a JSON object")
    obj = cast("dict[str, Any]", entry)
    description: object = obj.get("description", "")
    if not isinstance(description, str):
        raise PayloadInvalidError(detail=f"{where}.description must be a string")
    priority: object = obj.get("priority", _DEFAULT_PRIORITY)
    if not isinstance(priority, int) or isinstance(priority, bool):
        raise PayloadInvalidError(detail=f"{where}.priority must be an integer")
    return GapFinding(
        gap_id=require_str(obj=obj, key="gap_id", where=where),
        title=require_str(obj=obj, key="title", where=where),
        description=description,
        priority=priority,
    )


def _open_gap_ids(*, config: StoreConfig) -> set[str]:
    items = materialize_work_items(read_work_items(path=config)).values()
    return {item.gap_id for item in items if item.gap_id is not None and item.status != "closed"}


def _work_item_for(*, gap: GapFinding, config: StoreConfig, spec_version: int) -> WorkItem:
    description = f"{gap.description}\n\n(captured against spec version v{spec_version:03d})"
    return WorkItem(
        id=new_work_item_id(prefix=config.prefix),
        type="task",
        status="open",
        title=gap.title,
        description=description.strip(),
        origin="gap-tied",
        gap_id=gap.gap_id,
        priority=gap.priority,
        assignee=None,
        depends_on=(),
        captured_at=_now_iso(),
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
    )


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _emit(
    *,
    spec_version: int,
    dry_run: bool,
    created: list[dict[str, str]],
    skipped: list[str],
    as_json: bool,
) -> None:
    if as_json:
        payload = {
            "spec_version": spec_version,
            "dry_run": dry_run,
            "created": created,
            "skipped_existing": skipped,
        }
        _ = sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return
    verb = "would create" if dry_run else "created"
    for entry in created:
        _ = sys.stdout.write(f"{verb} {entry['id']} (gap {entry['gap_id']})\n")
    for gap_id in skipped:
        _ = sys.stdout.write(f"skipped existing gap {gap_id}\n")
