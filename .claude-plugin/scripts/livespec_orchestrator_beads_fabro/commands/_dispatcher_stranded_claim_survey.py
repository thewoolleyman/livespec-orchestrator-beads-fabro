"""Surveying the CLAIM half of the run-reconciliation invariant.

`reconcile_runs` walks each factory's runs and terminates the ones the ledger
disowns. That is run-centric, and it is why a claim whose run is GONE had
nothing to join to: the pass returned `held: []` and `reconciled: []` for an
item sitting `active` with assignee `fabro` and no run anywhere, and every
recovery was a hand `drive --action move:<id>:ready`. This module joins the
other way round — claims to runs — so a claim with no run is exactly the
population it finds rather than the one it cannot see.

IT RIDES THE SURVEY THE PASS ALREADY TOOK. The factory reading is the same
`fabro ps -a --json` listing the orphan join read, handed in as a
`FactoryInventory` per declared factory. Two listings a moment apart disagree
about any run that ended between them, so a second reading would let the orphan
lane and the claim lane describe the same factory two ways; and `ps -a`
enumerates terminal runs, which is what makes a run id absent from an answered
listing POSITIVELY absent rather than merely unseen.

EVERY EXPENSIVE MEASUREMENT IS CONDITIONAL, and the conditions are the grading
ladder's own. The forge and the predecessor history are read only for an ABSENT
run, because only that branch of the ladder consults either. The attribution
holds are graded FIRST, through the
same `attribute_claim` the full ladder exposes, so a claim stamped by another
host costs this host no lock reads and no forge call — which is what keeps a
fleet of hosts from each paying for every other host's claims.

A MARKED CLAIM IS NOT SURVEYED, and an UNREADABLE marker is treated as marked.
`rework:pending` and a `merge-hold:` label each describe an item that is
`active` with no live lock BY DESIGN, which is the exact shape this survey
reads as stranded. A hold reading that fails leaves the item out too: surveying
it could release a deliberate operator window, and skipping it costs one pass.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro._store_dispatch_claim import ClaimStamp, claim_row_for
from livespec_orchestrator_beads_fabro.commands._dispatcher_current_merge_hold import (
    read_current_merge_hold,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_grade import (
    ACTION_ABSENT_RUN_REPEATED,
    ATTRIBUTION_PENDING_REMEDY,
    FORGE_NO_MERGED_PR,
    HISTORY_NO_PREDECESSOR,
    HOLD_ATTRIBUTION_PENDING,
    RUN_ABSENT,
    AttributedClaim,
    ClaimHold,
    ClaimMeasurements,
    attribute_claim,
    grade_claim,
    run_state_from_inventory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_observe import (
    journal_records_or_none,
    observe_merged_pull_request,
    observe_owner_liveness,
    observe_predecessor_history,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_records import (
    HeldClaim,
    RecoveredClaim,
    hold_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_recovery import (
    ClaimRecoveryRequest,
    recover_claim,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "FactoryInventory",
    "StrandedClaimInputs",
    "StrandedClaimSurvey",
    "survey_stranded_claims",
]

_ACTIVE_STATUS = "active"
_FABRO_ASSIGNEE = "fabro"
_MERGE_HOLD_UNHELD = "unheld"
_RUN_STAMP_STAGE = "dispatch-run-stamp"
_RUN_ID_KEY = "run_id"
_STAGE_KEY = "stage"
_WORK_ITEM_KEY = "work_item_id"
# How many launch stamps an item needs before one of them names a PREDECESSOR
# run: the newest is this claim's own, so a second is the earliest that can be
# somebody else's.
_STAMPS_BEFORE_A_PREDECESSOR = 2

_LEDGER_READ_ERRORS: tuple[type[Exception], ...] = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


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
class StrandedClaimInputs:
    """Everything the claim survey reads or writes through.

    `dry_run` withholds EVERY effect rather than only the ledger ones: the
    projection's whole claim is that running it changes nothing, and a dry pass
    that journalled its holds would leave records an operator could not tell
    apart from a live pass's.
    """

    repo: Path
    items: tuple[WorkItem, ...]
    journal: JournalFile
    runner: CommandRunner
    inventories: tuple[FactoryInventory, ...]
    this_host: str
    now_iso: str
    dry_run: bool = False


@dataclass(frozen=True, kw_only=True)
class StrandedClaimSurvey:
    """What one claim survey recovered and what it left alone."""

    recovered: tuple[RecoveredClaim, ...]
    held: tuple[HeldClaim, ...]


def survey_stranded_claims(*, inputs: StrandedClaimInputs) -> StrandedClaimSurvey:
    """Grade every dispatch claim in the ledger, recovering only the proven ones."""
    by_name = {inventory.name: inventory for inventory in inputs.inventories}
    recovered: list[RecoveredClaim] = []
    held: list[HeldClaim] = []
    for item in inputs.items:
        if not _surveyable(inputs=inputs, item=item):
            continue
        outcome = _survey_one(inputs=inputs, item=item, by_name=by_name)
        if isinstance(outcome, HeldClaim):
            held.append(outcome)
            if not inputs.dry_run:
                inputs.journal.append(record=hold_journal_record(held=outcome))
            continue
        recovered.append(outcome)
    return StrandedClaimSurvey(recovered=tuple(recovered), held=tuple(held))


def _surveyable(*, inputs: StrandedClaimInputs, item: WorkItem) -> bool:
    if item.status != _ACTIVE_STATUS or item.assignee != _FABRO_ASSIGNEE:
        return False
    if item.rework_pending:
        return False
    return read_current_merge_hold(repo=inputs.repo, work_item_id=item.id) == _MERGE_HOLD_UNHELD


def _survey_one(
    *,
    inputs: StrandedClaimInputs,
    item: WorkItem,
    by_name: dict[str, FactoryInventory],
) -> RecoveredClaim | HeldClaim:
    stamp = _claim_stamp(repo=inputs.repo, work_item_id=item.id)
    named = None if stamp is None else stamp.factory_name
    attributed = attribute_claim(
        stamp=stamp,
        declared_factory=named is not None and named in by_name,
        this_host=inputs.this_host,
    )
    if isinstance(attributed, ClaimHold):
        return _held_claim(item=item, stamp=stamp, reason=attributed.reason)
    return _measure_and_act(
        inputs=inputs,
        item=item,
        attributed=attributed,
        inventory=by_name[attributed.factory_name],
    )


def _measure_and_act(
    *,
    inputs: StrandedClaimInputs,
    item: WorkItem,
    attributed: AttributedClaim,
    inventory: FactoryInventory,
) -> RecoveredClaim | HeldClaim:
    run_state = run_state_from_inventory(
        surveyed=inventory.surveyed,
        status_kinds=inventory.status_kinds,
        run_id=attributed.run_id,
    )
    records = journal_records_or_none(journal_path=inputs.journal.path)
    graded = grade_claim(
        measurements=ClaimMeasurements(
            attributed=attributed,
            run_state=run_state,
            owner_liveness=observe_owner_liveness(repo=inputs.repo, work_item_id=item.id),
            # Both absent-run readings are asked ONLY of an absent run,
            # because only the absent-run branch of the ladder consults them.
            # The pass-through values on the other branches are never read
            # there, and the forge call is the one round trip this survey can
            # spend per claim.
            forge=(
                observe_merged_pull_request(
                    repo=inputs.repo, runner=inputs.runner, work_item_id=item.id
                )
                if run_state == RUN_ABSENT
                else FORGE_NO_MERGED_PR
            ),
            predecessor=(
                observe_predecessor_history(records=records, work_item_id=item.id)
                if run_state == RUN_ABSENT
                else HISTORY_NO_PREDECESSOR
            ),
        )
    )
    if isinstance(graded, ClaimHold):
        return _held_claim(item=item, stamp=attributed.stamp, reason=graded.reason)
    if inputs.dry_run:
        return _projected(
            item=item, attributed=attributed, inventory=inventory, action=graded.action
        )
    return recover_claim(
        repo=inputs.repo,
        journal=inputs.journal,
        request=ClaimRecoveryRequest(
            item=item,
            run_id=attributed.run_id,
            factory_name=inventory.name,
            factory_server_url=inventory.server_url,
            action=graded.action,
            predecessor_run_id=(
                # `records or ()` rather than an optional parameter: this arm is
                # reachable only on the repeat route, which the ladder reaches
                # only when the predecessor reading was NOT `unavailable` — so
                # an unreadable journal cannot arrive here, and a guard for it
                # would be a branch no pass can take.
                _predecessor_run_id(records=records or (), work_item_id=item.id)
                if graded.action == ACTION_ABSENT_RUN_REPEATED
                else None
            ),
        ),
    )


def _projected(
    *,
    item: WorkItem,
    attributed: AttributedClaim,
    inventory: FactoryInventory,
    action: str,
) -> RecoveredClaim:
    """What a live pass WOULD do to this claim, with no effect performed.

    The item's CURRENT status is reported rather than the status the route
    would land it on: a projection that claimed the destination would read, in
    a `--json` payload, exactly like a live pass that had already written it.
    """
    return RecoveredClaim(
        work_item_id=item.id,
        run_id=attributed.run_id,
        factory_name=inventory.name,
        factory_server_url=inventory.server_url,
        reason=action,
        route=action,
        status=item.status,
        effects_written=(),
    )


def _predecessor_run_id(
    *,
    records: tuple[Mapping[str, object], ...],
    work_item_id: str,
) -> str | None:
    """The run id of the dispatch BEFORE the one holding this claim.

    Read off the launch STAMP rows, which are the only rows that name a run id
    at launch: the newest is this claim's own run and the one before it is its
    predecessor's. Fewer than two means no predecessor run was ever recorded —
    a dispatch that died before it learned one — which the comment STATES
    rather than omitting; the alternative is printing a run id belonging to
    nothing.
    """
    stamped = [
        record
        for record in records
        if record.get(_STAGE_KEY) == _RUN_STAMP_STAGE and record.get(_WORK_ITEM_KEY) == work_item_id
    ]
    if len(stamped) < _STAMPS_BEFORE_A_PREDECESSOR:
        return None
    previous = stamped[-2].get(_RUN_ID_KEY)
    return previous if isinstance(previous, str) and previous != "" else None


def _claim_stamp(*, repo: Path, work_item_id: str) -> ClaimStamp | None:
    """One item's claim stamp, with every read failure reported as none.

    An unreadable row is reason 1's own wording — "the item carries no READABLE
    run stamp" — so collapsing a ledger fault onto `None` reports the condition
    the clause names rather than inventing a fifteenth.
    """
    row = attempt(
        action=lambda: claim_row_for(path=store_config(repo=repo), work_item_id=work_item_id),
        exceptions=_LEDGER_READ_ERRORS,
    )
    return None if isinstance(row, AttemptFailure) else row.stamp


def _held_claim(*, item: WorkItem, stamp: ClaimStamp | None, reason: str) -> HeldClaim:
    return HeldClaim(
        work_item_id=item.id,
        run_id=None if stamp is None else stamp.run_id,
        factory_name=None if stamp is None else stamp.factory_name,
        factory_server_url=None if stamp is None else stamp.factory_server,
        dispatching_host=None if stamp is None else stamp.dispatching_host,
        hold_reason=reason,
        remedy=ATTRIBUTION_PENDING_REMEDY if reason == HOLD_ATTRIBUTION_PENDING else None,
    )
