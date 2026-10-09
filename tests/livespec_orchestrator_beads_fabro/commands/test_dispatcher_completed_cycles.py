"""One dispatch's completed Red-Green cycles, derived from its own provenance.

Scenario 165 requires the Dispatcher to derive current-dispatch progress from
its actual preserved commit and test-first provenance, where one completed cycle
is one DISTINCT verified Red-Green pair. The cases that matter are the ones that
would inflate or blind the count: a Green-amended commit retains BOTH trailer
sets and is one cycle rather than two; a retry re-committing the identical Red is
the same pair observed twice; an open Red, a suite-green-only commit and
unrelated history are not cycles at all; a reversed timestamp is unobserved
rather than zero; and an OBSERVED EMPTY series is not the same answer as a series
nobody could read.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_completed_cycles"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_completed_cycles.py"
)


def _module() -> ModuleType:
    """Import the module under test, asserting it exists first.

    The existence assertion is the genuine failing assertion this slice's Red
    commit stands on, rather than a collection-time `ModuleNotFoundError` that
    would prove only unimportability.
    """
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


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
    module = _module()

    pairs = module.verified_pairs(
        commits=(
            module.ProvenanceCommit(
                sha="aaaa111",
                message=_message(
                    red_at="2026-10-01T10:00:00Z",
                    green_at="2026-10-01T10:04:10Z",
                    checksum="sha256:one",
                ),
            ),
        )
    )

    assert len(pairs) == 1
    assert pairs[0].commit == "aaaa111"


def test_open_reds_suite_green_commits_and_unrelated_history_are_not_pairs() -> None:
    module = _module()

    pairs = module.verified_pairs(
        commits=(
            module.ProvenanceCommit(
                sha="open1", message=_message(red_at="2026-10-01T10:00:00Z", checksum="sha256:a")
            ),
            module.ProvenanceCommit(
                sha="suite1", message=_message(suite_green_at="2026-10-01T10:00:00Z")
            ),
            module.ProvenanceCommit(sha="plain1", message=_message()),
        )
    )

    assert pairs == ()


def test_a_retry_re_committing_the_identical_red_counts_the_pair_once() -> None:
    module = _module()
    message = _message(
        red_at="2026-10-01T10:00:00Z", green_at="2026-10-01T10:04:10Z", checksum="sha256:same"
    )

    pairs = module.verified_pairs(
        commits=(
            module.ProvenanceCommit(sha="first", message=message),
            module.ProvenanceCommit(sha="first", message=message),
            module.ProvenanceCommit(sha="retried", message=message),
        )
    )

    assert len(pairs) == 1


def test_cycles_are_ordinalled_one_based_in_preserved_red_chronology() -> None:
    module = _module()

    pairs = module.verified_pairs(
        commits=(
            module.ProvenanceCommit(
                sha="second",
                message=_message(
                    red_at="2026-10-01T11:00:00Z",
                    green_at="2026-10-01T11:05:00Z",
                    checksum="sha256:two",
                ),
            ),
            module.ProvenanceCommit(
                sha="first",
                message=_message(
                    red_at="2026-10-01T10:00:00Z",
                    green_at="2026-10-01T10:04:10Z",
                    checksum="sha256:one",
                ),
            ),
        )
    )
    series = module.observed_series(
        cycles=tuple(
            module.completed_cycle(ordinal=index + 1, source=source, product_lloc=7)
            for index, source in enumerate(pairs)
        ),
        assertion_count=2,
    )

    assert [cycle.ordinal for cycle in series.cycles] == [1, 2]
    assert [cycle.commit for cycle in series.cycles] == ["first", "second"]
    assert series.completed_count == 2
    assert series.assertion_count == 2


def test_elapsed_seconds_come_from_the_preserved_red_to_green_interval() -> None:
    module = _module()

    assert (
        module.elapsed_cycle_seconds(red_at="2026-10-01T10:00:00Z", green_at="2026-10-01T10:04:10Z")
        == 250
    )


def test_reversed_or_unparseable_instants_are_unobserved_rather_than_zero() -> None:
    module = _module()

    reversed_pair = module.elapsed_cycle_seconds(
        red_at="2026-10-01T10:04:10Z", green_at="2026-10-01T10:00:00Z"
    )
    unparseable = module.elapsed_cycle_seconds(red_at="not-an-instant", green_at="also-not")

    assert isinstance(reversed_pair, module.Unobserved)
    assert reversed_pair.reason == module.UNOBSERVED_TIMESTAMPS
    assert isinstance(unparseable, module.Unobserved)
    assert unparseable.reason == module.UNOBSERVED_TIMESTAMPS


def test_an_unavailable_size_measurement_keeps_the_pair_count_intact() -> None:
    module = _module()
    source = module.CycleSource(
        commit="aaaa111",
        pair_id="sha256:one@2026-10-01T10:00:00Z",
        red_captured_at="2026-10-01T10:00:00Z",
        green_verified_at="2026-10-01T10:04:10Z",
    )

    cycle = module.completed_cycle(
        ordinal=1,
        source=source,
        product_lloc=module.Unobserved(reason=module.UNOBSERVED_SOURCE_TREE),
    )
    series = module.observed_series(cycles=(cycle,), assertion_count=3)

    assert cycle.product_lloc_changed is None
    assert cycle.product_lloc_unobserved_reason == module.UNOBSERVED_SOURCE_TREE
    assert cycle.elapsed_seconds == 250
    assert series.completed_count == 1


def test_an_observed_empty_series_is_not_an_unreadable_series() -> None:
    module = _module()

    empty = module.observed_series(cycles=(), assertion_count=2)
    unreadable = module.unreadable_series(reason=module.UNREADABLE_PROVENANCE, assertion_count=2)

    assert empty.observed
    assert empty.completed_count == 0
    assert empty.unreadable_reason is None
    assert not unreadable.observed
    assert unreadable.completed_count is None
    assert unreadable.unreadable_reason == module.UNREADABLE_PROVENANCE
