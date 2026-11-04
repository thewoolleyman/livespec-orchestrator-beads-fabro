"""The identity a retried plan pointer write is recognised by.

PURE, and split out of `_plan_tracked_write` for the pure-from-impure reason this
tree splits everything: that module is the one path every sanctioned write takes
through the epoch chain, and every line of it is an effect, while this is one
deterministic function of a request's own fields. A derivation nobody can execute
without a store is a derivation nobody can exercise across the shapes it has to
answer for.
"""

from __future__ import annotations

from hashlib import sha256
from json import dumps
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._plan_tracked_write import TrackedWriteRequest

__all__: list[str] = [
    "derived_operation_id",
]


def derived_operation_id(*, request: TrackedWriteRequest) -> str:
    """A deterministic operation identity for a caller that named none.

    Two calls agreeing on the epic, author, instant, WHOLE pointer and handoff
    body are the SAME logical operation — a retry — and must recover one event rather than
    consume two handoff units. Anything that differs in any of those is a
    different operation.

    THE PROPOSED OBLIGATION IS PART OF THE IDENTITY, including the budget the
    continuation path goes on to discard. On the FRESH-obligation arm the
    proposed budget is the very thing that becomes durable, so excluding it
    would let the second of two distinct establishing writes be recovered as a
    retry of the first, silently adopting a budget its caller never asked for.

    A digest is used rather than the fields themselves because the identity
    rides in a close reason and a progress event, and an unbounded
    concatenation of caller prose does not belong in either. The parts are
    joined on a unit separator so no two different field splits can render one
    string, and `sort_keys` makes the reference rendering independent of dict
    insertion order so two equal references cannot digest differently.
    """
    material = "\x1f".join(
        (
            request.epic_id,
            request.author,
            request.now,
            request.action.kind,
            request.action.ref,
            request.action.text,
            request.body or "",
            str(request.is_handoff),
            dumps(request.action.required_result, sort_keys=True, default=str),
            dumps(request.action.budget, sort_keys=True, default=str),
        )
    )
    return f"plan-write-{sha256(material.encode('utf-8')).hexdigest()[:16]}"
