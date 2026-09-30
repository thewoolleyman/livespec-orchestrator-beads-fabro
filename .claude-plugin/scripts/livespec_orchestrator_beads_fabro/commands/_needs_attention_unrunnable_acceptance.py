"""The unrunnable-acceptance hygiene lane: a ready item no dispatch will take.

The orchestrator-owned-attention-facts clause of `SPECIFICATION/contracts.md`
ratifies exactly one stable `hygiene:unrunnable-acceptance:<work-item-id>` fact
per item that physically rests in `ready` while FAILING the shared
acceptance-eligibility decision. Such a row is silent on every other lane in the
snapshot — nothing is stranded, nothing is held, nothing is aging past a bound —
so without this one it is visible only by an operator happening to notice that
the queue never picks it.

THE LANE DECIDES NOTHING OF ITS OWN. It consumes `acceptance_eligibility`
verbatim, which is what the clause demands of every candidate-producing surface:
"The fact and every candidate-producing surface MUST consume the SAME eligibility
decision; neither side may re-derive the effective criteria or workflow variant."
That is also what makes the awkward `human-only` rule correct here for free — the
decision already refuses a `human-only` item ONLY for a Definition-of-Done
finding and never on the gradeable-assertion count, because the human owns that
grading. A lane that re-implemented the rule would be one edit away from flooding
the snapshot with every deliberately human-graded item in the tenant.

WHY THE HANDOFF IS NOT A DISPATCH. The clause forbids `impl:<work-item-id>`
outright, and the reason is worth keeping in view: the pre-dispatch wall would
refuse THIS VERY ITEM, so a dispatch handoff hands the operator a command that
cannot succeed. Its exit-5 refusal then reads as the factory being broken rather
than as the item needing repair — an attention item that misdirects is worse than
no attention item at all. What the operator is handed instead is the item's own
record, which is the thing they have to edit.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_eligibility import (
    AcceptanceEligibility,
    acceptance_eligibility,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "unrunnable_acceptance_items",
]

_READY_STATUS = "ready"


def unrunnable_acceptance_items(
    *, project_root: Path, repo: str, items: list[WorkItem]
) -> list[AttentionItem]:
    """One fact per `ready` item the shared eligibility decision refuses."""
    return [
        _unrunnable_item(project_root=project_root, repo=repo, item=item, decision=decision)
        for item in items
        if item.status == _READY_STATUS
        for decision in (acceptance_eligibility(item=item, cwd=project_root),)
        if not decision.eligible
    ]


def _unrunnable_item(
    *,
    project_root: Path,
    repo: str,
    item: WorkItem,
    decision: AcceptanceEligibility,
) -> AttentionItem:
    return ConformanceContext(project_root=project_root, repo=repo).candidate(
        # The orchestrator-owned `hygiene:<type>:<resource>` id form, keyed on the
        # work-item so the fact is STABLE across snapshots: a consumer tracking
        # whether this item is still unrunnable keys on the id, and a
        # snapshot-scoped id would read as a new problem every pass.
        id=f"hygiene:unrunnable-acceptance:{item.id}",
        kind="hygiene",
        urgency="medium",
        summary=_summary(item=item, decision=decision),
        source_ref=SourceRef(repo=repo, work_item=item.id),
        handoff=Handoff(
            kind="shell", command=_repair_command(project_root=project_root, item=item)
        ),
    )


def _summary(*, item: WorkItem, decision: AcceptanceEligibility) -> str:
    """The operator-facing one-liner, carrying the parse AND all three remedies.

    The parse is included because the three remedies are not interchangeable and
    only the parse says which applies: an item resolved from
    `description-exit-criteria` with zero assertions needs a Definition of Done
    section authored, while one resolved from that source with assertions has
    criteria in a legacy place and needs them MOVED.
    """
    return (
        f"Work-item {item.id} rests in {_READY_STATUS} but is UNRUNNABLE:"
        f" {decision.criteria.parse_display()}. Author the Definition of Done"
        " section in its description, author gradeable criteria by groom or edit,"
        " or deliberately select the human-only acceptance_policy where machine"
        " grading is genuinely inapplicable."
    )


def _repair_command(*, project_root: Path, item: WorkItem) -> str:
    """Read the item's own record, which is the surface the repair edits."""
    wrapper = Path(__file__).parents[2] / "bin" / "context.py"
    return (
        f"python3 {shlex.quote(str(wrapper))} "
        f"--project-root {shlex.quote(str(project_root))} {shlex.quote(item.id)} --json"
    )
