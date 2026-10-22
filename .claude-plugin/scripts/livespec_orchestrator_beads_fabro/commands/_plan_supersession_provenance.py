"""Whether the derivation a supersession NAMES wrote the obligation standing now.

PURE, and a LEAF: nothing here imports the refusal ladder it serves, which is
what lets `_plan_supersession` import it without a cycle. It answers in the one
currency the ladder needs — a reason, or `None` for no objection — and the ladder
wraps that reason in its own refusal type, so the decision about WHAT refuses
stays where every other condition's refusal is built.

WHY THE QUESTION EXISTS AT ALL. A supersession's deriving operation identity
resolves at the epoch its OWN transition recorded, which is what lets a RETAINED
obligation be superseded (`bd-ib-4hznqp`; `_plan_supersession_evidence` carries
the measurement). The cost of that is that the identity alone selects ANY
recorded transition of the plan — a real one, committed by a real derivation
actor — and the obligation that transition wrote need not be the obligation
standing now. Without this grade such a supersession reads as fully evidenced
while naming a derivation that has nothing to do with the result it is replacing,
which is the rename-with-a-verified-footnote shape the whole cause exists to
refuse.

TWO CONDITIONS, AND THE SECOND IS NOT IMPLIED BY THE FIRST. The named transition
must have RECORDED the retained obligation, and every transition after it must
have RETAINED that result unchanged. An obligation changed and then changed back
satisfies the first exactly — the named derivation did record the result standing
now — while the transition that WROTE what stands is the restoring one. So a
chain that changed its result away and back is the one shape in which naming the
original derivation looks fully evidenced and is not.

EVERY COMPARISON IS BETWEEN CANONICAL IDENTITIES, never between raw recorded
values, because canonical result identity "rather than session, wording, kind/ref
or last_session, MUST govern continuity". A recorded value that parses to no
typed reference therefore has no identity and compares unequal to every
obligation — the fail-closed answer, since a transition whose recorded result
this reader cannot place cannot be shown to have written or retained anything.

AND NO RAW RECORDED VALUE IS EVER RENDERED BACK INTO A REFUSAL. It is untrusted
ledger content, and the question a refusal answers is which canonical identity a
transition wrote; an unreadable one is named as exactly that.
"""

from __future__ import annotations

from collections.abc import Sequence

from livespec_orchestrator_beads_fabro.commands._plan_result_reference import (
    parse_result_reference,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import ResultReference

__all__: list[str] = [
    "UNREADABLE_REFERENCE",
    "provenance_detail",
]

# How a recorded result with no canonical identity is NAMED in a refusal. Public
# because a reader of a refusal — a test among them — needs the word this grade
# uses for "nothing could be placed here", and a second spelling of it would be a
# second account of the same absence.
UNREADABLE_REFERENCE = "an unreadable typed reference"


def provenance_detail(
    *,
    operation_id: str,
    recorded_result: object,
    later_results: Sequence[object],
    prior_identity: str,
) -> str | None:
    """Why the named derivation did not write the retained obligation, or `None`.

    `recorded_result` is the obligation that transition wrote and `later_results`
    is what every transition after it recorded, oldest first. `None` means no
    objection: the derivation recorded the retained obligation and every later
    transition kept it.
    """
    recorded = _identity_of(value=recorded_result)
    if recorded != prior_identity:
        return (
            f"the deriving operation {operation_id!r} recorded the required result"
            f" {_shown(identity=recorded)}, which is not the retained obligation"
            f" {prior_identity}"
        )
    for later in later_results:
        if _identity_of(value=later) != prior_identity:
            return (
                f"a transition recorded after {operation_id!r} changed the required result to"
                f" {_shown(identity=_identity_of(value=later))}, so the obligation"
                f" {prior_identity} that stands now was written by that later transition"
                " rather than by the derivation named"
            )
    return None


def _identity_of(*, value: object) -> str | None:
    """One recorded required result's canonical identity, or `None` for unreadable."""
    parsed = parse_result_reference(value=value)
    return parsed.identity if isinstance(parsed, ResultReference) else None


def _shown(*, identity: str | None) -> str:
    """How one recorded result is NAMED in a refusal, including when it has none."""
    return identity if identity is not None else UNREADABLE_REFERENCE
