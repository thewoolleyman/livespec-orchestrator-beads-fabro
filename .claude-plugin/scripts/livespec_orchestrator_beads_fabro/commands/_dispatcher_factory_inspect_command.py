"""The factory-addressed ``dispatcher inspect`` reader.

The host's ambient Fabro client and server are not a safe fallback for this
surface: a run belonging to a Petri-era factory can decode as missing when it
is read through the host client. This command builds its port from the selected
factory's binary and resolved server instead.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._config import (
    resolve_fabro_factory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import (
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = [
    "add_factory_inspect_arguments",
    "run_factory_inspect_command",
]

_FACTORY_INSPECT_TIMEOUT_SECONDS = 30.0


def add_factory_inspect_arguments(*, parser: argparse.ArgumentParser) -> None:
    """Add the factory-addressed run-reader flags."""
    _ = parser.add_argument("--factory", dest="factory", required=True)
    _ = parser.add_argument("run_id")
    _ = parser.add_argument("-o", "--output", dest="output_dir", type=Path)


def run_factory_inspect_command(*, args: argparse.Namespace) -> int:
    """Read one run through its declared factory client and server."""
    factory = resolve_fabro_factory(cwd=Path.cwd(), factory=args.factory)
    fabro_bin = cast(str, factory.fabro_bin)
    port = FabroPort(
        fabro_bin=fabro_bin,
        target=FabroTarget(
            server_url=factory.server,
            dev_token=factory.dev_token,
            environment=factory.environment.environment_id,
        ),
        runner=ShellCommandRunner(),
        cwd=Path.cwd(),
    )
    if args.output_dir is not None:
        result = port.dump(
            run_id=args.run_id,
            output_dir=args.output_dir,
            timeout_seconds=_FACTORY_INSPECT_TIMEOUT_SECONDS,
        )
        write_stdout(text=result.command.stdout)
        return result.command.exit_code
    result = port.inspect(run_id=args.run_id, timeout_seconds=_FACTORY_INSPECT_TIMEOUT_SECONDS)
    write_stdout(text=result.command.stdout)
    return result.command.exit_code
