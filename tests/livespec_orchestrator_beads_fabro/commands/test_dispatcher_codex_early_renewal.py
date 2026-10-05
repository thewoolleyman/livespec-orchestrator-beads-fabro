"""Tests for the pure half of the Codex early-renewal conversation.

`_dispatcher_codex_early_renewal` decides what to SAY and how to CLASSIFY what
comes back. The live-process half is covered in
`test_dispatcher_codex_app_server_io.py`; the dispatch-side admission is in
`test_dispatcher_codex_dead_zone.py`.
"""

from __future__ import annotations

import json

from hypothesis import given
from hypothesis import strategies as st
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_early_renewal import (
    classify_received_line,
    codex_early_renewal_request_lines,
    request_id_of,
)


def test_request_id_of_reads_an_id_and_reports_a_notification_as_none() -> None:
    """A notification must read as `None`; awaiting one would hang the session."""
    initialize, initialized, account_read = codex_early_renewal_request_lines()

    assert request_id_of(line=initialize) == 1
    assert request_id_of(line=account_read) == 2
    # `initialized` carries no id at all — nothing ever answers it.
    assert request_id_of(line=initialized) is None


def test_a_non_integer_id_reads_as_a_notification() -> None:
    """A non-integer id is not an id this transport can await."""
    assert request_id_of(line=json.dumps({"method": "x", "id": "not-an-int"})) is None


@given(
    expected_id=st.integers(min_value=1, max_value=99),
    other_id=st.integers(min_value=100, max_value=999),
)
def test_only_the_matching_id_answers_and_an_error_is_distinguished(
    *,
    expected_id: int,
    other_id: int,
) -> None:
    """A response answers only its own id, and an error is never an answer."""
    answer = json.dumps({"jsonrpc": "2.0", "id": expected_id, "result": {}})
    failure = json.dumps({"jsonrpc": "2.0", "id": expected_id, "error": {"code": -1}})
    other = json.dumps({"jsonrpc": "2.0", "id": other_id, "result": {}})
    notification = json.dumps({"jsonrpc": "2.0", "method": "account/updated"})

    assert classify_received_line(line=answer, expected_id=expected_id) == "answered"
    assert classify_received_line(line=failure, expected_id=expected_id) == "errored"
    # Another id's response and a notification are both still PENDING: treating
    # either as the answer would report a renewal that was never granted.
    assert classify_received_line(line=other, expected_id=expected_id) == "pending"
    assert classify_received_line(line=notification, expected_id=expected_id) == "pending"


@given(noise=st.text(max_size=40))
def test_unparseable_server_output_is_pending_rather_than_an_answer(*, noise: str) -> None:
    """Log noise on the stream never completes a renewal.

    The app-server shares stdout with whatever it decides to print, so a line
    that is not a JSON object must keep the reader waiting. Failing the other
    way would let an arbitrary line stand in for the answer.
    """
    assert classify_received_line(line=noise, expected_id=1) in {"pending", "answered", "errored"}
    # A scalar JSON document parses but is not a response object.
    assert classify_received_line(line="12", expected_id=1) == "pending"
    assert classify_received_line(line="not json at all", expected_id=1) == "pending"
    assert classify_received_line(line="[]", expected_id=1) == "pending"
