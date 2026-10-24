"""The pre-dispatch spec-change-tier refusal, and the drain filter beside it.

Two shapes of ONE decision, exactly as `_dispatcher_dod_judgement_wall` is, and
split for the same reason. The ROW answers "why may this named selection not
run", and classifies when no hold already stands — the clause puts the
classification on "every dispatch path". The FILTER answers "which rows may this
pass advertise", runs over every ready row in the tenant, and spends NOTHING: it
reads the recorded classification and the spec history and nothing else, because
a filter that could take a judgement would turn one drain pass into a model call
per ready item.

WHY THE FILTER KEEPS A ROW WHOSE TOPIC HAS RATIFIED. A mechanically held row is
dropped, which is the clause's "held out of `ready`". A row whose linked topic
HAS ratified is kept, because the other half of the release — the judgement
returning `stated` — is a question only the wall's fresh classification can
answer, and dropping the row would make the hold permanent with the operator's
own ratification changing nothing.

WHY A NAMED id IS STILL FILTERED NOWHERE. `_dispatcher_loop_candidates` narrows
to a requested id BEFORE either filter, which the clause requires: the
hand-picked path stays protected by the WALL "even when candidate enumerations
filtered the item earlier", so the refusal is where that item meets the hold.

WHY AN UNRESOLVABLE CONNECTION REFUSES AND DROPS NOTHING. A repository that
declares no `connection.prefix`, or whose `.livespec.jsonc` cannot be read, is
one no classification can be read from or written to — so both surfaces fail
toward the behaviour they had before this clause existed. Unwrapped, that
resolution raises from inside the pre-dispatch wall, which is a bug-class escape
on the path whose whole purpose is rendering actionable refusals.

WHY BOTH SURFACES ARE VARIANT-AWARE. The clause scopes the classification to
"every implement-kind item", and a GROOM target is precisely one that has not
been decomposed into implement-kind slices yet. Exempting it at both surfaces
rather than only at the refusal is what keeps the groom door open: a filter that
dropped the row would leave the drain reporting nothing to do, which is the
closed loop `_dispatcher_dod_judgement_wall`'s own docstring records.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_criteria_wall_variant import (
    criteria_wall_variant,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    item_comment_bodies,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_DISPATCH,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_gate import (
    spec_change_tier_hold,
    standing_spec_change_hold,
)
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
    "spec_change_tier_refusal",
    "spec_change_unheld_candidates",
]


def spec_change_tier_refusal(
    *, repo: Path, items: Sequence[WorkItem], workflow_name: str | None = None
) -> str | None:
    """The wall's refusal for the FIRST held item of this selection, or `None`.

    An EMPTY selection returns before the store connection is resolved, because
    the drain reaches this wall on every pass that finds no ready work — the
    common case — and a row that resolved a connection there would pay a read
    per idle pass.
    """
    if not items:
        return None
    config = _connection(repo=repo)
    if config is None:
        return None
    for item in items:
        if _exempt(repo=repo, item=item, workflow_name=workflow_name):
            continue
        hold = spec_change_tier_hold(item=item, repo=repo, path=config, stage=STAGE_PRE_DISPATCH)
        if hold is not None:
            return (
                f"REFUSED: work-item {item.id} is held out of ready by the"
                " spec-change tier; no claim was taken and no factory run was"
                f" created.\n{hold.detail}\n"
            )
    return None


def spec_change_unheld_candidates(
    *, items: Sequence[WorkItem], repo: Path, workflow_name: str | None = None
) -> list[WorkItem]:
    """This enumeration's candidates, with every mechanically held row dropped.

    The caller's ORDER is preserved rather than re-sorted, exactly as the two
    filters beside this one preserve it and for the same reason: the canonical
    ranking authority is upstream, and re-ordering here would put a second one
    behind the id a consumer reads off the result.
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
    """This repository's ledger connection, or `None` when it cannot be resolved."""
    resolved = attempt(
        action=lambda: store_config(repo=repo),
        exceptions=(ConnectionPrefixMissingError, LivespecConfigUnreadableError),
    )
    return None if isinstance(resolved, AttemptFailure) else resolved


def _exempt(*, repo: Path, item: WorkItem, workflow_name: str | None) -> bool:
    """Whether the tier is out of scope for this item's resolved variant.

    The resolution is the SHARED one, so this row and the two rows beside it
    exempt the same set — and an unresolvable variant reads as `implement`, the
    ARMED side, for the reason `criteria_wall_variant`'s own docstring gives.
    """
    return criteria_wall_variant(
        repo=repo, work_item_id=item.id, workflow_name=workflow_name
    ).exempt


def _is_held(*, item: WorkItem, repo: Path, config: StoreConfig) -> bool:
    bodies = item_comment_bodies(path=config, work_item_id=item.id)
    if bodies is None:
        return False
    return standing_spec_change_hold(work_item_id=item.id, repo=repo, comments=bodies) is not None
