"""Rest an already-satisfied item in `acceptance`, with its claim released.

A run that ended as already satisfied (`_dispatcher_already_satisfied`) merged nothing
and opened no pull request, so the post-merge acceptance valve does not apply. The item
rests in `acceptance` with its factory claim released, where `needs-attention` surfaces
it, and one ledger comment names the route by which its Proof of Done can still be
obtained. No ledger failure raises, and each is journaled. A refused rest leaves the item
active and claimed, so it is reported as a failed outcome at its own stage rather than as
the green ending; a refused comment only loses the route text, so the rest still stands.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro import store
from livespec_orchestrator_beads_fabro.commands._dispatcher_already_satisfied import (
    ALREADY_SATISFIED_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_lifecycle_writes import (
    write_work_item_status_and_reconcile,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.io import write_stderr

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
    from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile

__all__: list[str] = [
    "ALREADY_SATISFIED_COMMENT_FAILED_STAGE",
    "ALREADY_SATISFIED_REST_FAILED_STAGE",
    "rest_already_satisfied",
]

ALREADY_SATISFIED_REST_FAILED_STAGE = "already-satisfied-rest-failed"
ALREADY_SATISFIED_COMMENT_FAILED_STAGE = "already-satisfied-comment-failed"

_ACCEPTANCE_STATUS = "acceptance"
_LEDGER_ERRORS = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


def rest_already_satisfied(
    *,
    repo: Path,
    outcome: DispatchOutcome,
    journal: JournalFile,
) -> DispatchOutcome:
    """Journal the ending, release the claim and rest the item in `acceptance`.

    RETURNS the outcome the dispatch reports: the ending itself when the item rested, and a
    failed outcome at `already-satisfied-rest-failed` when the rest could not be written.
    """
    journal.append(
        record={
            "stage": ALREADY_SATISFIED_STAGE,
            "work_item_id": outcome.work_item_id,
            "dispatch_base": outcome.already_satisfied_base,
            "fabro_run_id": outcome.fabro_run_id,
        }
    )
    config = store_config(repo=repo)
    rested = attempt(
        action=lambda: write_work_item_status_and_reconcile(
            path=config,
            item_id=outcome.work_item_id,
            status=_ACCEPTANCE_STATUS,
            clear_assignee=True,
        ),
        exceptions=_LEDGER_ERRORS,
    )
    if isinstance(rested, AttemptFailure):
        journal.append(
            record={
                "stage": ALREADY_SATISFIED_REST_FAILED_STAGE,
                "work_item_id": outcome.work_item_id,
                "error": str(rested.error),
            }
        )
        _ = write_stderr(
            text=f"already-satisfied: {outcome.work_item_id} could not be rested in acceptance\n"
        )
        return replace(
            outcome,
            status="failed",
            stage=ALREADY_SATISFIED_REST_FAILED_STAGE,
            detail=(
                f"already satisfied, but {outcome.work_item_id} could not be rested in "
                f"acceptance, so it is still active and claimed: {rested.error}; "
                f"{outcome.detail}"
            ),
        )
    commented = attempt(
        action=lambda: store.append_work_item_comment(
            path=config, work_item_id=outcome.work_item_id, body=outcome.detail
        ),
        exceptions=_LEDGER_ERRORS,
    )
    if isinstance(commented, AttemptFailure):
        journal.append(
            record={
                "stage": ALREADY_SATISFIED_COMMENT_FAILED_STAGE,
                "work_item_id": outcome.work_item_id,
                "error": str(commented.error),
            }
        )
    return outcome
