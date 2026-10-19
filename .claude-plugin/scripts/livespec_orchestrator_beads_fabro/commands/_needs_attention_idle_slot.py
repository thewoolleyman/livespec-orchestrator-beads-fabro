"""The one attention row an empty factory queue beside priority work produces.

This fact and `hygiene:idle-factory:<repo>` are INDEPENDENT, and the clause
says so outright: neither suppresses, replaces, or re-derives the other. The
difference is scope and shape. The idle-factory row is scoped to ONE
repository — zero counted claims for it and its own ready set — so it cannot
see a priority epic in another tenant, cannot classify a non-ready child, and
structurally cannot show a stale edge, which is an item held only by blockers
that landed and were never closed. This row is the cross-tenant view.

ITS HANDOFF IS AN INSPECTION, NOT A DISPATCH. It MUST NOT advertise
`impl:<id>`, because the first child may live in another tenant and this
repository's `drive` cannot dispatch it — an attention row that hands the
operator a failing command is worse than none at all. So the handoff runs the
audit subcommand, which is the surface that can show every tenant.

ITS `source_ref` NAMES THE REPOSITORY AND NO WORK-ITEM, for the same reason: a
work-item field is read as an item of THIS repository, and the first
dispatchable child generally is not one.

DETERMINISM. Every subject in the summary — the factory, the two counts, the
first id — is read off the audit result itself, in configuration order. No
clock, no dwell, no run id appears here, so identical ledgers, board,
configuration and evaluation time render identical bytes.

The row clears the instant the finding would not print, which is exactly what
returning the empty list on `finding is None` means: an unconfigured audit, a
malformed one, an unobservable board, a queued run, or no dispatchable and no
stale-edge child all reach the same empty answer through the one condition.
"""

from __future__ import annotations

from pathlib import Path

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef

from livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_audit import (
    IdleSlotFinding,
    idle_slot_audit,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_command import (
    idle_slot_audit_command,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
)

__all__: list[str] = [
    "idle_slot_items",
]


def idle_slot_items(*, project_root: Path, repo: str) -> list[AttentionItem]:
    """The single idle-slot row, or nothing when the finding would not print."""
    result = idle_slot_audit(project_root=project_root)
    finding = result.finding
    if finding is None:
        return []
    return [_idle_slot_item(project_root=project_root, repo=repo, finding=finding)]


def _idle_slot_item(
    *,
    project_root: Path,
    repo: str,
    finding: IdleSlotFinding,
) -> AttentionItem:
    return ConformanceContext(project_root=project_root, repo=repo).candidate(
        id=f"hygiene:idle-slot:{finding.factory}",
        kind="hygiene",
        urgency="high",
        summary=_summary(finding=finding),
        source_ref=SourceRef(repo=repo),
        handoff=Handoff(
            kind="shell",
            command=idle_slot_audit_command(project_root=project_root),
        ),
    )


def _summary(*, finding: IdleSlotFinding) -> str:
    return (
        f"Factory {finding.factory} shows no runnable run while "
        f"{len(finding.dispatchable_ids)} priority-epic children are classified "
        f"DISPATCHABLE-NOW and {len(finding.stale_edge_ids)} are classified "
        f"STALE-EDGE; the first is {finding.child_ids[0]}. "
        f"Run the idle-slot audit for the per-tenant classification."
    )
