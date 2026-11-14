"""One dispatch's distinct verified Red-Green pairs, derived from its own provenance.

Scenario 165 requires the Dispatcher to derive current-dispatch progress from
its actual preserved commit and test-first provenance, where one completed cycle
is one DISTINCT verified Red-Green pair. The cases that matter are the ones that
would inflate or blind the count: a Green-amended commit retains BOTH trailer
sets and is one cycle rather than two; a retry re-committing the identical Red is
the same pair observed twice; an open Red, a suite-green-only commit and
unrelated history are not cycles at all; and an OBSERVED EMPTY series is not the
same answer as a series nobody could read.

The Dispatcher path that reports these counts is exercised end to end in
`test_dispatcher_tdd_probe`; this file pins the pure derivation beneath it.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st
from livespec_orchestrator_beads_fabro.commands._dispatcher_completed_cycles import (
    observed_pair_count,
    unobserved_pair_count,
    verified_pair_ids,
)


def _message(
    *,
    red_at: str | None = None,
    green_at: str | None = None,
    checksum: str | None = None,
    suite_green_at: str | None = None,
) -> str:
    lines = [
        "feat(dispatcher): one assertion",
        "",
        "Body prose.",
        "",
        "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>",
    ]
    if checksum is not None:
        lines.append(f"TDD-Red-Test-File-Checksum: {checksum}")
    if red_at is not None:
        lines.append(f"TDD-Red-Captured-At: {red_at}")
    if green_at is not None:
        lines.append(f"TDD-Green-Verified-At: {green_at}")
    if suite_green_at is not None:
        lines.append(f"TDD-Suite-Green-Captured-At: {suite_green_at}")
    return "\n".join(lines) + "\n"


def test_a_green_amended_commit_is_one_completed_pair() -> None:
    pairs = verified_pair_ids(
        messages=(
            _message(
                red_at="2026-10-01T10:00:00Z",
                green_at="2026-10-01T10:04:10Z",
                checksum="sha256:one",
            ),
        )
    )

    assert pairs == ("sha256:one@2026-10-01T10:00:00Z",)


def test_open_reds_suite_green_commits_and_unrelated_history_are_not_pairs() -> None:
    pairs = verified_pair_ids(
        messages=(
            _message(red_at="2026-10-01T10:00:00Z", checksum="sha256:open"),
            _message(green_at="2026-10-01T10:04:10Z", checksum="sha256:green-only"),
            _message(suite_green_at="2026-10-01T10:05:00Z"),
            _message(),
        )
    )

    assert pairs == ()


def test_a_retry_re_committing_the_identical_red_counts_the_pair_once() -> None:
    first = _message(
        red_at="2026-10-01T10:00:00Z", green_at="2026-10-01T10:04:10Z", checksum="sha256:one"
    )
    retry = _message(
        red_at="2026-10-01T10:00:00Z", green_at="2026-10-01T10:09:00Z", checksum="sha256:one"
    )

    assert len(verified_pair_ids(messages=(first, retry))) == 1
    assert len(verified_pair_ids(messages=(first, first))) == 1


def test_two_reds_with_different_evidence_are_two_pairs() -> None:
    pairs = verified_pair_ids(
        messages=(
            _message(
                red_at="2026-10-01T10:00:00Z",
                green_at="2026-10-01T10:04:10Z",
                checksum="sha256:one",
            ),
            _message(
                red_at="2026-10-01T10:00:00Z",
                green_at="2026-10-01T10:04:10Z",
                checksum="sha256:two",
            ),
            _message(
                red_at="2026-10-01T11:00:00Z",
                green_at="2026-10-01T11:04:10Z",
                checksum="sha256:one",
            ),
        )
    )

    assert len(pairs) == 3


def test_a_pair_with_no_red_checksum_is_identified_by_its_message() -> None:
    message = _message(red_at="2026-10-01T10:00:00Z", green_at="2026-10-01T10:04:10Z")

    assert verified_pair_ids(messages=(message,)) == (f"message:{message}",)
    assert len(verified_pair_ids(messages=(message, message))) == 1


def test_an_observed_empty_series_is_not_an_unreadable_series() -> None:
    observed = observed_pair_count(messages=(_message(red_at="2026-10-01T10:00:00Z"),))
    unreadable = unobserved_pair_count(reason="commits-unreadable")

    assert (observed.count, observed.unobserved_reason) == (0, None)
    assert (unreadable.count, unreadable.unobserved_reason) == (None, "commits-unreadable")


@given(
    cycles=st.lists(st.integers(min_value=0, max_value=5), max_size=12),
    open_reds=st.integers(min_value=0, max_value=4),
)
def test_the_count_is_the_number_of_distinct_cycles_however_often_each_repeats(
    cycles: list[int], open_reds: int
) -> None:
    messages = tuple(
        _message(
            red_at=f"2026-10-01T10:00:0{cycle}Z",
            green_at="2026-10-01T10:30:00Z",
            checksum=f"sha256:{cycle}",
        )
        for cycle in cycles
    ) + tuple(_message(red_at="2026-10-01T09:00:00Z") for _ in range(open_reds))

    assert observed_pair_count(messages=messages).count == len(set(cycles))
