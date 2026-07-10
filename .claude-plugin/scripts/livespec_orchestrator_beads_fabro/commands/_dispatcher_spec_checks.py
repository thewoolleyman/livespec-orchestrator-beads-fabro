"""Spec-context work-item invariants (the Dispatcher's spec-check surface).

Re-homes the three retired livespec doctor invariants that need
spec-tree / staleness context beyond the Ledger rows (livespec PR #396
retired all six work-item cross-boundary invariants when v103 made
work-items orchestrator-private; tracked as livespec-impl-beads-e6x;
source recoverable at livespec commit 682bf9cc under
`.claude-plugin/scripts/livespec/doctor/static/`). The pure-Ledger
trio lives in the sibling `_dispatcher_ledger_checks.py`; this module
carries the rest:

- `no-stalled-epic` (severity `fail`) — a live (non-`done`) epic whose
  non-empty `depends_on` resolves entirely closed is a data-model
  contradiction: the aggregated work is complete but the epic record
  was never transitioned. Unparseable, missing, or `unknown`-resolving
  entries do NOT count as closed (that drift class belongs to
  `no-orphan-dependency`), and any `open` dependency — local or
  cross-repo via `resolve_ref` — is a legitimate stall reason.
- `no-stale-gap-tied` (severity `warn`) — an open gap-tied work-item
  whose `gap_id` no longer surfaces in a fresh `detect_impl_gaps`
  detection run over the live spec tree should be closed via a
  non-fix disposition. The gap-id set comes from this plugin's own
  `detect_rules`, so derivation stays in lockstep with the canonical
  gap-detection surface.
- `unresolved-spec-commitment` (severity `fail`) — every accepted
  propose-change's declared `spec_commitments.impl_followups[]`
  id_hint must resolve to a Ledger work-item carrying the matching
  `spec_commitment_hint`, unless a later PC's `supersedes[]` exempts
  it. The history walk lives in `_dispatcher_spec_commitments.py`.

The two spec-tree-dependent checks emit `skipped` findings when the
spec tree is absent; `no-stalled-epic` is a pure function of the
Ledger rows plus the cross-repo manifest and always runs.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from livespec_runtime.cross_repo.resolve import resolve_ref
from livespec_runtime.cross_repo.types import CrossRepoManifest, RefStatus

from livespec_orchestrator_beads_fabro.commands._cross_repo import parse_entry
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_checks import LedgerFinding
from livespec_orchestrator_beads_fabro.commands._dispatcher_spec_commitments import (
    collect_obligations_and_supersedes,
)
from livespec_orchestrator_beads_fabro.commands.detect_impl_gaps import detect_rules
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["run_spec_checks"]

_SPEC_TREE_DEPENDENT_CHECKS = ("no-stale-gap-tied", "unresolved-spec-commitment")


def run_spec_checks(
    *,
    items: list[WorkItem],
    spec_root: Path,
    manifest: CrossRepoManifest,
) -> list[LedgerFinding]:
    """Run the three spec-context checks over the tenant rows + spec tree.

    Returns findings sorted by (check, item_id) so output is stable for
    journaling and tests. An empty list means every invariant holds.
    """
    findings = _check_stalled_epics(items=items, manifest=manifest)
    if spec_root.is_dir():
        findings.extend(_check_stale_gap_tied(items=items, spec_root=spec_root))
        findings.extend(_check_unresolved_commitments(items=items, spec_root=spec_root))
    else:
        findings.extend(
            LedgerFinding(
                check=check,
                item_id="-",
                severity="skipped",
                message=f"spec tree not found at {spec_root}; check skipped",
            )
            for check in _SPEC_TREE_DEPENDENT_CHECKS
        )
    return sorted(findings, key=lambda finding: (finding.check, finding.item_id))


def _check_stalled_epics(
    *,
    items: list[WorkItem],
    manifest: CrossRepoManifest,
) -> list[LedgerFinding]:
    index = {item.id: item for item in items}
    findings: list[LedgerFinding] = []
    for item in items:
        if item.type != "epic" or item.status == "done":
            continue
        if not item.depends_on:
            continue
        if all(
            _resolve_dep(raw=raw, index=index, manifest=manifest) == RefStatus.CLOSED
            for raw in item.depends_on
        ):
            findings.append(
                LedgerFinding(
                    check="no-stalled-epic",
                    item_id=item.id,
                    severity="fail",
                    message=(
                        f"every depends_on entry resolves closed but the epic is "
                        f"still {item.status}; close it with an appropriate "
                        f"resolution or add fresh depends_on entries"
                    ),
                )
            )
    return findings


def _check_stale_gap_tied(*, items: list[WorkItem], spec_root: Path) -> list[LedgerFinding]:
    open_gap_tied = [
        item
        for item in items
        if item.origin == "gap-tied" and item.status != "done" and item.gap_id is not None
    ]
    if not open_gap_tied:
        return []
    current_gap_ids = {rule.gap_id for rule in detect_rules(spec_root=spec_root)}
    return [
        LedgerFinding(
            check="no-stale-gap-tied",
            item_id=item.id,
            severity="warn",
            message=(
                f"gap_id {item.gap_id} no longer surfaces in a fresh detection "
                f"run over {spec_root}; close the work-item via a non-fix "
                f"disposition (spec-revised, no-longer-applicable, or "
                f"resolved-out-of-band)"
            ),
        )
        for item in open_gap_tied
        if item.gap_id not in current_gap_ids
    ]


def _check_unresolved_commitments(
    *,
    items: list[WorkItem],
    spec_root: Path,
) -> list[LedgerFinding]:
    obligations, superseded = collect_obligations_and_supersedes(spec_root=spec_root)
    hints = {item.spec_commitment_hint for item in items if item.spec_commitment_hint}
    return [
        LedgerFinding(
            check="unresolved-spec-commitment",
            item_id=obligation.id_hint,
            severity="fail",
            message=(
                f"declared in {obligation.version_label}/proposed_changes/"
                f"{obligation.pc_stem}.md but no Ledger work-item carries "
                f"spec_commitment_hint {obligation.id_hint}; file one via "
                f"capture-work-item --spec-commitment-hint {obligation.id_hint}"
            ),
        )
        for obligation in obligations
        if obligation.id_hint not in superseded and obligation.id_hint not in hints
    ]


def _resolve_dep(
    *,
    raw: object,
    index: dict[str, WorkItem],
    manifest: CrossRepoManifest,
) -> RefStatus:
    entry = parse_entry(raw=raw)
    if entry is None:
        return RefStatus.UNKNOWN
    return resolve_ref(
        entry=entry,
        manifest=manifest,
        local_status_lookup=_status_lookup(index=index),
    )


def _status_lookup(*, index: dict[str, WorkItem]) -> Callable[[str], RefStatus]:
    def _lookup_status(*, work_item_id: str) -> RefStatus:
        record = index.get(work_item_id)
        if record is None:
            return RefStatus.UNKNOWN
        if record.status == "done":
            return RefStatus.CLOSED
        return RefStatus.OPEN

    return lambda work_item_id: _lookup_status(work_item_id=work_item_id)
