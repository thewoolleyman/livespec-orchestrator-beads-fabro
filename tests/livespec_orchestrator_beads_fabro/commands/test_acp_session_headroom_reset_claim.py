"""The provider's claimed reset instant is journaled, and decides nothing.

Binds the reset sentence of `SPECIFICATION/contracts.md` section "Dispatcher
admission, WIP cap, and post-merge acceptance", paragraph "Admission filters
candidates by projected Claude session headroom": "A reset instant the response
carries MAY be journaled as an unverified provider claim and MUST NOT change
the projection skip."

THE PERMISSION AND THE PROHIBITION ARE TESTED SEPARATELY, because they fail in
opposite directions. Journaling the claim is optional, and a build that carried
it would be useless if it carried it unlabelled -- a reader seeing a reset
instant beside a measured drain rate has no way to tell which of the two the
provider merely asserted, and the clause names the claim "unverified" for
exactly that reason. So the key SAYS SO.

THE PROHIBITION IS ASSERTED BY DIFFERENCE, which is the only shape that can
fail. Two readings identical in every figure and differing ONLY in the reset
claim must produce byte-identical projections, including the skip decision. A
build that treated the claim as evidence -- "the window resets in ten minutes,
so admit" -- would pass any single-reading assertion, because its projection
would still be well-formed and its record would still name a horizon; only the
PAIR shows that the claim moved nothing. The claim is deliberately set to an
instant EARLIER than the projected exhaustion in one arm, so a build consulting
it has something to be wrong about.

NOTHING VERIFIES THE CLAIM, and that is the point rather than an omission. The
provider asserts it in a response header; the Dispatcher has no second source
for it and takes no second reading to check it against. Journaling it under a
name that admits as much is the whole of what this clause permits.
"""

from __future__ import annotations

from collections.abc import Callable
from email.message import Message
from typing import Any
from unittest.mock import MagicMock
from urllib.request import Request

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import (
    _acp_session_headroom_projection as projection_module,
)
from livespec_orchestrator_beads_fabro.commands import (
    _acp_session_headroom_records as headroom_records,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_io as headroom_io,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_drain import (
    SessionHeadroomBaseline,
)

_NOW = "2026-10-16T12:00:00Z"
_EARLIER = "2026-10-16T11:30:00Z"
_IDENTITY = "cred-1"
_FLOOR = 20
_HORIZON = 180
_UTILIZATION_HEADER = "anthropic-ratelimit-unified-5h-utilization"

# Spelled as LITERALS and bound to the exported names by the cases below,
# because this file's Red predates the names it binds and a Red's test bytes
# are fixed across its Red-to-Green pair.
_RESET_HEADER = "anthropic-ratelimit-unified-5h-reset"
_RECORD_KEY = "unverified_provider_reset_claim"

# EARLIER than the projected exhaustion of 14:00, so a build that consulted it
# as evidence of an imminent refill has something to get wrong.
_CLAIMED_RESET = "2026-10-16T12:10:00Z"

_PROJECTED_TOKEN = "a-token"


def _headers(**values: str) -> Message:
    message = Message()
    for name, value in values.items():
        message[name] = value
    return message


def _urlopen(*, headers: Message) -> Callable[..., Any]:
    def _open(request: Request, *, timeout: float) -> MagicMock:
        _ = (request, timeout)
        response = MagicMock()
        response.status = 200
        response.headers = headers
        response.read.return_value = b'{"type":"message"}'
        response.__enter__.return_value = response
        return response

    return _open


def _reading(*, reset_claim: str | None) -> headroom.SessionHeadroomReading:
    """50 points from empty at 25 an hour, differing only in the claim."""
    return headroom.SessionHeadroomReading(
        credential_identity=_IDENTITY,
        observed_at=_NOW,
        utilization_percent=50.0,
        remaining_percent=50.0,
        five_hour_drain_percent_per_hour=25.0,
        provider_reset_claim=reset_claim,
    )


def _projection(*, reset_claim: str | None) -> headroom.SessionHeadroomProjection:
    return projection_module.session_headroom_projection(
        reading=_reading(reset_claim=reset_claim),
        baseline=SessionHeadroomBaseline(
            utilization_percent=10.0, observed_at=_EARLIER, elapsed_hours=0.5
        ),
        floor_percent=_FLOOR,
        horizon_minutes=_HORIZON,
    )


def test_a_reset_instant_the_response_carries_changes_no_projection_skip() -> None:
    """The prohibition, asserted by DIFFERENCE between two otherwise-equal readings."""
    claimed = _projection(reset_claim=_CLAIMED_RESET)
    silent = _projection(reset_claim=None)

    assert claimed == silent
    assert claimed.result == headroom.PROJECTED_RESULT
    assert claimed.projected_exhaustion_at == "2026-10-16T14:00:00Z"
    assert claimed.skip_applied is True
    assert projection_module.projection_skips_candidate(
        reading=projection_module.reading_with_projection(
            reading=_reading(reset_claim=_CLAIMED_RESET), projection=claimed
        )
    ) is projection_module.projection_skips_candidate(
        reading=projection_module.reading_with_projection(
            reading=_reading(reset_claim=None), projection=silent
        )
    )


def test_the_reset_claim_is_journaled_under_a_key_that_admits_it_is_unverified() -> None:
    """The permission: carried, labelled, and null when the provider claimed none."""
    assert getattr(headroom_io, "FIVE_HOUR_RESET_HEADER", None) == _RESET_HEADER

    claimed = headroom_records.session_headroom_reading_fields(
        reading=_reading(reset_claim=_CLAIMED_RESET)
    )
    silent = headroom_records.session_headroom_reading_fields(reading=_reading(reset_claim=None))

    assert claimed[_RECORD_KEY] == _CLAIMED_RESET
    assert silent[_RECORD_KEY] is None


@pytest.mark.parametrize("reset", [_CLAIMED_RESET, None])
def test_the_reading_carries_whatever_reset_claim_the_response_header_held(
    monkeypatch: pytest.MonkeyPatch, reset: str | None
) -> None:
    """Read off the real response path, so the header name is exercised."""
    values = {_UTILIZATION_HEADER: "0.5"}
    if reset is not None:
        values[_RESET_HEADER] = reset
    monkeypatch.setattr(headroom_io, "urlopen", _urlopen(headers=_headers(**values)))

    reading = headroom_io.read_projected_session_headroom(token=_PROJECTED_TOKEN, observed_at=_NOW)

    assert reading.utilization_percent == 50.0
    assert reading.provider_reset_claim == reset


def test_an_unobservable_reading_still_carries_the_claim_the_provider_made(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A response with no readable utilization can still assert a reset.

    The two facts come from the same response and are graded independently: the
    utilization is the measurement the floor decides on, and the claim is the
    provider's assertion about a future the Dispatcher cannot check. Dropping
    the claim on the unobservable arm would discard the only thing that
    response said.
    """
    monkeypatch.setattr(
        headroom_io,
        "urlopen",
        _urlopen(
            headers=_headers(**{_UTILIZATION_HEADER: "not-a-number", _RESET_HEADER: _CLAIMED_RESET})
        ),
    )

    reading = headroom_io.read_projected_session_headroom(token=_PROJECTED_TOKEN, observed_at=_NOW)

    assert reading.observable is False
    assert reading.unobservable == headroom.UNREADABLE_UTILIZATION
    assert reading.provider_reset_claim == _CLAIMED_RESET
