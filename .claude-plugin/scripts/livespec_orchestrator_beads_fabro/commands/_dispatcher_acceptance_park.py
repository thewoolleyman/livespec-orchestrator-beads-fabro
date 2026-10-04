"""The park disposition: rest a merged item in `acceptance` and record why.

Split out of `_dispatcher_completion` along its cohesion seam once the park
acquired a LEDGER WRITE of its own. That module decides WHICH disposition a
verdict routes to; this one performs the single disposition that writes nothing to
the item's status and everything to its record. The RENDERING of that record is
pure and lives in `_dispatcher_acceptance_parking_record`.

THE LEDGER COMMENT IS NOT A DUPLICATE OF THE JOURNAL RECORD. The journal lives in
the `tmp/` tree of whichever host ran the dispatch, so an operator reading the
item sees the park and nothing about its cause — which is the whole finding this
module answers. The comment is written LAST, after the park is already journaled
and surfaced, because it is the one step that can fail on a ledger the other two
never touch.

EVERY FAILURE IS JOURNALED AND NONE RAISES, for the reason the pointer write fails
soft: the park has already happened and the item's work has already merged, so an
unreadable or unwritable comment sidecar must not turn a parked item into a
crashed dispatch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_parking_record import (
    parking_record,
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
from livespec_orchestrator_beads_fabro.store import (
    append_work_item_comment,
    read_work_item_comments,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_ai import (
        AcceptancePassResult,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
    from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile

__all__: list[str] = [
    "PARKED_STAGE",
    "PARKING_RECORD_STAGE",
    "UNCHANGED_PARKING_RECORD_STAGE",
    "park_in_acceptance",
    "record_acceptance_park",
]

PARKED_STAGE = "acceptance-parked"
PARKING_RECORD_STAGE = "acceptance-parking-record"
UNCHANGED_PARKING_RECORD_STAGE = "acceptance-parking-record-unchanged"
_ERROR_STAGE = "acceptance-parking-record-error"
_LEDGER_ERRORS = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


def park_in_acceptance(
    *,
    repo: Path,
    item_id: str,
    policy: str,
    acceptance_pass: AcceptancePassResult,
    outcome: DispatchOutcome,
    journal: JournalFile,
) -> None:
    """Park a merged item in `acceptance` for a human — recorded, journaled, surfaced.

    `acceptance_pass.absent_evidence` names the leg(s) the AI pass could not
    observe, which is empty for an advisory PASS/FAIL park and non-empty for a
    NEEDS_ATTENTION park; the journal record carries it so the parked item's
    attention surface can say WHY it cannot be judged rather than only that it is
    waiting.
    """
    journal.append(
        record={
            "stage": PARKED_STAGE,
            "work_item_id": item_id,
            "policy": policy,
            "advisory": policy == "human-only",
            "acceptance_verdict": acceptance_pass.verdict,
            "absent_evidence": list(acceptance_pass.absent_evidence),
        }
    )
    surface_line = (
        f"SURFACE: work-item {item_id} merged + live; parked in acceptance under "
        f"acceptance_policy {policy} — awaits a human's final acceptance "
        f"before done (no release with zero verification; the AI pass verdict was "
        f"{acceptance_pass.verdict}).\n"
    )
    _ = write_stderr(text=surface_line)
    record_acceptance_park(
        repo=repo,
        item_id=item_id,
        policy=policy,
        result=acceptance_pass,
        pull_request=outcome.pr_number,
        journal=journal,
    )


def record_acceptance_park(
    *,
    repo: Path,
    item_id: str,
    policy: str,
    result: AcceptancePassResult,
    pull_request: int | None,
    journal: JournalFile,
) -> None:
    """Append this park's record to the item, unless an identical one is standing."""
    record = parking_record(
        item_id=item_id, policy=policy, result=result, pull_request=pull_request
    )
    config = store_config(repo=repo)
    existing = attempt(
        action=lambda: read_work_item_comments(path=config, work_item_id=item_id),
        exceptions=_LEDGER_ERRORS,
    )
    if isinstance(existing, AttemptFailure):
        _journal_error(journal=journal, item_id=item_id, failure=existing)
        return
    if any(comment.text.startswith(record.key_line) for comment in existing):
        journal.append(
            record={
                "stage": UNCHANGED_PARKING_RECORD_STAGE,
                "work_item_id": item_id,
                "acceptance_verdict": record.verdict,
                "pending": [leg.name for leg in record.pending],
            }
        )
        return
    written = attempt(
        action=lambda: append_work_item_comment(
            path=config, work_item_id=item_id, body=record.render()
        ),
        exceptions=_LEDGER_ERRORS,
    )
    if isinstance(written, AttemptFailure):
        _journal_error(journal=journal, item_id=item_id, failure=written)
        return
    journal.append(
        record={
            "stage": PARKING_RECORD_STAGE,
            "work_item_id": item_id,
            "acceptance_verdict": record.verdict,
            "acceptance_policy": policy,
            "pending": [leg.name for leg in record.pending],
            "legs": [
                {"name": leg.name, "observed": leg.observed, "detail": leg.detail}
                for leg in record.legs
            ],
        }
    )


def _journal_error(*, journal: JournalFile, item_id: str, failure: AttemptFailure) -> None:
    journal.append(
        record={
            "stage": _ERROR_STAGE,
            "work_item_id": item_id,
            "reason": type(failure.error).__name__,
        }
    )
