"""The drain rate ON THE RECORD: written on every reading, null when unmeasured.

Binds the third assertion of work-item `bd-ib-rszkjc`: "An assessment record
whose drain rate cannot be computed carries null for
five_hour_drain_percent_per_hour and is never coerced to a numeric reading."

THIS IS A CLAIM ABOUT THE WIRE, NOT ABOUT THE READING, which is why the
assertions below go through `json.dumps` rather than reading the projected
mapping alone. The journal line is what an operator reads, and it is also what
the next pass's baseline read parses, so a field that exists in Python and
vanishes on serialization satisfies every in-memory assertion while leaving the
record exactly as a build predating this clause wrote it.

WRITTEN RATHER THAN OMITTED, nulls included, for the same reason the reading's
original five keys are: an omitted key is indistinguishable from a record that
was never asked for the figure, so a reader could not tell "this rate was not
measured" from "this build does not measure rates". The assessment record is
the one surface where that distinction is recoverable at all -- the reading
itself is gone by the time anyone looks.

AND NEVER COERCED, which is the half a reasonable implementation gets wrong.
Every numeric value available as a sentinel is also a genuine reading: 0.0 is
exactly what a credential nobody is spending measures at, so a record carrying
0.0 for an unmeasured rate reports a measurement that was never taken -- and an
operator judging whether a 20 percent floor is adequate would read it as proof
that the window is not draining. The cases below therefore assert `is None`
rather than falsity, since `0.0`, `0` and `""` are all falsy and all wrong.
"""

from __future__ import annotations

import json
from dataclasses import replace

from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import (
    _acp_session_headroom_records as headroom_records,
)

_NOW = "2026-10-15T12:00:00Z"
_IDENTITY = "cred-1"

# Spelled as a LITERAL and bound to the projected key by the cases below,
# because this file's Red predates the key and a Red's test bytes are fixed
# across its Red-to-Green pair.
_DRAIN_FIELD = "five_hour_drain_percent_per_hour"

_MEASURED_RATE = 30.0


def _graded(*, utilization: object = 25.0) -> headroom.SessionHeadroomReading:
    return headroom.session_headroom_reading(
        credential_identity=_IDENTITY, observed_at=_NOW, utilization=utilization
    )


def _unobservable() -> headroom.SessionHeadroomReading:
    return headroom.unobservable_session_headroom(
        credential_identity=_IDENTITY, observed_at=_NOW, reason="timed-out"
    )


def _assessments(*, reading: headroom.SessionHeadroomReading) -> list[object]:
    """One assessment record's `assessments`, round-tripped through JSON."""
    record = headroom_records.session_headroom_assessment_record(
        work_item_id="bd-ib-item", floor_percent=20, assessments=(reading,)
    )
    rendered = json.loads(json.dumps(record))
    assert isinstance(rendered, dict)
    entries = rendered["assessments"]
    assert isinstance(entries, list)
    return entries


def test_a_measured_rate_reaches_the_record_as_the_number_it_was() -> None:
    """The positive control: a projection that never reached the wire would pass below."""
    measured = replace(_graded(), five_hour_drain_percent_per_hour=_MEASURED_RATE)

    entry = _assessments(reading=measured)[0]

    assert isinstance(entry, dict)
    assert entry[_DRAIN_FIELD] == _MEASURED_RATE


def test_a_reading_with_no_measured_rate_carries_the_key_holding_null() -> None:
    """An uncomputable rate is written as an explicit null, never left out."""
    entry = _assessments(reading=_graded())[0]

    assert isinstance(entry, dict)
    assert _DRAIN_FIELD in entry
    assert entry[_DRAIN_FIELD] is None


def test_an_unobservable_reading_carries_the_key_holding_null() -> None:
    """The reading that failed to measure its own window measures no rate either.

    Its `unobservable` reason survives beside the null rate, which is what tells
    a reader WHY no rate was taken rather than leaving the two absences to be
    guessed apart.
    """
    entry = _assessments(reading=_unobservable())[0]

    assert isinstance(entry, dict)
    assert entry[_DRAIN_FIELD] is None
    assert entry["unobservable"] == "timed-out"


def test_the_rendered_record_spells_an_unmeasured_rate_as_a_json_null() -> None:
    """Read off the rendered TEXT, because a dropped key is invisible in a mapping."""
    record = headroom_records.session_headroom_assessment_record(
        work_item_id="bd-ib-item", floor_percent=20, assessments=(_graded(),)
    )

    rendered = json.dumps(record, sort_keys=True)

    assert f'"{_DRAIN_FIELD}": null' in rendered


def test_the_rate_sits_among_the_readings_whole_journaled_key_set() -> None:
    """The projection's whole key set, so a new key cannot arrive unnoticed.

    Nothing a credential value or a raw provider response could travel through
    is admissible here, and an exact set is what keeps that a structural
    property rather than a review note. The seventh key is the PROJECTION
    result `bd-ib-lgpsik` added beside this rate; it is named here rather than
    elsewhere because this set is the one place a key can be added silently.
    """
    fields = headroom_records.session_headroom_reading_fields(reading=_graded())

    assert set(fields) == {
        "credential_identity",
        "observed_at",
        "utilization_percent",
        "remaining_percent",
        "unobservable",
        _DRAIN_FIELD,
        "projection",
    }
