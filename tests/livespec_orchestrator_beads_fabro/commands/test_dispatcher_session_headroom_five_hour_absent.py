"""An ABSENT five-hour window is no five-hour limit, never an unobservable reading.

Binds the absent-window sentences of `SPECIFICATION/contracts.md` section
"Provider spend containment", paragraph "Admission filters candidates by
projected Claude session headroom": "The five-hour window is ABSENT when the
bounded usage request was answered successfully by the provider with the
projected credential authenticated (for Claude, a 2xx response to the usage
request) and that response reports no five-hour window at all", and "With a
positive floor, a slot whose five-hour window is absent MUST pass the floor; no
drain rate and no projection MUST be attempted for it, and its projection
result MUST be `not-projected` with the reason `five-hour-window-absent`; its
seven-day status MUST still govern it". The governing scenario is
`SPECIFICATION/scenarios.md` Scenario 288.

MEASURED 2026-11-01 ON THIS HOST, and the reason the clause changed: a one-token
Messages request on a pool slot answered HTTP 200 carrying the seven-day
headers (`-7d-status: allowed`, `-7d-utilization: 0.02`) and NO
`anthropic-ratelimit-unified-5h-*` header of any kind. The prior build graded
that `unreadable-utilization`, the default floor of 20 skipped every slot, and
the factory dispatched nothing. `_measured_response_headers` below is that
response's header set, minus the values that decide nothing here.

THE CONTROLS ARE THE OTHER HALF OF THE CLAUSE: a five-hour header that is
PRESENT but malformed, and a REFUSED response carrying no five-hour header,
both stay unobservable and floor-skip exactly as before. A build that read
every missing figure as "no limit" would pass the first case and fail these.

The new names are read through `getattr` and spelled as literals, because this
file's Red predates them and a Red's test bytes are fixed across its pair.
Everything is HERMETIC: the provider is reached through an injected `urlopen`.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from email.message import Message
from typing import Any, cast
from unittest.mock import MagicMock
from urllib.error import HTTPError
from urllib.request import Request

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import (
    _acp_session_headroom_projection as projection,
)
from livespec_orchestrator_beads_fabro.commands import (
    _acp_session_headroom_records as records,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_io as headroom_io,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_pool as pool,
)

_NOW = "2026-11-01T04:10:00Z"
_TOKEN = "projected-oauth-token"
_FLOOR = 20
_HORIZON = 180
_ABSENT = "five-hour-window-absent"


def _headers(values: dict[str, str]) -> Message:
    message = Message()
    for name, value in values.items():
        message[name] = value
    return message


def _measured_response_headers(*, seven_day_status: str = "allowed") -> Message:
    return _headers(
        {
            "anthropic-ratelimit-unified-status": "allowed",
            "anthropic-ratelimit-unified-representative-claim": "seven_day",
            "anthropic-ratelimit-unified-7d-status": seven_day_status,
            "anthropic-ratelimit-unified-7d-utilization": "0.02",
            "anthropic-ratelimit-unified-7d-reset": "1793941200",
        }
    )


def _answering(*, headers: Message) -> Callable[..., Any]:
    def _urlopen(request: Request, *, timeout: float) -> MagicMock:
        _ = (request, timeout)
        response = MagicMock()
        response.status = 200
        response.headers = headers
        response.__enter__.return_value = response
        return response

    return _urlopen


def _refusing(*, status: int, headers: Message) -> Callable[..., Any]:
    def _urlopen(request: Request, *, timeout: float) -> Any:
        _ = (request, timeout)
        raise HTTPError(
            url=headroom_io.CLAUDE_SESSION_HEADROOM_URL,
            code=status,
            msg="refused",
            hdrs=cast("Message", headers),
            fp=io.BytesIO(b"{}"),
        )

    return _urlopen


def _read(monkeypatch: pytest.MonkeyPatch, opener: Callable[..., Any]) -> Any:
    monkeypatch.setattr(headroom_io, "urlopen", opener)
    return headroom_io.read_projected_session_headroom(token=_TOKEN, observed_at=_NOW)


def test_a_2xx_response_with_no_five_hour_window_qualifies_and_is_named_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reading = _read(monkeypatch, _answering(headers=_measured_response_headers()))

    # Not unobservable, not a number: the absent window is its own named result.
    assert reading.unobservable is None
    assert reading.utilization_percent is None
    assert reading.remaining_percent is None
    assert getattr(reading, "five_hour_window_absent", None) is True
    # It passes the floor, and the seven-day half of the same response still read.
    assert headroom.headroom_skips_candidate(reading=reading, floor_percent=_FLOOR) is False
    assert projection.headroom_skip_kind(reading=reading, floor_percent=_FLOOR) is None
    assert reading.seven_day.status == "allowed"
    # No projection is attempted, and the result says why.
    result = projection.session_headroom_projection(
        reading=reading, baseline=None, floor_percent=_FLOOR, horizon_minutes=_HORIZON
    )
    assert result.result == headroom.NOT_PROJECTED_RESULT
    assert result.reason == _ABSENT
    # The journal names it distinctly.
    fields = records.session_headroom_reading_fields(
        reading=projection.reading_with_projection(reading=reading, projection=result)
    )
    assert fields["five_hour_window"] == _ABSENT
    assert fields["unobservable"] is None
    assert fields["utilization_percent"] is None


def test_the_seven_day_status_still_governs_a_slot_whose_window_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reading = _read(
        monkeypatch, _answering(headers=_measured_response_headers(seven_day_status="rejected"))
    )

    assert getattr(reading, "five_hour_window_absent", None) is True
    assert (
        projection.headroom_skip_kind(reading=reading, floor_percent=_FLOOR)
        == projection.SEVEN_DAY_SKIP_KIND
    )


def test_a_measured_slot_outranks_a_slot_whose_window_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    absent = _read(monkeypatch, _answering(headers=_measured_response_headers()))
    measured = projection.reading_with_projection(
        reading=headroom.session_headroom_reading(
            credential_identity="measured", observed_at=_NOW, utilization=10.0
        ),
        projection=headroom.SessionHeadroomProjection(result=headroom.PROJECTED_RESULT),
    )

    selection = pool.select_pool_slot(
        readings=[("ANTHROPIC_0", absent), ("ANTHROPIC_1", measured)], floor_percent=_FLOOR
    )

    assert selection.chosen_slot == "ANTHROPIC_1"
    by_slot = {r.slot.slot: r.slot for r in selection.readings if r.slot is not None}
    assert by_slot["ANTHROPIC_0"].skip_kind is None
    assert by_slot["ANTHROPIC_0"].not_chosen_reason is not None


def test_an_absent_window_alone_in_the_pool_is_chosen(monkeypatch: pytest.MonkeyPatch) -> None:
    absent = _read(monkeypatch, _answering(headers=_measured_response_headers()))

    selection = pool.select_pool_slot(readings=[("ANTHROPIC_0", absent)], floor_percent=_FLOOR)

    assert selection.chosen_slot == "ANTHROPIC_0"


@pytest.mark.parametrize(
    "opener",
    [
        _answering(headers=_headers({"anthropic-ratelimit-unified-5h-utilization": "soon"})),
        _refusing(status=429, headers=_measured_response_headers()),
        _refusing(status=401, headers=_measured_response_headers()),
    ],
    ids=["malformed-five-hour-figure", "refused-429", "authentication-401"],
)
def test_a_malformed_figure_or_a_refused_response_is_still_unobservable(
    monkeypatch: pytest.MonkeyPatch, opener: Callable[..., Any]
) -> None:
    reading = _read(monkeypatch, opener)

    assert reading.unobservable is not None
    assert getattr(reading, "five_hour_window_absent", False) is False
    assert headroom.headroom_skips_candidate(reading=reading, floor_percent=_FLOOR) is True
