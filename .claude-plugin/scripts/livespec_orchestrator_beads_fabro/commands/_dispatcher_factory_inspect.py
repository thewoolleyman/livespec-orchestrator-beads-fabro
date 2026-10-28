"""The factory-addressed reader for one Fabro run.

An inspection is meaningful only when it reaches the client binary that can
decode the selected factory's records. This command therefore requires the
factory's own ``bin`` and its resolved server address; it never substitutes the
dispatching host's ambient Fabro client or target.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TextIO

from livespec_orchestrator_beads_fabro.commands._config import (
    FactoryTarget,
    resolve_fabro_factory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_registry import (
    factory_registry_unobservable,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import (
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import (
    FabroCommand,
    FabroRunner,
    FabroTarget,
)
from livespec_orchestrator_beads_fabro.commands._factory_client_settings import (
    FACTORY_BIN_KEY,
)
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout

__all__: list[str] = [
    "FACTORY_INSPECT_REFUSAL_EXIT",
    "add_factory_inspect_arguments",
    "run_factory_inspect_command",
]

FACTORY_INSPECT_REFUSAL_EXIT = 2
_READ_TIMEOUT_SECONDS = 60.0


def add_factory_inspect_arguments(*, parser: argparse.ArgumentParser) -> None:
    """Register the read-only factory run reader's command-line arguments."""
    _ = parser.add_argument("--factory", required=True)
    _ = parser.add_argument("run_id")
    _ = parser.add_argument("-o", "--output", dest="output_dir", type=Path, default=None)
    _ = parser.add_argument("--repo", default=None)


def run_factory_inspect_command(
    *,
    args: argparse.Namespace,
    runner: FabroRunner | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Print or export a run using precisely the selected factory's client."""
    repo = Path(args.repo) if args.repo is not None else Path.cwd()
    factory = resolve_fabro_factory(cwd=repo, factory=args.factory)
    fabro_bin = factory.fabro_bin
    if fabro_bin is None or FACTORY_BIN_KEY in factory.registry_sourced_client_keys:
        write_stderr(text=_missing_bin_refusal(factory=factory), stream=stderr)
        return FACTORY_INSPECT_REFUSAL_EXIT
    refusal = _factory_address_refusal(factory=factory)
    if refusal is not None:
        write_stderr(text=refusal, stream=stderr)
        return FACTORY_INSPECT_REFUSAL_EXIT
    port = FabroPort(
        fabro_bin=fabro_bin,
        target=FabroTarget(server_url=factory.server, dev_token=factory.dev_token),
        runner=runner if runner is not None else ShellCommandRunner(),
        cwd=repo,
    )
    if args.output_dir is not None:
        result = port.dump(
            run_id=args.run_id,
            output_dir=args.output_dir,
            timeout_seconds=_READ_TIMEOUT_SECONDS,
        )
        return _report_command(command=result.command, stdout=stdout, stderr=stderr)
    result = port.inspect(run_id=args.run_id, timeout_seconds=_READ_TIMEOUT_SECONDS)
    return _report_command(command=result.command, stdout=stdout, stderr=stderr)


def _missing_bin_refusal(*, factory: FactoryTarget) -> str:
    """Explain why no declared client must never turn into a PATH fallback."""
    return (
        f"dispatcher inspect refused: factory {factory.name} declares no "
        f"dispatcher.factories.{factory.name}.bin; this reader requires the "
        "factory-specific Fabro client and will not use the host PATH client\n"
    )


def _factory_address_refusal(*, factory: FactoryTarget) -> str | None:
    """Explain why this factory cannot be addressed without an ambient fallback."""
    registry_refusal = factory_registry_unobservable(factory=factory)
    if registry_refusal is not None:
        return f"dispatcher inspect refused: {registry_refusal}\n"
    if factory.server is None:
        return (
            f"dispatcher inspect refused: factory {factory.name} has no resolved "
            "server address, so this reader will not use a host-default server\n"
        )
    return None


def _report_command(*, command: FabroCommand, stdout: TextIO | None, stderr: TextIO | None) -> int:
    """Relay the factory client's record or diagnostic without changing its meaning."""
    if command.exit_code != 0:
        text = command.stderr or command.stdout or "fabro read failed without diagnostic\n"
        write_stderr(text=text, stream=stderr)
        return command.exit_code
    write_stdout(text=command.stdout, stream=stdout)
    return 0
