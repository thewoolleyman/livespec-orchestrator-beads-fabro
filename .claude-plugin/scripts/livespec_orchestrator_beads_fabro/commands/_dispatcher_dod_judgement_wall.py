"""The pre-dispatch Definition-of-Done judgement: one wall row, one drain filter.

"Judged again before dispatch" places the same judgement in a second position,
because admission is not the only route to `ready`: an item also reaches it
through `resolve-blocked:<id>:ready` after a needs-human ending, and its
Definition of Done MAY be edited after it was admitted. Both surfaces this
module publishes consume the ONE decision in `_dispatcher_dod_judgement_gate`,
so a refusal and an exclusion can never disagree about the same item.

WHY THE WALL ROW AND THE DRAIN FILTER ARE DIFFERENT SHAPES OF ONE DECISION. The
row answers "why may this named selection not run", and spends the judgement
when no verdict stands. The filter answers "which rows may this pass advertise",
runs over every ready item in the tenant, and spends NOTHING — it reads only the
verdict already recorded. A filter that could take a judgement would turn one
drain pass into a model call per ready item.

WHY AN EMPTY SELECTION RETURNS BEFORE ANYTHING IS READ. The drain reaches this
wall on every pass that finds no ready work, which is the common case, so a row
that resolved the store connection there would pay a ledger read per idle pass —
the same reason `_dispatcher_codex_credential_gate` guards its own empty
selection, recorded in that module's docstring.

WHY AN UNREADABLE LEDGER EXCLUDES NOTHING. The filter's `None` answer means the
comment sidecar could not be read, which is the absence of evidence that a
verdict stands rather than evidence that none does. Dropping the row there would
make a transient ledger fault silently empty the queue, and the emptiness reads
exactly like a factory with no work.

WHY BOTH SURFACES ARE VARIANT-AWARE, exactly as the acceptance-criteria row
immediately above this one in `_refusing_sequence` is. "Judged again before
dispatch" scopes the judgement to an "implement-kind item", and a GROOM target
reaches the door of `SPECIFICATION/contracts.md` section "Consensus-gated
automated groom cut" precisely BECAUSE it is not yet decomposed into gradeable
slices — that clause says outright it "carries the approved draft in place of an
acceptance", and `judgement_subject` renders it as carrying no effective criteria
at all. So the judgement holds it, every dispatch of it exits 5, and the filter
then drops it "until its effective criteria or referenced headings change", which
is exactly what the groom run was going to produce. That is a closed loop whose
only symptom is a groom door that quietly stops opening, so the exemption has to
be honoured at BOTH surfaces rather than only at the refusal: a filter that
dropped the row would leave the drain reporting nothing to do.

WHY THE EXEMPTION IS TESTED BEFORE THE JUDGEMENT RATHER THAN AFTER IT. Exempt
means the judgement is NOT TAKEN, not that its verdict is forgiven. The spend is
what the clause's caps are about, and a groom target's verdict is a foregone hold
whose only effect would be a comment nobody can act on.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_criteria_wall_variant import (
    criteria_wall_variant,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    held_judgement,
    item_comment_bodies,
    judge_item_definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_DISPATCH,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "dod_judgement_refusal",
    "dod_unrefused_candidates",
]


def dod_judgement_refusal(
    *, repo: Path, items: Sequence[WorkItem], workflow_name: str | None = None
) -> str | None:
    """The wall's refusal for the FIRST held item of this selection, or `None`.

    The refusal names the judgement's own finding text, as the clause requires,
    rather than a summary of it: the operator edits the section once, and a
    paraphrase is one edit away from naming a different fault than the verdict
    recorded on the item.

    `workflow_name` is the dispatch's explicit `--workflow-name` when it carried
    one, threaded exactly as the acceptance-criteria row threads it: the rest of
    the variant precedence comes from the ONE resolution the launch itself uses,
    so this row cannot exempt a different variant than the one that would run.
    """
    if not items:
        return None
    config = _connection(repo=repo)
    if config is None:
        return None
    for item in items:
        if _exempt(repo=repo, item=item, workflow_name=workflow_name):
            continue
        decision = judge_item_definition_of_done(
            item=item, repo=repo, path=config, stage=STAGE_PRE_DISPATCH
        )
        if decision.holds:
            findings = "\n".join(decision.findings)
            return (
                f"REFUSED: work-item {item.id} is held by the pre-dispatch"
                " Definition-of-Done judgement; no claim was taken and no factory"
                " run was created. The verdict, with each remedy, is recorded on"
                f" the item.\n{findings}\n"
            )
    return None


def dod_unrefused_candidates(
    *, items: Sequence[WorkItem], repo: Path, workflow_name: str | None = None
) -> list[WorkItem]:
    """This enumeration's candidates, with every judgement-refused row dropped.

    The caller's ORDER is preserved rather than re-sorted, exactly as
    `acceptance_eligible_candidates` preserves it and for the same reason: the
    canonical ranking authority is upstream, and re-ordering here would put a
    second one behind the id a consumer reads off the result.

    A GROOM-kind candidate is retained whatever verdict stands against it, which
    matters even though the refusal above no longer takes one: a verdict recorded
    by an earlier build, or at admission, outlives the dispatch that wrote it, and
    the one change that would retire it is the decomposition the groom run has not
    been allowed to produce.
    """
    if not items:
        return []
    config = _connection(repo=repo)
    if config is None:
        return list(items)
    return [
        item
        for item in items
        if _exempt(repo=repo, item=item, workflow_name=workflow_name)
        or not _is_held(item=item, repo=repo, config=config)
    ]


def _connection(*, repo: Path) -> StoreConfig | None:
    """This repository's ledger connection, or `None` when it cannot be resolved.

    A repository that declares no `connection.prefix`, or whose
    `.livespec.jsonc` cannot be read, is one no verdict can be read from or
    written to — so the judgement cannot run, and both surfaces above fail
    toward the behaviour they had without it. Unwrapped, that resolution raises
    from inside the pre-dispatch wall, which is a bug-class escape on the path
    whose whole purpose is rendering actionable refusals.
    """
    resolved = attempt(
        action=lambda: store_config(repo=repo),
        exceptions=(ConnectionPrefixMissingError, LivespecConfigUnreadableError),
    )
    return None if isinstance(resolved, AttemptFailure) else resolved


def _exempt(*, repo: Path, item: WorkItem, workflow_name: str | None) -> bool:
    """Whether the judgement is out of scope for this item's resolved variant.

    The resolution is the SHARED one, so this row and the acceptance-criteria row
    above it exempt the same set — and an unresolvable variant reads as
    `implement`, the ARMED side, for the reason `criteria_wall_variant`'s own
    docstring gives: answering `groom` for an environment fault would let a
    directory or ledger fault promote an item through the judgement.
    """
    return criteria_wall_variant(
        repo=repo, work_item_id=item.id, workflow_name=workflow_name
    ).exempt


def _is_held(*, item: WorkItem, repo: Path, config: StoreConfig) -> bool:
    bodies = item_comment_bodies(path=config, work_item_id=item.id)
    if bodies is None:
        return False
    return held_judgement(item=item, repo=repo, comments=bodies) is not None
