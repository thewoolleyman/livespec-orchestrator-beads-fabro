"""ONE projected credential's five-hour session headroom, as a value.

`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance", the paragraph "Admission filters candidates by
projected Claude session headroom": the Dispatcher "MUST read the provider's
five-hour session utilization using the exact credential snapshot that the
dispatch would project", "Remaining headroom equals 100 minus the provider's
five-hour utilization percentage", and "A valid reading is a finite numeric
utilization from 0 through 100 inclusive. Missing, malformed, out-of-range,
transport-failed, authentication-failed, or timed-out readings are unobservable
and MUST be journaled as such, never coerced to a numeric reading."

NOTHING HERE READS A CREDENTIAL, A FILE OR A NETWORK. The reading arrives as a
value and the policy's `read` is a seam, which is what lets the whole decision
be exercised across every state the clause distinguishes without a provider --
and what keeps the pure half importable from the filter that consumes it.

AN UNOBSERVABLE READING IS A FIRST-CLASS ANSWER AND NEVER A NUMBER, which is
why `unobservable` is its own field rather than a sentinel in
`utilization_percent`. Every numeric sentinel available is also a perfectly
plausible genuine reading: 0 says the window is untouched, 100 says it is
spent, and either would make a failure to MEASURE indistinguishable, at every
surface downstream, from a measurement. The clause enumerates six distinct ways
a reading fails and requires each to be journaled AS unobservable, so the
reason travels with the reading rather than being re-derived by a reader.

COVERAGE FOLLOWS RESOLVED PROVENANCE, NEVER SPELLING. The clause is explicit --
"Coverage MUST follow resolved agent provenance and actual credential
projection, never display text, a model-name prefix, or a spelling inferred
from an opaque availability or candidate key" -- so `headroom_covers_candidate`
asks only two questions it can answer from provenance: whether the candidate
resolved through the `claude-acp` agent entry, and whether its identity is one
THIS BUILD rendered as a built-in Claude adapter (`_acp_builtin_candidates`
keys that table on exact rendered bytes, so matching it is provenance rather
than inference). An operator who named their own account after the vendor has
not opted into this clause, and an arbitrary manual adapter is outside it until
an explicit authentication binding brings it in.

THE SKIP PREDICATE IS THE WHOLE FILTER, and its two boundaries are the ones an
almost-correct implementation inverts: equality PASSES, and a floor of 0
disables both kinds of skip while retaining the reading. Both are the clause's
own words.

TWO FIGURES ON THIS READING ARE JOURNAL-ONLY AND ARE NOT GRADED BY THIS
MODULE'S VALID-READING RULE (`bd-ib-rszkjc`): the SEVEN-DAY utilization and the
five-hour DRAIN RATE. The clause's inclusive 0..100 grade governs the FIVE-HOUR
utilization, because that is the figure remaining headroom is computed from and
the floor decides on; neither journal-only figure decides anything, so coercing
them into that grade would discard readings nothing depends on -- a drain rate
is a rate and has no 0..100 range at all. The seven-day figure arrives already
read and travels through both constructors untouched; the drain rate is
attached afterwards by `_acp_session_headroom_drain`, which needs a history
this module has no business reading.

`headroom_skips_candidate` looks at NEITHER, which is what makes "journaled
only, changes no admission decision" a property of the predicate's inputs
rather than a note a reader has to trust: the predicate reads
`remaining_percent` and the floor, so no value either figure could take can
reach a decision.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_agent_catalog import CLAUDE_AGENT_ID
from livespec_orchestrator_beads_fabro.commands._acp_builtin_candidates import ANTHROPIC_DOMAIN
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate

__all__: list[str] = [
    "DEFAULT_SESSION_HEADROOM_FLOOR_PERCENT",
    "FULL_ALLOWANCE_PERCENT",
    "UNREADABLE_UTILIZATION",
    "SessionHeadroomPolicy",
    "SessionHeadroomReading",
    "headroom_covers_candidate",
    "headroom_skips_candidate",
    "session_headroom_reading",
    "unobservable_session_headroom",
]

# The ratified default of the committed-only
# `dispatcher.session_headroom_floor_percent`, in percentage points of the
# five-hour usage allowance REMAINING -- never elapsed wall-clock time.
DEFAULT_SESSION_HEADROOM_FLOOR_PERCENT = 20

# The allowance a utilization percentage is measured against, and the upper
# bound of the clause's inclusive valid range.
FULL_ALLOWANCE_PERCENT = 100.0

# The one unobservable reason this module can reach: a utilization that was
# missing, malformed or out of range. The transport reasons belong to whoever
# issued the request, because only it observed the fault.
UNREADABLE_UTILIZATION = "unreadable-utilization"


@dataclass(frozen=True, kw_only=True)
class SessionHeadroomReading:
    """One assessment of one projected credential, at one observation time.

    Every field is an opaque identity, a percentage or an instant. There is no
    field a credential value or a raw provider response could arrive through,
    which is the clause's "The journal MUST NOT contain credential values or
    raw provider responses" expressed as a type rather than as a review note.
    """

    credential_identity: str
    observed_at: str
    utilization_percent: float | None = None
    remaining_percent: float | None = None
    unobservable: str | None = None
    seven_day_utilization_percent: float | None = None
    five_hour_drain_percent_per_hour: float | None = None

    @property
    def observable(self) -> bool:
        """Whether this reading carries a valid utilization at all.

        Named for the FIVE-HOUR window, which is the one the filter decides on.
        The seven-day figure is journal-only and is graded independently, so a
        reading can be unobservable here while still carrying one.
        """
        return self.unobservable is None


@dataclass(frozen=True, kw_only=True)
class SessionHeadroomPolicy:
    """The governing floor plus the ONE reading seam for one admission evaluation.

    `read` is memoized by whoever BUILDS the policy, per admission evaluation,
    which is how "One assessment per distinct projected credential per admission
    evaluation MUST be reused across nodes and candidates sharing that
    credential" becomes a property of the value every node is filtered against
    rather than a convention each call site remembers.
    """

    floor_percent: int
    read: Callable[[], SessionHeadroomReading]


def session_headroom_reading(
    *,
    credential_identity: str,
    observed_at: str,
    utilization: object,
    seven_day_utilization_percent: float | None = None,
) -> SessionHeadroomReading:
    """Grade one provider utilization figure into a reading, or an unobservable.

    `utilization` is typed `object` deliberately: it arrives from a decoded
    provider document, so "a finite numeric utilization from 0 through 100
    inclusive" is a question about a value of unknown shape, and a narrower
    parameter type would push that grading onto the caller with the least
    context for it.

    `seven_day_utilization_percent` is typed `float | None` for the opposite
    reason: it is JOURNAL-ONLY, so the clause's valid-reading grade does not
    apply to it, and whoever read the header has already decided whether the
    header was there and parseable. It rides through BOTH arms, because the
    two windows are independent answers from one response -- a five-hour
    header that was absent says nothing about a seven-day header that was not.
    """
    percent = _valid_utilization(value=utilization)
    if percent is None:
        return unobservable_session_headroom(
            credential_identity=credential_identity,
            observed_at=observed_at,
            reason=UNREADABLE_UTILIZATION,
            seven_day_utilization_percent=seven_day_utilization_percent,
        )
    return SessionHeadroomReading(
        credential_identity=credential_identity,
        observed_at=observed_at,
        utilization_percent=percent,
        remaining_percent=FULL_ALLOWANCE_PERCENT - percent,
        seven_day_utilization_percent=seven_day_utilization_percent,
    )


def unobservable_session_headroom(
    *,
    credential_identity: str,
    observed_at: str,
    reason: str,
    seven_day_utilization_percent: float | None = None,
) -> SessionHeadroomReading:
    """The explicit unobservable result, naming the measurement that failed."""
    return SessionHeadroomReading(
        credential_identity=credential_identity,
        observed_at=observed_at,
        unobservable=reason,
        seven_day_utilization_percent=seven_day_utilization_percent,
    )


def headroom_covers_candidate(
    *, candidate: AcpCandidate, builtin_pairs: frozenset[tuple[str, str]]
) -> bool:
    """Whether this clause assesses this candidate at all.

    TWO provenance questions, and neither is a spelling. The STRUCTURED arm
    reads the agent catalog entry the candidate resolved through, which the
    renderer set and no configured text can forge. The BUILT-IN arm asks
    `builtin_pairs` -- the identity set THIS BUILD rendered, threaded down from
    `_acp_builtin_candidates.builtin_acp_identities`, keyed on exact rendered
    bytes. Asking either is provenance; asking the candidate's own
    `availability_key` would be the inference the clause forbids, which is why
    the domain test is applied ONLY to a pair that table already matched.
    """
    if candidate.agent_id == CLAUDE_AGENT_ID:
        return True
    identity = candidate.identity
    if identity is None:
        return False
    return identity.pair in builtin_pairs and identity.availability_key == ANTHROPIC_DOMAIN


def headroom_skips_candidate(*, reading: SessionHeadroomReading, floor_percent: int) -> bool:
    """Whether this covered candidate leaves the selectable set for this evaluation.

    TWO boundaries, and an almost-correct implementation inverts either.

    EQUALITY PASSES. "With a positive floor, a covered candidate is skipped for
    this admission evaluation when its remaining headroom is strictly below the
    floor or its reading is unobservable. Equality passes this filter."

    A NON-POSITIVE FLOOR DISABLES BOTH KINDS OF SKIP, and the UNOBSERVABLE arm
    is the only one that needs the guard: no remaining headroom is strictly
    below zero, so a predicate written without it passes every numeric case at a
    floor of 0 and still refuses on every unobservable reading. An operator who
    sets the dial to 0 to switch the filter OFF would then find their dispatches
    skipped whenever the usage endpoint timed out -- the opposite of what the
    clause ratifies, from the arm a numeric test cannot reach.
    """
    if floor_percent <= 0:
        return False
    remaining = reading.remaining_percent
    if remaining is None:
        return True
    return remaining < floor_percent


def _valid_utilization(*, value: object) -> float | None:
    """The clause's valid reading, or `None` for every shape that is not one.

    `bool` is excluded explicitly because it is a subclass of `int`, so a
    document carrying `true` would otherwise read as a utilization of 1 -- a
    valid, plausible 99 percent of headroom remaining, from a value that says
    nothing about usage at all.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0.0 or numeric > FULL_ALLOWANCE_PERCENT:
        return None
    return numeric
