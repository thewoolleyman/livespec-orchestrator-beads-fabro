"""What one surveyed dispatch claim earns: a recovery route, or a named hold.

PURE. Every measurement the ladder reads is taken elsewhere and handed in, so
each of the fourteen holds and both absent-run routes is exercisable without
a factory, a forge, a lock or a ledger — which is the only way a condition
ladder whose whole job is to not act can be checked at all.

THE ORDER IS THE CONTRACT'S OWN, and it is load-bearing rather than tidy.
`SPECIFICATION/contracts.md` section "Stranded claim release" grades every
hold "with the reason of the FIRST condition below that applies", and
Scenario 196's "The earliest failing condition names the hold" asserts the
consequence: a claim stamped by another host whose factory is also unreachable
is `owner-elsewhere`, never `factory-unobservable`. Two reasons that are both
true describe different remedies — one is "run this on the other host", the
other is "fix the factory" — so a ladder that returned whichever it noticed
first would send an operator to the wrong place.

EVERY UNOBSERVABLE MEASUREMENT IS ITS OWN REASON AND NEVER A NEGATIVE ANSWER.
That is the asymmetry the whole subsection rests on: releasing a claim is
destructive to a live dispatch, so "the factory did not answer" must never
read as "the run is gone", and "the lock could not be read" must never read as
"no owner is alive". Each such arm is a HOLD carrying the name of the
measurement that failed, so the next pass observes it again.

THE ATTRIBUTION LADDER IS ITS OWN PUBLIC STEP, and that is a cost decision as
much as a structural one. `attribute_claim` grades reasons 1-3 — the three that
decide whether this host may act on the claim AT ALL — from the stamp alone,
so a surveying pass can skip the lock reads, the forge call and the `fabro
inspect` for every claim belonging to another host. Its result is also what
NARROWS the stamp: a claim past those three reasons has a readable run id and
a declared factory, and returning that as a value rather than re-deriving it
keeps the narrowing in one place.

TWO OF THE FOURTEEN ARE NOT GRADED HERE, and that is deliberate.
`claim-changed` and `effect-unobservable` are discovered by the RECOVERY while
it holds the lock and re-reads the row — they are facts about an instant later
than this grading — so they are raised by `_dispatcher_stranded_claim_recovery`
and merely NAMED here, where the complete ordered reason set lives.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro._store_dispatch_claim import ClaimStamp
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatching_host import (
    UNKNOWN_DISPATCHING_HOST,
)

__all__: list[str] = [
    "ACTION_ABSENT_RUN_RELEASE",
    "ACTION_ABSENT_RUN_REPEATED",
    "ATTRIBUTION_PENDING_REMEDY",
    "FORGE_MERGED_PR",
    "FORGE_NO_MERGED_PR",
    "FORGE_UNOBSERVABLE",
    "HISTORY_ABSENT_RUN_RELEASE",
    "HISTORY_NO_PREDECESSOR",
    "HISTORY_OTHER_OUTCOME",
    "HISTORY_UNAVAILABLE",
    "HOLD_ATTRIBUTION_PENDING",
    "HOLD_CLAIM_CHANGED",
    "HOLD_CLAIM_UNATTRIBUTABLE",
    "HOLD_DISPATCH_LIVE",
    "HOLD_EFFECT_UNOBSERVABLE",
    "HOLD_FACTORY_UNOBSERVABLE",
    "HOLD_FORGE_UNOBSERVABLE",
    "HOLD_HISTORY_UNAVAILABLE",
    "HOLD_LIVENESS_UNOBSERVABLE",
    "HOLD_MERGED_PR",
    "HOLD_OWNER_ELSEWHERE",
    "HOLD_REASON_ORDER",
    "HOLD_RUN_LIVE",
    "HOLD_RUN_SUCCEEDED",
    "HOLD_TERMINAL_EVIDENCE_UNAVAILABLE",
    "LIVE_RUN_STATUS_KINDS",
    "OWNER_LIVE",
    "OWNER_NONE",
    "OWNER_UNOBSERVABLE",
    "RUN_ABSENT",
    "RUN_FAILED",
    "RUN_LIVE",
    "RUN_SUCCEEDED",
    "RUN_UNOBSERVABLE",
    "AttributedClaim",
    "ClaimHold",
    "ClaimMeasurements",
    "ClaimRoute",
    "attribute_claim",
    "grade_claim",
    "run_state_from_inventory",
]

# ---------------------------------------------------------------------------
# The fourteen hold reasons, in the contract's grading order.
# ---------------------------------------------------------------------------

HOLD_CLAIM_UNATTRIBUTABLE = "claim-unattributable"
HOLD_ATTRIBUTION_PENDING = "attribution-pending"
HOLD_OWNER_ELSEWHERE = "owner-elsewhere"
HOLD_FACTORY_UNOBSERVABLE = "factory-unobservable"
HOLD_RUN_LIVE = "run-live"
HOLD_LIVENESS_UNOBSERVABLE = "liveness-unobservable"
HOLD_DISPATCH_LIVE = "dispatch-live"
HOLD_RUN_SUCCEEDED = "run-succeeded"
HOLD_FORGE_UNOBSERVABLE = "forge-unobservable"
HOLD_MERGED_PR = "merged-pr"
HOLD_HISTORY_UNAVAILABLE = "history-unavailable"
HOLD_TERMINAL_EVIDENCE_UNAVAILABLE = "terminal-evidence-unavailable"
HOLD_CLAIM_CHANGED = "claim-changed"
HOLD_EFFECT_UNOBSERVABLE = "effect-unobservable"

# The complete set, ordered. Public so a surface rendering holds can order them
# by the contract's own grading rather than alphabetically, and so one test can
# assert the set is complete instead of asserting fourteen separate literals.
HOLD_REASON_ORDER: tuple[str, ...] = (
    HOLD_CLAIM_UNATTRIBUTABLE,
    HOLD_ATTRIBUTION_PENDING,
    HOLD_OWNER_ELSEWHERE,
    HOLD_FACTORY_UNOBSERVABLE,
    HOLD_RUN_LIVE,
    HOLD_LIVENESS_UNOBSERVABLE,
    HOLD_DISPATCH_LIVE,
    HOLD_RUN_SUCCEEDED,
    HOLD_FORGE_UNOBSERVABLE,
    HOLD_MERGED_PR,
    HOLD_HISTORY_UNAVAILABLE,
    HOLD_TERMINAL_EVIDENCE_UNAVAILABLE,
    HOLD_CLAIM_CHANGED,
    HOLD_EFFECT_UNOBSERVABLE,
)

# The one hold whose entry MUST name its remedy, because a dispatch between
# admission and taking its ownership lock is indistinguishable from a dead one:
# nothing automatic can ever clear it, so the operator valve is the only route.
ATTRIBUTION_PENDING_REMEDY = "drive --action 'move:<work-item-id>:ready'"

# ---------------------------------------------------------------------------
# The measurement vocabularies. Each is a CLOSED set of answers one
# observation may return, and each carries an unobservable member because no
# observation here may report a failure to measure as a negative answer.
# ---------------------------------------------------------------------------

RUN_ABSENT = "absent"
RUN_LIVE = "live"
RUN_SUCCEEDED = "succeeded"
RUN_FAILED = "failed"
RUN_UNOBSERVABLE = "unobservable"

OWNER_NONE = "none"
OWNER_LIVE = "live"
OWNER_UNOBSERVABLE = "unobservable"

FORGE_NO_MERGED_PR = "no-merged-pr"
FORGE_MERGED_PR = "merged-pr"
FORGE_UNOBSERVABLE = "unobservable"

HISTORY_NO_PREDECESSOR = "no-predecessor"
HISTORY_ABSENT_RUN_RELEASE = "absent-run-release"
HISTORY_OTHER_OUTCOME = "other-outcome"
HISTORY_UNAVAILABLE = "unavailable"

# Every status kind under which the factory is reporting a run that has NOT
# ended. `blocked` and `human_input_required` are LIVE here, which is the one
# reading worth stating: Scenario 196 lists "running, blocked or queued" under
# `run-live`, because a run parked at a human gate still holds its claim and
# the blocked-run grace — not this subsection — is what bounds that park.
LIVE_RUN_STATUS_KINDS: frozenset[str] = frozenset(
    {
        "blocked",
        "human_input_required",
        "paused",
        "pending",
        "queued",
        "runnable",
        "running",
        "starting",
    }
)

_SUCCEEDED_RUN_STATUS_KINDS: frozenset[str] = frozenset({"succeeded"})

# ---------------------------------------------------------------------------
# The two absent-run routes. They are PEERS rather than a route and its
# refusal: the release returns the item to the queue and the repeat rests it
# for a human, and which one a claim earns is decided by its predecessor.
# ---------------------------------------------------------------------------

ACTION_ABSENT_RUN_RELEASE = "absent-run-release"
ACTION_ABSENT_RUN_REPEATED = "absent-run-repeated"


@dataclass(frozen=True, kw_only=True)
class ClaimHold:
    """One graded reason this claim was left exactly as it was."""

    reason: str


@dataclass(frozen=True, kw_only=True)
class ClaimRoute:
    """The recovery route this claim earned."""

    action: str


@dataclass(frozen=True, kw_only=True)
class AttributedClaim:
    """A claim this host may act on, with its optionals already resolved.

    Returning the narrowed values rather than re-reading them off the stamp is
    what keeps "past reasons 1-3 the run id and the factory are known" a fact
    about the type instead of an invariant each caller re-asserts.
    """

    stamp: ClaimStamp
    run_id: str
    factory_name: str


@dataclass(frozen=True, kw_only=True)
class ClaimMeasurements:
    """Every measurement the ladder reads, taken before any of it is graded.

    Each field is a CLOSED vocabulary rather than a boolean, because every one
    of them has three answers and not two: the third is always "the
    measurement could not be taken", and a boolean has nowhere to put it.
    """

    attributed: AttributedClaim
    run_state: str
    owner_liveness: str
    forge: str
    predecessor: str


def attribute_claim(
    *,
    stamp: ClaimStamp | None,
    declared_factory: bool,
    this_host: str,
) -> AttributedClaim | ClaimHold:
    """Reasons 1-3: whether this host may act on this claim at all.

    `declared_factory` is a question about CONFIGURATION rather than about the
    stamp's text: a stamp naming a factory this repository no longer declares
    cannot be asked anything, so it is unattributable in exactly the way a
    missing stamp is.
    """
    if stamp is None or stamp.factory_name is None or not declared_factory:
        return ClaimHold(reason=HOLD_CLAIM_UNATTRIBUTABLE)
    run_id = stamp.run_id
    if run_id is None:
        return ClaimHold(reason=HOLD_ATTRIBUTION_PENDING)
    host = stamp.dispatching_host
    if host is None or host == UNKNOWN_DISPATCHING_HOST or host != this_host:
        return ClaimHold(reason=HOLD_OWNER_ELSEWHERE)
    return AttributedClaim(stamp=stamp, run_id=run_id, factory_name=stamp.factory_name)


def run_state_from_inventory(
    *,
    surveyed: bool,
    status_kinds: dict[str, str | None],
    run_id: str,
) -> str:
    """Grade one run against the factory listing this pass already took.

    The listing is `fabro ps -a --json`, which enumerates TERMINAL runs too, so
    a run id absent from a listing the factory DID answer is positively absent
    rather than merely unseen. That positive reading is the whole precondition
    of the absent-run release, which is why `surveyed` is a separate argument:
    an empty mapping from a factory that could not be reached would otherwise
    report every one of its runs as gone.
    """
    if not surveyed:
        return RUN_UNOBSERVABLE
    if run_id not in status_kinds:
        return RUN_ABSENT
    kind = status_kinds[run_id]
    if kind is None:
        return RUN_UNOBSERVABLE
    if kind in LIVE_RUN_STATUS_KINDS:
        return RUN_LIVE
    if kind in _SUCCEEDED_RUN_STATUS_KINDS:
        return RUN_SUCCEEDED
    return RUN_FAILED


def grade_claim(*, measurements: ClaimMeasurements) -> ClaimRoute | ClaimHold:
    """Route or hold one attributed claim, by the first condition that applies."""
    observation = _observation_hold(measurements=measurements)
    if observation is not None:
        return ClaimHold(reason=observation)
    if measurements.run_state == RUN_ABSENT:
        return _absent_run_grade(measurements=measurements)
    # A terminal run that did not succeed is a FAILED one, and completing its
    # disposition needs its recorded failure evidence. Nothing reads that
    # evidence yet, so it is unavailable, which is a hold rather than a verdict.
    return ClaimHold(reason=HOLD_TERMINAL_EVIDENCE_UNAVAILABLE)


def _observation_hold(*, measurements: ClaimMeasurements) -> str | None:
    """Reasons 4-8: what the factory and this host's locks actually report."""
    if measurements.run_state == RUN_UNOBSERVABLE:
        return HOLD_FACTORY_UNOBSERVABLE
    if measurements.run_state == RUN_LIVE:
        return HOLD_RUN_LIVE
    if measurements.owner_liveness == OWNER_UNOBSERVABLE:
        return HOLD_LIVENESS_UNOBSERVABLE
    if measurements.owner_liveness == OWNER_LIVE:
        return HOLD_DISPATCH_LIVE
    if measurements.run_state == RUN_SUCCEEDED:
        return HOLD_RUN_SUCCEEDED
    return None


def _absent_run_grade(*, measurements: ClaimMeasurements) -> ClaimRoute | ClaimHold:
    """Reasons 9-11 and the two absent-run routes.

    The REPEAT test runs last among the three readings because it is the only
    one whose answer is a route rather than a hold: a merged pull request or an
    unreadable history both mean this claim is not the reconciler's to dispose
    of at all, and asking about the predecessor first would decide between two
    routes for a claim that earns neither.
    """
    if measurements.forge == FORGE_UNOBSERVABLE:
        return ClaimHold(reason=HOLD_FORGE_UNOBSERVABLE)
    if measurements.forge == FORGE_MERGED_PR:
        return ClaimHold(reason=HOLD_MERGED_PR)
    if measurements.predecessor == HISTORY_UNAVAILABLE:
        return ClaimHold(reason=HOLD_HISTORY_UNAVAILABLE)
    if measurements.predecessor == HISTORY_ABSENT_RUN_RELEASE:
        return ClaimRoute(action=ACTION_ABSENT_RUN_REPEATED)
    return ClaimRoute(action=ACTION_ABSENT_RUN_RELEASE)
