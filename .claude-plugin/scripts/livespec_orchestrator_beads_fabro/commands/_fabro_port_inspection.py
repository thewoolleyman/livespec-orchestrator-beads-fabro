"""One `fabro inspect --json` command read as the result the port reports."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._fabro_port_payload import fabro_json_payload
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_failure_detail_from_payload,
    fabro_status_kind_from_payload,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import (
    FabroCommand,
    FabroInspectResult,
)

__all__: list[str] = [
    "fabro_inspect_result",
]


def fabro_inspect_result(*, command: FabroCommand) -> FabroInspectResult:
    """Read the payload, status kind and failure out of one inspect command."""
    payload = fabro_json_payload(command=command)
    return FabroInspectResult(
        command=command,
        payload=payload,
        status_kind=fabro_status_kind_from_payload(payload=payload),
        failure=fabro_failure_detail_from_payload(payload=payload),
    )
