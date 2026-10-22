"""Reading the ledger evidence one claimed causal supersession rests on.

The IMPURE companion of `_plan_supersession`, which is the decision and is pure
over the readings this module takes. The split is the usual one in this tree, and
it matters here for the same reason it does at the carrier gate: the refusal
ladder is a pure function of three facts, so every arm of it — including the ones
a healthy ledger cannot produce — is exercisable without a store.

THE THREE READINGS, and why each is a reading rather than something the caller
could supply. The DERIVING TRANSITION comes from the epic's own
`plan-progress-event` comments, because the clause requires the named operation
identity to "resolve to that epoch's recorded transition" and it is that
comment's header that records WHO committed it and WHEN — the canonical payload
is rendered before the comment exists and can carry neither.

THAT EPOCH IS THE DERIVATION'S OWN, NEVER THE CHAIN HEAD'S, and the distinction
is the whole of `bd-ib-4hznqp`. "That epoch" in the clause is the epoch the
derivation wrote the obligation at, which the deriving event's own payload
records; the epoch the SUPERSESSION names is the chain head, because
`validate_causal_supersession` keeps the ordinary staleness check on the write
itself. Requiring the two to agree made a misderived obligation supersedable only
while NOTHING had been written since it was derived — so the human pointer the
derivation gate prescribes, or any handoff, made it permanently unsupersedable.
Measured 2026-10-22 on plan epic `bd-ib-fyozyd`, derived at epoch 99 -> 100 and
retained to epoch 101 nine minutes later: naming 101 resolved no transition, and
naming 100 was refused as stale.

The CARRIER's status
history comes from the carrier's OWN tenant, resolved through the same carrier
tenancy the gate uses, because a carrier of a real plan is routinely
cross-tenant and this project's ledger has no record of it. And whether the
superseded obligation is a PLAN-LEVEL step is read off its own target, through
`names_plan_epic`, because the authority chain records no pointer kind at all.

WHY A SUPERSESSION IS GRADED AGAINST THE CHAIN-HELD OBLIGATION AND NOT THE
POINTER. The pointer is a PROJECTION every sanctioned writer rewrites wholesale,
so an obligation read from it is one any writer could have restated; the chain is
the durable authority, and `_plan_tracked_write` already reads it to decide
continuity. Reading the same obligation from the same place is what keeps the
supersession's own `prior_identity` and this module's `plan_level` answer from
being about two different obligations.

WHY EVERY UNREADABLE READING IS `None` RATHER THAN A FILLED-IN DEFAULT. A
supersession replaces an obligation irreversibly, so a reading nobody could take
must refuse rather than resolve to the value that would admit it. `None` for the
deriving transition says the operation identity resolved to nothing; `None` for
the carrier says its own tenant could not be reached or holds no such record.
Both are refusals in `_plan_supersession`, and neither is distinguishable there
from the other's absence — which is why each is a separate field rather than one
collapsed verdict.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._plan_carrier_gate import plan_carrier_ids
from livespec_orchestrator_beads_fabro.commands._plan_carrier_tenancy import (
    carrier_tenancy,
    repository_for_carrier,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import (
    read_progress_events,
)
from livespec_orchestrator_beads_fabro.commands._plan_obligation import obligation_of
from livespec_orchestrator_beads_fabro.commands._plan_result_plan_owned import names_plan_epic
from livespec_orchestrator_beads_fabro.commands._plan_result_repository import result_store_config
from livespec_orchestrator_beads_fabro.commands._plan_supersession import (
    CarrierEvidence,
    CausalSupersession,
    DerivingTransition,
    SupersessionEvidence,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain_head import ChainHead
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "supersession_evidence",
]

# The EXPECTED-error surface one cross-tenant record read can raise. Catching
# exactly this set — never a blanket except — is what keeps an unreachable,
# unconfigured or absent tenant an unreadable carrier rather than a traceback
# escaping a sanctioned write.
_LEDGER_ERRORS: tuple[type[Exception], ...] = (
    BeadsConnectionError,
    BeadsCommandError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
)
_STATUS_FIELD = "status"
_CLOSED_AT_FIELD = "closed_at"


def supersession_evidence(
    *,
    config: StoreConfig,
    epic_id: str,
    supersession: CausalSupersession | None,
    head: ChainHead,
) -> SupersessionEvidence | None:
    """Take every ledger reading the named cause's verification needs.

    `None` when the write carries no supersession at all, which is every
    ordinary write: the readings below cost two tenant round trips and a comment
    scan, and spending them on a write that claims nothing would put them on the
    whole plan path.
    """
    if supersession is None:
        return None
    obligation = obligation_of(authority=head.authority)
    return SupersessionEvidence(
        deriving=_deriving(
            config=config,
            epic_id=epic_id,
            operation_id=supersession.deriving_operation_id,
        ),
        carrier=_carrier(config=config, epic_id=epic_id, carrier_id=supersession.open_carrier_id),
        plan_level=obligation is not None
        and names_plan_epic(required_result=obligation.required_result, epic_id=epic_id),
    )


def _deriving(
    *,
    config: StoreConfig,
    epic_id: str,
    operation_id: str,
) -> DerivingTransition | None:
    """The recorded transition one operation identity resolves to, at its own epoch.

    The IDENTITY alone selects it, because the epoch the clause asks it to
    resolve at is the one that transition itself recorded — see the module
    docstring for what requiring the chain head's epoch here cost.

    An event whose canonical payload did not parse resolves NOTHING. The payload
    is where the obligation that transition WROTE is recorded, and that is the
    fact the `misderived` cause's verification rests on, so a comment this reader
    can see the operation identity in but not the payload of establishes nothing
    about the derivation it names.
    """
    client = make_beads_client(config=config)
    for event in read_progress_events(client=client, epic_id=epic_id):
        if event.operation_id != operation_id or event.payload is None:
            continue
        return DerivingTransition(author=event.author, recorded_at=event.recorded_at)
    return None


def _carrier(*, config: StoreConfig, epic_id: str, carrier_id: str) -> CarrierEvidence | None:
    """One named carrier's recorded status history, read from its OWN tenant.

    `mapped` is answered first and from this project's own ledger, so a carrier
    the epic's latest carrier-map event does not name costs no cross-tenant read
    at all — and reports as unmapped rather than as unreadable, which is the
    honest finding about a carrier nobody claimed.
    """
    mapped = carrier_id in plan_carrier_ids(config=config, epic_id=epic_id)
    record = _carrier_record(config=config, carrier_id=carrier_id)
    if record is None:
        return None
    status = record.get(_STATUS_FIELD)
    closed_at = record.get(_CLOSED_AT_FIELD)
    if not isinstance(status, str) or status == "":
        return None
    return CarrierEvidence(
        mapped=mapped,
        status=status,
        closed_at=closed_at if isinstance(closed_at, str) and closed_at != "" else None,
    )


def _carrier_record(*, config: StoreConfig, carrier_id: str) -> dict[str, Any] | None:
    """The carrier's own ledger record, or `None` when it cannot be read.

    Resolved through the SAME carrier tenancy the gate reads a carrier's status
    through, so the repository this reading is taken from is the repository the
    gate would have waited on. A separately-derived resolution is how one
    carrier comes to be graded against two tenants.
    """
    tenancy = carrier_tenancy(config=config)
    repository = repository_for_carrier(tenancy=tenancy, carrier_id=carrier_id)
    if repository is None:
        return None
    resolved = result_store_config(repository=repository)
    if resolved is None:
        return None
    read = attempt(
        action=lambda: make_beads_client(config=resolved).show_issue(issue_id=carrier_id),
        exceptions=_LEDGER_ERRORS,
    )
    if isinstance(read, AttemptFailure):
        return None
    return dict(read)
