"""One dispatch's completed Red-Green cycles, and what each of them measured.

Plan slice S6 (`bd-ib-z2y4ca`). `SPECIFICATION/contracts.md` requires the
Dispatcher to derive current-dispatch progress from its ACTUAL PRESERVED commit
and test-first provenance — including failed and unmerged runs, because
"observing a run that may bounce MUST NOT depend on a successful merge" — and
fixes one completed cycle as one DISTINCT verified Red-Green pair.

WHAT IS AND IS NOT A PAIR, and why each exclusion has its own arm. The
`red_green_replay` hook stamps a Red trailer block at the Red commit and
PRESERVES it through the Green `--amend`, so a completed cycle is ONE commit
carrying BOTH `TDD-Red-Captured-At` and `TDD-Green-Verified-At`. Counting
trailer occurrences instead of commits would double every cycle. An OPEN Red
carries only the Red block and is a cycle that has not completed; a
SUITE-GREEN-ONLY commit carries the `TDD-Suite-Green-*` family and no Red at
all, which is precisely the shape that must never read as a completed cycle;
and a commit carrying neither is unrelated history.

WHY THE PAIR IDENTITY IS THE RED'S OWN EVIDENCE RATHER THAN THE COMMIT SHA.
"Duplicate observations or retries MUST NOT count the same pair again", and a
retry is exactly the case a sha cannot catch: this repository rebase-merges and
a re-dispatch re-authors the same work, so the same Red arrives under a new sha.
The Red test-file checksum plus the preserved Red instant is what the hook
recorded ABOUT THAT RED, so two commits carrying both are two observations of
one pair. A pair whose provenance carries no checksum falls back to the sha,
which still de-duplicates a series that simply listed one commit twice.

WHY ORDER IS THE PRESERVED RED CHRONOLOGY. The ordinal is "one-based" and must
mean the order the cycles were WORKED, which is the order their Reds were
captured — not the order a forge happens to list commits in, and not merge
order. A pair whose Red instant does not parse keeps its arrival position rather
than being dropped, because its COUNT is still evidence even when its timing is
not.

WHY ABSENCE IS A REASON RATHER THAN A ZERO, IN THREE PLACES. The clause requires
unavailable source trees, unsupported counting, incomplete provenance and
invalid or reversed timestamps to be "exposed as unobserved with a reason for
the affected measurement, never substituted with zero or a fabricated
duration" — and separately requires that "an unavailable individual size/time
measurement MUST NOT erase an otherwise independently established completed-pair
count". So a cycle holds its two measurements independently, each either a number
or an `Unobserved` carrying its reason, while the cycle itself still counts.

And the SERIES has a third state the two above cannot express: "the comparison
MUST distinguish an observed empty series from a series which could not be
read". `observed_series(cycles=())` is a run that authored no completed cycle —
a finding. `unreadable_series(...)` is a run whose provenance could not be
reached — not a finding about the run at all. Collapsing them would report every
unreachable provenance as a total progress deficit, which is the manufactured
breach this module exists to avoid.

This module is PURE: no IO, no environment reads, and it never raises. The git
and forge reads that supply its inputs live in `_dispatcher_cycle_probe`.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_commits import (
    GREEN_TRAILER_KEY,
    RED_TRAILER_KEY,
    commit_trailers,
    trailer_instant,
)

__all__: list[str] = [
    "UNOBSERVED_COUNTING",
    "UNOBSERVED_PROVENANCE",
    "UNOBSERVED_SOURCE_TREE",
    "UNOBSERVED_TIMESTAMPS",
    "UNREADABLE_PROVENANCE",
    "CompletedCycle",
    "CompletedCycleSeries",
    "CycleSource",
    "ProvenanceCommit",
    "Unobserved",
    "completed_cycle",
    "elapsed_cycle_seconds",
    "observed_series",
    "unreadable_series",
    "verified_pairs",
]

# The four per-measurement absence reasons the clause enumerates, spelled once.
# They ride the journal and the span verbatim, so an operator reading a null
# learns WHICH measurement could not be taken rather than only that one was not.
UNOBSERVED_SOURCE_TREE = "source-tree-unavailable"
UNOBSERVED_COUNTING = "unsupported-counting"
UNOBSERVED_PROVENANCE = "incomplete-provenance"
UNOBSERVED_TIMESTAMPS = "invalid-or-reversed-timestamps"

# The SERIES-level absence reason: the provenance itself could not be read, so
# there is no count — distinct from a readable provenance holding no pair.
UNREADABLE_PROVENANCE = "provenance-unreadable"

# The Red trailer that identifies WHICH Red a pair completed. Restated here for
# the reason `_dispatcher_tdd_commits` restates the other three: the keys are
# module-private to the dev-tooling check that writes them, and the shipped
# plugin package must not depend on that package at all.
_RED_TEST_CHECKSUM_TRAILER_KEY = "TDD-Red-Test-File-Checksum"


@dataclass(frozen=True, kw_only=True)
class Unobserved:
    """One measurement that could not be taken, and why.

    A value rather than `None` so the reason travels WITH the absence: a bare
    `None` reaching the journal would record that nothing was measured while
    discarding the only thing that tells an operator whether to fix a probe, a
    clock or a counter.
    """

    reason: str


@dataclass(frozen=True, kw_only=True)
class ProvenanceCommit:
    """One commit of the dispatch's own series, as its provenance was read."""

    sha: str
    message: str


@dataclass(frozen=True, kw_only=True)
class CycleSource:
    """One distinct verified Red-Green pair, before its measurements are taken.

    `pair_id` is the identity duplicates and retries are collapsed on, and it is
    retained on the record so an operator can replay which pair a measurement
    belongs to rather than inferring it from a sha that a rebase will not
    preserve.
    """

    commit: str
    pair_id: str
    red_captured_at: str
    green_verified_at: str


@dataclass(frozen=True, kw_only=True)
class CompletedCycle:
    """One completed cycle's ordinal, identity and two measurements.

    Each measurement is EITHER a number or an absent value paired with its
    reason, never a zero standing in for an absence. The two are independent:
    a cycle whose size could not be counted still reports its elapsed seconds,
    and either way the cycle counts toward the completed-pair total.
    """

    ordinal: int
    pair_id: str
    commit: str
    product_lloc_changed: int | None
    product_lloc_unobserved_reason: str | None
    elapsed_seconds: int | None
    elapsed_unobserved_reason: str | None


@dataclass(frozen=True, kw_only=True)
class CompletedCycleSeries:
    """This dispatch's completed-cycle series, plus the dispatched assertion count.

    `unreadable_reason` is `None` for a series that WAS read, however empty, and
    carries the reason for one that was not. `completed_count` follows it: a
    readable series reports its length (zero included) and an unreadable one
    reports `None`, which is what keeps an unreachable provenance from reading
    as a zero-cycle deficit.

    `assertion_count` is `None` when the dispatched criteria could not be
    parsed, for the same reason — the clause requires the progress comparison to
    be "reported unobserved rather than as a zero-count deficit" when either
    side cannot be established.
    """

    cycles: tuple[CompletedCycle, ...]
    assertion_count: int | None
    unreadable_reason: str | None

    @property
    def observed(self) -> bool:
        """Whether the series was read at all."""
        return self.unreadable_reason is None

    @property
    def completed_count(self) -> int | None:
        """The completed-pair count, or None when the series could not be read."""
        return len(self.cycles) if self.observed else None


def verified_pairs(*, commits: tuple[ProvenanceCommit, ...]) -> tuple[CycleSource, ...]:
    """The distinct verified Red-Green pairs in one dispatch's commit series.

    `commits` is already this dispatch's OWN series — the caller selects it by
    the `Factory-Run-Id` trailer — so unrelated history is excluded upstream by
    identity as well as here by trailer shape.

    Ordered by the preserved Red instant, with an unparseable instant keeping its
    arrival position (sorted last among its parseable siblings rather than
    dropped). The sort is STABLE, so two Reds captured in the same second keep
    the order the provenance listed them in.
    """
    found: dict[str, tuple[int, CycleSource]] = {}
    for index, commit in enumerate(commits):
        trailers = commit_trailers(message=commit.message)
        red_at = trailers.get(RED_TRAILER_KEY)
        green_at = trailers.get(GREEN_TRAILER_KEY)
        if red_at is None or green_at is None:
            continue
        checksum = trailers.get(_RED_TEST_CHECKSUM_TRAILER_KEY)
        pair_id = f"{checksum}@{red_at}" if checksum is not None else f"commit:{commit.sha}"
        if pair_id in found:
            continue
        found[pair_id] = (
            index,
            CycleSource(
                commit=commit.sha,
                pair_id=pair_id,
                red_captured_at=red_at,
                green_verified_at=green_at,
            ),
        )
    return tuple(
        source for _, source in sorted(found.values(), key=lambda entry: _red_order(entry=entry))
    )


def elapsed_cycle_seconds(*, red_at: str, green_at: str) -> int | Unobserved:
    """The cycle's elapsed seconds, or the unobserved verdict with its reason.

    "Elapsed seconds MUST be the nonnegative interval from the preserved Red
    capture time to the verified Green time, not later merge timestamps." A
    reversed interval is therefore not a negative duration to be clamped — a
    clamp would publish a fabricated zero — and an unparseable instant is not a
    duration at all. Both are the same unobserved verdict because both say the
    same thing: this pair's timing cannot be trusted.
    """
    red_instant = trailer_instant(value=red_at)
    green_instant = trailer_instant(value=green_at)
    if red_instant is None or green_instant is None:
        return Unobserved(reason=UNOBSERVED_TIMESTAMPS)
    elapsed = (green_instant - red_instant).total_seconds()
    if elapsed < 0:
        return Unobserved(reason=UNOBSERVED_TIMESTAMPS)
    return round(elapsed)


def completed_cycle(
    *, ordinal: int, source: CycleSource, product_lloc: int | Unobserved
) -> CompletedCycle:
    """One completed cycle, with its size measurement taken by the caller.

    The size comes IN because measuring it needs the two source trees, which is
    IO; the elapsed interval is derived here because the preserved instants are
    already part of the pair's provenance.
    """
    elapsed = elapsed_cycle_seconds(
        red_at=source.red_captured_at, green_at=source.green_verified_at
    )
    return CompletedCycle(
        ordinal=ordinal,
        pair_id=source.pair_id,
        commit=source.commit,
        product_lloc_changed=None if isinstance(product_lloc, Unobserved) else product_lloc,
        product_lloc_unobserved_reason=(
            product_lloc.reason if isinstance(product_lloc, Unobserved) else None
        ),
        elapsed_seconds=None if isinstance(elapsed, Unobserved) else elapsed,
        elapsed_unobserved_reason=elapsed.reason if isinstance(elapsed, Unobserved) else None,
    )


def observed_series(
    *, cycles: tuple[CompletedCycle, ...], assertion_count: int | None
) -> CompletedCycleSeries:
    """A series that WAS read — possibly holding no completed cycle."""
    return CompletedCycleSeries(
        cycles=cycles, assertion_count=assertion_count, unreadable_reason=None
    )


def unreadable_series(*, reason: str, assertion_count: int | None) -> CompletedCycleSeries:
    """A series that could not be read, carrying why rather than a zero count."""
    return CompletedCycleSeries(
        cycles=(), assertion_count=assertion_count, unreadable_reason=reason
    )


def _red_order(*, entry: tuple[int, CycleSource]) -> tuple[int, float, int]:
    """The sort key preserving Red chronology, with unparseable instants last.

    The leading flag is what puts an unparseable instant after every parseable
    one without inventing a timestamp for it; the arrival index is the stable
    tiebreak for two Reds sharing one instant.
    """
    index, source = entry
    instant = trailer_instant(value=source.red_captured_at)
    if instant is None:
        return (1, 0.0, index)
    return (0, instant.timestamp(), index)
