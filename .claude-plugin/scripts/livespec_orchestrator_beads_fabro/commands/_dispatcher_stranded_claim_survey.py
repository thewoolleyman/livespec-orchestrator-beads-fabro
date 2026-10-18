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
ladder's own. The forge is asked only about an ABSENT run, because the
merged-pull-request question is one of the absent-run release's preconditions
and nothing else reads it. The attribution holds are graded FIRST, through the
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
    observe_merged_pull_request,
    observe_owner_liveness,
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
    graded = grade_claim(
        measurements=ClaimMeasurements(
            attributed=attributed,
            run_state=run_state,
            owner_liveness=observe_owner_liveness(repo=inputs.repo, work_item_id=item.id),
            # The forge is asked ONLY about an absent run, because only the
            # absent-run branch of the ladder consults it. The pass-through
            # value on the other branches is never read there.
            forge=(
                observe_merged_pull_request(
                    repo=inputs.repo, runner=inputs.runner, work_item_id=item.id
                )
                if run_state == RUN_ABSENT
                else FORGE_NO_MERGED_PR
            ),
            predecessor=HISTORY_NO_PREDECESSOR,
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
