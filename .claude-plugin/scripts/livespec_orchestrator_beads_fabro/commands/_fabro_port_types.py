"""Typed Fabro port records and runner protocols."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    FabroFailureDetail,
    FabroRunSummary,
)

__all__: list[str] = [
    "FabroCommand",
    "FabroCommandResult",
    "FabroEventsResult",
    "FabroInspectResult",
    "FabroJsonResult",
    "FabroPsResult",
    "FabroRunResult",
    "FabroRunner",
    "FabroTarget",
    "FabroVersionResult",
]


class FabroCommand(Protocol):
    """Result fields consumed from the dispatcher's command runner."""

    @property
    def exit_code(self) -> int: ...

    @property
    def stdout(self) -> str: ...

    @property
    def stderr(self) -> str: ...


class FabroRunner(Protocol):
    """The subprocess seam every engine invocation of this family runs through.

    `env` is the child's environment DELTA against this process, exactly as
    `CommandRunner`'s is: a string value SETS the variable and a `None` value
    REMOVES it. The removal arm is what lets an invocation ask for a child
    WITHOUT a variable this process carries, which a mapping merged over
    `os.environ` cannot express -- and `FabroPort.version` needs exactly that,
    because the probe must address the selected factory with that factory's own
    client settings rather than with whatever Fabro credential the dispatching
    environment happens to carry.
    """

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> FabroCommand: ...


@dataclass(frozen=True, kw_only=True)
class FabroTarget:
    """Factory target for one Fabro client binary."""

    server_url: str | None = None
    dev_token: str | None = None
    # The server-catalog sandbox environment this factory's runs are placed
    # in. It sits on the TARGET beside the server rather than on the launch
    # call because it is a property of the factory, so a port can no more
    # launch into another factory's environment than it can reach another
    # factory's server. None means this factory names none.
    environment: str | None = None


@dataclass(frozen=True, kw_only=True)
class FabroCommandResult:
    """Result for Fabro commands whose output is not parsed further."""

    command: FabroCommand


@dataclass(frozen=True, kw_only=True)
class FabroRunResult:
    """Result for `fabro run`, including the run id printed by the CLI."""

    command: FabroCommand
    run_id: str | None


@dataclass(frozen=True, kw_only=True)
class FabroJsonResult:
    """Result for a `--json` Fabro command."""

    command: FabroCommand
    payload: object | None


@dataclass(frozen=True, kw_only=True)
class FabroEventsResult:
    """Parsed `fabro events --json` result."""

    command: FabroCommand
    payload: object | None


@dataclass(frozen=True, kw_only=True)
class FabroInspectResult:
    """Parsed `fabro inspect --json` result with normalized status kind."""

    command: FabroCommand
    payload: object | None
    status_kind: str | None
    failure: FabroFailureDetail | None
    events_payload: object | None = None


@dataclass(frozen=True, kw_only=True)
class FabroPsResult:
    """Parsed `fabro ps -a --json` result."""

    command: FabroCommand
    payload: object | None
    runs: tuple[FabroRunSummary, ...]


@dataclass(frozen=True, kw_only=True)
class FabroVersionResult:
    """Raw `fabro version` result."""

    command: FabroCommand
    text: str
