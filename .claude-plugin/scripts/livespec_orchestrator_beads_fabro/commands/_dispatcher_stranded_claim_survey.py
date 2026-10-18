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

THE ATTRIBUTION HOLDS ARE GRADED FIRST, through the same `attribute_claim` the
full ladder exposes, so a claim stamped by another host costs this host no lock
reads, no forge call and no `fabro inspect` — which is what keeps a fleet of
hosts from each paying for every other host's claims. What each remaining claim
is MEASURED on, and which of those readings are skipped, lives in
`_dispatcher_stranded_claim_measure`.

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
    ACTION_ABSENT_RUN_REPEATED,
    ACTION_TERMINAL_COMPLETION,
    ATTRIBUTION_PENDING_REMEDY,
    HOLD_ATTRIBUTION_PENDING,
    AttributedClaim,
    ClaimHold,
    attribute_claim,
    grade_claim,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_measure import (
    ClaimReadInputs,
    FactoryInventory,
    measure_claim,
    predecessor_run_id,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_observe import (
    journal_records_or_none,
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
    records = journal_records_or_none(journal_path=inputs.journal.path)
    measured = measure_claim(
        inputs=ClaimReadInputs(
            repo=inputs.repo,
            journal=inputs.journal,
            runner=inputs.runner,
            records=records,
        ),
        work_item_id=item.id,
        attributed=attributed,
        inventory=inventory,
    )
    graded = grade_claim(measurements=measured.measurements)
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
                predecessor_run_id(records=records or (), work_item_id=item.id)
                if graded.action == ACTION_ABSENT_RUN_REPEATED
                else None
            ),
            terminal=measured.terminal if graded.action == ACTION_TERMINAL_COMPLETION else None,
        ),
        now_iso=inputs.now_iso,
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
