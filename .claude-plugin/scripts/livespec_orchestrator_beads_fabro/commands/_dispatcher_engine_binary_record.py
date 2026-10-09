"""Which engine client binary drove one dispatch, as the record carries it.

The dispatch record is the one artifact written before a run starts, so it is
where a reader later establishes what the orchestrator believed at dispatch
time. While one global client drove every factory that question had one answer
for the whole host and nothing needed recording; with a per-factory `bin`
(`_dispatcher_factory_bin`) two dispatches minutes apart can run different
engines, and NOTHING ELSE in the record says which.

TWO FIELDS, BECAUSE NEITHER ANSWERS THE OTHER'S QUESTION. The ABSOLUTE PATH
says which FILE was executed: a bare name or a relative path resolves against
a `PATH` and a working directory that are not part of the record, so recording
the unresolved value records a question rather than an answer. The
`fabro --version` TEXT says which BUILD that file is, which a path cannot
answer once a path is re-pinned in place — which is exactly how this fleet
rolls an engine out.

AN UNREPORTABLE VERSION IS `None`, NEVER AN EMPTY STRING. A client that exits
non-zero was not observed; a client that exits 0 printing nothing reported
nothing. The two have different remedies, and a record that spelled both the
same way would send a reader hunting a silent client when the binary was
simply not runnable.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._fabro_port import (
    FabroPort,
    FabroTarget,
    FabroVersionResult,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroRunner

__all__: list[str] = [
    "EngineBinary",
    "engine_binary",
    "engine_binary_path",
]

# `fabro --version` is a local flag read, so it is bounded far below any verb
# that reaches a server: a client that cannot answer this in seconds is one the
# record should report as unobserved rather than one a dispatch waits on.
_VERSION_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True, kw_only=True)
class EngineBinary:
    """The engine client binary that drove one dispatch, as journaled."""

    path: str
    version: str | None


def engine_binary(*, fabro_bin: str, runner: FabroRunner, cwd: Path) -> EngineBinary:
    """Measure the binary `fabro_bin` names: its absolute path and its build.

    The probe goes through `FabroPort` rather than straight to the runner so
    the Dispatcher keeps ONE place that knows Fabro is a CLI. The port is
    opened on an EMPTY target deliberately: `--version` is a question about a
    local file, and pointing it at a server would make a dispatch's own record
    depend on that server being reachable.
    """
    port = FabroPort(
        fabro_bin=fabro_bin,
        target=FabroTarget(),
        runner=runner,
        cwd=cwd,
    )
    return EngineBinary(
        path=engine_binary_path(fabro_bin=fabro_bin),
        version=_reported_version(
            result=port.client_version(timeout_seconds=_VERSION_TIMEOUT_SECONDS)
        ),
    )


def engine_binary_path(*, fabro_bin: str) -> str:
    """The ABSOLUTE path of the file `fabro_bin` names.

    `shutil.which` covers both shapes in one call — it resolves a bare name
    through `PATH` and checks a path-shaped value directly — and the absolutize
    fallback is what an UNRESOLVABLE value records: the path the Dispatcher
    tried, made unambiguous, rather than a relative string whose meaning
    depends on a working directory the record does not carry.
    """
    located = shutil.which(fabro_bin)
    if located is not None:
        return str(Path(located).absolute())
    return str(Path(fabro_bin).absolute())


def _reported_version(*, result: FabroVersionResult) -> str | None:
    if result.command.exit_code != 0:
        return None
    return result.text.strip()
