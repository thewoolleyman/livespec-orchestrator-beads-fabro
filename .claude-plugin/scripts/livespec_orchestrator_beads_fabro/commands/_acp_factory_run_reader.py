"""Production factory-native reader for host-wide ACP availability evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._config import (
    resolve_fabro_bin,
    resolve_fabro_factory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_bin import (
    factory_fabro_bin,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    FabroRunSummary,
    fabro_inspect_record,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroRunner

__all__: list[str] = [
    "FactoryRunReader",
]

_READ_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True, kw_only=True)
class FactoryRunReader:
    """Read declared factories through the Dispatcher Fabro-port facade.

    Every read resolves the named factory from the target repository's
    ``dispatcher.factories`` table. A missing server is unreadable rather than
    a reason to let Fabro select its local default server.
    """

    repo: Path
    runner: FabroRunner = field(default_factory=ShellCommandRunner)

    def list_runs(self, *, factory: str) -> tuple[FabroRunSummary, ...] | None:
        """Return the declared factory's parsed run rows, or ``None`` if unreadable."""
        port = self._port(factory=factory)
        if port is None:
            return None
        result = port.ps(timeout_seconds=_READ_TIMEOUT_SECONDS)
        if result.command.exit_code != 0 or not _ps_payload(payload=result.payload):
            return None
        return result.runs

    def inspect_payload(self, *, factory: str, run_id: str) -> object | None:
        """Return one declared factory's inspect payload, or ``None`` if unreadable."""
        port = self._port(factory=factory)
        if port is None:
            return None
        result = port.inspect(run_id=run_id, timeout_seconds=_READ_TIMEOUT_SECONDS)
        if result.command.exit_code != 0 or fabro_inspect_record(payload=result.payload) is None:
            return None
        return result.payload

    def _port(self, *, factory: str) -> FabroPort | None:
        target = resolve_fabro_factory(cwd=self.repo, factory=factory)
        if target.server is None:
            return None
        return FabroPort(
            fabro_bin=factory_fabro_bin(factory=target, fallback=resolve_fabro_bin(cwd=self.repo)),
            target=FabroTarget(server_url=target.server, dev_token=target.dev_token),
            runner=self.runner,
            cwd=self.repo,
        )


def _ps_payload(*, payload: object | None) -> bool:
    """Whether a parsed ``fabro ps --json`` payload has its documented shape."""
    if isinstance(payload, list):
        return True
    if not isinstance(payload, dict):
        return False
    return isinstance(cast("dict[str, object]", payload).get("runs"), list)
