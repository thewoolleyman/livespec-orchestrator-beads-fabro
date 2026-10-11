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
    "CONDITION_UNIDENTIFIED_BUILD",
    "CURRENCY_WINDOW_DAYS",
    "FABRO_UPSTREAM_REPO",
    "OBSERVATION_MAX_AGE_DAYS",
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
    # THREE FURTHER ARMS SPELT OUT rather than one computed condition, because
    # each of the three also NARROWS a value the arithmetic below needs. A
    # single condition-returning helper leaves the caller holding optionals it
    # has to re-assert, and an `assert` in product code is both banned here and
    # a worse record of the invariant than the branch that established it.
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
    gap = calendar_days_between(earlier=subject.base.published_at, later=newest.published_at)
    if gap > CURRENCY_WINDOW_DAYS:
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
            f" {subject.base.tag} is {gap} calendar days behind {newest.tag}"
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
