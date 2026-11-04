"""The standing lease one recovery record carries, and whether it can be read at all.

Split from `_session_recovery_lease` by cohesion: that module DECIDES a claim,
and this one answers the prior question it decides against — what lease does the
record currently hold. Keeping the reading here means every unreadable lease
shape can be exercised against a payload alone, with no store and no claim.

WHY THERE ARE THREE ANSWERS AND NOT TWO. `None` is an UNCLAIMED attempt, a
readable lease is a lease, and the third answer is a lease this build cannot
read. The third exists because of the direction its absence would fail in: the
natural coding of "I cannot read this expiry" is to treat the lease as lapsed,
which hands a takeover to a competitor while the recorded holder may be
mid-command — the exact duplicate effect the fencing exists to prevent. So an
expiry, a holder or a generation that is not of its declared type refuses the
claim instead of lapsing it.

WHY `bool` IS EXCLUDED FROM THE EXPIRY EXPLICITLY. `bool` is an `int` subclass,
so `True` would otherwise read as a lease expiring one second after the epoch —
permanently lapsed, and permanently handing takeovers to whoever asks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

__all__: list[str] = [
    "StandingLease",
    "standing_lease",
]


@dataclass(frozen=True, kw_only=True)
class StandingLease:
    """A lease a record already carries, or the fact that it cannot be read.

    When `unobservable` is true the other three fields carry nothing a caller
    may act on; they are present so the type stays one shape rather than two,
    and every caller tests `unobservable` before reading them.
    """

    holder: str
    generation: int
    expires_at: float
    unobservable: bool


def standing_lease(*, payload: dict[str, object]) -> StandingLease | None:
    """The lease this record holds, `None` when unclaimed, else an unreadable marker."""
    holder = payload["holder"]
    generation = payload["generation"]
    expires_at = payload["lease_expires_at"]
    if holder is None and generation == 0:
        return None
    if not _readable(holder=holder, generation=generation, expires_at=expires_at):
        return StandingLease(holder="", generation=0, expires_at=0.0, unobservable=True)
    return StandingLease(
        holder=cast("str", holder),
        generation=cast("int", generation),
        expires_at=float(cast("float", expires_at)),
        unobservable=False,
    )


def _readable(*, holder: object, generation: object, expires_at: object) -> bool:
    """Whether all three lease fields hold a value of the type the schema names."""
    return (
        isinstance(holder, str)
        and isinstance(generation, int)
        and isinstance(expires_at, int | float)
        and not isinstance(expires_at, bool)
    )
