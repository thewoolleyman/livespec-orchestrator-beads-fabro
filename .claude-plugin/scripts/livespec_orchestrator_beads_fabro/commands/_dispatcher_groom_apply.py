"""File an apply run's approved cut HOST-SIDE, where the ledger credential is.

The APPLY half of the ratified two-phase groom cut, and the mirror of
`_dispatcher_groom_park`'s propose half. The propose phase publishes a DRAFT
and the Dispatcher records it on the ledger; the apply phase publishes a
FILING PLAN and the Dispatcher executes it. Both publications ride the one
channel a terminated run has -- its needs-human sentinel line -- and both
ledger writes happen on the side that legitimately holds the tenant password.

WHY THE FILING MOVED HERE. A factory sandbox is deliberately given no beads
credential, so the apply node could never complete the filing the contract
asks of the apply PHASE; `_groom_filing_plan`'s docstring carries the full
argument and the measurement. What matters at this seam is the consequence:
nothing in this module runs inside a sandbox, and nothing it calls reaches for
a credential wrapper that only exists on the host.

WHY THE DISPATCH CLAIM IS RELEASED BEFORE THE FILING. The regroom-out
disposition is `regroom.close_regroomed_out`, which refuses a target that is
not `backlog` -- the front-end's precondition, because the front-end grooms a
backlog item in place. An apply-dispatched item is `active` under its dispatch
claim by the time this seam runs, so the claim is ended FIRST and the item
returns to the `backlog` it was groomed out of, which is exactly where a
failed filing should leave it: re-groomable, unclaimed, with its approved
draft still on the record. The close follows immediately and is what the
contract calls the terminal disposition of the original.

WHY EVERY REFUSAL IS JOURNALED AND NONE OF THEM RAISES. This seam runs inside
the Dispatcher's post-run sequence, after the run is already dead. An
exception here would abort the sequence that rests the item somewhere a human
can find it, so a filing that cannot proceed is journaled and reported as
NOT filed, leaving the ordinary needs-human escalation to run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._store_groom_approval import GroomApproval
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._groom_filing_plan import parse_groom_filing_plan
from livespec_orchestrator_beads_fabro.commands.groom import GroomResult, file_approved_slices
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
    GroomApprovalRequiredError,
    GroomDraftError,
    GroomExitRefusedError,
    GroomTargetNotBacklogError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.regroom import BACKLOG_STATUS
from livespec_orchestrator_beads_fabro.store import update_work_item_status

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import JournalWriter
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "GROOM_CUT_FILED_STAGE",
    "GROOM_CUT_REFUSED_STAGE",
    "file_groom_plan",
]

GROOM_CUT_FILED_STAGE = "groom-cut-filed"
GROOM_CUT_REFUSED_STAGE = "groom-cut-refused"

# Everything a filing can legitimately fail on: the plan's own shape, the
# filing seam's four modelled refusals, the ledger this seam reads and writes,
# and the process boundary underneath it. `BeadsCredentialMissingError` is
# listed for the same reason the rest are -- a Dispatcher run outside its
# credential wrapper must journal a refusal rather than abort the post-run
# sequence -- and NOT because this seam is expected to hit it.
_REFUSALS = (
    GroomDraftError,
    GroomApprovalRequiredError,
    GroomExitRefusedError,
    GroomTargetNotBacklogError,
    WorkItemNotFoundError,
    BeadsCredentialMissingError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    OSError,
)


def file_groom_plan(
    *,
    repo: Path,
    item: WorkItem,
    text: str,
    variant: str,
    run_id: str,
    journal: JournalWriter,
) -> bool:
    """File the published cut and regroom the original out; report whether it landed.

    `True` says the approved factory slices now exist in the ledger and the
    original closed against them, so the terminated run needs no human. `False`
    says nothing was filed and the caller should escalate as it would for any
    other needs-human termination — the item keeps its approved draft, so a
    re-dispatch re-enters the apply phase rather than starting over.
    """
    filed = attempt(
        action=lambda: _file_groom_plan(repo=repo, item=item, text=text),
        exceptions=_REFUSALS,
    )
    if isinstance(filed, AttemptFailure):
        journal.append(
            record={
                "stage": GROOM_CUT_REFUSED_STAGE,
                "work_item_id": item.id,
                "workflow_name": variant,
                "run_id": run_id,
                "reason": type(filed.error).__name__,
                "detail": str(filed.error),
            }
        )
        return False
    journal.append(
        record={
            "stage": GROOM_CUT_FILED_STAGE,
            "work_item_id": item.id,
            "workflow_name": variant,
            "run_id": run_id,
            "filed_slice_ids": list(filed.filed_slice_ids),
            "spec_change_slices": [candidate.title for candidate in filed.spec_change_slices],
            "cross_repo_slices": [entry.minted_id for entry in filed.cross_repo_slices],
        }
    )
    return True


def _file_groom_plan(*, repo: Path, item: WorkItem, text: str) -> GroomResult:
    """Parse, release the claim, then file — in that order, and only that order.

    The parse comes first so a malformed plan is refused with the item still
    `active` under its claim, which is a state the ordinary needs-human
    escalation already knows how to rest. Only once the whole cut is
    representable is the claim released, because a released claim on an
    unfilable plan is a `backlog` item nobody is driving.

    The filing itself is ONE call, and its internal ordering is the seam's:
    `file_approved_slices` resolves the whole cut before its first write, files
    each approved factory slice through the same intake routing the capture
    front-end uses, and only then closes the original against the ids it filed.
    So the regroom target cannot close ahead of its replacements.
    """
    plan = parse_groom_filing_plan(text=text)
    config = store_config(repo=repo)
    if item.status != BACKLOG_STATUS:
        update_work_item_status(
            path=config, item_id=item.id, status=BACKLOG_STATUS, clear_assignee=True
        )
    return file_approved_slices(
        path=config,
        regroom_item_id=item.id,
        local_repo=repo.name,
        approval=GroomApproval(approver=plan.approver, route=plan.route),
        slices=list(plan.slices),
    )
