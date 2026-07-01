"""Pre-dispatch Ledger integrity checks (the Dispatcher's hard pre-gate).

Re-homes the dispatch-safety subset of the six work-item integrity
invariants that livespec PR #396 retired from core's doctor when v103
made work-items orchestrator-private (tracked as livespec-impl-beads-e6x;
source recoverable at livespec commit 682bf9cc under
`.claude-plugin/scripts/livespec/doctor/static/`). The re-homed
here are exactly the ones that are pure functions of the work-item rows
the Dispatcher already loads, and that make dispatching UNSAFE when
violated:

- `status-conformance` — every live row's status is one of the seven
  livespec lifecycle states, encoded as `ALLOWED_BEADS_STATUSES`
  (DERIVED from the canonical `WorkItemStatus` Literal, never
  hand-typed); beads' extra built-ins/customs (`open`/`deferred`) or an
  ad-hoc `bd update --status foo` must not silently park dispatchable
  work in an unknown lane.
- `depends-on-ref-wellformedness` — every `depends_on` entry on a
  non-closed item parses to a typed entry (`parse_entry` returning
  `None` means the readiness predicate silently treats the row as
  blocked forever).
- `no-orphan-dependency` — every same-tenant dependency target of a
  non-closed item exists in the tenant (a missing target can never
  close, so the dependent can never become ready).
- `no-duplicate-gap-id` — no two non-closed items share a `gap_id`
  (double-dispatching one gap produces colliding branches and PRs).

The remaining three retired invariants (`no_stalled_epic`,
`no_stale_gap_tied`, `unresolved_spec_commitment`) need spec-tree and
staleness context beyond the Ledger rows and are re-homed in the
sibling `_dispatcher_spec_checks.py` (the `spec-check` subcommand);
`LedgerFinding` below is the finding shape shared by every Dispatcher
check surface (ledger-check / spec-check / janitor-check).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from livespec_runtime.cross_repo.types import LocalDependency

from livespec_orchestrator_beads_fabro.commands._cross_repo import parse_entry
from livespec_orchestrator_beads_fabro.store import ALLOWED_BEADS_STATUSES
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "STATUS_CONFORMANCE_CHECK",
    "LedgerFinding",
    "Severity",
    "run_ledger_checks",
]

# `fail` findings flip the surfacing subcommand to exit 1; `warn`
# findings surface recoverable housekeeping and also exit 1 when
# present; `skipped` findings record an unmet precondition (absent
# spec tree, failed git/gh probe) and never affect the exit code.
Severity = Literal["fail", "warn", "skipped"]

# The check id the `status-conformance` gate stamps on its findings. Shared
# so the `dev-tooling/checks/status_conformance.py` wiring (which runs the
# Ledger registry under `just check` / `/livespec:doctor`) can select this
# check's findings by name without re-typing the string.
STATUS_CONFORMANCE_CHECK = "status-conformance"


@dataclass(frozen=True, kw_only=True)
class LedgerFinding:
    """One Dispatcher-side check finding (Ledger / spec / janitor surfaces)."""

    check: str
    item_id: str
    message: str
    severity: Severity = "fail"


def run_ledger_checks(*, items: list[WorkItem]) -> list[LedgerFinding]:
    """Run the dispatch-safety Ledger checks over the tenant rows.

    Returns findings sorted by (check, item_id) so output is stable for
    journaling and tests. An empty list means the Ledger is safe to
    dispatch from.
    """
    index = {item.id: item for item in items}
    active = [item for item in items if item.status != "done"]
    findings: list[LedgerFinding] = []
    findings.extend(_check_status_conformance(active=active))
    findings.extend(_check_ref_wellformedness(active=active))
    findings.extend(_check_orphan_dependencies(active=active, index=index))
    findings.extend(_check_duplicate_gap_ids(active=active))
    return sorted(findings, key=lambda finding: (finding.check, finding.item_id))


def _check_status_conformance(*, active: list[WorkItem]) -> list[LedgerFinding]:
    """Flag every live row whose status ∉ the derived allowed-status set.

    `active` is already the non-`done` subset, so each materialized status
    here is the stored beads status verbatim — the sole `done` ↔ `closed`
    rename only touches closed rows, which are excluded. Membership is
    tested against `ALLOWED_BEADS_STATUSES` (DERIVED from the canonical
    `WorkItemStatus` Literal), so beads' native `open`/`deferred` and any
    ad-hoc status that would silently park the row in an unknown lane are
    named here rather than dispatched.
    """
    allowed = ", ".join(sorted(ALLOWED_BEADS_STATUSES))
    findings: list[LedgerFinding] = []
    for item in active:
        if item.status in ALLOWED_BEADS_STATUSES:
            continue
        findings.append(
            LedgerFinding(
                check=STATUS_CONFORMANCE_CHECK,
                item_id=item.id,
                message=(
                    f"status {item.status!r} is outside the livespec lifecycle "
                    f"(allowed: {allowed})"
                ),
            )
        )
    return findings


def _check_ref_wellformedness(*, active: list[WorkItem]) -> list[LedgerFinding]:
    findings: list[LedgerFinding] = []
    for item in active:
        for raw in item.depends_on:
            if parse_entry(raw=raw) is not None:
                continue
            findings.append(
                LedgerFinding(
                    check="depends-on-ref-wellformedness",
                    item_id=item.id,
                    message=f"unparseable depends_on entry: {raw!r}",
                )
            )
    return findings


def _check_orphan_dependencies(
    *,
    active: list[WorkItem],
    index: dict[str, WorkItem],
) -> list[LedgerFinding]:
    findings: list[LedgerFinding] = []
    for item in active:
        for raw in item.depends_on:
            entry = parse_entry(raw=raw)
            if not isinstance(entry, LocalDependency):
                continue
            if entry.work_item_id in index:
                continue
            findings.append(
                LedgerFinding(
                    check="no-orphan-dependency",
                    item_id=item.id,
                    message=f"depends_on names a missing item: {entry.work_item_id}",
                )
            )
    return findings


_DUPLICATE_THRESHOLD = 2


def _check_duplicate_gap_ids(*, active: list[WorkItem]) -> list[LedgerFinding]:
    by_gap: dict[str, list[str]] = {}
    for item in active:
        if item.gap_id is None:
            continue
        by_gap.setdefault(item.gap_id, []).append(item.id)
    findings: list[LedgerFinding] = []
    for gap_id, item_ids in by_gap.items():
        if len(item_ids) < _DUPLICATE_THRESHOLD:
            continue
        others = ", ".join(sorted(item_ids))
        findings.extend(
            LedgerFinding(
                check="no-duplicate-gap-id",
                item_id=item_id,
                message=f"gap_id {gap_id} is shared by non-closed items: {others}",
            )
            for item_id in item_ids
        )
    return findings
