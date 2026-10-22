"""The SATISFIED advance: derive the plan's next step and persist it.

A satisfied required result makes the pointer STALE, and the clause's remedy is
not a report — the resume "advances to the next step the plan prose derives from
the ledger (the next ready child, the proof leg, the review, the archive),
recording a new obligation under the ordinary rules". Reporting alone leaves the
stale pointer standing, so the next resume re-observes the same satisfied result
and re-derives the same step for ever, and nothing downstream of this session can
see where the plan now stands.

WHY A PLAN-LEVEL LEG IS GATED ON THE EPIC'S CARRIER MAP AND NOT ONLY ON ITS
CHILDREN. The plan Definition-of-Done clause records which child, or which
plan-level proof, carries each plan assertion ONLY in the epic's carrier-map
scope event, and a plan's Proof of Done cannot be true while a work-item carrier
of one of its assertions is still open. The child check alone cannot see such a
carrier: a carrier filed in a sibling tenant under the cross-tenant execution
mirror is no child of this epic by either linkage mechanism, so the check comes
back empty and the plan-level leg is derived against work nobody has done.
Measured 2026-10-22 on plan epic `bd-ib-fyozyd`, every carrier of which is
cross-tenant: nine carriers of ordinal 6 sat open across five sibling tenants
while the resume advanced to `proof:capture:bd-ib-fyozyd`.

AND WHY THE DERIVATION IS WHERE THAT GATE BELONGS, rather than a correction
applied afterwards. Once a plan-level obligation is PERSISTED it cannot be
re-aimed: replacing an unmet obligation is refused without evidenced causal
supersession, and the `await` a human would reach for names another tenant's
item, so the only state left is a human pointer. The gate therefore runs before
the pointer is written, and `_plan_supersession` is what unlocks the epics whose
records already carry a falsely derived step.

WHY THE PLAN-LEVEL LEG IS DERIVED FROM THE SATISFIED POINTER'S OWN KIND. Once
every child is disposed the ledger's only record of how far the plan has come is
the pointer the plan last wrote: a satisfied `proof` pointer means the proof leg
landed, so the review is next. A derivation reading the forge instead would put a
network round trip on the resume path and would still answer from records this
same pointer summarizes.

WHY EACH LEG'S REQUIRED RESULT IS A LEDGER RECORD THAT LEG PRODUCES. The plan
proof record and the completeness-review evidence are both comments on the epic,
and archiving closes it, so each obligation is the step's own observable outcome.
That is not the forbidden substitution of a marker for a verified proof: the
marker is the result of POSTING the record, while whether the posted record is
evidence is the archive gate's own grading, which `plan_proof_leg` performs. A
`verified_proof` reference cannot be derived here in any case — it must name the
build identity and assertion identifiers, and the release this plan will be
proved against does not exist yet.

WHY THE NEW BUDGET KEEPS THE PLAN'S OWN DEADLINE. A satisfied result "permits
advancing to a new result and budget", so the obligation is new — fresh epoch,
handoff count back to zero. The wall clock is NOT new: the plan's recorded
deadline is the only deadline evidence the ledger holds, and minting a longer one
here would let each satisfied step silently postpone a deadline the maintainer
set, which every neighbouring clause forbids. If that deadline has already
passed, the next resume reports expiry — which is the correct reading of a plan
that has run out of time, not a fault in this advance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._store_ready_dwell import utc_now_iso
from livespec_orchestrator_beads_fabro.commands._plan_carrier_gate import (
    OpenCarrier,
    carrier_status_target,
    first_open_carrier,
)
from livespec_orchestrator_beads_fabro.commands._plan_completeness_evidence import (
    PLAN_COMPLETENESS_REVIEW_PREFIX,
)
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    ARCHIVE_KIND,
    AWAIT_KIND,
    IMPL_KIND,
    PLAN_RESUME_ACTOR,
    PROOF_KIND,
    REVIEW_KIND,
    NextAction,
    ResumeDirective,
    dispatchable_action_id,
    set_next_action,
)
from livespec_orchestrator_beads_fabro.commands._plan_proof_record import (
    PLAN_PROOF_RECORD_TITLE,
)
from livespec_orchestrator_beads_fabro.commands._plan_ready_child import next_ready_child_id
from livespec_orchestrator_beads_fabro.commands._plan_result_repository import (
    project_repository_identity,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
        ResultObservation,
    )
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "AdvanceRequest",
    "advance_after_satisfied_result",
]

_DEADLINE_FIELD = "deadline"
_MAX_HANDOFFS_FIELD = "max_handoffs"


@dataclass(frozen=True, kw_only=True)
class _Carried:
    """What every derived pointer carries forward from the satisfied one.

    The plan's own repository identity and its `deadline`/`max_handoffs` are read
    ONCE and threaded through, so no derived leg can resolve a different
    repository or a different wall clock from its siblings.
    """

    epic_id: str
    repo: str
    budget: dict[str, object]


@dataclass(frozen=True, kw_only=True)
class AdvanceRequest:
    """All inputs to one satisfied-pointer advance across the module boundary.

    `ruling_identity` is resolved by the CALLER and passed in rather than read
    here, because the ruling is the resume's own authority question and reading
    it twice would be two readings of one timeline that cannot be shown to agree.
    """

    config: StoreConfig
    epic_id: str
    action: NextAction
    observation: ResultObservation
    findings: tuple[str, ...]
    unattended: bool
    ruling_identity: str | None


def advance_after_satisfied_result(*, request: AdvanceRequest) -> ResumeDirective:
    """Report the stale pointer, persist the derived step, and decide who takes it."""
    stale = (
        f"next_action stale: observed {request.observation.target} satisfied via"
        f" {request.observation.evidence}"
    )
    derived = _derived_action(request=request)
    if derived is None:
        return _terminal(
            request=request,
            reason=f"{stale}; no further plan step is derivable from the ledger",
        )
    refusal = set_next_action(
        config=request.config,
        epic_id=request.epic_id,
        action=derived,
        session=PLAN_RESUME_ACTOR,
        now=utc_now_iso(),
    )
    if refusal is not None:
        # The advance is the clause's remedy, so a REFUSED replacement write is
        # reported rather than ridden past: taking a step whose obligation never
        # landed would leave the plan advancing against no recorded budget at all.
        return _terminal(
            request=request,
            reason=f"{stale}; the derived replacement pointer was refused: {refusal.detail}",
        )
    identifier = dispatchable_action_id(action=derived)
    reason = f"{stale}; derived next ledger step {identifier}"
    if not request.unattended and request.ruling_identity is None:
        # Reconciliation runs FIRST, but it does not AUTHORIZE. An attended
        # resume with no current ruling is owed its picker, and the derived step
        # is what that picker defaults to.
        return ResumeDirective(
            ask=True,
            next_action=None,
            reason=reason,
            findings=(*request.findings, reason),
            picker_default=identifier,
            observation=request.observation,
        )
    if request.ruling_identity is not None:
        reason = f"{reason} under {request.ruling_identity}"
    return ResumeDirective(
        ask=False,
        next_action=identifier,
        reason=reason,
        findings=(*request.findings, reason),
        observation=request.observation,
    )


def _terminal(*, request: AdvanceRequest, reason: str) -> ResumeDirective:
    return ResumeDirective(
        ask=False,
        next_action=None,
        reason=reason,
        findings=(*request.findings, reason),
        observation=request.observation,
    )


def _derived_action(*, request: AdvanceRequest) -> NextAction | None:
    """The next step this plan owes, as a complete five-key pointer.

    THE CARRIER GATE SITS BETWEEN THE CHILD CHECK AND THE PLAN-LEVEL LEG, and
    that position is the whole of its correctness. The epic's own ready children
    are the work the plan tracks DIRECTLY, so a ready child is the next step
    whatever the carrier map says; and the plan-level legs each assert something
    about the whole Definition of Done, so none of them may be derived while a
    carrier of one of its assertions is still open. Asking the gate FIRST would
    hold a plan's own ready child behind a sibling tenant's carrier, and asking
    it after the plan-level leg had been chosen would be asking it too late.
    """
    carried = _carried(request=request)
    child = next_ready_child_id(config=request.config, epic_id=request.epic_id)
    if child is not None:
        return _pointer(
            kind=IMPL_KIND,
            ref=child,
            text=f"Implement plan child {child}.",
            result={"item_status": {"item_id": child, "status": "closed"}},
            carried=carried,
        )
    plan_level = _plan_level_action(action=request.action, carried=carried)
    if plan_level is None:
        return None
    return _carrier_gated(request=request, carried=carried, plan_level=plan_level)


def _carrier_gated(
    *,
    request: AdvanceRequest,
    carried: _Carried,
    plan_level: NextAction,
) -> NextAction:
    """Wait on an open carrier, or let the derived plan-level step stand.

    The TERMINAL state is deliberately settled before this is reached: a
    satisfied `archive` pointer derives no successor at all, so a plan whose
    archive has landed is not held open by a carrier map nobody will restate.

    THE WAIT IS THE ONE DERIVED STEP WHOSE OBLIGATION DOES NOT NAME THE PLAN'S
    OWN REPOSITORY, and the exception is the same fact that makes every other leg
    name it: an obligation names the repository its own TARGET lives in, and this
    target is a work-item in the carrier's tenant rather than the plan epic.
    Stamping the plan's repository here would make the obligation unobservable on
    the very next resume, which is the state `_plan_result_plan_owned` records
    the cost of.
    """
    carrier: OpenCarrier | None = first_open_carrier(config=request.config, epic_id=request.epic_id)
    if carrier is None:
        return plan_level
    return _pointer(
        kind=AWAIT_KIND,
        ref=f"item:{carrier.item_id}",
        text=f"Wait for plan carrier {carrier.item_id} to close in {carrier.repo}.",
        result=carrier_status_target(carrier=carrier),
        carried=carried,
        repo=carrier.repo,
    )


def _plan_level_action(*, action: NextAction, carried: _Carried) -> NextAction | None:
    """The plan-level leg a disposed plan owes next, read off the satisfied kind."""
    epic_id = carried.epic_id
    if action.kind == ARCHIVE_KIND:
        return None
    if action.kind == REVIEW_KIND:
        return _pointer(
            kind=ARCHIVE_KIND,
            ref=epic_id,
            text=f"Archive plan {epic_id} through archive_thread.",
            result={"item_status": {"item_id": epic_id, "status": "closed"}},
            carried=carried,
        )
    if action.kind == PROOF_KIND:
        return _pointer(
            kind=REVIEW_KIND,
            ref=epic_id,
            text=f"Commission the independent completeness review of {epic_id}.",
            result={
                "item_comment": {
                    "item_id": epic_id,
                    "marker": PLAN_COMPLETENESS_REVIEW_PREFIX,
                }
            },
            carried=carried,
        )
    return _pointer(
        kind=PROOF_KIND,
        ref=f"capture:{epic_id}",
        text=f"Capture the plan Proof of Done record for {epic_id}.",
        result={"item_comment": {"item_id": epic_id, "marker": PLAN_PROOF_RECORD_TITLE}},
        carried=carried,
    )


def _pointer(
    *,
    kind: str,
    ref: str,
    text: str,
    result: dict[str, object],
    carried: _Carried,
    repo: str | None = None,
) -> NextAction:
    """One derived pointer, with a FRESH obligation on the plan's own deadline.

    The epoch is derived deterministically from the epic and the step it names,
    so a retried advance recovers the same obligation identity rather than
    minting a second one for the same step.

    `repo` OVERRIDES the plan's own repository and defaults to not overriding it,
    because exactly one derived step targets something outside the plan's tenant:
    the carrier wait. Defaulting the other way would make every leg state its own
    repository, and the one that stated it wrongly would be the one that locks a
    plan (`_plan_result_plan_owned`).
    """
    return NextAction(
        kind=kind,
        ref=ref,
        text=text,
        required_result={"repo": carried.repo if repo is None else repo, **result},
        budget={
            **carried.budget,
            "epoch": f"{carried.epic_id}:{kind}:{ref}",
            "handoff_count": 0,
        },
    )


def _carried(*, request: AdvanceRequest) -> _Carried:
    """What the derived pointer carries forward, read ONCE for every leg.

    THE REPOSITORY IS THE PLAN'S OWN AND NEVER THE SATISFIED OBLIGATION'S. Every
    step derivable here is a step against the PLAN: the proof, review and archive
    legs each target the plan epic, and the `impl` leg targets a child read out of
    the plan's own tenant. The satisfied obligation's repository is a fact about
    the leg that just LANDED — legitimately a sibling tenant, where a carrier
    child was filed under the cross-tenant execution mirror — so carrying it
    forward stamps a repository the derived step's own target does not live in.

    That mis-stamping is terminal rather than cosmetic, which is why it is read
    from this project rather than from the observation the reader already
    resolved. The next resume reads the derived obligation against the wrong
    tenant and reports it UNOBSERVABLE; dispatch is withheld while a required
    result is unobservable, and replacing an unobservable obligation is refused by
    design — so the plan locks behind the pointer for its whole budget, with no
    sanctioned write able to correct it. Measured 2026-10-20 on plan epic
    `bd-ib-fyozyd`, whose satisfied `await` named a `livespec-dev-tooling` item.

    The two budget fields are carried through AS FOUND, not validated, and a
    recorded budget that is not an object at all yields both as absent. A
    malformed one is refused by `set_next_action`, which is the single authority
    on a pointer's admissibility, and that refusal names the first field it
    could not admit — whereas a second grade here would either duplicate that
    ladder or, worse, silently derive a pointer the writer then rejects for a
    reason this module had decided not to mention.
    """
    recorded = request.action.budget
    typed: dict[str, Any] = cast("dict[str, Any]", recorded) if isinstance(recorded, dict) else {}
    return _Carried(
        epic_id=request.epic_id,
        repo=project_repository_identity(config=request.config),
        budget={
            _DEADLINE_FIELD: typed.get(_DEADLINE_FIELD),
            _MAX_HANDOFFS_FIELD: typed.get(_MAX_HANDOFFS_FIELD),
        },
    )
