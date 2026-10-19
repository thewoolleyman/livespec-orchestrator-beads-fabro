"""How ONE `fabro preflight` invocation is assembled: argv, environment, parse.

Part of the `_fabro_port` facade family, which is the only place this package
reaches the engine, and a sibling of `_fabro_port_run_launch` for the same
reason that module exists: the preflight is an invocation whose argv is
assembled from the launch's own operands — the workflow package, the goal file
and the `--input` pairs — and that assembly is a concern in its own right rather
than a line of the facade class.

WHY THE ENVIRONMENT IS HANDED THE SERVER URL AND NOT A `--server` FLAG ALONE.
`fabro preflight` resolves the engine it validates against from the same
`FABRO_SERVER` mechanism the launch uses, so a preflight that carried only the
subcommand flag would validate one factory's graph against whichever server the
host's ambient configuration names. The flag AND the environment are both
supplied here, exactly as the launch supplies them, so a preflight can only
ever answer about the factory its port was constructed for.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _fabro_client as client
from livespec_orchestrator_beads_fabro.commands._fabro_port_payload import fabro_json_payload
from livespec_orchestrator_beads_fabro.commands._fabro_port_run_launch import server_env
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import (
    FabroJsonResult,
    FabroRunner,
)

__all__: list[str] = [
    "fabro_preflight",
    "fabro_preflight_argv",
]


def fabro_preflight(  # noqa: PLR0913 — kw-only invocation assembly, the same reasoning `launch_fabro_run` carries: each argument is one INDEPENDENT operand of the one invocation, and folding any pair into a carrier would invent a relationship the argv does not have.
    *,
    fabro_bin: str,
    runner: FabroRunner,
    cwd: Path,
    server_url: str | None,
    workflow_toml: Path,
    goal_file: Path,
    inputs: tuple[str, ...],
    timeout_seconds: float,
) -> FabroJsonResult:
    """Run `fabro preflight` for one launch's operands and parse its payload."""
    argv = fabro_preflight_argv(
        fabro_bin=fabro_bin,
        server_url=server_url,
        workflow_toml=workflow_toml,
        goal_file=goal_file,
        inputs=inputs,
    )
    env = server_env(server_url=server_url)
    command = (
        runner.run(argv=argv, cwd=cwd, timeout_seconds=timeout_seconds)
        if env is None
        else runner.run(argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env)
    )
    return FabroJsonResult(command=command, payload=fabro_json_payload(command=command))


def fabro_preflight_argv(
    *,
    fabro_bin: str,
    server_url: str | None,
    workflow_toml: Path,
    goal_file: Path,
    inputs: tuple[str, ...],
) -> list[str]:
    """The `fabro preflight` argv, with `--server` LAST on the subcommand.

    The pinned 0.254.0 engine rejects the flag in global position, so its place
    at the end of the subcommand is a wire requirement rather than a style, and
    it is omitted entirely when the port names no server — which is how an
    unconfigured repository keeps the bare CLI's ambient behaviour.
    """
    server_suffix = [] if server_url is None else ["--server", server_url]
    return [
        fabro_bin,
        "preflight",
        str(workflow_toml),
        "--goal-file",
        str(goal_file),
        *client.fabro_input_args(inputs=inputs),
        "--no-upgrade-check",
        "--json",
        *server_suffix,
    ]
