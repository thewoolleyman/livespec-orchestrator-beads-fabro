"""Commit-series derivation of one dispatch's TDD order signals.

Plan `factory-test-first-enforcement` slice S3 (work-item `bd-ib-3h5vfq`) puts
seven `tdd.*` fields on the terminal `dispatcher.calibration` span. FOUR of
them are derived HERE, from the dispatch's own commit series:
`tdd.red_commit_count`, `tdd.green_commit_count`, `tdd.suite_green_count` and
`tdd.red_green_gap_seconds_median`. The remaining three come from the
sandbox-side order guard's decision spans (`_dispatcher_tdd_order_sink`) and
from the sanctioned acceptance-criteria parser.

WHY THE GAP MEDIAN IS THE LOAD-BEARING NUMBER. The `red_green_replay` hook
sees staged bytes at exactly two moments, so a commit shape produced AFTER the
implementation was written is byte-identical to one produced test-first. What
DOES differ is the interval between `TDD-Red-Captured-At` and
`TDD-Green-Verified-At`: genuine test-first work spends the implementation
time inside that interval, while the stash-and-unstash dance spends seconds in
it. The fleet-wide measurement that motivated the whole plan is recorded in
`plan/factory-test-first-enforcement/research/opening-research-2026-09-30.md`
(median 197s across 147 product-touching commits).

THREE DERIVATION RULES THAT ARE EASY TO GET WRONG, each asserted by the paired
test:

1. **A GREEN-AMENDED COMMIT RETAINS BOTH TRAILER SETS.** The Green step is a
   `git commit --amend` that PRESERVES the Red block, so one commit carries
   `TDD-Red-Captured-At` AND `TDD-Green-Verified-At`. It is ONE Red and ONE
   Green — counting trailer occurrences as commits would double the series.
   An OPEN Red (a Red not yet amended) carries only the Red trailer.
2. **THE SUITE-GREEN LEG IS A DIFFERENT TRAILER FAMILY.** `red_green_replay`
   leg 5 stamps `TDD-Suite-Green-*` on product code that carries no Red at
   all. It is counted separately rather than folded into the Green count,
   because conflating them would report a no-Red commit as a completed cycle.
3. **AN UNPARSEABLE INSTANT CONTRIBUTES NO SAMPLE.** A commit whose trailer
   instants do not parse is omitted from the gap samples, and a series with no
   parseable pair reports `None`. Absent telemetry is UNKNOWN, never zero
   evidence — a zero-second gap is exactly the post-hoc signature, so
   inventing one would manufacture the finding this span exists to measure.

A clock-skewed NEGATIVE gap is deliberately NOT filtered. Dropping it would be
a silent filter on the very distribution under study; it is kept as the sample
it is, and the derived column's threshold reads it as post-hoc, which is the
honest reading of a Green stamped before its Red.

This module is PURE: no IO, no environment reads, and it never raises. The
`gh pr view --json commits` probe that supplies `messages` lives in
`_dispatcher_calibration_emit`, so the derivation stays directly testable.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    JsonParseFailure,
    attempt,
    parse_json,
)

__all__: list[str] = [
    "GREEN_TRAILER_KEY",
    "RED_TRAILER_KEY",
    "SUITE_GREEN_TRAILER_KEY",
    "TddCommitSignals",
    "commit_trailers",
    "parse_commit_messages",
    "tdd_commit_signals",
]

# The three trailer keys `livespec_dev_tooling.checks.red_green_replay` writes.
# Restated here rather than imported: they are module-private to that check,
# and the shipped plugin package must not depend on the dev-tooling package at
# all. The paired test pins the exact spellings against real commit bodies.
RED_TRAILER_KEY = "TDD-Red-Captured-At"
GREEN_TRAILER_KEY = "TDD-Green-Verified-At"
SUITE_GREEN_TRAILER_KEY = "TDD-Suite-Green-Captured-At"

# A git trailer line: a key of letters, digits and hyphens, a colon, a space,
# then the value. Anchored at the line start so prose containing a colon mid
# sentence cannot be read as a trailer.
_TRAILER_RE = re.compile(r"(?m)^([A-Za-z][A-Za-z0-9-]*):[ \t]*(.*)$")

_UTC_SUFFIX = "Z"
_UTC_OFFSET = "+00:00"


@dataclass(frozen=True, kw_only=True)
class TddCommitSignals:
    """The four commit-derived TDD order signals for one dispatch.

    `red_green_gap_seconds_median` is `None` when the series carries no
    parseable Red→Green pair — an unobservable median, never a zero one.
    """

    red_commit_count: int
    green_commit_count: int
    suite_green_count: int
    red_green_gap_seconds_median: float | None


def tdd_commit_signals(*, messages: tuple[str, ...]) -> TddCommitSignals:
    """Derive the four commit signals from one dispatch's commit messages.

    Counts commits, NOT trailer occurrences: a Green-amended commit carries
    both trailer sets and contributes one Red, one Green and one gap sample.
    """
    red = 0
    green = 0
    suite_green = 0
    gaps: list[float] = []
    for message in messages:
        trailers = commit_trailers(message=message)
        red_at = trailers.get(RED_TRAILER_KEY)
        green_at = trailers.get(GREEN_TRAILER_KEY)
        red += 1 if red_at is not None else 0
        green += 1 if green_at is not None else 0
        suite_green += 1 if SUITE_GREEN_TRAILER_KEY in trailers else 0
        gap = _gap_seconds(red_at=red_at, green_at=green_at)
        if gap is not None:
            gaps.append(gap)
    return TddCommitSignals(
        red_commit_count=red,
        green_commit_count=green,
        suite_green_count=suite_green,
        red_green_gap_seconds_median=statistics.median(gaps) if gaps else None,
    )


def commit_trailers(*, message: str) -> dict[str, str]:
    """The trailer key/value pairs one commit message carries.

    The FIRST occurrence of a key wins. A commit carries each TDD trailer at
    most once in practice, and first-wins keeps the result deterministic for a
    malformed body rather than letting a trailing duplicate silently override
    the authoritative value the hook wrote.
    """
    trailers: dict[str, str] = {}
    for match in _TRAILER_RE.finditer(message):
        key = match.group(1)
        if key not in trailers:
            trailers[key] = match.group(2).strip()
    return trailers


def parse_commit_messages(*, stdout: str) -> tuple[str, ...] | None:
    """The commit messages in a `gh pr view <pr> --json commits` payload.

    Returns `None` — unobservable — for an unparseable payload, a payload that
    is not an object, or one whose `commits` key is not a list. An entry that
    is not an object, or whose headline is not a string, is SKIPPED rather than
    failing the whole read: one odd entry must not blind the series.

    Each message is rebuilt as `<headline>\\n\\n<body>`, the shape `git log %B`
    produces, so the trailer scan above reads a `gh`-sourced series exactly as
    it reads a git-sourced one.
    """
    parsed = parse_json(text=stdout)
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return None
    raw_commits = cast("dict[str, object]", parsed).get("commits")
    if not isinstance(raw_commits, list):
        return None
    messages: list[str] = []
    for raw in cast("list[object]", raw_commits):
        if not isinstance(raw, dict):
            continue
        entry = cast("dict[str, object]", raw)
        headline = entry.get("messageHeadline")
        if not isinstance(headline, str):
            continue
        body = entry.get("messageBody")
        messages.append(f"{headline}\n\n{body if isinstance(body, str) else ''}")
    return tuple(messages)


def _gap_seconds(*, red_at: str | None, green_at: str | None) -> float | None:
    """The Red→Green interval in seconds, or None when either end is absent."""
    if red_at is None or green_at is None:
        return None
    red_instant = _instant(value=red_at)
    green_instant = _instant(value=green_at)
    if red_instant is None or green_instant is None:
        return None
    return (green_instant - red_instant).total_seconds()


def _instant(*, value: str) -> datetime | None:
    """Parse one trailer instant, or None when it does not parse.

    The hook writes a `Z`-suffixed UTC instant, which `fromisoformat` does not
    accept on this interpreter's version, so the suffix is normalized to the
    equivalent offset before parsing.
    """
    normalized = value.strip()
    if normalized.endswith(_UTC_SUFFIX):
        normalized = normalized[: -len(_UTC_SUFFIX)] + _UTC_OFFSET
    parsed = attempt(action=lambda: datetime.fromisoformat(normalized), exceptions=(ValueError,))
    if isinstance(parsed, AttemptFailure):
        return None
    return parsed
