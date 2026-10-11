"""Fabro currency admission, as a PURE predicate over one factory target.

The decision half of the Fabro-currency-admission clause of
`SPECIFICATION/contracts.md` and the exact-upstream-base-and-bounded-currency
clause of `SPECIFICATION/constraints.md`, bound by `SPECIFICATION/scenarios.md`
"Scenario 130 — Dispatch admits only a current, identifiable Fabro base".

WHY THE SPLIT RUNS HERE. The rule is a pure function of one target's serving
commit, the base resolved for it and one upstream release observation; the reads
that produce those three are `_dispatcher_fabro_currency_sources`, and a rule
that reached for the engine and the forge itself could not be exercised across
the states the clause distinguishes without a double for both.

EVERY REFUSAL CARRIES THE WHOLE EVIDENCE BLOCK, not only the fact that failed.
The clause enumerates seven things a refusal must name — the target, the serving
integration commit when known, the base and its publication time when one
exists, the newest observed release and its publication time, the observation
time, the failed condition and the corrective route — and an operator reading
"out of window" alone cannot tell which of them to act on. Rendering one block
for every condition is also what keeps the conditions from drifting into
differently-informative messages.

PUBLICATION TIME IS THE ONLY ORDERING EVIDENCE. `constraints.md` says so in as
many words, and the consequence is that nothing here may read a semantic version
or a commit timestamp: upstream publishes nightly prerelease tags whose
semantic-version order and publication order routinely disagree, so a
semver-ordered reading would pick a base nobody is serving and compare it to a
newest release nobody published last.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

__all__: list[str] = [
    "CONDITION_CURRENT",
    "CONDITION_NO_ANCESTOR",
    "CONDITION_OBSERVATION_UNOBSERVABLE",
    "CONDITION_OUT_OF_WINDOW",
    "CONDITION_STALE_OBSERVATION",
    "CONDITION_TRANSITION_ADMITTED",
    "CONDITION_UNIDENTIFIED_BUILD",
    "CURRENCY_WINDOW_DAYS",
    "FABRO_UPSTREAM_REPO",
    "OBSERVATION_MAX_AGE_DAYS",
    "TRANSITION_BASE_SERIES",
    "TRANSITION_DEADLINE",
    "TRANSITION_WORK_ITEM",
    "FabroCurrencySubject",
    "FabroCurrencyVerdict",
    "FabroRelease",
    "FabroReleaseObservation",
    "calendar_days_between",
    "fabro_currency_verdict",
    "newest_observed_release",
]

# The upstream repository whose GitHub Releases surface is the ONLY admissible
# source of a base tag. A moving branch, an untagged commit or a locally
# invented version is not a base, so there is deliberately no second source.
FABRO_UPSTREAM_REPO = "fabro-sh/fabro"

# The ratified window and observation bounds, in CALENDAR days.
CURRENCY_WINDOW_DAYS = 30
OBSERVATION_MAX_AGE_DAYS = 7

CONDITION_CURRENT = "current"
CONDITION_OUT_OF_WINDOW = "base-out-of-window"

# THREE DISTINCT WAYS A READING CAN FAIL TO BE TAKEN, each its own condition,
# because the three have DIFFERENT REMEDIES and refuse the same dispatch. An
# unreadable releases surface is waited out; an unidentifiable serving build is
# a fault on one factory host; a build with no release-tag ancestor is re-pinned
# onto a published tag. A single generic condition refuses correctly and then
# makes the operator guess which of the three they have.
CONDITION_OBSERVATION_UNOBSERVABLE = "release-observation-unobservable"
CONDITION_UNIDENTIFIED_BUILD = "serving-build-unidentified"
CONDITION_NO_ANCESTOR = "no-release-tag-ancestor"

# A reading that EXISTS and is past its bound, separate from one that could not
# be taken at all. Both refuse; the remedies differ, because a stale record says
# the refresh path is broken while evidence exists, and an absent one says no
# evidence has ever been taken on this host.
CONDITION_STALE_OBSERVATION = "release-observation-stale"

# The ONE window exception, and it is ADMITTED rather than `current`: the clause
# requires an out-of-window carrier to be surfaced as a transition and never
# silently described as in-window, so it cannot share the ordinary admitted
# condition.
CONDITION_TRANSITION_ADMITTED = "transition-admitted"

# THE EXCEPTION'S THREE LITERALS, AND THEY ARE RATIFIED RATHER THAN CONFIGURED.
# A deadline an operator could move is a deadline that would be moved, which is
# exactly the indefinite 0.254 freeze `constraints.md` forbids in as many words —
# so there is deliberately no key, no environment variable and no override for
# any of these. Changing them is a specification change.
TRANSITION_BASE_SERIES = "0.254"
TRANSITION_DEADLINE = datetime(2026, 11, 14, 0, 0, tzinfo=timezone.utc)
TRANSITION_WORK_ITEM = "bd-ib-6tcjfx"

_UNKNOWN = "unknown"

# The one remedy every refusal here points at. Named once so the six conditions
# cannot drift into six differently-worded routes to the same act.
_CORRECTIVE_ROUTE = (
    "re-pin the selected factory's fabro build onto a published"
    f" {FABRO_UPSTREAM_REPO} release tag within {CURRENCY_WINDOW_DAYS} calendar days of the"
    " newest release (orchestrator-image/README.md), then re-dispatch"
)


@dataclass(frozen=True, kw_only=True)
class FabroRelease:
    """One published upstream release: its exact tag and its publication time."""

    tag: str
    published_at: datetime


@dataclass(frozen=True, kw_only=True)
class FabroReleaseObservation:
    """One reading of the upstream releases surface, and when it was taken.

    `observed_at` is a property of the READING rather than of any release in it,
    which is why it is here and not on `FabroRelease`: the clause bounds how old
    the reading may be, and a per-release timestamp cannot answer that.
    """

    releases: tuple[FabroRelease, ...]
    observed_at: datetime


@dataclass(frozen=True, kw_only=True)
class FabroCurrencySubject:
    """One factory target as the gathering layer measured it.

    Every field but `target` is optional because every one of them is a
    MEASUREMENT that can fail, and the clause requires a refusal naming which
    one did. A subject that collapsed an unmeasured field onto a plausible
    default would admit on evidence nobody took.
    """

    target: str
    serving_commit: str | None
    base: FabroRelease | None
    observation: FabroReleaseObservation | None
    unobservable_detail: str | None
    # Why the release reading could not be USED, when it could not. Separate
    # from `unobservable_detail` — which carries the PER-TARGET gather fault —
    # because an observation can be PRESENT and unusable at the same time, and
    # that pair is the one state the two-field shape exists to represent: a
    # record the refusal must name while never treating it as evidence. Folding
    # them into one field loses exactly that distinction, which is the
    # fail-open this field closed.
    observation_failure: str | None


@dataclass(frozen=True, kw_only=True)
class FabroCurrencyVerdict:
    """The predicate's answer for one target: admitted or not, and why."""

    target: str
    condition: str
    admitted: bool
    detail: str


def calendar_days_between(*, earlier: datetime, later: datetime) -> int:
    """Whole CALENDAR days from `earlier` to `later`, both read in UTC.

    Calendar days rather than 24-hour spans because the clause is written in
    calendar days: two instants nineteen hours apart that straddle midnight are
    one calendar day apart, and a seconds-based reading would call them zero.
    """
    return (later.astimezone(timezone.utc).date() - earlier.astimezone(timezone.utc).date()).days


def newest_observed_release(*, observation: FabroReleaseObservation) -> FabroRelease | None:
    """The newest release in one observation, or `None` when it holds none.

    "Newest" is the forge's own enumeration order at this point: the releases
    endpoint returns most-recent-first, so the head of the list is the newest
    release the reading saw.
    """
    if not observation.releases:
        return None
    return observation.releases[0]


def fabro_currency_verdict(*, subject: FabroCurrencySubject, now: datetime) -> FabroCurrencyVerdict:
    """Whether `subject`'s serving build may be dispatched onto, and why.

    FAIL-CLOSED IN EVERY ARM THAT COULD NOT MEASURE. A gauge that admitted when
    blinded would turn this refusal into a pass and leave a journal record that
    reads exactly like a healthy one, which is the one direction a dispatch
    admission gate must never fail in.

    THE FOUR COULD-NOT-MEASURE ARMS ARE SPELT OUT HERE rather than computed by a
    helper, because each of them also NARROWS a value `_window_verdict` needs. A
    condition-returning helper leaves this function holding optionals it has to
    re-assert, and an `assert` in product code is both banned here and a worse
    record of the invariant than the branch that established it.
    """
    newest = _newest(observation=subject.observation)
    # THE UNUSABLE-READING ARM RUNS FIRST, AND IT IS THE FAIL-CLOSED ONE. A
    # stale observation still carries releases, a newest entry and plausible
    # ancestry, so every arm below it would succeed on expired evidence and
    # report `current` — measured, before this arm existed, as an admitted
    # dispatch on a nine-day-old reading. The two conditions it can raise are
    # told apart by whether a record EXISTS to be named.
    if subject.observation_failure is not None:
        return _refusal(
            subject=subject,
            newest=newest,
            now=now,
            condition=(
                CONDITION_STALE_OBSERVATION
                if subject.observation is not None
                else CONDITION_OBSERVATION_UNOBSERVABLE
            ),
            clause=subject.observation_failure,
        )
    # THE REMAINING ORDER IS LOAD-BEARING and matches the gathering layer's own:
    # the release observation is graded before the serving build because an
    # absent one makes the base question unanswerable for EVERY target, while an
    # unidentified serving build is a fault on one host — so reporting the
    # per-target fault while the shared one stands sends the operator to the
    # wrong place. The missing base is last because it is the only one of the
    # three that presupposes the other two were measured.
    if newest is None:
        return _unmeasured(
            subject=subject, newest=None, now=now, condition=CONDITION_OBSERVATION_UNOBSERVABLE
        )
    if subject.serving_commit is None:
        return _unmeasured(
            subject=subject, newest=newest, now=now, condition=CONDITION_UNIDENTIFIED_BUILD
        )
    if subject.base is None:
        return _unmeasured(subject=subject, newest=newest, now=now, condition=CONDITION_NO_ANCESTOR)
    return _window_verdict(subject=subject, base=subject.base, newest=newest, now=now)


def _window_verdict(
    *,
    subject: FabroCurrencySubject,
    base: FabroRelease,
    newest: FabroRelease,
    now: datetime,
) -> FabroCurrencyVerdict:
    """The publication-window comparison, once every input has been measured.

    Split from the ladder above by COHESION rather than by line count: that
    function decides whether the three measurements exist, and this one is the
    only arithmetic in the module. It takes `base` and `newest` as NON-optional
    parameters, which is what lets the split happen without re-asserting
    anything the caller already established.
    """
    gap = calendar_days_between(earlier=base.published_at, later=newest.published_at)
    if gap > CURRENCY_WINDOW_DAYS:
        # The exception is asked ONLY of a base that has already failed the
        # ordinary rule, which is what keeps it an exception: a carrier inside
        # the window is admitted as `current` and carries no transition notice,
        # because there is nothing to transition away from yet.
        if _within_transition(base=base, now=now):
            return _transition(subject=subject, base=base, newest=newest, gap=gap)
        return _refusal(
            subject=subject,
            newest=newest,
            now=now,
            condition=CONDITION_OUT_OF_WINDOW,
            clause=(
                f"the base was published {gap} calendar days before the newest observed"
                f" release; the window is {CURRENCY_WINDOW_DAYS}"
            ),
        )
    return FabroCurrencyVerdict(
        target=subject.target,
        condition=CONDITION_CURRENT,
        admitted=True,
        detail=(
            f"Fabro currency admitted for factory target {subject.target!r}: base"
            f" {base.tag} is {gap} calendar days behind {newest.tag}"
        ),
    )


def _within_transition(*, base: FabroRelease, now: datetime) -> bool:
    """Whether `base` is the carrier AND the deadline has not yet arrived.

    The comparison is STRICTLY LESS THAN the deadline, so the ratified instant
    itself already refuses: the clause says the carrier may remain in service
    "before" that instant and that at or after it the ordinary rule applies, and
    an inclusive comparison would hand the exception one extra day.
    """
    return _is_transition_carrier(tag=base.tag) and now < TRANSITION_DEADLINE


def _is_transition_carrier(*, tag: str) -> bool:
    """Whether a release tag names the 0.254 series.

    The leading `v` is optional because upstream has published both spellings,
    and the match is on the SERIES rather than on one exact tag: the carrier has
    had patch releases, and an exact-tag test would quietly drop the exception
    the first time one landed.
    """
    numeric = tag.removeprefix("v")
    return numeric == TRANSITION_BASE_SERIES or numeric.startswith(f"{TRANSITION_BASE_SERIES}.")


def _transition(
    *,
    subject: FabroCurrencySubject,
    base: FabroRelease,
    newest: FabroRelease,
    gap: int,
) -> FabroCurrencyVerdict:
    """The admitted transition, which STATES the gap it is excusing.

    The gap is in the text deliberately. An admitted transition that reported
    only "admitted" would be indistinguishable at every surface from an
    in-window base, which is the one description the clause forbids it.
    """
    return FabroCurrencyVerdict(
        target=subject.target,
        condition=CONDITION_TRANSITION_ADMITTED,
        admitted=True,
        detail=(
            f"NOTICE: Fabro currency admitted factory target {subject.target!r} as the"
            f" {TRANSITION_WORK_ITEM} transition, NOT as an in-window base: the"
            f" {TRANSITION_BASE_SERIES} carrier {base.tag} was published {gap} calendar days"
            f" before {newest.tag}, against a {CURRENCY_WINDOW_DAYS}-calendar-day window."
            f" This one non-renewable exception expires at"
            f" {TRANSITION_DEADLINE.isoformat()}, after which this dispatch is refused on"
            f" the ordinary rule; re-pin the factory onto a current"
            f" {FABRO_UPSTREAM_REPO} release before then."
        ),
    )


def _unmeasured(
    *,
    subject: FabroCurrencySubject,
    newest: FabroRelease | None,
    now: datetime,
    condition: str,
) -> FabroCurrencyVerdict:
    """One of the three could-not-measure refusals, carrying the gather's clause.

    The gathering layer's own account of what failed is carried through VERBATIM
    rather than re-worded per condition: the ladder cannot tell an unreachable
    forge from a stale cache or an unidentified engine, and a second account of
    one measurement would be the one a reader trusts instead of the measurement.
    """
    return _refusal(
        subject=subject,
        newest=newest,
        now=now,
        condition=condition,
        clause=subject.unobservable_detail or "the currency reading could not be taken",
    )


def _newest(*, observation: FabroReleaseObservation | None) -> FabroRelease | None:
    if observation is None:
        return None
    return newest_observed_release(observation=observation)


def _refusal(
    *,
    subject: FabroCurrencySubject,
    newest: FabroRelease | None,
    now: datetime,
    condition: str,
    clause: str,
) -> FabroCurrencyVerdict:
    """One refusal, carrying the whole evidence block the clause enumerates."""
    return FabroCurrencyVerdict(
        target=subject.target,
        condition=condition,
        admitted=False,
        detail=_evidence(
            subject=subject, newest=newest, now=now, condition=condition, clause=clause
        ),
    )


def _evidence(
    *,
    subject: FabroCurrencySubject,
    newest: FabroRelease | None,
    now: datetime,
    condition: str,
    clause: str,
) -> str:
    lines = (
        f"ERROR: Fabro currency admission refused for factory target {subject.target!r}: {clause}",
        f"  factory target: {subject.target}",
        f"  serving integration commit: {subject.serving_commit or _UNKNOWN}",
        f"  upstream base: {_release(release=subject.base)}",
        f"  newest observed upstream release: {_release(release=newest)}",
        f"  release observation taken at: {_observed_at(observation=subject.observation)}",
        f"  currency evaluated at: {_instant(value=now)}",
        f"  failed currency condition: {condition}",
        f"  corrective route: {_CORRECTIVE_ROUTE}",
    )
    return "\n".join(lines) + "\n"


def _observed_at(*, observation: FabroReleaseObservation | None) -> str:
    if observation is None:
        return _UNKNOWN
    return _instant(value=observation.observed_at)


def _release(*, release: FabroRelease | None) -> str:
    if release is None:
        return _UNKNOWN
    return f"{release.tag} published {_instant(value=release.published_at)}"


def _instant(*, value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()
