"""Which workflow variant a pending dispatch runs, as the criteria wall sees it.

WHY THE PRE-DISPATCH ACCEPTANCE-CRITERIA WALL NEEDS THIS AT ALL. The wall
refuses an AI-dispositive item whose effective acceptance criteria parse to
zero gradeable assertions, and it is right to: an implement dispatch of an
ungradeable item silently passes a no-op acceptance, which is the failure the
wall exists to prevent. But an item reaches the GROOM DOOR of
`SPECIFICATION/contracts.md` section "Grooming and slice-size calibration" ->
"Consensus-gated automated groom cut" precisely BECAUSE it is not yet
decomposed into gradeable slices, and that clause says outright that such an
item "carries the approved draft in place of an acceptance". Requiring
gradeable criteria before a groom run inverts the dependency: the run's whole
output is the draft that PRODUCES those criteria. So the wall is made
VARIANT-AWARE rather than laxer -- a groom-kind dispatch is exempt because its
acceptance is the human approval of the draft and it terminates at needs-human
by construction, and every other dispatch meets the wall unchanged.

WHY IT IS A MODULE OF ITS OWN. `_dispatcher_effective_criteria` is the ONE
resolution of a work-item's criteria, shared by four gates, and three of those
gates are not dispatches at all -- the capture and groom parse displays, the
entry-to-`ready` approve valve, the post-merge acceptance pass. "Which graph
will this dispatch run" is a question only the pre-dispatch gate asks, and it
answers it out of the registry, the item's ledger pin and the target's config.
Folding those reads into the criteria primitive would put a store read and a
workflow-registry read behind every one of the other three gates.

WHY AN UNRESOLVABLE VARIANT READS AS `implement`, which is the ARMED side.
Every read this module makes can fail for reasons that have nothing to do with
grooming: an item absent from the tenant, an unreadable `.livespec.jsonc`, a
connection descriptor that will not resolve. Answering `groom` for any of them
would let an environment fault open the one gate standing between an
ungradeable item and a machine-graded run -- a fail-OPEN whose refusal looks
exactly like a deliberate exemption. The failing direction is therefore the
refusing one, matching `_workflow_variant_kind`'s own rule that the kind which
unlocks a door is the one that has to be SAID.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_workflow_ledger import (
    previewed_workflow_variant,
)
from livespec_orchestrator_beads_fabro.commands._workflow_variant_kind import (
    WORKFLOW_KIND_GROOM,
    WORKFLOW_KIND_IMPLEMENT,
    variant_kind,
)
from livespec_orchestrator_beads_fabro.commands._workflow_variants import RESERVED_WORKFLOW_NAME
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)

__all__: list[str] = [
    "CriteriaWallVariant",
    "criteria_wall_variant",
]

# Every EXPECTED way the preview can fail to reach an answer, enumerated rather
# than caught broadly: each of these is an environment or configuration fault,
# and none of them is evidence about the variant. A bug still raises.
_UNRESOLVABLE = (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
    OSError,
)


@dataclass(frozen=True, kw_only=True)
class CriteriaWallVariant:
    """The variant one pending dispatch resolved, and what the wall does with it."""

    name: str
    kind: str

    @property
    def exempt(self) -> bool:
        """Whether this dispatch is exempt from the acceptance-criteria wall."""
        return self.kind == WORKFLOW_KIND_GROOM

    def clause(self) -> str:
        """The wall's operator-facing naming of the variant it resolved.

        Carried in the refusal so an operator can tell a groom-path refusal from
        an implement-path one. Without it the two are the same sentence, and the
        remedy differs completely: an implement-path refusal wants criteria on
        the item, a groom-path one means the variant did not resolve to the
        groom kind the operator believed it had pinned.
        """
        return (
            f"resolved workflow variant {self.name!r} is of kind {self.kind},"
            f" and only a {WORKFLOW_KIND_GROOM}-kind variant is exempt from this wall"
        )


def criteria_wall_variant(
    *,
    repo: Path,
    work_item_id: str,
    workflow_name: str | None = None,
) -> CriteriaWallVariant:
    """Resolve the variant this dispatch would run, failing toward the armed side.

    `workflow_name` is the dispatch's explicit `--workflow-name` when it carried
    one; the rest of the precedence -- the item's `dispatch_workflow` pin, then
    `dispatcher.default_workflow`, then the reserved workflow -- comes from the
    ONE resolution the launch itself uses, so the wall cannot judge a different
    variant than the one that would run.
    """
    resolved = attempt(
        action=lambda: previewed_workflow_variant(
            repo=repo, work_item_id=work_item_id, name=workflow_name
        ),
        exceptions=_UNRESOLVABLE,
    )
    if isinstance(resolved, AttemptFailure):
        return CriteriaWallVariant(name=RESERVED_WORKFLOW_NAME, kind=WORKFLOW_KIND_IMPLEMENT)
    return CriteriaWallVariant(name=resolved.name, kind=variant_kind(repo=repo, variant=resolved))
