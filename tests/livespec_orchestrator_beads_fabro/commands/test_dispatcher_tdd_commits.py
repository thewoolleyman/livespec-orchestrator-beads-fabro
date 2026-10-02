"""Commit-series derivation of the run's TDD order signals.

The four commit-derived fields of plan slice S3 come from the dispatch's OWN
commit series, so this module's job is to turn commit MESSAGES into counts and
one gap median. The cases that matter are the ones a naive reader gets wrong:
a Green-amended commit retains BOTH trailer sets and is ONE Red and ONE Green,
not two commits; the suite-green leg carries its own trailer family; and a
commit whose timestamps do not parse contributes no gap sample rather than a
zero-second one.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_commits"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_tdd_commits.py"
)


def _module() -> ModuleType:
    """Import the module under test, asserting it exists first.

    The existence assertion is deliberate: it is the genuine failing assertion
    the Red commit for this slice stands on, rather than a collection-time
    `ModuleNotFoundError` that would prove only unimportability.
    """
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


def _green_amended(*, red_at: str, green_at: str) -> str:
    return (
        "feat: do the thing (bd-ib-x)\n"
        "\n"
        "Body prose.\n"
        "\n"
        "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>\n"
        "TDD-Red-Test: tests/test_x.py\n"
        f"TDD-Red-Captured-At: {red_at}\n"
        f"TDD-Green-Verified-At: {green_at}\n"
    )


def test_a_green_amended_commit_counts_as_one_red_and_one_green() -> None:
    module = _module()

    signals = module.tdd_commit_signals(
        messages=(_green_amended(red_at="2026-10-01T20:38:30Z", green_at="2026-10-01T20:42:24Z"),)
    )

    assert signals.red_commit_count == 1
    assert signals.green_commit_count == 1
    assert signals.suite_green_count == 0
    assert signals.red_green_gap_seconds_median == 234.0


def test_an_open_red_counts_a_red_with_no_green_and_no_gap_sample() -> None:
    module = _module()

    signals = module.tdd_commit_signals(
        messages=(
            "feat: open red\n\nTDD-Red-Captured-At: 2026-10-01T20:38:30Z\n",
            "chore: no trailers at all\n",
        )
    )

    assert signals.red_commit_count == 1
    assert signals.green_commit_count == 0
    assert signals.red_green_gap_seconds_median is None


def test_the_suite_green_leg_is_counted_separately_from_red_green_pairs() -> None:
    module = _module()

    signals = module.tdd_commit_signals(
        messages=("feat: suite green\n\nTDD-Suite-Green-Captured-At: 2026-10-01T20:42:24Z\n",)
    )

    assert signals.suite_green_count == 1
    assert signals.red_commit_count == 0
    assert signals.green_commit_count == 0


def test_the_gap_median_averages_an_even_number_of_samples() -> None:
    module = _module()

    signals = module.tdd_commit_signals(
        messages=(
            _green_amended(red_at="2026-10-01T20:00:00Z", green_at="2026-10-01T20:01:00Z"),
            _green_amended(red_at="2026-10-01T21:00:00Z", green_at="2026-10-01T21:05:00Z"),
        )
    )

    assert signals.red_green_gap_seconds_median == 180.0


def test_an_unparseable_trailer_instant_contributes_no_gap_sample() -> None:
    module = _module()

    signals = module.tdd_commit_signals(
        messages=(_green_amended(red_at="not-a-timestamp", green_at="2026-10-01T20:42:24Z"),)
    )

    assert signals.red_commit_count == 1
    assert signals.green_commit_count == 1
    assert signals.red_green_gap_seconds_median is None


def test_commit_trailers_keeps_the_first_value_and_ignores_prose() -> None:
    module = _module()

    trailers = module.commit_trailers(
        message=(
            "feat: subject line\n"
            "\n"
            "Prose with no colon at all.\n"
            "TDD-Red-Captured-At: first\n"
            "TDD-Red-Captured-At: second\n"
        )
    )

    assert trailers["TDD-Red-Captured-At"] == "first"
    assert "Prose with no colon at all." not in trailers


def test_commit_messages_parse_from_a_gh_pr_view_commits_payload() -> None:
    module = _module()

    messages = module.parse_commit_messages(
        stdout=(
            '{"commits": ['
            '{"messageHeadline": "feat: one", "messageBody": "TDD-Red-Captured-At: x"},'
            '{"messageHeadline": "chore: two", "messageBody": ""}'
            "]}"
        )
    )

    assert messages == ("feat: one\n\nTDD-Red-Captured-At: x", "chore: two\n\n")


def test_a_malformed_commits_payload_reads_as_unobservable_not_empty() -> None:
    module = _module()

    assert module.parse_commit_messages(stdout="not json at all") is None
    assert module.parse_commit_messages(stdout="[]") is None
    assert module.parse_commit_messages(stdout='{"commits": "nope"}') is None


def test_a_non_mapping_or_non_string_commit_entry_is_skipped() -> None:
    module = _module()

    messages = module.parse_commit_messages(
        stdout=(
            '{"commits": ['
            '"a bare string",'
            '{"messageHeadline": 7, "messageBody": "body"},'
            '{"messageHeadline": "feat: kept", "messageBody": "kept body"}'
            "]}"
        )
    )

    assert messages == ("feat: kept\n\nkept body",)
