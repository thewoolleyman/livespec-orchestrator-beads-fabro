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
    dispatch_traceparent,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_run_id_from_output,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import (
    FabroRunner,
    FabroRunResult,
)

__all__: list[str] = [
    "TRACEPARENT_ENV_VAR",
    "fabro_run_argv",
    "fabro_run_env",
    "launch_fabro_run",
    "server_env",
]

# The W3C/OTel environment convention the engine reads to find its parent.
# Non-secret by construction: a traceparent carries trace and span ids and
# a flag byte, never a credential.
TRACEPARENT_ENV_VAR = "TRACEPARENT"


def launch_fabro_run(  # noqa: PLR0913 — kw-only launch assembly; each argument is one INDEPENDENT input the invocation needs, and folding any pair into a carrier would invent a grouping the launch does not have.
    *,
    fabro_bin: str,
    runner: FabroRunner,
    cwd: Path,
    fabro_version: str | None,
    server_url: str | None,
    environment: str | None,
    workflow_toml: Path,
    goal_file: Path,
    inputs: tuple[str, ...],
    timeout_seconds: float,
    labels: tuple[str, ...],
    correlation: DispatchCorrelation | None,
) -> FabroRunResult:
    """Run `fabro run` for one dispatch and read the run id off its output."""
    argv = fabro_run_argv(
        fabro_bin=fabro_bin,
        workflow=client.run_workflow(version=fabro_version, workflow_toml=workflow_toml),
        goal_file=goal_file,
        inputs=inputs,
        labels=labels,
        correlation=correlation,
        environment=environment,
        server_url=server_url,
    )
    env = fabro_run_env(server_url=server_url, correlation=correlation)
    command = (
        runner.run(argv=argv, cwd=cwd, timeout_seconds=timeout_seconds)
        if env is None
        else runner.run(argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env)
    )
    return FabroRunResult(
        command=command,
        run_id=fabro_run_id_from_output(output=f"{command.stdout}\n{command.stderr}"),
    )


def fabro_run_argv(  # noqa: PLR0913 — kw-only argv assembly, same reasoning as `launch_fabro_run` above: each argument is one INDEPENDENT operand of the one invocation, and grouping any pair into a carrier would invent a relationship the argv does not have.
    *,
    fabro_bin: str,
    workflow: Path,
    goal_file: Path,
    inputs: tuple[str, ...],
    labels: tuple[str, ...],
    correlation: DispatchCorrelation | None,
    environment: str | None,
    server_url: str | None,
) -> list[str]:
    """The `fabro run` argv, with one `--label` pair per passable value.

    The labels and the environment sit BEFORE the per-subcommand `--server`,
    which pinned 0.254 requires to stay last on the subcommand.

    `labels` carries the `KEY=VALUE` pairs the DISPATCH resolved -- the
    repository and each ACP node's rendered candidate entitlement -- and
    arrives already rendered, exactly as `inputs` does, because the values
    come from a plan this seam cannot see. They ride BESIDE the correlation
    triple rather than through it: the triple is the trace-join identity,
    and `_dispatcher_correlation` is the one place that stays true.

    An `environment` of None emits NO flag rather than the `default` id the
    server would have selected anyway. The two are equivalent only on an
    engine that HAS the flag: pinned 0.254 has none and selects from
    `workflow.toml`, so an unconditional pair kills every dispatch to that
    engine at argument parsing, before any run exists to diagnose.
    """
    return [
        fabro_bin,
        "run",
        str(workflow),
        "--goal-file",
        str(goal_file),
        *client.fabro_input_args(inputs=inputs),
        "--no-upgrade-check",
        *([] if environment is None else ["--environment", environment]),
        *correlation_label_args(correlation=correlation),
        *client.fabro_label_args(labels=labels),
        *([] if server_url is None else ["--server", server_url]),
    ]


def fabro_run_env(
    *,
    server_url: str | None,
    correlation: DispatchCorrelation | None,
) -> dict[str, str] | None:
    """The `fabro run` environment: the factory binding plus the traceparent.

    The traceparent rides the environment rather than an argv flag because
    that is the convention the engine reads, and it is derived from the
    dispatch id so it names the same span the Dispatcher emitted — a
    second identity minted here would parent the run to a span nobody
    wrote. A launch with no factory URL still carries it: the two arms are
    independent, and a traceparent that only shipped when there happened
    to be a `FABRO_SERVER` beside it would be a join that worked by
    coincidence.
    """
    base = server_env(server_url=server_url)
    if correlation is None:
        return base
    traceparent = dispatch_traceparent(dispatch_id=correlation.dispatch_id)
    return {**(base or {}), TRACEPARENT_ENV_VAR: traceparent}


def server_env(*, server_url: str | None) -> dict[str, str] | None:
    """The `FABRO_SERVER` environment that binds a verb to one factory."""
    if server_url is None:
        return None
    return {"FABRO_SERVER": server_url}
