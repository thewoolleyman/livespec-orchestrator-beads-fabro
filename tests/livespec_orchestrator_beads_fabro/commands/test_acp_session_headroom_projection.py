"""The projected exhaustion one reading and its baseline imply, as a result.

Binds the projection-result sentences of `SPECIFICATION/contracts.md` section
"Dispatcher admission, WIP cap, and post-merge acceptance", paragraph
"Admission filters candidates by projected Claude session headroom": "When the
projection is available, the projected exhaustion instant is the observation
time plus the remaining headroom divided by the rate, in hours"; "For each
assessed credential, the journal record MUST additionally carry exactly one
projection result: the drain rate, the baseline's observation time, the
projected exhaustion instant, the governing horizon, and whether a projection
skip applied; or an explicit `unavailable` result with its reason; or an
explicit `not-projected` result when no projection was attempted because the
floor is 0, the reading was skipped by the floor, or the reading was
unobservable. `not-projected` and `unavailable` MUST remain distinct values";
"An unavailable projection MUST be journaled with its reason and MUST NOT skip
the candidate"; "The projection MUST be computed only from journaled
assessments and MUST NOT issue any usage request beyond the one bounded reading
this clause already requires"; and "A projection creates NO observed
availability record and retires none."

THE TWO NON-RESULTS ARE THE EXPENSIVE PAIR AND THE CLAUSE SAYS SO IN AS MANY
WORDS. `not-projected` means the dial or the floor settled the reading before
any history was consulted; `unavailable` means a projection was attempted and
its inputs could not support one. Both end at a null rate, so a build that
collapsed them would report "this operator disabled the figure" and "this
credential has no history in this checkout" as one state -- and only the second
is a reason to expect a rate once the checkout has been dispatching for an
hour.

AN UNAVAILABLE PROJECTION MUST NOT SKIP, which is the fail-open half, and it is
asserted on the RESULT rather than on a filter: the filter reads
`skip_applied`, so a projection that set that flag while reporting its own
inputs unmeasurable would skip every first dispatch on every fresh checkout
while the record read perfectly honest.

THE "NO WRITE" CLAIM IS STRUCTURAL AND IS ASSERTED STRUCTURALLY. The decision
module is handed no journal and imports nothing that could write one, so there
is no parameter a ledger could arrive through -- and the behavioural leg puts a
real journal on disk beside the computation and reads the hold ledger off it
before and after, because "creates no observed availability record and retires
none" is a claim about that ledger rather than about this function's return
value.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import json
from pathlib import Path
from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import (
    _acp_session_headroom_records as headroom_records,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_gate as headroom_gate,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_ledger import read_acp_hold_ledger
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_drain import (
    SessionHeadroomBaseline,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    CLAUDE_OAUTH_TOKEN_ENV,
)

_NOW = "2026-10-16T12:00:00Z"
_EARLIER = "2026-10-16T11:30:00Z"
_IDENTITY = "cred-1"
_TOKEN = "projected-token"
_HORIZON = 180

# The repository path the new decision module is expected at. Asserted as a
# FILE before the import, so a build without it fails on an assertion about the
# missing module rather than at collection, where no assertion runs at all.
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_acp_session_headroom_projection.py"
)

# Anything that could persist a record. The claim is that the decision CANNOT
# write, so the check is on what the module can reach rather than on what it
# happens to call.
_WRITE_CAPABLE_IMPORTS = frozenset(
    {
        "livespec_orchestrator_beads_fabro.commands._acp_hold_ledger",
        "livespec_orchestrator_beads_fabro.commands._acp_hold_records",
        "livespec_orchestrator_beads_fabro.commands._dispatcher_io",
        "livespec_orchestrator_beads_fabro.commands._dispatcher_session_headroom_baseline",
        "pathlib",
        "subprocess",
    }
)


def _projection_module() -> Any:
    """The decision module, with its expected path asserted before the import."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._acp_session_headroom_projection"
    )


def _reading(
    *,
    utilization: float | None = 50.0,
    observed_at: str = _NOW,
    rate: float | None = 25.0,
    unobservable: str | None = None,
) -> headroom.SessionHeadroomReading:
    """One already-graded reading, built directly so every arm is reachable."""
    return headroom.SessionHeadroomReading(
        credential_identity=_IDENTITY,
        observed_at=observed_at,
        utilization_percent=utilization,
        remaining_percent=(
            None if utilization is None else headroom.FULL_ALLOWANCE_PERCENT - utilization
        ),
        unobservable=unobservable,
        five_hour_drain_percent_per_hour=rate,
    )


def _baseline(*, observed_at: str = _EARLIER) -> SessionHeadroomBaseline:
    return SessionHeadroomBaseline(
        utilization_percent=10.0, observed_at=observed_at, elapsed_hours=0.5
    )


def _project(
    *,
    reading: headroom.SessionHeadroomReading,
    baseline: SessionHeadroomBaseline | None = None,
    floor_percent: int = 20,
    horizon_minutes: int = _HORIZON,
) -> Any:
    return _projection_module().session_headroom_projection(
        reading=reading,
        baseline=baseline,
        floor_percent=floor_percent,
        horizon_minutes=horizon_minutes,
    )


def _prior_journal_line() -> str:
    """One earlier assessment of this credential, as the journal records it."""
    return json.dumps(
        {
            "at": _EARLIER,
            "stage": headroom_records.SESSION_HEADROOM_STAGE,
            "work_item_id": "bd-ib-another-item",
            "session_headroom_floor_percent": 20,
            "assessments": [
                {
                    "credential_identity": _IDENTITY,
                    "utilization_percent": 10.0,
                    "remaining_percent": 90.0,
                    "unobservable": None,
                    "observed_at": _EARLIER,
                    "five_hour_drain_percent_per_hour": None,
                }
            ],
            "node_selections": {},
        }
    )


def test_the_projection_decision_is_pure_and_can_write_no_record(tmp_path: Path) -> None:
    """The structural half of "creates no observed availability record"."""
    module = _projection_module()
    imported = {
        node.module
        for node in ast.walk(ast.parse(_MODULE_PATH.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(ast.parse(_MODULE_PATH.read_text(encoding="utf-8")))
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    journal = tmp_path / "fabro-dispatch-journal.jsonl"
    _ = journal.write_text(_prior_journal_line() + "\n", encoding="utf-8")
    before = read_acp_hold_ledger(journal_path=journal, now_iso=_NOW)
    bytes_before = journal.read_bytes()

    projection = _project(reading=_reading(), baseline=_baseline())

    assert imported & _WRITE_CAPABLE_IMPORTS == set()
    assert projection.result == headroom.PROJECTED_RESULT
    assert journal.read_bytes() == bytes_before
    assert read_acp_hold_ledger(journal_path=journal, now_iso=_NOW) == before
    assert set(inspect.signature(module.session_headroom_projection).parameters) == {
        "reading",
        "baseline",
        "floor_percent",
        "horizon_minutes",
    }


def test_a_measurable_projection_names_its_rate_baseline_exhaustion_and_horizon() -> None:
    """50 points remaining draining at 25 a hour empties two hours from now."""
    projection = _project(reading=_reading(), baseline=_baseline())

    assert projection.result == headroom.PROJECTED_RESULT
    assert projection.reason is None
    assert projection.five_hour_drain_percent_per_hour == 25.0
    assert projection.baseline_observed_at == _EARLIER
    assert projection.projected_exhaustion_at == "2026-10-16T14:00:00Z"
    assert projection.horizon_minutes == _HORIZON
    assert projection.skip_applied is True


def test_an_exhaustion_beyond_the_horizon_is_projected_without_a_skip() -> None:
    """The control for the assertion above: the same shape, outside the horizon.

    Without it, a build that set `skip_applied` on every measurable projection
    would satisfy every other assertion in this file.
    """
    projection = _project(reading=_reading(rate=5.0), baseline=_baseline())

    assert projection.projected_exhaustion_at == "2026-10-16T22:00:00Z"
    assert projection.skip_applied is False


@pytest.mark.parametrize(
    ("baseline", "rate", "observed_at", "reason_name"),
    [
        (None, None, _NOW, "NO_BASELINE_REASON"),
        (_baseline(), None, _NOW, "UTILIZATION_NOT_HIGHER_REASON"),
        (_baseline(), 25.0, "not-an-instant", "UNREADABLE_OBSERVATION_REASON"),
    ],
)
def test_an_unmeasurable_projection_is_unavailable_with_its_reason_and_no_skip(
    baseline: SessionHeadroomBaseline | None,
    rate: float | None,
    observed_at: str,
    reason_name: str,
) -> None:
    """Each input that cannot be measured names itself and refuses nothing."""
    module = _projection_module()

    projection = _project(reading=_reading(rate=rate, observed_at=observed_at), baseline=baseline)

    assert projection.result == headroom.UNAVAILABLE_RESULT
    assert projection.reason == getattr(module, reason_name)
    assert projection.projected_exhaustion_at is None
    assert projection.skip_applied is False


@pytest.mark.parametrize(
    ("floor_percent", "utilization", "unobservable", "reason_name"),
    [
        (0, 50.0, None, "FLOOR_DISABLED_REASON"),
        (20, 95.0, None, "FLOOR_SKIPPED_READING_REASON"),
        (20, None, headroom.UNREADABLE_UTILIZATION, "UNOBSERVABLE_READING_REASON"),
    ],
)
def test_the_three_not_projected_conditions_stay_distinct_from_unavailable(
    floor_percent: int, utilization: float | None, unobservable: str | None, reason_name: str
) -> None:
    """A reading the dial or the floor settled was never projected at all."""
    module = _projection_module()

    projection = _project(
        reading=_reading(utilization=utilization, unobservable=unobservable),
        baseline=_baseline(),
        floor_percent=floor_percent,
    )

    assert headroom.NOT_PROJECTED_RESULT != headroom.UNAVAILABLE_RESULT
    assert projection.result == headroom.NOT_PROJECTED_RESULT
    assert projection.reason == getattr(module, reason_name)
    assert projection.five_hour_drain_percent_per_hour is None
    assert projection.skip_applied is False


def test_the_assessment_record_carries_exactly_one_projection_result() -> None:
    """One `projection` key per reading, every field written, nulls included."""
    module = _projection_module()
    reading = module.reading_with_projection(
        reading=_reading(), projection=_project(reading=_reading(), baseline=_baseline())
    )

    record = headroom_records.session_headroom_assessment_record(
        work_item_id="bd-ib-item", floor_percent=20, assessments=(reading,)
    )

    [assessment] = cast("list[dict[str, object]]", record["assessments"])
    assert [key for key in assessment if "projection" in key] == ["projection"]
    assert assessment["projection"] == {
        "result": headroom.PROJECTED_RESULT,
        "reason": None,
        "five_hour_drain_percent_per_hour": 25.0,
        "baseline_observed_at": _EARLIER,
        "projected_exhaustion_at": "2026-10-16T14:00:00Z",
        "session_headroom_horizon_minutes": _HORIZON,
        "projection_skip_applied": True,
    }


def test_a_reading_carrying_no_projection_journals_an_explicit_null() -> None:
    """The fourth state, which is "this reading was never projected at all".

    It is an explicit null rather than a fourth result value: a record from a
    build predating this clause looks exactly like one with the key omitted, so
    the key is always written and its absence of content is said out loud.
    """
    record = headroom_records.session_headroom_assessment_record(
        work_item_id="bd-ib-item", floor_percent=20, assessments=(_reading(rate=None),)
    )

    [assessment] = cast("list[dict[str, object]]", record["assessments"])
    assert assessment["projection"] is None


def test_the_gate_projects_once_per_credential_and_spends_one_usage_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The projection is computed from the journal and costs no second request."""
    monkeypatch.setenv(CLAUDE_OAUTH_TOKEN_ENV, _TOKEN)
    journal = tmp_path / "fabro-dispatch-journal.jsonl"
    _ = journal.write_text(_prior_journal_line() + "\n", encoding="utf-8")
    requests: list[str | None] = []

    def _read(*, token: str | None, observed_at: str) -> headroom.SessionHeadroomReading:
        requests.append(token)
        return headroom.session_headroom_reading(
            credential_identity=_IDENTITY, observed_at=observed_at, utilization=50
        )

    policy = headroom_gate.session_headroom_policy(
        repo=tmp_path, now_iso=_NOW, journal_path=journal, read=_read
    )
    first = policy.read()
    again = policy.read()

    assert requests == [_TOKEN]
    assert first is again
    # 10 percent used at 11:30 against 50 at 12:00 is 80 points an hour, and 50
    # points remaining at that rate empties 37 and a half minutes from now.
    assert first.five_hour_drain_percent_per_hour == 80.0
    assert first.projection is not None
    assert first.projection.result == headroom.PROJECTED_RESULT
    assert first.projection.projected_exhaustion_at == "2026-10-16T12:37:30Z"
    assert first.projection.horizon_minutes == _HORIZON
