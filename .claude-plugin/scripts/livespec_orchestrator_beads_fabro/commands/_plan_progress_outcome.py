"""What one sanctioned plan pointer write DECIDES, and the retention it rests on.

PURE and a LEAF: it imports nothing from this family, which is the whole reason
it exists. The decision ladder splits across two modules — the arms for an
obligation that is absent, satisfied or null-tracked in `_plan_progress_decision`,
and the arms for an UNMET one in `_plan_progress_unmet` — and both need these two
values, so a home for them inside either closes an import cycle.

`EVENT_SUPERSESSION` is deliberately NOT here. It is the one progress-event kind
whose meaning is fixed by the cause that produces it, so it lives beside that
cause in `_plan_supersession`; the four below are kinds a write chooses from what
it is DOING, which is this module's own subject.

WHY `retained_authority` IS HERE RATHER THAN BESIDE EITHER CALLER. It is the
guarantee the whole clause rests on — "Routine handoffs, supervisor handoffs and
direct set_next_action calls MUST NOT reset the deadline or count" — and both the
picker arm and the continuation arm are writes that must honour it. A second copy
is how one of them comes to reset a limit the other preserves, which is invisible
in any single write.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import AuthorityState

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._plan_next_action import NextAction
    from livespec_orchestrator_beads_fabro.commands._plan_obligation import Obligation

__all__: list[str] = [
    "EVENT_HANDOFF",
    "EVENT_PICKER",
    "EVENT_POINTER",
    "EVENT_RECOVERY",
    "TrackedDecision",
    "TrackedRefusal",
    "retained_authority",
]

EVENT_HANDOFF = "handoff"
EVENT_POINTER = "pointer"
EVENT_PICKER = "picker"
EVENT_RECOVERY = "recovery"


@dataclass(frozen=True, kw_only=True)
class TrackedDecision:
    """The authority to commit and the pointer that projects it."""

    action: NextAction
    authority: AuthorityState
    event_kind: str


@dataclass(frozen=True, kw_only=True)
class TrackedRefusal:
    """Why one sanctioned write was refused BEFORE it mutated anything."""

    detail: str


def retained_authority(
    *, prior: Obligation, consumed: int, attempt: object = None
) -> AuthorityState:
    """The prior obligation, with only its accepted-handoff count advanced.

    `attempt` is CARRIED FORWARD rather than defaulted away on an ordinary
    continuation: the item-attributable repetition count lives inside it, so
    dropping it would reset that count on every handoff that followed a recovery.
    """
    return AuthorityState(
        required_result=prior.required_result,
        original_deadline=prior.original_deadline,
        max_handoffs=prior.max_handoffs,
        consumed_handoffs=prior.consumed_handoffs + consumed,
        last_recovery_attempt=attempt,
    )
