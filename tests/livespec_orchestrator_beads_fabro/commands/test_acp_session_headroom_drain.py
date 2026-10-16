"""The five-hour DRAIN RATE: how fast the window the floor guards is emptying.

Binds the first assertion of work-item `bd-ib-rszkjc` -- the assessment record
carries a `five_hour_drain_percent_per_hour` "equal to the increase in
utilization percentage points divided by the elapsed hours since a baseline,
where the baseline is the earliest assessment carrying a valid reading of the
same opaque credential identity in the dispatching checkout's dispatch journal,
for any work-item, observed no less than 15 minutes and no more than 90 minutes
earlier".

WHY A RATE AND NOT ANOTHER LEVEL. A run keeps its dispatch-time token to the
end, so the reading taken at admission is the only guard an in-flight run has,
and a LEVEL cannot say whether that guard will still hold an hour from now. The
`caam-anthropic-loop` runner (`livespec-overseer-07`) measured `anthropic-3`
draining about 15 points of its five-hour window per 30-minute tick, faster
than the loop's own rotation cadence -- a 20 percent floor is ample or useless
depending entirely on that rate, and nothing in the journal could tell an
operator which.

THE BASELINE FIXTURES ARE BUILT THROUGH THE REAL PROJECTION, never hand-written
JSON. The baseline reader's whole job is to read records the assessment writer
produced, so a hand-authored fixture would let the reader and the writer
disagree about the record shape while every assertion here still passed -- the
reader would be measuring a population no dispatch ever writes. The shapes the
writer CANNOT produce are the sibling
`test_dispatcher_session_headroom_baseline.py`'s subject, and it hand-authors
them for exactly that reason.

THE EARLIEST-IN-WINDOW RULE NEEDS A DISCRIMINATING FIXTURE, which is why the
multi-record case below seeds utilizations that yield DIFFERENT rates for the
earliest and the newest in-window candidate. With a uniformly-drained fixture
both selections produce one number, so the test would pass against a reader
that picked either.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import (
    _acp_session_headroom_records as headroom_records,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_gate as headroom_gate,
)

_NOW_DT = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)
_NOW = "2026-10-15T12:00:00Z"
_IDENTITY = "cred-1"
_OTHER_IDENTITY = "cred-2"
_FLOOR = 20

# Spelled as LITERALS and bound to the exported names by the first test below,
# because this file's Red predates both modules and the field it names, and a
# Red's test bytes are fixed across its Red-to-Green pair.
_DRAIN_MODULE = "livespec_orchestrator_beads_fabro.commands._acp_session_headroom_drain"
_DRAIN_FIELD = "five_hour_drain_percent_per_hour"
_DRAIN_MODULE_PATH = Path(headroom.__file__).parent / "_acp_session_headroom_drain.py"
_BASELINE_MODULE_PATH = Path(headroom.__file__).parent / "_dispatcher_session_headroom_baseline.py"

# `session_headroom_policy` gains its `journal_path` parameter at this Green, so
# the Red cannot name it through the checked signature. The loose callable type
# is the same device the literals above are: it lets the Red SAY what the Green
# must accept without asserting that it already does.
_build_policy = cast(
    "Callable[..., headroom.SessionHeadroomPolicy]", headroom_gate.session_headroom_policy
)


def _ago(*, minutes: int) -> str:
    return (_NOW_DT - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _prior(
    *, minutes: int, utilization: float, identity: str = _IDENTITY
) -> headroom.SessionHeadroomReading:
    return headroom.session_headroom_reading(
        credential_identity=identity, observed_at=_ago(minutes=minutes), utilization=utilization
    )


def _unreadable_prior(*, minutes: int) -> headroom.SessionHeadroomReading:
    return headroom.unobservable_session_headroom(
        credential_identity=_IDENTITY, observed_at=_ago(minutes=minutes), reason="timed-out"
    )


def _seed(*, path: Path, readings: tuple[headroom.SessionHeadroomReading, ...]) -> None:
    """One `acp-session-headroom` record per prior reading, as the writer writes it."""
    lines = [
        json.dumps(
            {
                "at": reading.observed_at,
                "invoker": "role:prior-pass",
                **headroom_records.session_headroom_assessment_record(
                    work_item_id="bd-ib-some-other-item",
                    floor_percent=_FLOOR,
                    assessments=(reading,),
                ),
            }
        )
        for reading in readings
    ]
    _ = path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")


def _reader(*, utilization: object) -> Callable[..., headroom.SessionHeadroomReading]:
    def _read(*, token: str | None, observed_at: str) -> headroom.SessionHeadroomReading:
        _ = token
        return headroom.session_headroom_reading(
            credential_identity=_IDENTITY, observed_at=observed_at, utilization=utilization
        )

    return _read


def _drain(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    readings: tuple[headroom.SessionHeadroomReading, ...],
    utilization: object = 25.0,
) -> object:
    """This evaluation's drain rate, read off the reading the policy hands back.

    The journal is ALWAYS seeded here, even for the cases that expect no
    baseline: every case in this file is about which seeded assessment the read
    selects, and an absent journal is a different question that
    `test_dispatcher_session_headroom_baseline.py` owns.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    journal_path = tmp_path / "tmp" / "fabro-dispatch-journal.jsonl"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    _seed(path=journal_path, readings=readings)
    policy = _build_policy(
        repo=tmp_path,
        now_iso=_NOW,
        journal_path=journal_path,
        read=_reader(utilization=utilization),
    )
    return getattr(policy.read(), _DRAIN_FIELD, None)


def test_the_drain_modules_exist_and_export_the_window_the_clause_names() -> None:
    """The new-module slice, via the importlib pattern so the Red is an assertion."""
    assert _DRAIN_MODULE_PATH.is_file()
    assert _BASELINE_MODULE_PATH.is_file()

    drain = importlib.import_module(_DRAIN_MODULE)

    assert drain.SESSION_HEADROOM_BASELINE_MINIMUM_MINUTES == 15
    assert drain.SESSION_HEADROOM_BASELINE_MAXIMUM_MINUTES == 90


def test_the_drain_rate_is_the_utilization_increase_over_the_hours_elapsed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """15 points gained over half an hour is 30 points per hour."""
    rate = _drain(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        readings=(_prior(minutes=30, utilization=10.0),),
        utilization=25.0,
    )

    assert rate == 30.0


def test_the_baseline_is_the_earliest_valid_assessment_inside_the_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three priors, each yielding a DIFFERENT rate, so the selection is observable.

    The 90-minute prior is the earliest inside the window and gives
    `(25 - 10) / 1.5 == 10.0`. Picking the NEWEST in-window prior instead would
    give `(25 - 22) / 0.5 == 6.0`, and picking the 5-minute one -- which is too
    new to be a baseline at all -- would give 60.0. One number tells all three
    readers apart.
    """
    rate = _drain(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        readings=(
            _prior(minutes=90, utilization=10.0),
            _prior(minutes=30, utilization=22.0),
            _prior(minutes=5, utilization=24.5),
        ),
        utilization=25.0,
    )

    assert rate == 10.0


def test_the_journal_order_does_not_decide_the_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The EARLIEST OBSERVATION, not the first line: a journal is append-ordered.

    The dispatch journal is appended to by concurrent passes, and
    `_dispatcher_io.JournalFile` stamps `at` at append time rather than at
    observation time, so a record's position cannot stand in for its instant.
    """
    rate = _drain(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        readings=(
            _prior(minutes=30, utilization=22.0),
            _prior(minutes=90, utilization=10.0),
        ),
        utilization=25.0,
    )

    assert rate == 10.0


@pytest.mark.parametrize("minutes", [15, 90])
def test_the_window_bounds_are_inclusive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, minutes: int
) -> None:
    """ "No less than 15 minutes and no more than 90 minutes" includes both ends."""
    rate = _drain(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        readings=(_prior(minutes=minutes, utilization=10.0),),
        utilization=25.0,
    )

    assert rate is not None


@pytest.mark.parametrize("minutes", [0, 14, 91, 600])
def test_an_assessment_outside_the_window_is_not_a_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, minutes: int
) -> None:
    """Too new says nothing about a rate; too old is a rate about another window."""
    rate = _drain(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        readings=(_prior(minutes=minutes, utilization=10.0),),
        utilization=25.0,
    )

    assert rate is None


def test_another_credentials_assessment_is_not_a_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two accounts drain independently, so one cannot stand in for the other."""
    rate = _drain(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        readings=(_prior(minutes=30, utilization=10.0, identity=_OTHER_IDENTITY),),
        utilization=25.0,
    )

    assert rate is None


def test_an_unobservable_prior_assessment_is_not_a_valid_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A prior that failed to MEASURE carries no utilization to subtract."""
    rate = _drain(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        readings=(_unreadable_prior(minutes=30),),
        utilization=25.0,
    )

    assert rate is None


def test_a_valid_earlier_assessment_wins_over_an_unobservable_earlier_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The earliest VALID one, so an unreadable prior is skipped rather than fatal."""
    rate = _drain(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        readings=(_unreadable_prior(minutes=85), _prior(minutes=30, utilization=10.0)),
        utilization=25.0,
    )

    assert rate == 30.0
