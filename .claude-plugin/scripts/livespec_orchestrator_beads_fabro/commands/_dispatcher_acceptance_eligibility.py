"""The ONE shared, variant-aware acceptance-eligibility decision.

The effective-acceptance-criteria clause of `SPECIFICATION/contracts.md` (v114)
ratifies exactly one public decision that combines the effective-criteria result
with the effective workflow variant, and names its consumers: the pre-dispatch
wall, the Dispatcher drain, `next`, the needs-attention implementation item, the
idle-factory fact, and the unrunnable-acceptance fact. They "MUST NOT
independently parse criteria, approximate workflow resolution, or disagree about
whether the same item is dispatchable."

WHY THIS IS A MODULE OF ITS OWN RATHER THAN MORE OF THE PRIMITIVE.
`_dispatcher_effective_criteria` resolves criteria from an item ALONE, and three
of its consumers hold nothing else — the capture and groom parse displays and the
post-merge acceptance pass. This decision needs the REPOSITORY as well: the
workflow-variant preview (a store read plus a registry read) and the governed
spec tree the reference line is graded against. Folding either into the primitive
would put both behind every display.

WHY THE WALL MOVED HERE FROM THE PRIMITIVE. `pre_dispatch_criteria_refusal` is
the wall's operator-facing rendering of exactly this decision over a WAVE of
candidates, so leaving it beside the primitive while the decision lived here
would be the second composition point the clause forbids — and the two would
drift the moment one gained a check.

WHAT THE REFUSAL ORDER MEANS. The section findings come FIRST and the
empty-criteria refusal second, because an item with no Definition of Done section
also has no gradeable assertions from one: reporting "criteria are empty" for
such an item names a symptom and hides the cause, and the operator would author
criteria into the legacy field — the very thing v114 stops accepting for new
work. When the section IS present and parses to nothing, the empty-criteria
refusal is the accurate one and it fires.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_criteria_wall_variant import (
    CriteriaWallVariant,
    criteria_wall_variant,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done_findings import (
    definition_of_done_findings,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    AI_ONLY_POLICY,
    EffectiveCriteria,
    effective_criteria,
    effective_policy,
    ungradeable_criteria_refusal,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "PROOF_ROUTING_FACTORY_CAPTURED_ONLY",
    "PROOF_ROUTING_PARKS_FOR_HUMAN_ATTESTATION",
    "AcceptanceEligibility",
    "acceptance_eligibility",
    "pre_dispatch_criteria_refusal",
]

# The two DERIVED item-level proof routings. The clause forbids storing an
# item-level proof mode in any field, label or metadata key, so these are
# computed from the assertions every time and never written anywhere. The names
# are self-describing, as the enumeration rule requires of every mode-adjacent
# value: they say what the item DOES, not which tier it sits in.
PROOF_ROUTING_FACTORY_CAPTURED_ONLY = "factory-captured-only"
PROOF_ROUTING_PARKS_FOR_HUMAN_ATTESTATION = "parks-for-human-attestation"


@dataclass(frozen=True, kw_only=True)
class AcceptanceEligibility:
    """One item's eligibility verdict, and everything the consumers read off it.

    `refusal` is the operator-facing detail for ONE item, or `None` when the item
    clears every wall. `findings` carries the mechanical Definition-of-Done
    findings separately, because the `dod_gate` node's needs-human question and
    the capture and groom displays render them without the wall's framing.

    `proof_routing` is the DERIVED item-level consequence of the assertions'
    modes. It is reported even for a REFUSED item, because the refusal's whole
    remedy is about the routing: an operator told only "ai-only is refused" has
    to re-derive why, and the routing is the why.

    `variant` and `criteria` ride along deliberately: a consumer that needed
    either would otherwise resolve it a second time, which is precisely the
    disagreement this one decision exists to prevent.
    """

    work_item_id: str
    variant: CriteriaWallVariant
    criteria: EffectiveCriteria
    findings: tuple[str, ...]
    proof_routing: str
    refusal: str | None

    @property
    def eligible(self) -> bool:
        """Whether the item clears every wall this decision owns."""
        return self.refusal is None


def acceptance_eligibility(
    *, item: WorkItem, cwd: Path, workflow_name: str | None = None
) -> AcceptanceEligibility:
    """Decide whether one item may be dispatched, and why not when it may not.

    `workflow_name` is the dispatch's explicit `--workflow-name` when it carried
    one; the rest of the variant precedence comes from the ONE resolution the
    launch itself uses, so the decision cannot judge a different graph than the
    one that would run.
    """
    variant = criteria_wall_variant(repo=cwd, work_item_id=item.id, workflow_name=workflow_name)
    criteria = effective_criteria(item=item)
    if variant.exempt:
        # A groom target is sent to the door precisely BECAUSE it is not yet
        # decomposed into gradeable slices, and its whole output is the draft
        # that produces them — so it is exempt from the section requirement
        # entirely, not merely from the assertion count.
        return _verdict(item=item, variant=variant, criteria=criteria, findings=(), refusal=None)
    findings = definition_of_done_findings(item=item, cwd=cwd)
    return _verdict(
        item=item,
        variant=variant,
        criteria=criteria,
        findings=findings,
        refusal=_refusal(item=item, variant=variant, criteria=criteria, findings=findings, cwd=cwd),
    )


def pre_dispatch_criteria_refusal(
    *,
    items: Sequence[WorkItem],
    cwd: Path,
    workflow_name: str | None = None,
) -> str | None:
    """The pre-dispatch wall's operator-facing refusal, or `None` to proceed.

    Applied to the SELECTED candidates of both dispatch paths — the hand-picked
    `dispatch --item` target and the `loop` drain's wave — before any factory run
    is created, so a refused item is never claimed, never admitted, and never
    leaves a run behind to reap. The variant is resolved for EVERY candidate
    rather than only for the ones that would otherwise refuse, because a wave
    dispatches item by item and the groom exemption is a property of the
    candidate, not of the wave.
    """
    details = [
        detail
        for detail in (
            acceptance_eligibility(item=item, cwd=cwd, workflow_name=workflow_name).refusal
            for item in items
        )
        if detail is not None
    ]
    if not details:
        return None
    lines = "".join(f"  {detail}\n" for detail in details)
    return f"ERROR: refusing to dispatch; no factory run was created:\n{lines}"


def _verdict(
    *,
    item: WorkItem,
    variant: CriteriaWallVariant,
    criteria: EffectiveCriteria,
    findings: tuple[str, ...],
    refusal: str | None,
) -> AcceptanceEligibility:
    return AcceptanceEligibility(
        work_item_id=item.id,
        variant=variant,
        criteria=criteria,
        findings=findings,
        proof_routing=_proof_routing(criteria=criteria),
        refusal=refusal,
    )


def _proof_routing(*, criteria: EffectiveCriteria) -> str:
    """The item-level routing its assertions' modes imply.

    ONE human-attested assertion decides the whole item, however many
    factory-captured ones sit beside it: the item cannot close until the human
    leg lands, so a routing that averaged the modes would close it early.
    """
    if criteria.human_attested_assertions:
        return PROOF_ROUTING_PARKS_FOR_HUMAN_ATTESTATION
    return PROOF_ROUTING_FACTORY_CAPTURED_ONLY


def _refusal(
    *,
    item: WorkItem,
    variant: CriteriaWallVariant,
    criteria: EffectiveCriteria,
    findings: tuple[str, ...],
    cwd: Path,
) -> str | None:
    """The one refusal detail for a non-exempt item, or `None` to proceed."""
    if findings:
        return f"{'; '.join(findings)}; {variant.clause()}"
    human_attested = criteria.human_attested_assertions
    if human_attested and effective_policy(item=item, cwd=cwd) == AI_ONLY_POLICY:
        return _ai_only_routing_refusal(item=item, human_attested=human_attested)
    detail = ungradeable_criteria_refusal(item=item, cwd=cwd)
    if detail is None:
        return None
    return f"{detail}; {variant.clause()}"


def _ai_only_routing_refusal(*, item: WorkItem, human_attested: tuple[str, ...]) -> str:
    """The refusal for an `ai-only` item whose Definition of Done needs a human.

    It names the assertions rather than counting them, because the remedy is a
    judgement about THOSE assertions: either the policy is wrong for this item or
    the assertion was declared human-attested when the sandbox could in fact
    exercise it, and a count cannot tell an operator which.
    """
    named = "; ".join(repr(assertion) for assertion in human_attested)
    return (
        f"work-item {item.id}: the effective acceptance_policy is"
        f" {AI_ONLY_POLICY!r}, which cannot close an item whose Definition of Done"
        f" carries a human-attested assertion ({named}); declare ai-then-human or"
        " human-only, or make the assertion factory-capturable and drop its"
        " Human-attested sub-heading"
    )
