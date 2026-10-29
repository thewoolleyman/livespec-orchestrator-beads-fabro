"""One inspect command read as the port's inspect result."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_inspection import fabro_inspect_result


def test_an_inspect_command_carries_its_payload_and_status_kind() -> None:
    command = CommandResult(
        exit_code=0, stdout='[{"run_id": "01RUN", "status": {"kind": "running"}}]', stderr=""
    )

    result = fabro_inspect_result(command=command)

    assert result.command is command
    assert result.payload == [{"run_id": "01RUN", "status": {"kind": "running"}}]
    assert result.status_kind == "running"
    assert result.failure is None


def test_a_failed_inspect_command_carries_no_payload() -> None:
    command = CommandResult(exit_code=1, stdout="", stderr="no such run")

    result = fabro_inspect_result(command=command)

    assert result.command is command
    assert result.payload is None
    assert result.status_kind is None
