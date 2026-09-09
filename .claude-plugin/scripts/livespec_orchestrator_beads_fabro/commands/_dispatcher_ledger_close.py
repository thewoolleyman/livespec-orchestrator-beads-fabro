"""Ledger close status normalization and outcome emission for the Dispatcher.

The status-normalization note routes through `JournalFile.append` — the single
append layer of the journal invoker attribution contract in
`SPECIFICATION/contracts.md`. It used to open the journal path directly, so the
one record saying which rows the Dispatcher silently re-statused carried no
timestamp and no attribution.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from livespec_runtime.work_items.rank import BOTTOM_SENTINEL, key_between

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
# differently. `deferred` is deliberately left untouched because it is modeled
# as a parked beads-native state. Every OTHER status (hooked / pinned / closed /
# any ad-hoc or unknown value) is a KEY-miss here and is left untouched — those
# surface via the post-normalization ledger status-conformance check, never
# auto-remapped.
_NATIVE_STATUS_REMAP: dict[str, _NativeRemap] = {
    "open": _NativeRemap(to="backlog", reason="beads-native intake default"),
    "in_progress": _NativeRemap(to="active", reason="raw claim normalized to active"),
}

# The one livespec status whose rows are NOT part of the live order: a `done`
# row's key cannot be the bottom a fresh insert lands after, and the
# non-sentinel-rank invariant the adoption satisfies exempts it too.
_LIVESPEC_DONE = "done"


def plan_native_status_remaps(*, items: list[WorkItem]) -> list[dict[str, str]]:
    """Plan the beads-native → livespec status + rank adoptions for `items` (PURE).

    Returns one `{item_id, from, to, reason}` dict per row whose stored
    status is a KEY of `_NATIVE_STATUS_REMAP`; every other row (already-
    conformant, parked, hooked, ad-hoc, unknown) contributes nothing.
    A planned row whose `rank` reads back through `BOTTOM_SENTINEL` — the
    adapter's stand-in for metadata carrying no real key — additionally
    carries a `rank`: a fresh key from a single bottom-of-order insert, so the
    adopted row satisfies the "every live head has a real, non-sentinel rank"
    invariant without an on-demand `rebalance-ranks`. Successive rank-less
    rows chain off each other's fresh key, so each lands at its own position
    and NO already-ranked row is re-keyed — this is a run of single inserts,
    never a rebalance.
    Performs NO store mutation and NO journaling, so all four normalization
    cadences share identical adoption logic.
    """
    plan: list[dict[str, str]] = []
    bottom = _bottom_live_rank(items=items)
    for item in items:
        stored_status = str(item.status)
        remap = _NATIVE_STATUS_REMAP.get(stored_status)
        if remap is None:
            continue
        planned = {
            "item_id": item.id,
            "from": stored_status,
            "to": remap.to,
            "reason": remap.reason,
        }
        if item.rank == BOTTOM_SENTINEL:
            bottom = key_between(a=bottom, b=None)
            planned["rank"] = bottom
        plan.append(planned)
    return plan


def _bottom_live_rank(*, items: list[WorkItem]) -> str | None:
    """The greatest REAL key among the live rows — the bottom of the live order (PURE).

    `done` rows are excluded because they are not part of the live order, and
    the sentinel is excluded because it is the ABSENCE of a key rather than one
    (it sorts after every real key precisely so a rank-less row does not crash a
    listing, so taking it as the bottom would make every fresh insert land after
    a value no row really holds). `None` — no live row carries a real key — is
    the open start `key_between` accepts.
    """
    live = [
        item.rank
        for item in items
        if str(item.status) != _LIVESPEC_DONE and item.rank != BOTTOM_SENTINEL
    ]
    return max(live) if live else None


def apply_native_status_remaps(
    *,
    remaps: list[dict[str, str]],
    config: StoreConfig,
) -> None:
    """Write each planned adoption through the `update_work_item_status` seam.

    The status and any assigned `rank` ride ONE call, so no call path — and no
    interrupted partial heal — can adopt a row status-only and leave it resting
    on the bottom-sentinel.
    """
    for remap in remaps:
        update_work_item_status(
            path=config,
            item_id=remap["item_id"],
            status=remap["to"],
            rank=remap.get("rank"),
        )


def project_native_status_remaps(
    *,
    items: list[WorkItem],
    remaps: list[dict[str, str]],
) -> list[WorkItem]:
    """Return `items` with each planned adoption applied in memory (PURE).

    The post-adoption view the store would read back — the dispatch path and
    the CLI dry-run both use it so residual ledger checks run against the
    same projected rows without a second store round-trip. A planned row that
    was already ranked keeps its existing key.
    """
    planned_by_id = {remap["item_id"]: remap for remap in remaps}
    return [_projected(item=item, remap=planned_by_id.get(item.id)) for item in items]


def _projected(*, item: WorkItem, remap: dict[str, str] | None) -> WorkItem:
    """One row's post-adoption view: unplanned rows pass through untouched (PURE)."""
    if remap is None:
        return item
    return replace(item, status=remap["to"], rank=remap.get("rank", item.rank))


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
    journal.append(record={"stage": "status-normalization", "normalized": normalized})


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
        payload = [_outcome_payload(outcome=outcome) for outcome in outcomes]
        _ = write_stdout(text=json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return
    if not outcomes:
        _ = write_stdout(text="(nothing dispatched)\n")
        return
    for outcome in outcomes:
        pr_part = f" PR#{outcome.pr_number}" if outcome.pr_number is not None else ""
        line = f"{outcome.work_item_id}  {outcome.status} at {outcome.stage}{pr_part}"
        _ = write_stdout(text=f"{line}  {outcome.detail}\n")


# Optional outcome fields that are DROPPED from the emitted payload when unset,
# so an ordinary outcome does not carry a column of nulls for the three shapes
# that populate them: a fabro failure, a degraded step outcome, and a
# dead-implementer truncation.
_OPTIONAL_OUTCOME_FIELDS: tuple[str, ...] = (
    "dead_implementer_condition",
    "fabro_failure_cause",
    "fabro_failure_category",
    "fabro_failure_signature",
    "missing_integration_point",
    "provider_usage_limit_provider",
    "remedy",
    "step",
)


def _outcome_payload(*, outcome: DispatchOutcome) -> dict[str, object]:
    payload = asdict(outcome)
    for name in _OPTIONAL_OUTCOME_FIELDS:
        if payload.get(name) is None:
            _ = payload.pop(name)
    _ = payload.pop("provider_usage_limit", None)
    return payload
