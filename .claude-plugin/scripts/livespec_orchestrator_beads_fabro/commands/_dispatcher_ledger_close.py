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

# The one terminal livespec status. A `done` row is not part of the LIVE order
# the adoption insert appends to, so its key never bounds a fresh one.
_LIVESPEC_DONE = "done"


def plan_native_status_remaps(*, items: list[WorkItem]) -> list[dict[str, str]]:
    """Plan the beads-native → livespec status ADOPTIONS for `items` (PURE).

    Returns one `{item_id, from, to, reason}` dict per row whose stored
    status is a KEY of `_NATIVE_STATUS_REMAP`; every other row (already-
    conformant, parked, hooked, ad-hoc, unknown) contributes nothing.
    An adopted row whose `rank` reads back through `BOTTOM_SENTINEL` also
    carries a `rank` key: a real, non-sentinel key from a SINGLE
    bottom-of-order insert, so the adopted row satisfies the ratified
    "every live (head) issue has a real, non-sentinel rank" invariant
    without waiting for an on-demand `rebalance-ranks` that never
    auto-fires. Successive rank-less adoptions each insert below the
    previous one, so two adopted rows never collide on one key. An
    already-ranked row carries NO `rank` key and keeps the key it has —
    this is an insert, never a rebalance, so no OTHER row is re-keyed.

    Performs NO store mutation and NO journaling, so all four normalization
    cadences (the dispatch loop, the single-dispatch path, the standalone
    `ledger-normalize` CLI, and the pre-push `ledger-normalize --gate`)
    share identical adoption logic.
    """
    plan: list[dict[str, str]] = []
    bottom = _max_real_live_rank(items=items)
    for item in items:
        stored_status = str(item.status)
        remap = _NATIVE_STATUS_REMAP.get(stored_status)
        if remap is None:
            continue
        adoption = {
            "item_id": item.id,
            "from": stored_status,
            "to": remap.to,
            "reason": remap.reason,
        }
        if item.rank == BOTTOM_SENTINEL:
            bottom = key_between(a=bottom, b=None)
            adoption["rank"] = bottom
        plan.append(adoption)
    return plan


def _max_real_live_rank(*, items: list[WorkItem]) -> str | None:
    """The lexicographically LAST real rank key among the LIVE rows (PURE).

    `rank` sorts ascending, so the greatest key is the bottom of the order and
    `key_between(a=<this>, b=None)` inserts below every live row. `done` rows
    are excluded because the invariant this feeds is scoped to live (head)
    issues — the same scope `dev-tooling/checks/work_item_state_invariants.py`
    exempts `done` from — and a closed row's key is not part of the live order.
    `BOTTOM_SENTINEL` is excluded because it is the adapter's read-time
    substitute for "no real key", not a key. `None` (the open start of the
    order) when no live row carries a real key at all.
    """
    real = [
        item.rank
        for item in items
        if item.status != _LIVESPEC_DONE and item.rank != BOTTOM_SENTINEL
    ]
    return max(real) if real else None


def apply_native_status_remaps(
    *,
    remaps: list[dict[str, str]],
    config: StoreConfig,
) -> None:
    """Write each planned adoption to the store via the `update_work_item_status` seam.

    One mutation per adopted row carrying BOTH the livespec status and, when the
    plan assigned one, the real rank — so no call path adopts status-only and no
    window exists in which the row is a live head with no real rank.
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

    The post-adoption view the store would read back — status AND any assigned
    rank — so the dispatch path and the CLI dry-run run residual ledger checks
    against the same projected rows the store holds, without a second round-trip.
    """
    adoptions = {remap["item_id"]: remap for remap in remaps}
    return [_adopted(item=item, adoption=adoptions.get(item.id)) for item in items]


def _adopted(*, item: WorkItem, adoption: dict[str, str] | None) -> WorkItem:
    """One row with its planned adoption applied, or the row unchanged (PURE)."""
    if adoption is None:
        return item
    return replace(item, status=adoption["to"], rank=adoption.get("rank", item.rank))


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
