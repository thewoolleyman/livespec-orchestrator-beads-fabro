"""The evidenced causal supersession: the one way an UNMET obligation is renamed.

PURE. `contracts.md` section "Required result, budget and progress epoch" fixes
what the event must carry and how far it may reach: "An evidenced causal
supersession is a typed event that replaces an unmet obligation's required
result. It is accepted ONLY through `set_next_action` or `append_handoff`
carrying it, and it MUST be recorded as a `plan-progress-event` of kind
`supersession` before the pointer changes. It MUST name the superseded
obligation's canonical result identity and epoch, the replacement required
result, exactly one cause, the evidence identifiers that cause requires, and the
writer."

WHY ANYTHING IS OWED HERE AT ALL. Renaming an unmet obligation is otherwise
refused outright — "a new label, repair-child milestone, acknowledgment or
changed-approach claim cannot evade expiry" — and that refusal is what makes a
FALSELY DERIVED obligation permanent: a plan-level step derived while a carrier
of one of the plan's own assertions was still open cannot be re-aimed at that
carrier, so the only rest state left is a human pointer. Measured 2026-10-22 on
plan epic `bd-ib-fyozyd`, whose derived proof obligation refused every await on
the open carrier its carrier map named.

THE CAUSE SET IS CLOSED, AND THIS BUILD VERIFIES ONE OF ITS MEMBERS. Three causes
are ratified — `misderived`, `disposed` and `subsumed` — and each "is accepted
only when its evidence verifies against the ledger or the forge at write time".
`SUPERSESSION_CAUSES` is the ratified set, so a later implementer sees the whole
grammar rather than inferring it; what this build can VERIFY is `misderived`, and
a cause whose evidence it cannot verify is refused by the clause's own rule that
a cause whose evidence does not verify must be refused. That is fail-closed in
the only direction available: before this module existed, every one of the three
was refused.

WHAT `misderived` TURNS ON, as spec v198 widened it. Two conditions, and BOTH are
required: the superseded obligation was written by a DERIVATION — the
`plan-resume` or `plan-archive` actor, "not by a writer that named it" — and it
"names a plan-level step (`proof`, `review` or `archive`) while a work-item
carrier named by the epic's latest carrier-map scope event was not closed, so the
step could not honestly be taken". The evidence is the deriving operation
identity, "which MUST resolve to that epoch's recorded transition", together with
"the carrier's recorded status history showing it not closed at that transition's
recorded time".

"THAT EPOCH" IS THE DERIVATION'S OWN, NOT THE CHAIN HEAD'S. The epoch the
supersession NAMES is graded against the head below, as the ordinary staleness
check on the write; the deriving identity then resolves at whatever epoch its own
payload records. Requiring the two to agree is what made a retained obligation
permanently unsupersedable — `_plan_supersession_evidence` carries the
measurement.

AND WHAT IT DELIBERATELY DOES NOT TURN ON. "A derived obligation whose step could
legitimately be taken when it was derived is not misderived, however it was
written or whatever its target or carriers show now" — so a carrier that was
CLOSED when the derivation was recorded does not qualify, and neither does a
carrier that has closed SINCE. The second is the same rule the clause states
separately: "The replacement result MUST be unsatisfied when the supersession is
written; a supersession naming an already satisfied replacement MUST be refused,
so no cause can trade an unmet obligation for satisfied-result advancement."

WHY THE REPLACEMENT IS TIED TO THE CARRIER THE EVIDENCE NAMES. The evidence for
this arm IS a carrier, and the step the plan actually owes is to wait for that
carrier to close. A replacement free to name anything else would make the carrier
evidence for a rename it has nothing to do with — which is a label with a
verified footnote attached, the shape the whole clause exists to refuse.

WHY EVERY UNREADABLE INSTANT REFUSES. The derivation-time question is whether the
carrier was open at a recorded instant, and an instant neither side can compare
establishes nothing. A supersession is irreversible — it replaces an obligation
and the original cannot be recovered from the pointer — so the conservative
answer is the only safe one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from livespec_orchestrator_beads_fabro.commands._plan_archive import PLAN_ARCHIVE_ACTOR
from livespec_orchestrator_beads_fabro.commands._plan_carrier_gate import CLOSED_STATUS
from livespec_orchestrator_beads_fabro.commands._plan_next_action import PLAN_RESUME_ACTOR
from livespec_orchestrator_beads_fabro.commands._plan_result_reference import (
    parse_result_reference,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import (
    ItemStatusTarget,
    ResultReference,
)
from livespec_orchestrator_beads_fabro.commands._plan_supersession_provenance import (
    provenance_detail,
)
from livespec_orchestrator_beads_fabro.effects import IsoDatetimeParseFailure, parse_iso_datetime

__all__: list[str] = [
    "CAUSE_DISPOSED",
    "CAUSE_MISDERIVED",
    "CAUSE_SUBSUMED",
    "DERIVATION_ACTORS",
    "EVENT_SUPERSESSION",
    "SUPERSESSION_CAUSES",
    "CarrierEvidence",
    "CausalSupersession",
    "DerivingTransition",
    "SupersessionEvidence",
    "SupersessionRefusal",
    "validate_causal_supersession",
]

CAUSE_MISDERIVED = "misderived"
CAUSE_DISPOSED = "disposed"
CAUSE_SUBSUMED = "subsumed"

# The RATIFIED closed set, in the order the clause enumerates it. Closed is the
# point: an open grammar admits a typo and an invented label on identical
# evidence, and an invented label is exactly what "a new label ... cannot evade
# expiry" names.
SUPERSESSION_CAUSES: tuple[str, ...] = (CAUSE_MISDERIVED, CAUSE_DISPOSED, CAUSE_SUBSUMED)

# The two reserved author literals a DERIVATION signs its own writes with. They
# are imported rather than respelled, because a respelling here would admit a
# supersession against an obligation no derivation wrote — the one condition the
# `misderived` cause rests on — while reading perfectly correct.
DERIVATION_ACTORS: tuple[str, ...] = (PLAN_RESUME_ACTOR, PLAN_ARCHIVE_ACTOR)

# The progress-event kind this write commits, which is what lets an operator
# reading the epic's obligation history tell a renamed obligation from an
# advanced one.
EVENT_SUPERSESSION = "supersession"


@dataclass(frozen=True, kw_only=True)
class CausalSupersession:
    """What one write must NAME to replace an unmet obligation.

    `open_carrier_id` is the evidence identifier the `misderived` cause's
    plan-level arm requires: the work-item carrier the epic's latest carrier-map
    scope event names and whose openness made the derived step undeliverable.
    """

    superseded_result_identity: str
    previous_epoch: int
    cause: str
    deriving_operation_id: str
    open_carrier_id: str
    writer: str


@dataclass(frozen=True, kw_only=True)
class DerivingTransition:
    """The recorded transition a supersession's operation identity resolves to.

    `required_result` is the obligation that transition WROTE, and
    `later_results` is what every transition recorded AFTER it: together they
    establish the named derivation as the one that wrote the obligation standing
    now. A later result the reader could not place is `None`, which has no
    canonical identity and so compares unequal to every obligation — the
    fail-closed answer, since a transition whose recorded result is unreadable
    cannot be shown to have retained anything.

    Neither carries a default. An absent one reads as a transition that recorded
    nothing, and an absent `later_results` reads as a derivation nothing
    followed, so a caller that forgot either field would refuse every
    supersession or admit one it should not — each retiring the cause in silence.
    """

    author: str
    recorded_at: str
    required_result: object
    later_results: tuple[object, ...]


@dataclass(frozen=True, kw_only=True)
class CarrierEvidence:
    """One named carrier's recorded status history, as the ledger holds it.

    `closed_at` is the instant the ledger records the closure, when it records
    one. A record that is closed and carries NO instant is read as closed at an
    unknowable time, which refuses — see `_closed_by` for why that is the
    conservative direction rather than a tolerance.
    """

    mapped: bool
    status: str
    closed_at: str | None


@dataclass(frozen=True, kw_only=True)
class SupersessionEvidence:
    """Every ledger reading one cause's verification needs, taken by the caller.

    `plan_level` is whether the SUPERSEDED obligation's own target is the plan
    epic itself, which is what makes it a `proof`, `review` or `archive` step:
    the authority chain records no pointer kind, so the target is the only thing
    a reader of the obligation has. Both other fields are `None` for a reading
    that could not be taken at all, which refuses.
    """

    deriving: DerivingTransition | None
    carrier: CarrierEvidence | None
    plan_level: bool


@dataclass(frozen=True, kw_only=True)
class SupersessionRefusal:
    """Why one claimed supersession is not an EVIDENCED causal supersession."""

    detail: str


def validate_causal_supersession(
    *,
    supersession: CausalSupersession,
    evidence: SupersessionEvidence | None,
    prior_identity: str,
    current_epoch: int,
    replacement: object,
) -> SupersessionRefusal | None:
    """Admit only a supersession whose named cause verifies against the ledger.

    The checks run in the clause's own order, and the order matters for the
    REPORT rather than the verdict: a reader told that its carrier is already
    closed, about a supersession that also named the wrong epoch, would fix the
    carrier and meet the same refusal again.
    """
    if supersession.superseded_result_identity != prior_identity:
        return SupersessionRefusal(
            detail=f"a supersession must name the unmet obligation {prior_identity}"
        )
    if supersession.previous_epoch != current_epoch:
        return SupersessionRefusal(
            detail=(
                f"the supersession names previous epoch {supersession.previous_epoch},"
                f" but the chain stands at epoch {current_epoch}"
            )
        )
    if supersession.cause not in SUPERSESSION_CAUSES:
        return SupersessionRefusal(
            detail=(
                f"supersession cause {supersession.cause!r} is not one of"
                f" {SUPERSESSION_CAUSES}; a label, an acknowledgment, approach prose"
                " and elapsed time never qualify"
            )
        )
    if supersession.cause != CAUSE_MISDERIVED:
        return SupersessionRefusal(
            detail=(
                f"supersession cause {supersession.cause!r} is ratified, but this build"
                " verifies evidence for"
                f" {CAUSE_MISDERIVED!r} only, so its evidence does not verify"
            )
        )
    if evidence is None:
        return SupersessionRefusal(detail="the supersession's evidence could not be read")
    return _misderived_refusal(
        supersession=supersession,
        evidence=evidence,
        prior_identity=prior_identity,
        replacement=replacement,
    )


def _misderived_refusal(
    *,
    supersession: CausalSupersession,
    evidence: SupersessionEvidence,
    prior_identity: str,
    replacement: object,
) -> SupersessionRefusal | None:
    """Grade the plan-level arm of the `misderived` cause, one condition at a time."""
    if not evidence.plan_level:
        return SupersessionRefusal(
            detail=(
                "the superseded obligation's own target is not the plan epic, so it names"
                " no plan-level step this build can establish was misderived"
            )
        )
    if evidence.deriving is None:
        return SupersessionRefusal(
            detail=(
                f"the deriving operation {supersession.deriving_operation_id!r} resolves to"
                " no recorded transition of this plan"
            )
        )
    provenance = provenance_detail(
        operation_id=supersession.deriving_operation_id,
        recorded_result=evidence.deriving.required_result,
        later_results=evidence.deriving.later_results,
        prior_identity=prior_identity,
    )
    if provenance is not None:
        return SupersessionRefusal(detail=provenance)
    if evidence.deriving.author not in DERIVATION_ACTORS:
        return SupersessionRefusal(
            detail=(
                f"the obligation was written by {evidence.deriving.author!r}, which is no"
                f" derivation: the cause is accepted only for {DERIVATION_ACTORS}"
            )
        )
    return _carrier_refusal(
        supersession=supersession,
        evidence=evidence,
        deriving=evidence.deriving,
        replacement=replacement,
    )


def _carrier_refusal(
    *,
    supersession: CausalSupersession,
    evidence: SupersessionEvidence,
    deriving: DerivingTransition,
    replacement: object,
) -> SupersessionRefusal | None:
    """Grade the carrier half: mapped, open then, open now, and named by the replacement."""
    carrier = evidence.carrier
    if carrier is None or not carrier.mapped:
        return SupersessionRefusal(
            detail=(
                f"carrier {supersession.open_carrier_id!r} is not named by the epic's latest"
                " carrier-map scope event, so its state is evidence about nothing this plan"
                " asserted"
            )
        )
    if carrier.status == CLOSED_STATUS:
        return _closed_carrier_refusal(
            supersession=supersession, carrier=carrier, deriving=deriving
        )
    if not _replacement_names(replacement=replacement, carrier_id=supersession.open_carrier_id):
        return SupersessionRefusal(
            detail=(
                "the replacement result must be the closure of the carrier the evidence"
                f" names, {supersession.open_carrier_id!r}: a carrier is evidence for"
                " waiting on that carrier and for nothing else"
            )
        )
    return None


def _closed_carrier_refusal(
    *,
    supersession: CausalSupersession,
    carrier: CarrierEvidence,
    deriving: DerivingTransition,
) -> SupersessionRefusal:
    """Say WHICH of the two closed readings refuses, because the remedies differ.

    A carrier already closed when the derivation was recorded means the step
    could legitimately have been taken, so nothing was misderived. A carrier
    that has closed SINCE means the replacement result is already satisfied,
    which no cause may trade an unmet obligation for. Reporting either as the
    other sends its reader to the wrong question.
    """
    if _closed_by(closed_at=carrier.closed_at, instant=deriving.recorded_at):
        return SupersessionRefusal(
            detail=(
                f"carrier {supersession.open_carrier_id!r} was already closed when the"
                f" derivation was recorded at {deriving.recorded_at}, so the derived step"
                " could legitimately have been taken"
            )
        )
    return SupersessionRefusal(
        detail=(
            f"carrier {supersession.open_carrier_id!r} is closed now, so the replacement"
            " result is already satisfied and no obligation may be traded for it"
        )
    )


def _closed_by(*, closed_at: str | None, instant: str) -> bool:
    """Whether a closure is recorded at or before one instant, failing CLOSED.

    An absent or uncomparable closure instant answers TRUE, which routes to the
    "already closed when it was derived" refusal. That is the conservative
    direction: the opposite would report a carrier whose closure nobody can date
    as having closed AFTER the derivation, which is the arm that ADMITS a
    supersession, and a supersession cannot be undone.
    """
    if closed_at is None:
        return True
    closed = _utc(value=closed_at)
    derived = _utc(value=instant)
    if closed is None or derived is None:
        return True
    return closed <= derived


def _utc(*, value: str) -> datetime | None:
    """One instant as an aware UTC datetime, or `None` when it is not one.

    `None` rather than a naive value, because comparing an aware instant with a
    naive one raises: an instant this reader cannot place on the UTC timeline is
    one it must not compare at all.
    """
    parsed = parse_iso_datetime(text=value.replace("Z", "+00:00"))
    if isinstance(parsed, IsoDatetimeParseFailure):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return None
    return parsed


def _replacement_names(*, replacement: object, carrier_id: str) -> bool:
    """Whether the replacement result is that carrier's own closed status."""
    parsed = parse_result_reference(value=replacement)
    if not isinstance(parsed, ResultReference):
        return False
    target = parsed.target
    if not isinstance(target, ItemStatusTarget):
        return False
    return target.item_id == carrier_id and target.status == CLOSED_STATUS
