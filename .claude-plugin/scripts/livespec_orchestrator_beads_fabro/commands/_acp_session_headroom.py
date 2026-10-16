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

THE FIVE-HOUR DRAIN RATE IS NOT GRADED BY THIS MODULE'S VALID-READING RULE,
and the asymmetry is deliberate. The clause's inclusive 0..100 grade governs
the five-hour UTILIZATION, because that is the figure remaining headroom is
computed from and the floor decides on; a RATE has no 0..100 range at all, so
coercing it into that grade would discard measurements nothing bounds. The rate
is attached AFTER grading by `_acp_session_headroom_drain`, which needs a
journal history this module has no business reading -- which is also why the
field defaults to null here rather than being a constructor argument: a reading
carries no rate until an evaluation holding that history attaches one.

THE PROJECTION RESULT IS CARRIED HERE AND DECIDED NEXT DOOR, for the same
reason. `SessionHeadroomProjection` is a VALUE -- the result kind, the figures
and whether a skip applied -- so it belongs beside the reading it rides; the
decision that produces it needs the drain rate, the baseline and the committed
horizon, so it lives in `_acp_session_headroom_projection`. Keeping the type
here is also what lets the reading carry it without this module importing the
decision, which would close a cycle.
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
    "DEFAULT_SESSION_HEADROOM_HORIZON_MINUTES",
    "FULL_ALLOWANCE_PERCENT",
    "NOT_PROJECTED_RESULT",
    "PROJECTED_RESULT",
    "UNAVAILABLE_RESULT",
    "UNREADABLE_UTILIZATION",
    "SessionHeadroomPolicy",
    "SessionHeadroomProjection",
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

# The ratified default of the committed-only
# `dispatcher.session_headroom_horizon_minutes`: how far ahead of an
# observation a PROJECTED exhaustion still refuses the candidate. It lives
# beside the floor rather than with the projection decision because both are
# ratified dial defaults carried on the per-evaluation policy, and a reader
# looking for one expects to find the other.
DEFAULT_SESSION_HEADROOM_HORIZON_MINUTES = 180

# The allowance a utilization percentage is measured against, and the upper
# bound of the clause's inclusive valid range.
FULL_ALLOWANCE_PERCENT = 100.0

# The one unobservable reason this module can reach: a utilization that was
# missing, malformed or out of range. The transport reasons belong to whoever
# issued the request, because only it observed the fault.
UNREADABLE_UTILIZATION = "unreadable-utilization"

# The THREE projection results the clause closes, and they are three rather
# than two because `not-projected` and `unavailable` "MUST remain distinct
# values". A projection nobody attempted (the horizon's own dial is irrelevant
# there -- the FLOOR settled the reading) and a projection attempted against a
# history that could not support one both end at a null rate, and only the
# second is a reason to expect a figure once this checkout has been dispatching
# for an hour.
PROJECTED_RESULT = "projected"
UNAVAILABLE_RESULT = "unavailable"
NOT_PROJECTED_RESULT = "not-projected"


@dataclass(frozen=True, kw_only=True)
class SessionHeadroomProjection:
    """What a reading's projected exhaustion came to, as ONE closed result.

    THE RESULT KIND IS A FIELD AND NOT AN ABSENCE, which is the whole reason
    this is a value rather than three optional columns on the reading. A null
    rate beside a null exhaustion instant is what BOTH non-results look like,
    so a reader holding only the figures cannot tell a dial that was off from a
    history that was missing -- the distinction the clause requires be kept.

    `skip_applied` is DECIDED HERE, where the horizon is in hand, and merely
    READ by the filter. The filter runs per node against candidates sharing one
    reading, so a filter that re-derived the comparison would re-derive it once
    per candidate against a horizon it would have to be handed anyway -- and two
    derivations of one inequality are how a refusal record comes to disagree
    with the refusal it explains.

    Every field is a percentage, an instant, a count of minutes or a closed
    token. There is no field a credential value or a raw provider response could
    arrive through, exactly as on the reading this rides.
    """

    result: str
    reason: str | None = None
    five_hour_drain_percent_per_hour: float | None = None
    baseline_observed_at: str | None = None
    projected_exhaustion_at: str | None = None
    horizon_minutes: int | None = None
    skip_applied: bool = False


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
    five_hour_drain_percent_per_hour: float | None = None
    projection: SessionHeadroomProjection | None = None

    @property
    def observable(self) -> bool:
        """Whether this reading carries a valid utilization at all.

        Named for the UTILIZATION, which is the figure the floor decides on.
        The drain rate is a separate measurement over a history, so a reading
        can be observable here and still carry no rate.
        """
        return self.unobservable is None


@dataclass(frozen=True, kw_only=True)
class SessionHeadroomPolicy:
    """The two governing dials plus the ONE reading seam for one evaluation.

    `read` is memoized by whoever BUILDS the policy, per admission evaluation,
    which is how "One assessment per distinct projected credential per admission
    evaluation MUST be reused across nodes and candidates sharing that
    credential" becomes a property of the value every node is filtered against
    rather than a convention each call site remembers.

    `horizon_minutes` carries NO DEFAULT, exactly as the floor does not. Both
    dials are resolved by the one builder that reads the repository, and a
    default here would let a caller that simply forgot to thread the horizon
    through report the ratified 180 for every dispatch forever -- a policy that
    reads exactly like one whose operator configured nothing.
    """

    floor_percent: int
    horizon_minutes: int
    read: Callable[[], SessionHeadroomReading]


def session_headroom_reading(
    *, credential_identity: str, observed_at: str, utilization: object
) -> SessionHeadroomReading:
    """Grade one provider utilization figure into a reading, or an unobservable.

    `utilization` is typed `object` deliberately: it arrives from a decoded
    provider document, so "a finite numeric utilization from 0 through 100
    inclusive" is a question about a value of unknown shape, and a narrower
    parameter type would push that grading onto the caller with the least
    context for it.
    """
    percent = _valid_utilization(value=utilization)
    if percent is None:
        return unobservable_session_headroom(
            credential_identity=credential_identity,
            observed_at=observed_at,
            reason=UNREADABLE_UTILIZATION,
        )
    return SessionHeadroomReading(
        credential_identity=credential_identity,
        observed_at=observed_at,
        utilization_percent=percent,
        remaining_percent=FULL_ALLOWANCE_PERCENT - percent,
    )


def unobservable_session_headroom(
    *, credential_identity: str, observed_at: str, reason: str
) -> SessionHeadroomReading:
    """The explicit unobservable result, naming the measurement that failed."""
    return SessionHeadroomReading(
        credential_identity=credential_identity, observed_at=observed_at, unobservable=reason
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
