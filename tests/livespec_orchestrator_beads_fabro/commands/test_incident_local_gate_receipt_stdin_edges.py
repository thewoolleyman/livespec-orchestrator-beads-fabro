"""The stdin receipt source is exclusive with argv, scoped to its action, and refuses non-UTF-8."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-3ufhng
from __future__ import annotations

import io
import json
import sys

import pytest
from livespec_orchestrator_beads_fabro.commands import incident_authority as command
from livespec_orchestrator_beads_fabro.commands.incident_local_gate_receipt import (
    read_receipt_stream,
)

from tests.livespec_orchestrator_beads_fabro.commands.test_incident_local_gate_receipt import (
    _chain,
)
from tests.livespec_orchestrator_beads_fabro.commands.test_incident_local_gate_receipt_stdin import (
    _identity,
)


@pytest.mark.parametrize(
    ("action", "extra"),
    [
        ("record-local-gates", ["--receipt-json", "{}", "--receipt-stdin"]),
        ("read-current", ["--receipt-stdin"]),
    ],
)
def test_the_stdin_receipt_source_is_exclusive_and_scoped_to_record_local_gates(
    action: str, extra: list[str]
) -> None:
    with pytest.raises(SystemExit, match="2"):
        command.main(argv=[action, *_identity(), *extra])


def test_a_receipt_that_is_not_utf8_on_stdin_is_refused_invalid_and_records_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client, _attempt, _root, _current = _chain()
    monkeypatch.setattr(command, "store_config", lambda **_kwargs: None)
    monkeypatch.setattr(command, "make_beads_client", lambda **_kwargs: client)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b'{"a":"\xff"}')))
    actual = command.main(argv=["record-local-gates", *_identity(), "--receipt-stdin"])
    response = json.loads(capsys.readouterr().out)
    assert (actual, response["result"]["code"]) == (78, "incident-receipt-invalid")
    assert len(client.list_comments(issue_id="test-incident")) == 1


def test_the_receipt_stream_read_holds_one_byte_past_the_bound_and_no_more() -> None:
    stream = io.BytesIO(b"x" * (1048576 + 4096))
    assert len(read_receipt_stream(stream=stream)) == 1048576 + 1
    assert stream.tell() == 1048576 + 1
