"""Taking the measurements one attributed claim is graded on.

Split out of `_dispatcher_stranded_claim_survey` by cohesion. That module owns
WHO is surveyed and what becomes of each verdict; this owns the gathering the
verdict is computed from — which readings are taken, in what order, and which
are skipped because the ladder would not consult them.

EVERY EXPENSIVE READING IS CONDITIONAL, and the conditions are the ladder's own
rather than a cost heuristic. The forge and the dispatch history are read only
for an ABSENT run, and the failure evidence only for a FAILED one, because
those are the only branches of the ladder that consult them. The pass-through
values the other branches receive are never read there, so a reading skipped
is a reading no verdict depended on.

THE PREDECESSOR RUN ID IS READ OFF THE LAUNCH STAMPS, not off the release row.
Those stamp rows are the only rows that name a run id at launch: the newest is
this claim's own and the one before it is its predecessor's. Fewer than two
means no predecessor run was ever recorded — a dispatch that died before it
learned one — which the comment STATES rather than omitting, because printing a
run id belonging to nothing is the one thing worse than saying none was
recorded.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_grade import (
    FORGE_NO_MERGED_PR,
    HISTORY_NO_PREDECESSOR,
    RUN_ABSENT,
    RUN_FAILED,
    AttributedClaim,
    ClaimMeasurements,
    run_state_from_inventory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_observe import (
    observe_merged_pull_request,
    observe_owner_liveness,
    observe_predecessor_history,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_terminal import (
    TerminalObservation,
    TerminalReadContext,
    observe_terminal_outcome,
)

__all__: list[str] = [
    "ClaimReadInputs",
    "FactoryInventory",
    "MeasuredClaim",
    "measure_claim",
    "predecessor_run_id",
]

_RUN_STAMP_STAGE = "dispatch-run-stamp"
_RUN_ID_KEY = "run_id"
_STAGE_KEY = "stage"
_WORK_ITEM_KEY = "work_item_id"
# How many launch stamps an item needs before one of them names a PREDECESSOR
# run: the newest is this claim's own, so a second is the earliest that can be
# somebody else's.
_STAMPS_BEFORE_A_PREDECESSOR = 2


@dataclass(frozen=True, kw_only=True)
class FactoryInventory:
    """One declared factory's answer about its own runs, as this pass read it.

    `surveyed` is NOT `bool(status_kinds)`: a factory that answered with an
    empty inventory WAS surveyed, and that answer is what makes every claim
    naming it positively absent. A factory that could not be reached, or that
    declares no server target, was not — and its claims are held as
    `factory-unobservable` rather than released.
    """

    name: str
    server_url: str | None
    fabro_bin: str
    surveyed: bool
    status_kinds: dict[str, str | None]


@dataclass(frozen=True, kw_only=True)
class ClaimReadInputs:
    """The seams every measurement goes through, for one surveyed claim."""

    repo: Path
    journal: JournalFile
    runner: CommandRunner
    records: tuple[Mapping[str, object], ...] | None


@dataclass(frozen=True, kw_only=True)
class MeasuredClaim:
    """The graded inputs, with the terminal reading kept beside them.

    The observation rides along rather than being re-taken by whoever applies
    it: the grading needed it to decide whether the failure evidence was
    readable at all, and a second `fabro inspect` could answer about a record
    the first reading already judged.
    """

    measurements: ClaimMeasurements
    terminal: TerminalObservation | None


def measure_claim(
    *,
    inputs: ClaimReadInputs,
    work_item_id: str,
    attributed: AttributedClaim,
    inventory: FactoryInventory,
) -> MeasuredClaim:
    """Take every measurement the ladder will read for this claim."""
    run_state = run_state_from_inventory(
        surveyed=inventory.surveyed,
        status_kinds=inventory.status_kinds,
        run_id=attributed.run_id,
    )
    terminal = (
        observe_terminal_outcome(
            context=TerminalReadContext(
                repo=inputs.repo,
                journal=inputs.journal,
                runner=inputs.runner,
                records=() if inputs.records is None else inputs.records,
                fabro_bin=inventory.fabro_bin,
                factory_name=inventory.name,
                factory_server_url=inventory.server_url,
            ),
            work_item_id=work_item_id,
            run_id=attributed.run_id,
        )
        if run_state == RUN_FAILED
        else None
    )
    return MeasuredClaim(
        measurements=ClaimMeasurements(
            attributed=attributed,
            run_state=run_state,
            owner_liveness=observe_owner_liveness(repo=inputs.repo, work_item_id=work_item_id),
            forge=(
                observe_merged_pull_request(
                    repo=inputs.repo, runner=inputs.runner, work_item_id=work_item_id
                )
                if run_state == RUN_ABSENT
                else FORGE_NO_MERGED_PR
            ),
            predecessor=(
                observe_predecessor_history(records=inputs.records, work_item_id=work_item_id)
                if run_state == RUN_ABSENT
                else HISTORY_NO_PREDECESSOR
            ),
            terminal_evidence_readable=run_state != RUN_FAILED or terminal is not None,
        ),
        terminal=terminal,
    )


def predecessor_run_id(
    *,
    records: tuple[Mapping[str, object], ...],
    work_item_id: str,
) -> str | None:
    """The run id of the dispatch BEFORE the one holding this claim."""
    stamped = [
        record
        for record in records
        if record.get(_STAGE_KEY) == _RUN_STAMP_STAGE and record.get(_WORK_ITEM_KEY) == work_item_id
    ]
    if len(stamped) < _STAMPS_BEFORE_A_PREDECESSOR:
        return None
    previous = stamped[-2].get(_RUN_ID_KEY)
    return previous if isinstance(previous, str) and previous != "" else None
