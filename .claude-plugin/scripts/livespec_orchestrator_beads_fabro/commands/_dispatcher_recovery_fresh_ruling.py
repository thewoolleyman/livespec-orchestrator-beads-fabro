"""The fresh route a current fresh ruling assigns, past every preserved tree.

A fresh ruling still identifies the item's needs-human refs.  The route does not
take one, but its record must name each ref it deliberately passed over; an
unreadable listing is held rather than mistaken for no preserved trees.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_refs import (
    NeedsHumanRefsUnobservable,
    NeedsHumanScope,
    carrying_needs_human_refs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_measurements import (
    MEASUREMENT_PRESERVED_WORK,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_preserved import (
    NEEDS_HUMAN_REF_PREFIX,
    SEED_REMOTE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_FRESH,
    RecoveryHold,
    RecoveryMeasurement,
    RecoveryRoute,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_run_age import (
    foreign_run_ids,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_ruling_currency import FreshRuling

__all__: list[str] = ["fresh_ruling_route"]

_GIT_TIMEOUT_SECONDS = 120.0


def fresh_ruling_route(
    *,
    runner: CommandRunner,
    repo: Path,
    work_item_id: str,
    earlier_run_ids: tuple[str, ...],
    journal_records: tuple[dict[str, object], ...],
    ruling: FreshRuling,
) -> RecoveryRoute | RecoveryHold:
    """Record the current ruling's instant and every needs-human ref it passes over."""
    carrying = carrying_needs_human_refs(
        runner=runner,
        repo=repo,
        scope=NeedsHumanScope(
            run_ids=earlier_run_ids,
            foreign_run_ids=foreign_run_ids(
                records=journal_records, work_item_id=work_item_id, own=earlier_run_ids
            ),
        ),
        ref_prefix=NEEDS_HUMAN_REF_PREFIX,
        remote=SEED_REMOTE,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if isinstance(carrying, NeedsHumanRefsUnobservable):
        return RecoveryHold(
            measurements=(
                RecoveryMeasurement(
                    name=MEASUREMENT_PRESERVED_WORK,
                    detail=(
                        f"{carrying.detail}, so the fresh ruling cannot establish every "
                        "needs-human ref it must pass over"
                    ),
                ),
            )
        )
    return RecoveryRoute(
        work_item_id=work_item_id,
        route=ROUTE_FRESH,
        fresh_ruling_instant=ruling.instant,
        passed_over_needs_human=tuple((one.ref, one.commit_sha) for one in carrying),
    )
