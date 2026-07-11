"""Ledger close status normalization and outcome emission for the Dispatcher."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_checks import (
    LedgerFinding,
    run_ledger_checks,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout
from livespec_orchestrator_beads_fabro.store import (
    materialize_work_items,
    read_work_items,
    update_work_item_status,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "emit_outcomes",
    "ledger_blocked_after_normalization",
    "load_items",
]

_BEADS_NATIVE_OPEN = "open"
_LIVESPEC_BACKLOG = "backlog"


def _normalize_native_open_statuses(
    *,
    items: list[WorkItem],
    config: StoreConfig,
    journal: JournalFile,
) -> list[WorkItem]:
    normalized: list[dict[str, str]] = []
    result: list[WorkItem] = []
    for item in items:
        stored_status = str(item.status)
        if stored_status != _BEADS_NATIVE_OPEN:
            result.append(item)
            continue
        update_work_item_status(path=config, item_id=item.id, status=_LIVESPEC_BACKLOG)
        result.append(replace(item, status=_LIVESPEC_BACKLOG))
        normalized.append(
            {
                "item_id": item.id,
                "from": _BEADS_NATIVE_OPEN,
                "to": _LIVESPEC_BACKLOG,
                "reason": "beads-native intake default",
            }
        )
    if normalized:
        _append_normalization_note(journal=journal, normalized=normalized)
    return result


def _append_normalization_note(
    *,
    journal: JournalFile,
    normalized: list[dict[str, str]],
) -> None:
    line = json.dumps(
        {"stage": "status-normalization", "normalized": normalized},
        sort_keys=True,
    )
    journal.path.parent.mkdir(parents=True, exist_ok=True)
    with journal.path.open("a", encoding="utf-8") as handle:
        _ = handle.write(f"{line}\n")


def ledger_blocked_after_normalization(
    *,
    items: list[WorkItem],
    config: StoreConfig,
    journal: JournalFile,
) -> bool:
    items[:] = _normalize_native_open_statuses(items=items, config=config, journal=journal)
    return _ledger_blocked(items=items, journal=journal)


def _ledger_blocked(*, items: list[WorkItem], journal: JournalFile) -> bool:
    findings = run_ledger_checks(items=items)
    if not findings:
        return False
    journal.append(
        record={
            "stage": "ledger-check",
            "findings": [asdict(finding) for finding in findings],
        }
    )
    _write_findings(findings=findings)
    return True


def _write_findings(*, findings: list[LedgerFinding]) -> None:
    for finding in findings:
        _ = write_stderr(
            text=f"LEDGER: {finding.check}  {finding.item_id}  {finding.message}\n",
        )
    _ = write_stderr(text="ERROR: pre-dispatch ledger checks failed; dispatch blocked\n")


def load_items(*, repo: Path) -> list[WorkItem]:
    records = read_work_items(path=store_config(repo=repo))
    return list(materialize_work_items(records=records).values())


def emit_outcomes(*, outcomes: list[DispatchOutcome], as_json: bool) -> None:
    if as_json:
        payload = [asdict(outcome) for outcome in outcomes]
        _ = write_stdout(text=json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return
    if not outcomes:
        _ = write_stdout(text="(nothing dispatched)\n")
        return
    for outcome in outcomes:
        pr_part = f" PR#{outcome.pr_number}" if outcome.pr_number is not None else ""
        line = f"{outcome.work_item_id}  {outcome.status} at {outcome.stage}{pr_part}"
        _ = write_stdout(text=f"{line}  {outcome.detail}\n")
