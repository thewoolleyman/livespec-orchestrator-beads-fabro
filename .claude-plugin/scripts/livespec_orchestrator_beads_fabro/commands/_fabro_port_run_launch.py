"""How ONE `fabro run` invocation is assembled: argv, environment, labels.

Part of the `_fabro_port` facade family, which is the only place this
package reaches the engine. It is its own module because the launch is the
one invocation whose shape depends on something no other verb carries: the
dispatch's CORRELATION. The argv grows a `--label` pair per passable value
and the environment grows a `TRACEPARENT` naming the dispatch's own span,
and those two have to be decided together — a label without the
traceparent gives correlated spans in two disjoint traces, and a
traceparent without the labels gives one trace whose spans cannot be
queried by work-item.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _fabro_client as client
from livespec_orchestrator_beads_fabro.commands._dispatcher_correlation import (
    DispatchCorrelation,
    correlation_label_args,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_run_id_from_output,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import (
    FabroRunner,
    FabroRunResult,
)

__all__: list[str] = [
    "fabro_run_argv",
    "launch_fabro_run",
    "server_env",
]


def launch_fabro_run(  # noqa: PLR0913 — kw-only launch assembly; each argument is one INDEPENDENT input the invocation needs, and folding any pair into a carrier would invent a grouping the launch does not have.
    *,
    fabro_bin: str,
    runner: FabroRunner,
    cwd: Path,
    fabro_version: str | None,
    server_url: str | None,
    workflow_toml: Path,
    goal_file: Path,
    inputs: tuple[str, ...],
    timeout_seconds: float,
    correlation: DispatchCorrelation | None,
) -> FabroRunResult:
    """Run `fabro run` for one dispatch and read the run id off its output."""
    argv = fabro_run_argv(
        fabro_bin=fabro_bin,
        workflow=client.run_workflow(version=fabro_version, workflow_toml=workflow_toml),
        goal_file=goal_file,
        inputs=inputs,
        correlation=correlation,
        server_url=server_url,
    )
    env = server_env(server_url=server_url)
    command = (
        runner.run(argv=argv, cwd=cwd, timeout_seconds=timeout_seconds)
        if env is None
        else runner.run(argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env)
    )
    return FabroRunResult(
        command=command,
        run_id=fabro_run_id_from_output(output=f"{command.stdout}\n{command.stderr}"),
    )


def fabro_run_argv(
    *,
    fabro_bin: str,
    workflow: Path,
    goal_file: Path,
    inputs: tuple[str, ...],
    correlation: DispatchCorrelation | None,
    server_url: str | None,
) -> list[str]:
    """The `fabro run` argv, with one `--label` pair per passable value.

    The labels sit BEFORE the per-subcommand `--server`, which pinned
    0.254 requires to stay last on the subcommand.
    """
    return [
        fabro_bin,
        "run",
        str(workflow),
        "--goal-file",
        str(goal_file),
        *client.fabro_input_args(inputs=inputs),
        "--no-upgrade-check",
        *correlation_label_args(correlation=correlation),
        *([] if server_url is None else ["--server", server_url]),
    ]


def server_env(*, server_url: str | None) -> dict[str, str] | None:
    """The `FABRO_SERVER` environment that binds a verb to one factory."""
    if server_url is None:
        return None
    return {"FABRO_SERVER": server_url}
