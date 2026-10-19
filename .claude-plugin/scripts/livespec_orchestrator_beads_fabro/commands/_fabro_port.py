"""Thin Fabro CLI facade for the dispatcher dependency surface."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_correlation import DispatchCorrelation
from livespec_orchestrator_beads_fabro.commands._fabro_port_auth import fabro_auth_login
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import (
    FabroHttpPort,
    FabroHttpTransport,
    UrllibFabroHttpTransport,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_payload import (
    fabro_events_payload,
    fabro_json_payload,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    FabroFailureDetail,
    FabroRunSummary,
    fabro_failure_detail_from_payload,
    fabro_run_summaries_from_payload,
    fabro_run_summaries_from_stdout,
    fabro_status_kind_from_payload,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_run_launch import (
    launch_fabro_run,
    server_env,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import (
    FabroCommand,
    FabroCommandResult,
    FabroEventsResult,
    FabroInspectResult,
    FabroJsonResult,
    FabroPsResult,
    FabroRunner,
    FabroRunResult,
    FabroTarget,
    FabroVersionResult,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_workflow import fabro_preflight

__all__: list[str] = [
    "FabroCommand",
    "FabroCommandResult",
    "FabroEventsResult",
    "FabroFailureDetail",
    "FabroHttpPort",
    "FabroInspectResult",
    "FabroJsonResult",
    "FabroPort",
    "FabroPsResult",
    "FabroRunResult",
    "FabroRunSummary",
    "FabroTarget",
    "FabroVersionResult",
    "fabro_port_for_plan",
    "fabro_run_summaries_from_stdout",
]


@dataclass(frozen=True, kw_only=True)
class FabroPort:
    """Single place this repo knows Fabro is a CLI.

    The port deliberately exposes only the Fabro operations the dispatcher
    already depends on. The client binary and factory target are constructor
    data, so an upgrade-candidate binary is tested by constructing another
    port with a different `fabro_bin`.

    Most verbs shell out through `runner`; the interview-answer and cancel
    verbs go over `http` instead, because the pinned CLI exposes neither
    non-interactively. Both seams read the SAME `target`, so a port can only
    ever act on the factory it was constructed for.
    """

    fabro_bin: str
    target: FabroTarget
    runner: FabroRunner
    cwd: Path
    http: FabroHttpTransport = field(default_factory=UrllibFabroHttpTransport)
    fabro_version: str | None = None

    def run(  # noqa: PLR0913 — kw-only launch assembly, the same reasoning `launch_fabro_run` and `fabro_run_argv` below it carry: each argument is one INDEPENDENT operand of the one invocation, and grouping any pair into a carrier would invent a relationship the argv does not have.
        self,
        *,
        workflow_toml: Path,
        goal_file: Path,
        inputs: tuple[str, ...],
        timeout_seconds: float,
        labels: tuple[str, ...] = (),
        correlation: DispatchCorrelation | None = None,
        runner: FabroRunner | None = None,
    ) -> FabroRunResult:
        """Launch one `fabro run`, carrying this dispatch's correlation.

        `labels` are the already-rendered `KEY=VALUE` run labels the
        dispatch resolved beside that correlation — the repository and each
        ACP node's candidate entitlement. Rendered pairs rather than a
        carrier for the reason `inputs` is: the values come from a plan
        this facade does not read.

        An injected runner changes only this launch's source venue. Every other
        verb retains the port's bound runner, including watchdog inspection.
        """
        return launch_fabro_run(
            fabro_bin=self.fabro_bin,
            runner=runner if runner is not None else self.runner,
            cwd=self.cwd,
            fabro_version=self.fabro_version,
            server_url=self.target.server_url,
            environment=self.target.environment,
            workflow_toml=workflow_toml,
            goal_file=goal_file,
            inputs=inputs,
            timeout_seconds=timeout_seconds,
            labels=labels,
            correlation=correlation,
        )

    def auth_login(self, *, timeout_seconds: float) -> FabroCommandResult | None:
        return fabro_auth_login(
            fabro_bin=self.fabro_bin,
            runner=self.runner,
            cwd=self.cwd,
            target=self.target,
            timeout_seconds=timeout_seconds,
        )

    def secret_set(self, *, secret_name: str, stdin: int, timeout_seconds: float) -> FabroCommand:
        """Store one named secret while its value travels only on stdin."""
        return self.runner.run(
            argv=[
                self.fabro_bin,
                "secret",
                *self._server_suffix(),
                "set",
                secret_name,
                "--value-stdin",
            ],
            cwd=self.cwd,
            timeout_seconds=timeout_seconds,
            stdin=stdin,
        )

    def inspect(self, *, run_id: str, timeout_seconds: float) -> FabroInspectResult:
        command = self._run(
            argv=[self.fabro_bin, "inspect", run_id, "--json", *self._server_suffix()],
            timeout_seconds=timeout_seconds,
        )
        payload = fabro_json_payload(command=command)
        return FabroInspectResult(
            command=command,
            payload=payload,
            status_kind=fabro_status_kind_from_payload(payload=payload),
            failure=fabro_failure_detail_from_payload(payload=payload),
        )

    def events(self, *, run_id: str, timeout_seconds: float) -> FabroEventsResult:
        command = self._run(
            argv=[self.fabro_bin, "events", run_id, "--json", *self._server_suffix()],
            timeout_seconds=timeout_seconds,
        )
        return FabroEventsResult(command=command, payload=fabro_events_payload(command=command))

    def dump(self, *, run_id: str, output_dir: Path, timeout_seconds: float) -> FabroCommandResult:
        """Export one run's whole record into `output_dir`.

        Reports WHETHER the export ran rather than what it produced: what
        counts as the artifact differs per caller — the preserve-by-reference
        writer globs for a checkpointed diff, while its reader re-digests the
        paths a pointer already named — so the directory is left to whoever
        asked for it.
        """
        command = self._run(
            argv=[self.fabro_bin, "dump", run_id, *self._server_suffix(), "-o", str(output_dir)],
            timeout_seconds=timeout_seconds,
        )
        return FabroCommandResult(command=command)

    def ps(self, *, timeout_seconds: float) -> FabroPsResult:
        command = self._run(
            argv=[self.fabro_bin, "ps", "-a", "--json", *self._server_suffix()],
            timeout_seconds=timeout_seconds,
        )
        payload = fabro_json_payload(command=command)
        return FabroPsResult(
            command=command,
            payload=payload,
            runs=fabro_run_summaries_from_payload(payload=payload),
        )

    def settings(self, *, timeout_seconds: float) -> FabroJsonResult:
        """`fabro settings --json` — the EFFECTIVE settings of this port's server.

        Read for one figure the facade carried no other route to: the server's
        own `scheduler.max_concurrent_runs`, which overflow selection compares a
        candidate's non-terminal run count against. The whole payload is handed
        back rather than that one number, because the shape differs between
        builds and `_fabro_port_records` is where this family's readings of a
        payload live.
        """
        command = self._run(
            argv=[self.fabro_bin, "settings", "--json", *self._server_suffix()],
            timeout_seconds=timeout_seconds,
        )
        return FabroJsonResult(command=command, payload=fabro_json_payload(command=command))

    def preflight(
        self,
        *,
        workflow_toml: Path,
        goal_file: Path,
        inputs: tuple[str, ...],
        timeout_seconds: float,
    ) -> FabroJsonResult:
        return fabro_preflight(
            fabro_bin=self.fabro_bin,
            runner=self.runner,
            cwd=self.cwd,
            server_url=self.target.server_url,
            workflow_toml=workflow_toml,
            goal_file=goal_file,
            inputs=inputs,
            timeout_seconds=timeout_seconds,
        )

    def rm(self, *, run_id: str, timeout_seconds: float) -> FabroCommandResult:
        command = self._run(
            argv=[self.fabro_bin, "rm", "-f", run_id, *self._server_suffix()],
            timeout_seconds=timeout_seconds,
        )
        return FabroCommandResult(command=command)

    def server_api(self) -> FabroHttpPort:
        """This same factory's server-API face: `questions` / `answer` / `cancel`.

        Those three verbs sit beside `rm` rather than inside it because the
        pinned CLI exposes none of them non-interactively, so they speak HTTP.
        The face is built from THIS port's own `target`, so it cannot reach a
        factory this port was not constructed for — the whole reason the
        reconciler goes through the port at all.
        """
        return FabroHttpPort(target=self.target, transport=self.http)

    def top_level_server_parse_probe(
        self,
        *,
        subcommand: tuple[str, ...],
        timeout_seconds: float,
    ) -> FabroCommandResult:
        server_url = self.target.server_url or ""
        command = self._run(
            argv=[self.fabro_bin, "--server", server_url, *subcommand],
            timeout_seconds=timeout_seconds,
        )
        return FabroCommandResult(command=command)

    def validate(self, *, workflow_toml: Path, timeout_seconds: float) -> FabroJsonResult:
        command = self._run(
            argv=[self.fabro_bin, "validate", str(workflow_toml), "--json"],
            timeout_seconds=timeout_seconds,
        )
        return FabroJsonResult(command=command, payload=fabro_json_payload(command=command))

    def version(self, *, timeout_seconds: float) -> FabroVersionResult:
        """`fabro version --json` — the client AND the server the port is bound to.

        The JSON form, because the human form spreads each build over several
        labelled lines, and every build from the pinned 0.254 engine to the
        Petri-era candidate carries `server.git_sha` under `--json`.

        Addressed through `FABRO_SERVER`, the same env mechanism `run` relies on,
        rather than through a per-subcommand `--server`: a port constructed on one
        factory must not report another factory's engine. Without it the verb
        reads whichever server the host's ambient configuration names, which on a
        two-factory host is a fleet-global surrogate for a per-target question —
        and the currency predicate is required to be target-aware.
        """
        command = self._run(
            argv=[self.fabro_bin, "version", "--json"],
            timeout_seconds=timeout_seconds,
            env=self._server_env(),
        )
        return FabroVersionResult(command=command, text=command.stdout)

    def client_version(self, *, timeout_seconds: float) -> FabroVersionResult:
        """`fabro --version` — the CLIENT build alone, with no server round trip.

        Distinct from `version`, which ALSO asks the configured server for its
        own build: a dispatch records which BINARY drove it, and a local flag
        answers that without putting a network call on the dispatch path.
        """
        command = self._run(
            argv=[self.fabro_bin, "--version"],
            timeout_seconds=timeout_seconds,
        )
        return FabroVersionResult(command=command, text=command.stdout)

    def _run(
        self,
        *,
        argv: list[str],
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> FabroCommand:
        if env is None:
            return self.runner.run(argv=argv, cwd=self.cwd, timeout_seconds=timeout_seconds)
        return self.runner.run(
            argv=argv,
            cwd=self.cwd,
            timeout_seconds=timeout_seconds,
            env=env,
        )

    def _server_suffix(self) -> list[str]:
        # Most verbs take a per-subcommand `--server`; pinned 0.254.0 rejects
        # global placement. Petri-era `secret` instead owns it on the group.
        if self.target.server_url is None:
            return []
        return ["--server", self.target.server_url]

    def _server_env(self) -> dict[str, str] | None:
        return server_env(server_url=self.target.server_url)


def fabro_port_for_plan(*, plan: Any, runner: FabroRunner) -> FabroPort:
    """Construct the Fabro CLI port from a dispatch plan."""
    return FabroPort(
        fabro_bin=plan.fabro_bin,
        target=FabroTarget(
            server_url=plan.fabro_factory_server,
            dev_token=plan.fabro_factory_dev_token,
            environment=plan.fabro_factory_environment,
        ),
        runner=runner,
        cwd=plan.repo,
        fabro_version=getattr(plan, "fabro_version", None),
    )
