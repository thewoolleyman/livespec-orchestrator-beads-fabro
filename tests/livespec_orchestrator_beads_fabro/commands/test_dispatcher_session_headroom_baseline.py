"""What the drain rate's journal read TOLERATES, and what it refuses to count.

Covers `_dispatcher_session_headroom_baseline`, the half of the drain figure
that reads this repository's dispatch journal for one credential's earlier
assessments (work-item `bd-ib-rszkjc`).

THE RECORDS HERE ARE DELIBERATELY HAND-BUILT, which is the OPPOSITE of the
sibling `test_acp_session_headroom_drain.py` choice and for a reason. That file
asserts the happy path and builds its fixtures through the real projection, so
the reader and the writer cannot drift apart. These cases are about shapes the
writer CANNOT produce -- a truncated line, a record whose `assessments` is not
a list, an entry carrying a boolean where a utilization belongs -- and the only
way to present one is to author it. They exist because the journal is
append-only and is written by concurrent passes, so an ill-formed tail is an
ordinary state rather than a fault.

NOTHING HERE MAY RAISE, and that is the whole claim. The drain rate is
journal-only, so the worst honest outcome of an unreadable history is a null
figure; an exception escaping this read would fail an admission evaluation over
a number that decides nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_records import (
    SESSION_HEADROOM_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_session_headroom_baseline import (
    session_headroom_baseline,
)

_NOW = "2026-10-15T12:00:00Z"
_IN_WINDOW = "2026-10-15T11:30:00Z"
_IDENTITY = "cred-1"


def _assessment_record(*, assessments: object) -> str:
    return json.dumps(
        {
            "at": _IN_WINDOW,
            "stage": SESSION_HEADROOM_STAGE,
            "work_item_id": "bd-ib-some-other-item",
            "session_headroom_floor_percent": 20,
            "assessments": assessments,
            "node_selections": {},
        }
    )


def _valid_entry(**overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "credential_identity": _IDENTITY,
        "utilization_percent": 10.0,
        "remaining_percent": 90.0,
        "unobservable": None,
        "observed_at": _IN_WINDOW,
        "seven_day_utilization_percent": None,
        "five_hour_drain_percent_per_hour": None,
    }
    entry.update(overrides)
    return entry


def _baseline(*, tmp_path: Path, lines: tuple[str, ...], write: bool = True) -> object:
    path = tmp_path / "fabro-dispatch-journal.jsonl"
    if write:
        _ = path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return session_headroom_baseline(journal_path=path, credential_identity=_IDENTITY, now_iso=_NOW)


def test_a_well_formed_record_is_the_positive_control(tmp_path: Path) -> None:
    """Without this, a reader that counted NOTHING would satisfy every case below."""
    baseline = _baseline(
        tmp_path=tmp_path, lines=(_assessment_record(assessments=[_valid_entry()]),)
    )

    assert baseline is not None


def test_an_absent_journal_file_holds_no_baseline(tmp_path: Path) -> None:
    """The first dispatch in a fresh clone has no history to measure against."""
    assert _baseline(tmp_path=tmp_path, lines=(), write=False) is None


def test_no_journal_path_at_all_holds_no_baseline() -> None:
    """A caller holding no journal says so, and is answered rather than refused."""
    assert (
        session_headroom_baseline(journal_path=None, credential_identity=_IDENTITY, now_iso=_NOW)
        is None
    )


@pytest.mark.parametrize(
    "line",
    [
        "{not json at all",
        '{"stage": "acp-session-headroom", "assessments": [{"credential',
        "[]",
        '"a bare string"',
        "",
    ],
)
def test_an_unreadable_line_is_passed_over_rather_than_fatal(tmp_path: Path, line: str) -> None:
    """A truncated tail is what a concurrent append looks like mid-write."""
    assert _baseline(tmp_path=tmp_path, lines=(line,)) is None


def test_an_unreadable_line_does_not_hide_the_readable_records_after_it(
    tmp_path: Path,
) -> None:
    """The skip is per LINE; a bad line must not abandon the rest of the walk."""
    baseline = _baseline(
        tmp_path=tmp_path,
        lines=("{truncated", _assessment_record(assessments=[_valid_entry()])),
    )

    assert baseline is not None


def test_another_stages_record_is_not_an_assessment(tmp_path: Path) -> None:
    """The journal carries every dispatch stage; only this one's rows are readings."""
    line = json.dumps(
        {
            "at": _IN_WINDOW,
            "stage": "provider-exhaustion-observed",
            "assessments": [_valid_entry()],
        }
    )

    assert _baseline(tmp_path=tmp_path, lines=(line,)) is None


@pytest.mark.parametrize("assessments", [None, {}, "two", 3])
def test_a_record_whose_assessments_are_not_a_list_counts_nothing(
    tmp_path: Path, assessments: object
) -> None:
    assert (
        _baseline(tmp_path=tmp_path, lines=(_assessment_record(assessments=assessments),)) is None
    )


@pytest.mark.parametrize("entry", [None, "cred-1", 7, []])
def test_an_assessment_entry_that_is_not_a_mapping_counts_nothing(
    tmp_path: Path, entry: object
) -> None:
    assert _baseline(tmp_path=tmp_path, lines=(_assessment_record(assessments=[entry]),)) is None


@pytest.mark.parametrize("utilization", [None, True, False, "10", [10]])
def test_an_entry_without_a_numeric_utilization_is_not_a_valid_assessment(
    tmp_path: Path, utilization: object
) -> None:
    """`True` is the sharp one: it is an `int` subclass worth 1 percent used.

    A document carrying `true` where a utilization belongs would otherwise read
    as 1 percent -- a perfectly plausible figure that says nothing about usage,
    and one that would then be subtracted from a real reading to manufacture a
    rate.
    """
    entry = _valid_entry(utilization_percent=utilization)

    assert _baseline(tmp_path=tmp_path, lines=(_assessment_record(assessments=[entry]),)) is None


@pytest.mark.parametrize("observed_at", [None, 1760524200, {"at": _IN_WINDOW}])
def test_an_entry_without_a_textual_instant_is_not_a_valid_assessment(
    tmp_path: Path, observed_at: object
) -> None:
    """An age cannot be measured from a value that is not an instant."""
    entry = _valid_entry(observed_at=observed_at)

    assert _baseline(tmp_path=tmp_path, lines=(_assessment_record(assessments=[entry]),)) is None


def test_an_entry_whose_instant_cannot_be_parsed_is_passed_over(tmp_path: Path) -> None:
    """Textual but not an instant: the window is a question about an age."""
    entry = _valid_entry(observed_at="half past eleven")

    assert _baseline(tmp_path=tmp_path, lines=(_assessment_record(assessments=[entry]),)) is None


def test_an_unparseable_instant_does_not_hide_a_readable_sibling(tmp_path: Path) -> None:
    """One bad entry inside a record must not discard the record's other entries."""
    line = _assessment_record(
        assessments=[_valid_entry(observed_at="half past eleven"), _valid_entry()]
    )

    assert _baseline(tmp_path=tmp_path, lines=(line,)) is not None


def test_an_unreadable_clock_holds_no_baseline(tmp_path: Path) -> None:
    """The window is an AGE, so an unreadable `now` measures nothing.

    This arm cannot be reached through the Dispatcher, which stamps `now` from
    `utc_now_iso`, and it is covered because the function is public surface and
    the alternative to answering `None` is comparing against a value that
    could not be read.
    """
    path = tmp_path / "fabro-dispatch-journal.jsonl"
    _ = path.write_text(f"{_assessment_record(assessments=[_valid_entry()])}\n", encoding="utf-8")

    assert (
        session_headroom_baseline(
            journal_path=path, credential_identity=_IDENTITY, now_iso="no clock here"
        )
        is None
    )
