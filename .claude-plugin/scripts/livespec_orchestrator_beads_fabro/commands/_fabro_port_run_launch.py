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

IT IS ALSO WHERE THE FAMILY'S FACTORY-BINDING ENVIRONMENTS LIVE, because
`server_env` has had two readers outside the launch since the preflight needed
one: `fabro preflight` and `fabro version` both resolve the engine they speak to
from `FABRO_SERVER` rather than from a per-subcommand flag, so the one place that
binding is spelled serves all three. `version_probe_env` is the second of those
environments and sits beside it for the same reason — a binding and the credential
scrub that completes it are one question about one child environment.
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
    "version_probe_env",
]

# The W3C/OTel environment convention the engine reads to find its parent.
# Non-secret by construction: a traceparent carries trace and span ids and
# a flag byte, never a credential.
TRACEPARENT_ENV_VAR = "TRACEPARENT"

# Every Fabro CLIENT SETTING the dispatching process may carry that would
# address an invocation at a credential other than the selected factory's own,
# removed from the child environment rather than overridden (a `None` delta
# value REMOVES the name — see `FabroRunner.run`).
#
# WHY THE VERSION PROBE OWES THIS AND NOT MERELY A `FABRO_SERVER` BINDING. A
# governed repository's credential wrapper may route its own adopter Fabro, and
# it does so by exporting `FABRO_HOME` plus a bare `FABRO_DEV_TOKEN` into every
# process it wraps — the Dispatcher included. `fabro version` then reads its
# credential out of THAT home's `auth.json`, which holds no login for the
# selected factory, the server answers `Authentication required.` with no
# `git_sha`, and the Fabro currency gate refuses the dispatch as
# `serving-build-unidentified` before claim. Measured 2026-10-23 on the control
# node against `https://gmktec-xubuntu.perch-rudd.ts.net:32276`: the host
# default home reported `server.git_sha` `9f6c38f`, an empty `FABRO_HOME`
# reported the authentication error with no commit, and that same empty home
# plus the host's VALID dev token for that factory still reported the error — so
# the credential comes from the home and passing a token through the environment
# is not a fix. Keeping the foreign home out of the probe is.
#
# THE PER-FACTORY `FABRO_DEV_TOKEN__<factory>` NAMES ARE DELIBERATELY NOT HERE.
# Those ARE the selected factory's own client settings — `_config` reads one into
# the target's `dev_token` and `_fabro_port_auth` resolves the bearer credential
# from it — so scrubbing them would remove the very credential the probe is
# supposed to authenticate with. The bare name is the wrapper's; the suffixed
# name is the factory's.
_FOREIGN_CLIENT_SETTINGS: dict[str, str | None] = {
    "FABRO_HOME": None,
    "FABRO_DEV_TOKEN": None,
}


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


def version_probe_env(*, server_url: str | None) -> dict[str, str | None]:
    """`fabro version`'s child environment: the binding, with the scrub applied.

    The binding alone does not settle WHICH CREDENTIAL the probe authenticates
    with, and `_FOREIGN_CLIENT_SETTINGS` is why that matters.
    """
    return {**(server_env(server_url=server_url) or {}), **_FOREIGN_CLIENT_SETTINGS}
