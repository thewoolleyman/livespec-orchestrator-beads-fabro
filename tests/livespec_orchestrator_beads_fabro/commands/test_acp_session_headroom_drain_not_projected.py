"""When NO drain rate is attempted at all, because the FLOOR settled the reading.

Binds the two floor-governed null arms of work-item `bd-ib-rszkjc`: the
`five_hour_drain_percent_per_hour` "is null when the floor is 0, when the
reading was skipped by the floor or is unobservable". The arms that turn on the
rate's own inputs -- no baseline, and a window that did not rise -- are the
sibling `test_acp_session_headroom_drain_null_arms.py`'s subject; these are the
cases where the inputs are perfectly measurable and the rate is still not
taken.

`SPECIFICATION/contracts.md` is where the distinction comes from: a reading
settled by the floor carries "an explicit `not-projected` result ... because
the floor is 0, the reading was skipped by the floor, or the reading was
unobservable", and that is a DIFFERENT value from the `unavailable` one an
attempted-but-unmeasurable projection carries. This item journals the rate
alone; naming the two results apart belongs to `bd-ib-lgpsik`.

EVERY FIXTURE HERE WOULD YIELD A RATE IF THE FLOOR WERE IGNORED, which is the
only thing that makes the cases able to fail. Each seeds an in-window baseline
of 10 percent utilization against a current reading that rose above it, so a
build consulting the inputs alone computes a number for all four -- and the
expected answer is a number in exactly one of them.

THE CLAIM IS ABOUT A READ THAT DID NOT HAPPEN, so the journal read is counted
rather than inferred from the null. A null rate is also what an attempted
projection with no baseline looks like, so a build that attempted every
projection and happened to find nothing would satisfy a null-only assertion
while spending a journal read per pass on a dial set to disable the figure --
and, for the unobservable case, while reporting an absence of HISTORY for a
reading whose own window was never read.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import (
    _acp_session_headroom_records as headroom_records,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_gate as headroom_gate,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_session_headroom_baseline import (
    session_headroom_baseline,
)

_NOW_DT = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)
_NOW = "2026-10-15T12:00:00Z"
_IDENTITY = "cred-1"
_BASELINE_UTILIZATION = 10.0
_BASELINE_MINUTES = 30

# The default floor is 20, so 75 percent remaining passes it and 15 does not.
_PASSING_UTILIZATION = 25.0
_SKIPPED_UTILIZATION = 85.0


def _write_floor(*, root: Path, value: str) -> None:
    _ = (root / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": '
        f'{{"session_headroom_floor_percent": {value}}}}}}}',
        encoding="utf-8",
    )


def _seed_baseline(*, path: Path) -> None:
    """One in-window prior assessment, written exactly as the writer writes it."""
    observed_at = (_NOW_DT - timedelta(minutes=_BASELINE_MINUTES)).strftime("%Y-%m-%dT%H:%M:%SZ")
    prior = headroom.session_headroom_reading(
        credential_identity=_IDENTITY,
        observed_at=observed_at,
        utilization=_BASELINE_UTILIZATION,
    )
    record = headroom_records.session_headroom_assessment_record(
        work_item_id="bd-ib-some-other-item", floor_percent=20, assessments=(prior,)
    )
    _ = path.write_text(
        f"{json.dumps({'at': observed_at, 'invoker': 'role:prior-pass', **record})}\n",
        encoding="utf-8",
    )


def _reader(*, utilization: object | None, unobservable: bool) -> Callable[..., object]:
    def _read(*, token: str | None, observed_at: str) -> headroom.SessionHeadroomReading:
        _ = token
        if unobservable:
            return headroom.unobservable_session_headroom(
                credential_identity=_IDENTITY, observed_at=observed_at, reason="timed-out"
            )
        return headroom.session_headroom_reading(
            credential_identity=_IDENTITY, observed_at=observed_at, utilization=utilization
        )

    return _read


def _recording_baseline_reads(*, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The identities the gate asked the journal about, through the real reader."""
    asked: list[str] = []

    def _recording(*, journal_path: Path | None, credential_identity: str, now_iso: str) -> object:
        asked.append(credential_identity)
        return session_headroom_baseline(
            journal_path=journal_path, credential_identity=credential_identity, now_iso=now_iso
        )

    monkeypatch.setattr(headroom_gate, "session_headroom_baseline", _recording)
    return asked


def _read_once(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    floor: str | None = None,
    utilization: object | None = _PASSING_UTILIZATION,
    unobservable: bool = False,
) -> tuple[float | None, list[str]]:
    """This evaluation's drain rate, and the journal reads it spent getting there."""
    monkeypatch.setenv("HOME", str(tmp_path))
    if floor is not None:
        _write_floor(root=tmp_path, value=floor)
    journal_path = tmp_path / "fabro-dispatch-journal.jsonl"
    _seed_baseline(path=journal_path)
    asked = _recording_baseline_reads(monkeypatch=monkeypatch)
    policy = headroom_gate.session_headroom_policy(
        repo=tmp_path,
        now_iso=_NOW,
        journal_path=journal_path,
        read=_reader(utilization=utilization, unobservable=unobservable),
    )
    return policy.read().five_hour_drain_percent_per_hour, asked


def test_a_reading_that_passes_a_positive_floor_is_projected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The positive control: without it, a gate projecting NOTHING passes below.

    15 points gained over half an hour is 30 points per hour, and the journal
    was asked about exactly the credential the reading named.
    """
    rate, asked = _read_once(tmp_path=tmp_path, monkeypatch=monkeypatch)

    assert rate == 30.0
    assert asked == [_IDENTITY]


def test_a_floor_of_zero_attempts_no_projection_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dial that disables the filter disables the figure, and reads no history.

    An operator who sets the floor to 0 has switched this clause off; the
    bounded reading and its journal row are still taken, which
    `test_acp_session_headroom_disabled_floor.py` binds, but there is no
    admission question left for a rate to inform.
    """
    rate, asked = _read_once(tmp_path=tmp_path, monkeypatch=monkeypatch, floor="0")

    assert rate is None
    assert asked == []


def test_a_reading_the_floor_skipped_attempts_no_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """85 percent used leaves 15 remaining, strictly below the default floor of 20.

    The candidate has already left the selectable set on the level alone, so
    asking how fast it is draining answers a question nothing is waiting on.
    Its baseline is in window and its utilization rose from 10 to 85, so a
    build reading the inputs alone would report 150 points per hour here.
    """
    rate, asked = _read_once(
        tmp_path=tmp_path, monkeypatch=monkeypatch, utilization=_SKIPPED_UTILIZATION
    )

    assert rate is None
    assert asked == []


def test_an_unobservable_reading_attempts_no_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reading that failed to MEASURE is already skipped by a positive floor.

    The null here is cheap to reach by accident -- an unobservable reading
    carries no utilization to subtract -- so the load-bearing assertion is the
    one about the journal: no history was read, because no projection was
    attempted, rather than a projection being attempted and finding nothing.
    """
    rate, asked = _read_once(tmp_path=tmp_path, monkeypatch=monkeypatch, unobservable=True)

    assert rate is None
    assert asked == []
