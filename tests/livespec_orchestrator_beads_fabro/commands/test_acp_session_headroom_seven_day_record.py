"""The weekly figures are journaled beside the five-hour ones, on every reading.

Binds the journal sentence of the seven-day half of
`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance", paragraph "Admission filters candidates by projected
Claude session headroom": "The journal record of each assessment MUST carry the
seven-day utilization percentage and status, or an explicit unobservable
result, beside the five-hour figures." The governing scenario is
`SPECIFICATION/scenarios.md` Scenario 231, whose second block ends "the journal
records the seven-day reading, or records it as unobservable when it is
absent".

EVERY KEY IS ASSERTED ON EVERY READING, NULLS INCLUDED, which is the one thing
this surface gets wrong in a way nothing announces: an omitted key is exactly
what a record written by a build predating the clause looks like, so a reader
could not tell "the provider reported no weekly window" from "this record was
never asked". The cases therefore compare the WHOLE assessment entry rather
than looking a key up, since a containment check passes for a record missing
the key it did not ask about.

THE ABSENT READING IS THE LOAD-BEARING CASE. An absent weekly window is the
ordinary shape of every response today, and the two cheap ways to render it --
omit the block, or write a zero -- are each indistinguishable downstream from a
measurement: a zero says the weekly allowance is untouched, which is a
perfectly plausible reading and the opposite of a failure to observe.

THE UNOBSERVABLE FIVE-HOUR CASE IS ASSERTED TOO, because the two windows fail
independently: the response most likely to carry a weekly refusal is a REFUSED
one, so a record that dropped the weekly block whenever the five-hour half was
unobservable would lose the figures on exactly the reading they matter for.

Everything is HERMETIC: nothing here reads a credential, a file or a network.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import (
    _acp_session_headroom_records as headroom_records,
)

_NOW = "2026-10-22T12:00:00Z"
_IDENTITY = "cred-weekly-record"
_FLOOR = 20

# Spelled as a LITERAL and bound to the rendered record by every case, because
# this file's Red predates the key and a Red's test bytes are fixed across its
# Red-to-Green pair.
_SEVEN_DAY_KEY = "seven_day"


def _entry(*, reading: headroom.SessionHeadroomReading) -> dict[str, Any]:
    """The one assessment entry the record renders for one reading."""
    record = headroom_records.session_headroom_assessment_record(
        work_item_id="bd-ib-item", floor_percent=_FLOOR, assessments=(reading,)
    )
    [entry] = cast("list[dict[str, Any]]", record["assessments"])
    return entry


def _five_hour_figures(*, unobservable: str | None) -> dict[str, Any]:
    """The five-hour half of an entry, which every case asserts is unchanged."""
    return {
        "credential_identity": _IDENTITY,
        "utilization_percent": None if unobservable else 55.0,
        "remaining_percent": None if unobservable else 45.0,
        "unobservable": unobservable,
        "observed_at": _NOW,
        "five_hour_drain_percent_per_hour": None,
        "projection": None,
        "unverified_provider_reset_claim": None,
    }


@pytest.mark.parametrize(
    ("weekly", "expected"),
    [
        (
            headroom.seven_day_reading(utilization=100.0, status="rejected"),
            {"utilization_percent": 100.0, "status": "rejected", "unobservable": None},
        ),
        (
            headroom.seven_day_reading(utilization=40.0, status="allowed_warning"),
            {"utilization_percent": 40.0, "status": "allowed_warning", "unobservable": None},
        ),
        (
            headroom.seven_day_reading(utilization=None, status="rejected"),
            {"utilization_percent": None, "status": "rejected", "unobservable": None},
        ),
        (
            headroom.seven_day_reading(utilization=None, status=None),
            {
                "utilization_percent": None,
                "status": None,
                "unobservable": headroom.ABSENT_SEVEN_DAY_READING,
            },
        ),
    ],
    ids=["refused", "warning", "status-only", "absent"],
)
def test_the_assessment_entry_carries_the_weekly_figures_beside_the_five_hour_ones(
    weekly: headroom.SevenDayReading, expected: dict[str, Any]
) -> None:
    """One block, three keys, written on every reading whatever it reports."""
    reading = headroom.session_headroom_reading(
        credential_identity=_IDENTITY, observed_at=_NOW, utilization=55, seven_day=weekly
    )

    entry = _entry(reading=reading)

    assert entry == {**_five_hour_figures(unobservable=None), _SEVEN_DAY_KEY: expected}


def test_an_unobservable_five_hour_reading_still_journals_the_weekly_refusal() -> None:
    """The two windows fail independently, and a refusal is where that bites."""
    reading = headroom.unobservable_session_headroom(
        credential_identity=_IDENTITY,
        observed_at=_NOW,
        reason=headroom.UNREADABLE_UTILIZATION,
        seven_day=headroom.seven_day_reading(utilization=100.0, status="rejected"),
    )

    entry = _entry(reading=reading)

    assert entry == {
        **_five_hour_figures(unobservable=headroom.UNREADABLE_UTILIZATION),
        _SEVEN_DAY_KEY: {
            "utilization_percent": 100.0,
            "status": "rejected",
            "unobservable": None,
        },
    }


def test_a_reading_no_caller_supplied_a_weekly_window_for_is_explicitly_absent() -> None:
    """A build that never asked records the absence rather than an omitted key."""
    reading = headroom.session_headroom_reading(
        credential_identity=_IDENTITY, observed_at=_NOW, utilization=55
    )

    entry = _entry(reading=reading)

    assert entry[_SEVEN_DAY_KEY] == {
        "utilization_percent": None,
        "status": None,
        "unobservable": headroom.ABSENT_SEVEN_DAY_READING,
    }
