"""Tests that the sweep addresses each surveyed FACTORY's Docker daemon.

The sandbox containers run where the Fabro server runs. The reconciliation
pass runs wherever the timer that invoked it runs, and on this fleet those are
different hosts: measured 2026-10-14, every `sandbox-container-sweep` record
written on the reconciling host read `containers_observed: 0` while twelve
`fabro-run-*` containers were running on `hp`, four of them left by runs that
server reported `failed`. A sweep through the local daemon is a clean,
plausible, wrong answer — its record is indistinguishable at every field from
a sweep over a factory with nothing leaked on it.

THE FACTORIES ARE RESOLVED FROM A WRITTEN `.livespec.jsonc` rather than
constructed, because the daemon a factory is addressed through has to come
from the SAME declaration the reconciler surveys that factory by. A target
built in the test could carry a daemon no configuration can express, and the
whole defect was a sweep addressing a daemon nobody had declared.

A FACTORY DECLARING NO DAEMON IS THE OTHER HALF OF THE SAME CLAIM: it is not
swept through whichever daemon this host happens to run. A server url is no
evidence of a daemon's whereabouts — a loopback url is as likely to be a
forwarded tunnel as a local engine — so inferring one would remove a container
on the reconciling host on the strength of a status read from another host.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs import reconcile_runs
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    journaled_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_factories import (
    reconcile_factory_targets,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_container_port import DOCKER_BIN

_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"
_HP_SERVER = "https://hp-xubuntu.example:32276"
# The shape the hp factory declares: the Docker CLI's own remote-daemon
# address, which is what makes the sweep's reach a declaration rather than an
# inference from the server url beside it.
_HP_DOCKER_HOST = "ssh://cwoolley@hp-xubuntu.example"

# One of the four containers the 2026-10-14 measurement found still running on
# hp for a run the server had already reported `failed`.
_FAILED_RUN = "01M4V0HPJBETC2M026JQ4WKR0S"
_LIMIT = 4294967296


@dataclass(kw_only=True)
class _Runner:
    """One fake CLI for BOTH binaries, keyed on argv[0] before the verb.

    Keying on the verb alone would be wrong in the one way that matters here:
    `fabro ps` and `docker ps` are both `ps`, so a fake that read the verb
    first would answer the factory inventory to the container listing.
    """

    fabro_ps_json: str = "[]"
    docker_ps_stdout: str = ""
    docker_inspect_stdout: str = ""
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        if argv[0] == DOCKER_BIN:
            return self._docker(argv=argv)
        # Every `fabro` call these passes make is the factory survey: the
        # journal is empty, so the projection replay has nothing to re-read
        # and no orphan is terminated.
        return CommandResult(exit_code=0, stdout=self.fabro_ps_json, stderr="")

    def _docker(self, *, argv: list[str]) -> CommandResult:
        if "inspect" in argv:
            return CommandResult(exit_code=0, stdout=self.docker_inspect_stdout, stderr="")
        if "ps" in argv:
            return CommandResult(exit_code=0, stdout=self.docker_ps_stdout, stderr="")
        return CommandResult(exit_code=0, stdout="", stderr="")


@dataclass(kw_only=True)
class _Journal:
    written: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.written.append(record)


def _write_config(*, tmp_path: Path, factories: dict[str, dict[str, str]]) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({_PLUGIN_BLOCK: {"dispatcher": {"factories": factories}}}),
        encoding="utf-8",
    )


def _runner() -> _Runner:
    return _Runner(
        fabro_ps_json=json.dumps(
            [
                {
                    "run_id": _FAILED_RUN,
                    "goal": "Work-item: bd-ib-failed\nRepo: /tmp/repo",
                    "status": {"kind": "failed"},
                }
            ]
        ),
        docker_ps_stdout=f"fabro-run-{_FAILED_RUN}\n",
        docker_inspect_stdout=f"/fabro-run-{_FAILED_RUN}\t{_LIMIT}\n",
    )


def _inputs(*, tmp_path: Path, runner: _Runner, journal: _Journal) -> ReconcileInputs:
    """A reconcile bundle whose only live seams are the subprocess and the journal.

    The ledger is the package's own in-memory client, and the HTTP transport
    is left at its default, for the same reason: nothing in these passes
    reaches either — no orphan is reconciled, so no comment is written and no
    termination route is contacted — and a double whose methods nothing calls
    is dead weight that reads as coverage.
    """
    return ReconcileInputs(
        repo=tmp_path,
        fabro_bin="fabro",
        id_prefix="bd-ib",
        items=(),
        journaled=journaled_runs(text=""),
        runner=runner,
        journal=journal,
        ledger=FakeBeadsClient(),
    )


def _docker_argv_heads(*, runner: _Runner) -> list[list[str]]:
    """Every docker call's binary, daemon address and verb, in order."""
    return [argv[:4] for argv in runner.calls if argv[0] == DOCKER_BIN]


def _reconcile(*, tmp_path: Path, runner: _Runner, journal: _Journal) -> Any:
    return reconcile_runs(
        inputs=_inputs(tmp_path=tmp_path, runner=runner, journal=journal),
        factories=reconcile_factory_targets(repo=tmp_path),
    )


def test_every_docker_call_addresses_the_daemon_the_surveyed_factory_declares(
    tmp_path: Path,
) -> None:
    """The acceptance assertion, read off the argv the sweep actually ran.

    A return value cannot carry this claim: a sweep of the local daemon that
    happened to find the same container would report an identical reclaim. The
    daemon address in the argv is the only place the question is settled.
    """
    _write_config(
        tmp_path=tmp_path,
        factories={"hp": {"server": _HP_SERVER, "docker_host": _HP_DOCKER_HOST}},
    )
    runner = _runner()

    summary = _reconcile(tmp_path=tmp_path, runner=runner, journal=_Journal())

    assert _docker_argv_heads(runner=runner) == [
        [DOCKER_BIN, "--host", _HP_DOCKER_HOST, "ps"],
        [DOCKER_BIN, "--host", _HP_DOCKER_HOST, "inspect"],
        [DOCKER_BIN, "--host", _HP_DOCKER_HOST, "rm"],
    ]
    assert [
        (run.run_id, run.run_status_kind, run.removed)
        for sweep in summary.containers
        for run in sweep.reclaimed
    ] == [(_FAILED_RUN, "failed", True)]


def test_a_factory_declaring_no_daemon_is_not_swept_through_the_local_one(
    tmp_path: Path,
) -> None:
    """Nothing says which daemon runs an undeclared factory's containers.

    So no container is removed anywhere. The reconciling host's own daemon is
    the one answer that is certainly wrong, and it is the one a bare `docker`
    reaches.
    """
    _write_config(tmp_path=tmp_path, factories={"hp": {"server": _HP_SERVER}})
    runner = _runner()

    summary = _reconcile(tmp_path=tmp_path, runner=runner, journal=_Journal())

    assert _docker_argv_heads(runner=runner) == []
    assert [sweep.reclaimed for sweep in summary.containers] == []
