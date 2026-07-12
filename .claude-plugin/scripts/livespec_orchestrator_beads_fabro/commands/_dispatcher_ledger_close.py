"""Ledger close status normalization and outcome emission for the Dispatcher."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
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
    "apply_native_status_remaps",
    "emit_outcomes",
    "ledger_blocked_after_normalization",
    "load_items",
    "plan_native_status_remaps",
    "project_native_status_remaps",
]


@dataclass(frozen=True, kw_only=True)
class _NativeRemap:
    """The livespec lifecycle target + rationale for one beads-native status."""

    to: str
    reason: str


# The beads-native statuses the Dispatcher self-heals onto their livespec
# lifecycle equivalent: `open` (beads' intake default a fresh `bd create`
# lands in) → `backlog`, and `in_progress` (the status a raw `bd --claim`
# stamps) → `active`. Both carry a lifecycle intent the livespec model names
# differently. Every OTHER status (deferred / hooked / pinned / closed / any
# ad-hoc or unknown value) is a KEY-miss here and is left untouched — those
# surface via the post-normalization ledger status-conformance check, never
# auto-remapped.
_NATIVE_STATUS_REMAP: dict[str, _NativeRemap] = {
    "open": _NativeRemap(to="backlog", reason="beads-native intake default"),
    "in_progress": _NativeRemap(to="active", reason="raw claim normalized to active"),
}


def plan_native_status_remaps(*, items: list[WorkItem]) -> list[dict[str, str]]:
    """Plan the beads-native → livespec status remaps for `items` (PURE).

    Returns one `{item_id, from, to, reason}` dict per row whose stored
    status is a KEY of `_NATIVE_STATUS_REMAP`; every other row (already-
    conformant, deferred, hooked, ad-hoc, unknown) contributes nothing.
    Performs NO store mutation and NO journaling, so the dispatch path and
    the standalone `ledger-normalize` CLI share identical remap logic.
    """
    plan: list[dict[str, str]] = []
    for item in items:
        stored_status = str(item.status)
        remap = _NATIVE_STATUS_REMAP.get(stored_status)
        if remap is None:
            continue
        plan.append(
            {
                "item_id": item.id,
                "from": stored_status,
                "to": remap.to,
                "reason": remap.reason,
            }
        )
    return plan


def apply_native_status_remaps(
    *,
    remaps: list[dict[str, str]],
    config: StoreConfig,
) -> None:
    """Write each planned remap to the store via the `update_work_item_status` seam."""
    for remap in remaps:
        update_work_item_status(path=config, item_id=remap["item_id"], status=remap["to"])


def project_native_status_remaps(
    *,
    items: list[WorkItem],
    remaps: list[dict[str, str]],
) -> list[WorkItem]:
    """Return `items` with each planned remap applied in memory (PURE).

    The post-remap view the store would read back — the dispatch path and
    the CLI dry-run both use it so residual ledger checks run against the
    same projected rows without a second store round-trip.
    """
    remapped_status = {remap["item_id"]: remap["to"] for remap in remaps}
    return [
        replace(item, status=remapped_status[item.id]) if item.id in remapped_status else item
        for item in items
    ]


def _normalize_native_statuses(
    *,
    items: list[WorkItem],
    config: StoreConfig,
    journal: JournalFile,
) -> list[WorkItem]:
    remaps = plan_native_status_remaps(items=items)
    if not remaps:
        return items
    apply_native_status_remaps(remaps=remaps, config=config)
    _append_normalization_note(journal=journal, normalized=remaps)
    return project_native_status_remaps(items=items, remaps=remaps)


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
    items[:] = _normalize_native_statuses(items=items, config=config, journal=journal)
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
