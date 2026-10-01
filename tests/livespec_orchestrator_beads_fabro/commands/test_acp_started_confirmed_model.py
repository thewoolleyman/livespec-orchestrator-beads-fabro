"""The confirmed model and effort an `agent.acp.started` event reports.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "In-protocol model and effort selection": "The `agent.acp.started`
event MUST carry the confirmed model and effort values as additive non-secret
fields so a reader can verify which model actually ran without reading the
command", and Scenario 127's closing line, "the agent.acp.started event carries
the confirmed model and effort".

WHY A READER IS THE POINT, not merely the field's presence on the wire. The
whole value of the confirmation is that an operator -- or an acceptance test --
can establish WHICH MODEL RAN from the run's own events. If nothing in this
repository reads the field, then every assertion about it is an assertion about
the fixture that produced it, and a build whose engine silently ignored the
requested `config_options` reads exactly like one that honoured them. The
projection's reader is what turns the engine's claim into an observation.

THE FIELDS ARE ADDITIVE, SO THEIR ABSENCE MUST NOT COST THE START ITS READING.
This is the inversion that matters, and it is asserted in its own right. A
`candidate_index` is REQUIRED -- a start without one says nothing about which
candidate ran, so it is dropped rather than assumed to be the primary. The
confirmed values are the opposite: a candidate that requested no options
legitimately reports none, and a node whose agent takes its model in the
environment reports none ever. Treating them as required would discard those
starts, and discarding a start is not inert -- the model-fallback warning's
CLEARANCE rule turns on which candidate began a node visit, so a dropped start
leaves a warning standing forever.

AN EXPLICIT `null` IS ABSENCE, NOT A VALUE. The fork's own consumer contract
records that `null` for `model` or `effort` deserialises as absence past the
protocol boundary, so a reader that distinguished the two would invent a
third state the engine cannot emit.
"""

from __future__ import annotations

from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._acp_fallback_event_types import (
    ACP_STARTED_EVENT,
    AcpEventScan,
    AcpNodeStart,
)
from livespec_orchestrator_beads_fabro.commands._acp_fallback_events import scan_acp_events

_OCCURRED = "2026-10-01T12:00:00Z"
_MODEL = "gpt-5.6-sol"
_EFFORT = "high"


def _started(**overrides: Any) -> dict[str, Any]:
    """One `agent.acp.started` record, as the engine emits it after configuring."""
    record: dict[str, Any] = {
        "type": ACP_STARTED_EVENT,
        "node": "implement",
        "node_visit": 1,
        "candidate_index": 1,
        "occurred_at": _OCCURRED,
        "primary_generation": "gen-a",
    }
    record.update(overrides)
    return record


def _one_start(*, record: dict[str, Any]) -> AcpNodeStart:
    """The single start the reader takes from a one-record stream.

    The `__dataclass_fields__` assertion runs FIRST, and it is not ceremony: the
    vocabulary type is what every downstream reader destructures, so a confirmed
    value reachable only off the raw mapping is not a surface this repository
    can observe a model through.
    """
    assert "confirmed_model" in AcpNodeStart.__dataclass_fields__, sorted(
        AcpNodeStart.__dataclass_fields__
    )
    scan = scan_acp_events(payload=[record])
    assert isinstance(scan, AcpEventScan), scan
    [start] = scan.starts
    return start


def test_a_started_event_reports_the_confirmed_model_and_effort() -> None:
    """The values the engine confirmed before the prompt reach the reader."""
    start = _one_start(record=_started(model=_MODEL, effort=_EFFORT))

    assert start.confirmed_model == _MODEL
    assert start.confirmed_effort == _EFFORT
    assert start.candidate_index == 1


def test_a_start_requesting_no_options_is_still_read_with_no_confirmation() -> None:
    """The additive control: absence costs the confirmation, never the start.

    A node whose agent takes its model in the environment emits no confirmed
    values at all, and that start is exactly the one the warning-clearance rule
    needs. An assertion on the `None` values alone would pass against a reader
    that had dropped the record, so the start itself is asserted present.
    """
    start = _one_start(record=_started())

    assert start.confirmed_model is None
    assert start.confirmed_effort is None
    assert start.node == "implement"
    assert start.node_visit == 1


@pytest.mark.parametrize("value", [None, "", "   ", 7, True, ["gpt-5.6-sol"]])
def test_an_unreadable_confirmed_value_is_absence_and_keeps_the_start(value: Any) -> None:
    """`null`, blank and wrong-typed values are one answer: nothing was confirmed.

    An explicit `null` is what the engine emits for an option it did not set, and
    a blank string is not an identity -- it would compare equal to every other
    blank one the moment two confirmations were compared.
    """
    start = _one_start(record=_started(model=value, effort=value))

    assert start.confirmed_model is None
    assert start.confirmed_effort is None
    assert start.node == "implement"


def test_the_primary_and_the_fallback_report_different_confirmed_models() -> None:
    """Two starts in one node visit, each naming the model it actually ran.

    This is the shape the ordered-fallback journey produces, and it is the case
    that makes the field worth reading: a build that stamped the REQUESTED model
    rather than the confirmed one would report the primary's model twice, and the
    run would look as though the fallback had never been configured.
    """
    assert "confirmed_model" in AcpNodeStart.__dataclass_fields__, sorted(
        AcpNodeStart.__dataclass_fields__
    )
    scan = scan_acp_events(
        payload=[
            _started(candidate_index=0, model="gpt-5.5", effort=_EFFORT),
            _started(candidate_index=1, model=_MODEL, effort=_EFFORT),
        ]
    )

    assert isinstance(scan, AcpEventScan), scan
    assert [start.confirmed_model for start in scan.starts] == ["gpt-5.5", _MODEL]
    assert {start.node_visit for start in scan.starts} == {1}
