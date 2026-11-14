"""One dispatch's distinct verified Red-Green pairs, counted from its own provenance.

Plan slice S6 (`bd-ib-z2y4ca`), part one: PAIR ENUMERATION ONLY.
`SPECIFICATION/contracts.md` requires the Dispatcher to derive current-dispatch
progress from its ACTUAL PRESERVED commit and test-first provenance — including
failed and unmerged runs, because "observing a run that may bounce MUST NOT
depend on a successful merge" — and fixes one completed cycle as one DISTINCT
verified Red-Green pair. Measuring each pair (its logical-line size and its
Red-to-Green interval) is the next slice's job and is deliberately absent here.

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
one pair. A pair whose provenance carries no checksum falls back to its whole
message, which still de-duplicates a series that simply listed one commit twice.

WHY ABSENCE IS A REASON RATHER THAN A ZERO. "The comparison MUST distinguish an
observed empty series from a series which could not be read."
`observed_pair_count` over a series holding no pair is a run that authored no
completed cycle — a finding. `unobserved_pair_count` is a run whose provenance
could not be reached — not a finding about the run at all. Collapsing them would
report every unreachable provenance as a total progress deficit, which is the
manufactured breach this module exists to avoid.

This module is PURE: no IO, no environment reads, and it never raises. The
`gh` read that supplies its messages lives in `_dispatcher_tdd_probe`.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_commits import (
    GREEN_TRAILER_KEY,
    RED_TRAILER_KEY,
    commit_trailers,
)

__all__: list[str] = [
    "UNOBSERVED_COMMITS_UNREADABLE",
    "UNOBSERVED_NO_DISPATCH_ID",
    "UNOBSERVED_NO_PULL_REQUEST",
    "UNOBSERVED_SERIES_NOT_IDENTIFIED",
    "VerifiedPairCount",
    "observed_pair_count",
    "unobserved_pair_count",
    "verified_pair_ids",
]

# The series-level absence reasons, spelled once. They ride the journal and the
# span verbatim, so an operator reading a null learns WHICH read could not be
# taken rather than only that one was not.
UNOBSERVED_NO_PULL_REQUEST = "no-pull-request"
UNOBSERVED_NO_DISPATCH_ID = "no-dispatch-id"
UNOBSERVED_COMMITS_UNREADABLE = "commits-unreadable"
UNOBSERVED_SERIES_NOT_IDENTIFIED = "series-not-identified"

# The Red trailer that identifies WHICH Red a pair completed. Restated here for
# the reason `_dispatcher_tdd_commits` restates the other keys: it is
# module-private to the dev-tooling check that writes it, and the shipped plugin
# package must not depend on that package at all.
_RED_TEST_CHECKSUM_TRAILER_KEY = "TDD-Red-Test-File-Checksum"


@dataclass(frozen=True, kw_only=True)
class VerifiedPairCount:
    """One dispatch's verified-pair count, or why it could not be established.

    Exactly one of the two fields is set. `count` is `0` for a series that WAS
    read and held no pair, and `None` only alongside the reason a series could
    not be read, which is what keeps an unreachable provenance from reading as a
    zero-cycle deficit.
    """

    count: int | None
    unobserved_reason: str | None


def verified_pair_ids(*, messages: tuple[str, ...]) -> tuple[str, ...]:
    """The distinct verified Red-Green pairs in one dispatch's commit messages.

    `messages` is already this dispatch's OWN series — the caller selects it by
    the `Factory-Run-Id` trailer — so unrelated history is excluded upstream by
    identity as well as here by trailer shape. Each identity is returned once, in
    the order its pair first arrived.
    """
    found: dict[str, None] = {}
    for message in messages:
        trailers = commit_trailers(message=message)
        red_at = trailers.get(RED_TRAILER_KEY)
        if red_at is None or GREEN_TRAILER_KEY not in trailers:
            continue
        checksum = trailers.get(_RED_TEST_CHECKSUM_TRAILER_KEY)
        found[f"{checksum}@{red_at}" if checksum is not None else f"message:{message}"] = None
    return tuple(found)


def observed_pair_count(*, messages: tuple[str, ...]) -> VerifiedPairCount:
    """The count over a series that WAS read — possibly holding no pair."""
    return VerifiedPairCount(
        count=len(verified_pair_ids(messages=messages)), unobserved_reason=None
    )


def unobserved_pair_count(*, reason: str) -> VerifiedPairCount:
    """The count of a series that could not be read, carrying why rather than a zero."""
    return VerifiedPairCount(count=None, unobserved_reason=reason)
