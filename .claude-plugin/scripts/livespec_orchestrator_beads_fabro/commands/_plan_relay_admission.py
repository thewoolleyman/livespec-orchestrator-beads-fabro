"""Which relay recordings are admissible, and the displacement that admits one.

PURE, and the GRADE half of the relay primitive: `_plan_relay_delivery` observes
and records, and everything here decides whether it may. Both of the clause's
refusal surfaces live together because they answer one question — what this relay
id may be made to track — and splitting them is how a successor comes to be
refused for one reason while being admitted for the other.

EVERY GRADE RUNS BEFORE ANY READ IS SPENT. A relay with a blank id, a blank
operation identity, a blank sender or a blank deadline is one no later call can
address, and a relay id already tracking a different target is one no later call
may take; spending a tenant or forge read on either would be spending it on a
question nobody can ask again.

THE SUPERSESSION MUST CARRY ITS OWN RELAY ID. `bd comments` offers no edit, so a
successor wearing the displaced relay's id becomes the LATEST record under that
id and shadows the very disposition the clause requires preserved — which is why
a supersession naming the successor's own id is refused outright rather than
read as a no-op.

AND A SUPERSESSION OF AN UNCHANGED TARGET IS REFUSED, which is the arm that is
easiest to leave out and the one the deadline rule depends on. Without it the
laundering route is open: a fresh relay id, the same obligation, a deadline of
the sender's own choosing, and a supersession record that reads at every surface
as the clause's sanctioned path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._plan_relay_record import RelayRecord

__all__: list[str] = [
    "RelayRefusal",
    "RelaySupersession",
    "identity_refusal",
    "target_refusal",
]


@dataclass(frozen=True, kw_only=True)
class RelaySupersession:
    """The explicit displacement one relay's conflicting target requires.

    `relay_id` is the relay being DISPLACED and is never the successor's own:
    the successor keeps its own identity so the displaced relay's last
    observation stays the latest record under its id, which is the only way its
    disposition survives a store whose comments cannot be edited.
    """

    relay_id: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class RelayRefusal:
    """Why one relay was not recorded. Nothing was written when this is returned."""

    detail: str


def identity_refusal(
    *, relay_id: str, operation_id: str, sender: str, deadline: str
) -> RelayRefusal | None:
    """Refuse a relay no later call could address or attribute."""
    named = (
        ("relay id", relay_id),
        ("operation identity", operation_id),
        ("sender", sender),
        ("deadline", deadline),
    )
    blank = [field for field, value in named if value.strip() == ""]
    if not blank:
        return None
    return RelayRefusal(
        detail=(
            "a relay must carry a stable relay id, a stable operation identity, the"
            f" sender that owes it and an absolute UTC deadline; absent: {', '.join(blank)}"
        )
    )


def target_refusal(
    *,
    relay_id: str,
    epic_id: str,
    requested_identity: str,
    supersedes: RelaySupersession | None,
    history: RelayRecord | None,
    displaced: RelayRecord | None,
) -> RelayRefusal | None:
    """Refuse a target this relay id may not take.

    `history` is the relay's own latest record and `displaced` is the latest
    record of the relay a supersession names; both arrive already resolved,
    because one pass over the epic's comments answers every question here and
    three passes could disagree with each other about what the ledger holds.
    """
    if history is not None and history.result_identity != requested_identity:
        return RelayRefusal(
            detail=(
                f"relay {relay_id} already tracks {history.result_identity};"
                f" recording {requested_identity} under that id would shadow the"
                " obligation it displaces, so a conflicting target requires an"
                " explicit supersession under a new relay id"
            )
        )
    return _supersession_refusal(
        relay_id=relay_id,
        epic_id=epic_id,
        requested_identity=requested_identity,
        supersedes=supersedes,
        displaced=displaced,
    )


def _supersession_refusal(
    *,
    relay_id: str,
    epic_id: str,
    requested_identity: str,
    supersedes: RelaySupersession | None,
    displaced: RelayRecord | None,
) -> RelayRefusal | None:
    """Admit only a supersession that carries a displaced obligation forward."""
    if supersedes is None:
        return None
    if supersedes.relay_id == relay_id:
        return RelayRefusal(
            detail=(
                f"a supersession naming its own relay id {relay_id} displaces"
                " nothing: the successor becomes the latest record under that id and"
                " shadows the disposition it claims to preserve"
            )
        )
    if displaced is None:
        return RelayRefusal(
            detail=(
                f"the supersession names no recorded relay: {supersedes.relay_id} has no"
                f" observation on {epic_id} whose disposition could be preserved"
            )
        )
    if supersedes.reason.strip() == "":
        return RelayRefusal(
            detail="a supersession requires a causal reason for displacing the obligation"
        )
    if displaced.result_identity == requested_identity:
        return RelayRefusal(
            detail=(
                f"relay {supersedes.relay_id} already tracks {requested_identity}, so there"
                " is no conflicting target to supersede; a supersession is not a route to a"
                " fresh deadline on an unchanged obligation"
            )
        )
    return None
