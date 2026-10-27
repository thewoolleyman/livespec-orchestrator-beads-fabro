"""ONE projected Codex credential's usage windows, as a value.

`SPECIFICATION/contracts.md` section "Provider spend containment", the
paragraph "Admission filters Codex candidates by projected usage-window
headroom": "From the response the Dispatcher MUST take `rate_limit.allowed`,
`rate_limit.limit_reached`, and, for each of `rate_limit.primary_window` and
`rate_limit.secondary_window` that is present and non-null, its `used_percent`
and `limit_window_seconds`. A window's remaining headroom equals 100 minus its
`used_percent`; a valid window is one whose `used_percent` is a finite number
from 0 through 100 inclusive and whose `limit_window_seconds` is a positive
integer. ... The governing remaining headroom of a valid reading is the
smallest remaining headroom among its windows."

NOTHING HERE READS A CREDENTIAL, A FILE OR A NETWORK, exactly as in the Claude
value one venue over. The reading arrives as a decoded `rate_limit` mapping and
the policy's `read` is a seam, which is what lets every state the clause
distinguishes be exercised without a provider.

VALIDITY IS DECIDED FOR THE WHOLE READING, NEVER WINDOW BY WINDOW, and that is
the one sentence an almost-correct implementation inverts. A per-window grade is
the natural shape -- iterate the two fields, keep what parses -- and it produces
a well-formed reading with a plausible governing headroom while silently
discarding half the response. The clause forbids it in as many words ("MUST NOT
... be admitted on its valid part"), so a reading carrying any malformed present
window is unobservable AND CARRIES NO WINDOWS AT ALL: leaving the valid half in
place would let a downstream reader recover exactly the admission the clause
refuses.

A CREDIT BALANCE IS NOT HEADROOM. Only `rate_limit` is read, and the type has no
field anything outside it could arrive through -- which is the clause's "A credit
balance, an overage allowance, or any other field outside `rate_limit` MUST NOT
count as headroom and MUST NOT prevent a skip" expressed as a shape rather than
as a review note. Work served from credits beyond the usage window is spend the
operator did not schedule.

COVERAGE FOLLOWS RESOLVED PROVENANCE, NEVER SPELLING, which the clause states
identically to its Claude sibling. `codex_headroom_covers_candidate` asks ONE
question it can answer from provenance -- whether the candidate resolved through
the `codex-acp` agent entry -- and asks nothing of the candidate's own
`availability_key`, which is opaque by contract. There is no built-in-identity
arm here because this clause's coverage is the structured agent id alone: an
operator who named their pool after the vendor has not opted in.

THE PROJECTION RESULTS ARE CARRIED HERE AND DECIDED NEXT DOOR, for the reason
the Claude reading carries its own: `CodexWindowProjection` is a VALUE, so it
belongs beside the reading it rides, while the decision that produces it needs a
per-window journal history this module has no business reading. That is also why
`projections` defaults to empty rather than being a constructor requirement -- a
reading carries none until an evaluation holding that history attaches them.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import cast

from livespec_orchestrator_beads_fabro.commands._acp_agent_catalog import CODEX_AGENT_ID
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    FULL_ALLOWANCE_PERCENT,
    SessionHeadroomProjection,
)

__all__: list[str] = [
    "ALLOWED_FIELD",
    "CODEX_PROVIDER",
    "LIMIT_REACHED_FIELD",
    "LIMIT_WINDOW_SECONDS_FIELD",
    "PRIMARY_WINDOW_FIELD",
    "SECONDARY_WINDOW_FIELD",
    "UNREADABLE_USAGE_RESPONSE",
    "USED_PERCENT_FIELD",
    "WINDOW_FIELDS",
    "CodexHeadroomPolicy",
    "CodexUsageReading",
    "CodexUsageWindow",
    "CodexWindowProjection",
    "codex_headroom_covers_candidate",
    "codex_usage_reading",
    "unobservable_codex_usage",
]

# How every record surface and refusal names the provider this clause governs,
# which the clause requires of them: "MUST name the provider as `codex`". One
# literal, so a selection record and a refusal record cannot spell it two ways.
CODEX_PROVIDER = "codex"

# The response fields the clause enumerates, named once. The two window fields
# are read IN THIS ORDER so a reading's `windows` tuple is in response order
# rather than in whatever order a mapping iterates.
ALLOWED_FIELD = "allowed"
LIMIT_REACHED_FIELD = "limit_reached"
PRIMARY_WINDOW_FIELD = "primary_window"
SECONDARY_WINDOW_FIELD = "secondary_window"
WINDOW_FIELDS: tuple[str, ...] = (PRIMARY_WINDOW_FIELD, SECONDARY_WINDOW_FIELD)
USED_PERCENT_FIELD = "used_percent"
LIMIT_WINDOW_SECONDS_FIELD = "limit_window_seconds"

# The one unobservable reason THIS module can reach: a `rate_limit` block that
# did not parse into the shape the clause describes. The transport reasons
# belong to whoever issued the request, because only it observed the fault.
UNREADABLE_USAGE_RESPONSE = "unreadable-usage-response"


@dataclass(frozen=True, kw_only=True)
class CodexUsageWindow:
    """One valid usage window: how spent it is, and how long it spans.

    `limit_window_seconds` is carried rather than discarded because it is the
    window's IDENTITY for the baseline rule: the clause applies the drain-rate
    rules "per opaque credential identity AND per window length, so a reading of
    one window is never a baseline for another". A reading that kept only the
    percentage could not say which window a prior belonged to, and the two
    windows of one credential drain at completely different rates.
    """

    used_percent: float
    limit_window_seconds: int

    @property
    def remaining_percent(self) -> float:
        """100 minus this window's `used_percent`, as the clause defines it."""
        return FULL_ALLOWANCE_PERCENT - self.used_percent


@dataclass(frozen=True, kw_only=True)
class CodexWindowProjection:
    """ONE window's projection result, and which window it is about.

    `limit_window_seconds` is `None` for the clause's "or once, when no window
    is valid" case, which is a reading with no window to attribute a result to.
    It is a NULLABLE field rather than a separate shape because every consumer
    asks the same two questions of either -- what the result was, and which
    window it describes -- and a second type would make a reader hold two.
    """

    projection: SessionHeadroomProjection
    limit_window_seconds: int | None = None


@dataclass(frozen=True, kw_only=True)
class CodexUsageReading:
    """One assessment of one projected Codex credential, at one observation time.

    Every field is an opaque identity, a boolean the provider stated, a
    percentage, a span, an instant or a closed result. There is no field a
    credential value, an account email or a raw provider response could arrive
    through, which is the clause's "The journal MUST NOT contain credential
    values, the account email, or raw provider responses" expressed as a type.

    `allowed` and `limit_reached` are TRI-STATE, and the third state is
    load-bearing: an unobservable reading states neither, and `False`/`True` are
    both perfectly good provider answers, so a boolean defaulting either way
    would make a failure to measure indistinguishable from a measurement. The
    `limit_refused` property is what reads them, so no consumer compares them by
    hand.

    `provider_reset_claim` is the ONE field the provider itself asserts, named
    for what it is. The clause permits journaling "a reset instant the response
    carries" as "an unverified provider claim" and forbids it from changing any
    skip -- so it is carried, read by no decision here or in the projection, and
    rendered under a record key that says it is unverified.
    """

    credential_identity: str
    observed_at: str
    allowed: bool | None = None
    limit_reached: bool | None = None
    windows: tuple[CodexUsageWindow, ...] = ()
    unobservable: str | None = None
    projections: tuple[CodexWindowProjection, ...] = ()
    provider_reset_claim: str | None = None

    @property
    def observable(self) -> bool:
        """Whether this reading is a valid reading of the WHOLE response."""
        return self.unobservable is None

    @property
    def limit_refused(self) -> bool:
        """Whether the provider itself says this credential is at its limit.

        Compared against the two booleans EXPLICITLY rather than by truthiness,
        so an unobservable reading -- which states neither -- answers `False`.
        That is the right answer and not a convenience: an unreadable response
        has not reported a limit, and the clause routes it through the floor
        arm, which carries a different not-projected reason and a different
        remedy.
        """
        return self.allowed is False or self.limit_reached is True

    @property
    def governing_remaining_percent(self) -> float | None:
        """The SMALLEST remaining headroom among this reading's windows.

        `None` for a reading with no valid window, which is the unobservable
        case. It is an explicit absence rather than a full allowance, because
        100 is exactly what an untouched window reads as -- a coerced one would
        admit every credential whose response could not be read.
        """
        if not self.windows:
            return None
        return min(window.remaining_percent for window in self.windows)


@dataclass(frozen=True, kw_only=True)
class CodexHeadroomPolicy:
    """The two governing dials plus the ONE reading seam for one evaluation.

    The dials are the Claude clause's own committed `session_headroom_floor_
    percent` and `session_headroom_horizon_minutes`, which this clause states
    outright: "it introduces no configuration key of its own". A second pair
    would let an operator switch the brake off and still have dispatches
    refused by the provider they had not configured.

    `read` is memoized by whoever BUILDS the policy, per admission evaluation,
    which is how "MUST reuse that one reading across every node and candidate
    sharing the credential" becomes a property of the value every node is
    filtered against rather than a convention each call site remembers.

    Neither dial carries a default, exactly as on the Claude policy: both are
    resolved by the one builder that reads the repository, and a default here
    would let a caller that simply forgot to thread a dial through report the
    ratified figure for every dispatch forever.
    """

    floor_percent: int
    horizon_minutes: int
    read: Callable[[], CodexUsageReading]


def codex_usage_reading(
    *,
    credential_identity: str,
    observed_at: str,
    rate_limit: object,
    provider_reset_claim: str | None = None,
) -> CodexUsageReading:
    """Grade one response's `rate_limit` block, or the explicit unobservable result.

    `rate_limit` is typed `object` deliberately: it arrives from a decoded
    provider document, so every question the clause asks of it is a question
    about a value of unknown shape, and a narrower parameter type would push
    that grading onto the caller with the least context for it.

    THE FOUR REFUSALS ARE ONE LADDER AND THE ORDER IS NOT ARBITRARY. The block
    must be a mapping before any field can be read; both booleans must be
    booleans before a window's absence can mean anything; and only then is "at
    least one window present and non-null, and every present non-null window
    valid" a well-posed question.
    """
    unobservable = unobservable_codex_usage(
        credential_identity=credential_identity,
        observed_at=observed_at,
        reason=UNREADABLE_USAGE_RESPONSE,
        provider_reset_claim=provider_reset_claim,
    )
    if not isinstance(rate_limit, Mapping):
        return unobservable
    block = cast("Mapping[str, object]", rate_limit)
    allowed = block.get(ALLOWED_FIELD)
    limit_reached = block.get(LIMIT_REACHED_FIELD)
    if not isinstance(allowed, bool) or not isinstance(limit_reached, bool):
        return unobservable
    windows = _windows(block=block)
    if windows is None:
        return unobservable
    return CodexUsageReading(
        credential_identity=credential_identity,
        observed_at=observed_at,
        allowed=allowed,
        limit_reached=limit_reached,
        windows=windows,
        provider_reset_claim=provider_reset_claim,
    )


def unobservable_codex_usage(
    *,
    credential_identity: str,
    observed_at: str,
    reason: str,
    provider_reset_claim: str | None = None,
) -> CodexUsageReading:
    """The explicit unobservable result, naming the measurement that failed.

    It carries NO window and neither boolean, which is the whole-reading
    validity rule expressed where it cannot be undone: a consumer holding this
    value has nothing it could admit the credential on.

    A reset CLAIM survives, because it is graded independently of the block: a
    response whose `rate_limit` is missing or malformed can still assert when
    the window resets, and dropping the claim would discard the only thing that
    response said.
    """
    return CodexUsageReading(
        credential_identity=credential_identity,
        observed_at=observed_at,
        unobservable=reason,
        provider_reset_claim=provider_reset_claim,
    )


def codex_headroom_covers_candidate(*, candidate: AcpCandidate) -> bool:
    """Whether this clause assesses this candidate at all.

    ONE provenance question, and it is not a spelling: `agent_id` is the agent
    catalog entry the candidate resolved THROUGH, which the renderer set and no
    configured text can forge. Asking the candidate's own `availability_key`
    would be the inference the clause forbids outright.
    """
    return candidate.agent_id == CODEX_AGENT_ID


def _windows(*, block: Mapping[str, object]) -> tuple[CodexUsageWindow, ...] | None:
    """Every present non-null window, or `None` when the READING is not valid.

    `None` is returned for both of the clause's whole-reading faults -- a
    malformed present window, and no present window at all -- because both make
    the reading unobservable and the caller renders one result for either. A
    build that distinguished them here would be inventing a reason the clause's
    closed set does not carry.
    """
    graded: list[CodexUsageWindow] = []
    for field in WINDOW_FIELDS:
        value = block.get(field)
        if value is None:
            continue
        window = _window(value=value)
        if window is None:
            return None
        graded.append(window)
    return tuple(graded) if graded else None


def _window(*, value: object) -> CodexUsageWindow | None:
    """One window the clause calls valid, or `None` for every shape that is not.

    `bool` is excluded from BOTH fields because it is a subclass of `int`: a
    document carrying `true` where a percentage belongs would otherwise read as
    1 percent used -- a valid, plausible 99 points of headroom from a value that
    says nothing about usage -- and `true` where a span belongs would read as a
    one-second window, which is a window length no baseline could ever match.
    """
    if not isinstance(value, Mapping):
        return None
    fields = cast("Mapping[str, object]", value)
    used = fields.get(USED_PERCENT_FIELD)
    seconds = fields.get(LIMIT_WINDOW_SECONDS_FIELD)
    if isinstance(used, bool) or not isinstance(used, int | float):
        return None
    percent = float(used)
    if not math.isfinite(percent) or percent < 0.0 or percent > FULL_ALLOWANCE_PERCENT:
        return None
    if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds <= 0:
        return None
    return CodexUsageWindow(used_percent=percent, limit_window_seconds=seconds)
