"""Liveness and ownership refusals for a release-spec-tier valve press.

The release valve owns the attestation and intake route; this module owns the
independent question of whether an in-flight run or its dispatch lock makes the
press unsafe. Keeping those external observations together lets the valve read
as the ordered transaction it performs.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    live_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._drive_merge_hold_arm_guard import (
    observe_item_run_liveness,
)
from livespec_orchestrator_beads_fabro.commands._drive_valve_result import valve_refusal

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._drive_reject_valve import HumanValveRunner
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["release_activity_refusal"]


def release_activity_refusal(
    *,
    repo: Path,
    item: WorkItem,
    aid: str,
    runner: HumanValveRunner | None,
    action: str,
) -> dict[str, Any] | None:
    """Refuse while a run is live, unmeasured, or its ownership lock is held."""
    liveness = observe_item_run_liveness(repo=repo, work_item_id=item.id, runner=runner)
    if not liveness.observed:
        return valve_refusal(
            aid=aid,
            wid=item.id,
            err="live-run",
            msg=(
                f"{action} refused: whether a run of {item.id} is live could not be established,"
                " because the configured factory did not answer with a run inventory; the hold"
                " stands."
            ),
        )
    if liveness.live_run_ids:
        return valve_refusal(
            aid=aid,
            wid=item.id,
            err="live-run",
            msg=(
                f"{action} refused: {', '.join(liveness.live_run_ids)} is still non-terminal, so a"
                f" run of {item.id} is live; the hold stands."
            ),
        )
    if live_dispatch_lock(repo=repo, work_item_id=item.id) is not None:
        return valve_refusal(
            aid=aid,
            wid=item.id,
            err="dispatch-lock-held",
            msg=(
                f"{action} refused: a live process holds the dispatch-scoped ownership lock of"
                f" {item.id}; the hold stands."
            ),
        )
    return None
