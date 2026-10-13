"""The durable obligation a plan epic's authority chain carries, and its exact limits.

`contracts.md` section "Required result, budget and progress epoch" puts the
deadline and the handoff ceiling beyond every writer's reach: "Routine handoffs,
supervisor handoffs and direct set_next_action calls MUST NOT reset the deadline
or count." This module is the reading of that obligation out of the chain's
`AuthorityState`, the two exact limits it expires at, and the projection the
`next_action` pointer carries back.

WHY THE OBLIGATION IS READ FROM THE CHAIN RATHER THAN FROM THE POINTER. The
pointer is one metadata object every sanctioned writer rewrites WHOLESALE, so a
budget living there is a budget the writer can hand itself a new value for — and
the defect was invisible, because the rewritten pointer is perfectly well-formed
whether it preserved the deadline or extended it. The chain's authority can only
move through a transition the Beads server serializes, so preserving the
obligation becomes a property of where it is stored rather than a rule each
writer remembers.

WHY THE PROJECTION IS DERIVED AND NEVER ACCEPTED. `projected_action` rebuilds the
pointer's `required_result` and `budget` from the COMMITTED authority, discarding
whatever the candidate asked for. A writer that merely validated the candidate
and then stored it would pass every test whose fixture happened to ask for the
original values; deriving the stored value from the authority is what makes the
candidate's request unable to matter.

WHY EXPIRY IS A SEPARATE READING FROM THE REFUSAL IT CAUSES. `obligation_expiry`
NAMES which of the two limits was reached and says nothing about what to do, and
the clause needs both halves apart: "An expired wall clock MUST be visible even
when no new handoff is written", so a resume reports the expiry without writing,
while a writer turns the same reading into a refusal. One function answering
both would force the read-only surface to ask a question phrased as a mutation.

THE HANDOFF LIMIT IS TESTED BEFORE THE CLOCK, and the order is reportable rather
than arbitrary: "the first limit reached expires the obligation", and a count
that has reached its ceiling is a fact about work already accepted, whereas the
clock keeps moving. Reporting the count first means a reader whose deadline ALSO
passed still learns the limit that actually stopped the work.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro.commands._plan_continuation import instant_expired

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import AuthorityState
    from livespec_orchestrator_beads_fabro.commands._plan_next_action import NextAction

__all__: list[str] = [
    "BUDGET_DEADLINE_FIELD",
    "BUDGET_EPOCH_FIELD",
    "BUDGET_HANDOFF_COUNT_FIELD",
    "BUDGET_MAX_HANDOFFS_FIELD",
    "EXPIRY_DEADLINE",
    "EXPIRY_HANDOFFS",
    "CandidateBudget",
    "Obligation",
    "budget_projection",
    "candidate_budget",
    "obligation_expiry",
    "obligation_of",
    "projected_action",
]

EXPIRY_HANDOFFS = "handoffs"
EXPIRY_DEADLINE = "deadline"

BUDGET_DEADLINE_FIELD = "deadline"
BUDGET_MAX_HANDOFFS_FIELD = "max_handoffs"
BUDGET_HANDOFF_COUNT_FIELD = "handoff_count"
BUDGET_EPOCH_FIELD = "epoch"


@dataclass(frozen=True, kw_only=True)
class Obligation:
    """One unmet required result, with the two limits that bound work on it.

    `original_deadline` is the FIRST deadline the obligation was ever recorded
    under and never a later one, which is the whole guarantee this type exists to
    carry. `consumed_handoffs` counts ACCEPTED handoffs only — a direct pointer
    write leaves it alone.
    """

    required_result: object
    original_deadline: str
    max_handoffs: int
    consumed_handoffs: int


@dataclass(frozen=True, kw_only=True)
class CandidateBudget:
    """The two limits a NEW obligation's candidate pointer proposes."""

    deadline: str
    max_handoffs: int


def obligation_of(*, authority: AuthorityState) -> Obligation | None:
    """The obligation an authority records, or `None` when it tracks none.

    BOTH limits are required, and a state holding only one is read as tracking
    NOTHING rather than as a half-obligation. An obligation with no ceiling or no
    clock cannot expire, so admitting one would create a budget that silently
    never runs out — which reads, at every surface, exactly like a budget being
    honoured.
    """
    deadline = authority.original_deadline
    maximum = authority.max_handoffs
    if deadline is None or maximum is None:
        return None
    return Obligation(
        required_result=authority.required_result,
        original_deadline=deadline,
        max_handoffs=maximum,
        consumed_handoffs=authority.consumed_handoffs,
    )


def obligation_expiry(*, obligation: Obligation, now: str) -> str | None:
    """Name the first limit this obligation has reached, or `None` while it holds.

    Both boundaries are INCLUSIVE, as the clause words them: "At the exact
    deadline or when accepted handoffs reach max_handoffs, the next continuation
    is expired." So the comparisons are `>=`, not `>`; `instant_expired` supplies
    that for the clock and fails CLOSED on an unreadable instant, which is the
    direction a budget gate must fail in.
    """
    if obligation.consumed_handoffs >= obligation.max_handoffs:
        return EXPIRY_HANDOFFS
    if instant_expired(until=obligation.original_deadline, now=now):
        return EXPIRY_DEADLINE
    return None


def candidate_budget(*, budget: object) -> CandidateBudget | None:
    """Read the two limits off a candidate pointer's budget, or `None`.

    `validate_next_action` has already admitted the shape by the time any writer
    reaches here, so this is the narrow re-read that turns an admitted object
    into typed values. It returns `None` rather than raising for the same reason
    the result-reference parse returns a refusal value: a writer turns the
    absence into its own refusal, and an exception would have to be caught
    outside this tree's one permitted effect boundary.
    """
    if not isinstance(budget, dict):
        return None
    fields = cast("dict[str, Any]", budget)
    deadline = fields.get(BUDGET_DEADLINE_FIELD)
    maximum = fields.get(BUDGET_MAX_HANDOFFS_FIELD)
    if not isinstance(deadline, str):
        return None
    if not isinstance(maximum, int) or isinstance(maximum, bool):
        return None
    if maximum <= 0:
        return None
    return CandidateBudget(deadline=deadline, max_handoffs=maximum)


def budget_projection(*, obligation: Obligation, epoch: int) -> dict[str, object]:
    """Render the committed obligation as the pointer's `budget` object.

    `handoff_count` and `epoch` ride alongside the two ratified fields because
    the resume path compares the count against the ceiling and an operator needs
    to see which epoch's authority the pointer is projecting. `epoch` is rendered
    as a string because `validate_next_action` admits it only as a non-empty one.
    """
    return {
        BUDGET_DEADLINE_FIELD: obligation.original_deadline,
        BUDGET_MAX_HANDOFFS_FIELD: obligation.max_handoffs,
        BUDGET_HANDOFF_COUNT_FIELD: obligation.consumed_handoffs,
        BUDGET_EPOCH_FIELD: str(epoch),
    }


def projected_action(
    *,
    action: NextAction,
    authority: AuthorityState,
    epoch: int,
) -> NextAction:
    """Overlay the COMMITTED obligation onto the pointer a writer will store.

    An authority tracking no obligation hands the action back unchanged, which is
    what keeps a `human` or `none` pointer's explicit null tracking fields null:
    the clause requires both to be null for those kinds, so projecting an
    obligation onto one would make the pointer itself invalid.
    """
    obligation = obligation_of(authority=authority)
    if obligation is None:
        return action
    return replace(
        action,
        required_result=obligation.required_result,
        budget=budget_projection(obligation=obligation, epoch=epoch),
    )
