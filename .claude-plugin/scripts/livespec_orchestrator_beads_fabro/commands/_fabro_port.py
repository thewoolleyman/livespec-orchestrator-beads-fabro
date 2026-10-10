"""Thin Fabro CLI facade for the dispatcher dependency surface."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
    fabro_run_id_from_output,
    fabro_run_summaries_from_payload,
    fabro_run_summaries_from_stdout,
    fabro_status_kind_from_payload,
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

    def run(
        self,
        *,
        workflow_toml: Path,
        goal_file: Path,
        inputs: tuple[str, ...],
        timeout_seconds: float,
    ) -> FabroRunResult:
        command = self._run(
            argv=[
                self.fabro_bin,
                "run",
                str(workflow_toml),
                "--goal-file",
                str(goal_file),
                *_input_args(inputs=inputs),
                "--no-upgrade-check",
                *self._server_suffix(),
            ],
            timeout_seconds=timeout_seconds,
            env=self._server_env(),
        )
        return FabroRunResult(
            command=command,
            run_id=fabro_run_id_from_output(output=f"{command.stdout}\n{command.stderr}"),
        )

    def auth_login(self, *, timeout_seconds: float) -> FabroCommandResult | None:
        if self.target.server_url is None or self.target.dev_token is None:
            return None
        command = self._run(
            argv=[
                self.fabro_bin,
                "auth",
                "login",
                "--dev-token",
                self.target.dev_token,
                "--server",
                self.target.server_url,
            ],
            timeout_seconds=timeout_seconds,
        )
        return FabroCommandResult(command=command)

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

    def preflight(
        self,
        *,
        workflow_toml: Path,
        goal_file: Path,
        inputs: tuple[str, ...],
        timeout_seconds: float,
    ) -> FabroJsonResult:
        command = self._run(
            argv=[
                self.fabro_bin,
                "preflight",
                str(workflow_toml),
                "--goal-file",
                str(goal_file),
                *_input_args(inputs=inputs),
                "--no-upgrade-check",
                "--json",
                *self._server_suffix(),
            ],
            timeout_seconds=timeout_seconds,
            env=self._server_env(),
        )
        return FabroJsonResult(command=command, payload=fabro_json_payload(command=command))

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
        command = self._run(
            argv=[self.fabro_bin, "version"],
            timeout_seconds=timeout_seconds,
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
        if self.target.server_url is None:
            return None
        return {"FABRO_SERVER": self.target.server_url}


def fabro_port_for_plan(*, plan: Any, runner: FabroRunner) -> FabroPort:
    """Construct the Fabro CLI port from a dispatch plan."""
    return FabroPort(
        fabro_bin=plan.fabro_bin,
        target=FabroTarget(
            server_url=plan.fabro_factory_server,
            dev_token=plan.fabro_factory_dev_token,
        ),
        runner=runner,
        cwd=plan.repo,
    )


def _input_args(*, inputs: tuple[str, ...]) -> list[str]:
    argv: list[str] = []
    for item in inputs:
        argv.extend(["--input", item])
    return argv
