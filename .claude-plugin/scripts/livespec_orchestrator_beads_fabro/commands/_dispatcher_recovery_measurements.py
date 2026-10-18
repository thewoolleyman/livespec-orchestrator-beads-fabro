"""Which of recovery routing's measurements could not be taken, and what each is called.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work" puts one rule above every other
grading step: "Routes are graded in the order listed; the first that holds is the
route, and an unobservable or unreadable measurement at any step routes `held`."
This module answers the one question that rule turns on — which of the resume's
measurements went unanswered.

PURE, AND THE TEXT IS BORROWED RATHER THAN WRITTEN. Each refusal is rendered by
the arm of `_dispatcher_resume_refusals` that owns the measurement, and carried
here verbatim. That is not economy: the clause requires a held item's record to
carry the measurement's own account, and two renderings of one measurement are
free to drift — the journal would then say something the refusal an operator reads
does not.

WHY EACH MEASUREMENT HAS A SHORT NAME BESIDE THAT TEXT. The detail is prose an
operator reads; the name is a token they grep the journal for, and it names the
READ that failed rather than the route it stopped. An operator triaging a repeated
hold needs to know whether the forge or the factory is the thing to look at, and
the four reads fail independently.

WHY THE CONDITIONS MIRROR THE ARMS RATHER THAN RE-DERIVING THEM. Each predicate
below is the exact condition under which its arm renders an unobservable refusal,
including the SHORT-CIRCUIT between the two forge reads: `anchor_refusals` returns
on an unobservable listing before it looks at the record list, so asking about the
records when the listing itself went unanswered would report a read that was never
attempted. Where a predicate and its arm disagree the arm wins, because the arm is
what the operator is shown — so the arms are called, not reimplemented, and the
predicates only decide WHICH name to attach.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    RecoveryMeasurement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals import (
    ResumeObservation,
    anchor_refusals,
    head_refusals,
    liveness_refusals,
)

__all__: list[str] = [
    "MEASUREMENT_FACTORY_RUN_LIVENESS",
    "MEASUREMENT_FORGE_PULL_REQUEST",
    "MEASUREMENT_FORGE_PULL_REQUEST_HEAD",
    "MEASUREMENT_FORGE_PULL_REQUEST_RECORDS",
    "MEASUREMENT_PRESERVED_WORK",
    "unobservable_measurements",
]

# The four reads recovery routing takes through the resume's own gather, plus the
# fifth the fallback arm takes on its own. One token per read, because they fail
# independently and an operator triaging a repeated hold acts on which one failed.
MEASUREMENT_FORGE_PULL_REQUEST = "forge-pull-request"
MEASUREMENT_FORGE_PULL_REQUEST_RECORDS = "forge-pull-request-records"
MEASUREMENT_FORGE_PULL_REQUEST_HEAD = "forge-pull-request-head"
MEASUREMENT_FACTORY_RUN_LIVENESS = "factory-run-liveness"
MEASUREMENT_PRESERVED_WORK = "preserved-work"


def unobservable_measurements(*, observation: ResumeObservation) -> tuple[RecoveryMeasurement, ...]:
    """Every measurement this observation could not take, in the ladder's own order.

    EMPTY means every read answered — which is the precondition for grading a
    route at all, and deliberately not the same as "every read said no".
    """
    found: list[RecoveryMeasurement] = []
    if not observation.forge_observed:
        found.append(
            _measured(
                name=MEASUREMENT_FORGE_PULL_REQUEST,
                refusals=anchor_refusals(observation=observation),
            )
        )
    elif observation.pull_request is not None and not observation.records_observed:
        found.append(
            _measured(
                name=MEASUREMENT_FORGE_PULL_REQUEST_RECORDS,
                refusals=anchor_refusals(observation=observation),
            )
        )
    if _head_unobservable(observation=observation):
        found.append(
            _measured(
                name=MEASUREMENT_FORGE_PULL_REQUEST_HEAD,
                refusals=head_refusals(observation=observation),
            )
        )
    if not observation.liveness_observed:
        found.append(
            _measured(
                name=MEASUREMENT_FACTORY_RUN_LIVENESS,
                refusals=liveness_refusals(observation=observation),
            )
        )
    return tuple(found)


def _head_unobservable(*, observation: ResumeObservation) -> bool:
    """Whether the forge named a pull request but not the head it carries.

    All three conditions, because that is exactly when `head_refusals` renders
    its unobservable arm: with no anchor there is no head to compare against, and
    with no pull request there is nothing to have asked about — so a predicate
    naming only the absent head would report a read nobody took.
    """
    return (
        observation.anchor_head is not None
        and observation.pull_request is not None
        and observation.pull_request_head is None
    )


def _measured(*, name: str, refusals: tuple[str, ...]) -> RecoveryMeasurement:
    """One named measurement, carrying the refusal its own arm rendered.

    JOINED rather than indexed, which keeps this total: each arm renders exactly
    one refusal under these conditions, so the join is that one string — and an
    arm that rendered none would yield an empty detail rather than raising from
    inside the routing step that was about to hold the item.
    """
    return RecoveryMeasurement(name=name, detail=" ".join(refusals))
