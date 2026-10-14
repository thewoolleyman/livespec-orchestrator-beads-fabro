"""Tests for the sandbox-container sweep: what it removes, and what it spares.

The sweep's whole safety condition is the OWNING SERVER's own verdict about
the run, so every case here is built from a status map plus a container
inventory, and each asserts the DOCKER ARGV the sweep issued rather than only
the summary it returned. A driver that reported the right dispositions while
removing the wrong container would satisfy every assertion made on the
summary alone.

The three fail-closed arms are asserted individually rather than folded
together, because each one arrives through a different absence and each is
one edit away from becoming a removal: a run no surveyed server reports, a
status kind this build does not recognise, and an inventory that could not be
read at all. All three must HOLD, and a hold is only meaningful if it is
distinguishable from the others — a single "not removed" assertion would pass
for a sweep that had collapsed them into one reason.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_COMMANDS_DIR = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE_NAMES = (
    "_dispatcher_sandbox_container_sweep",
    "_dispatcher_sandbox_container_port",
    "_dispatcher_sandbox_container_reclaim",
)

# The memory limit `fabro-sandbox.slice` containers carry on hp, in bytes.
_LIMIT = 4294967296
# A deliberate blank line: `docker ps` output ends in a newline, and a reader
# that does not drop empty lines invents a container named "".
_PS_STDOUT = "fabro-run-01TERMINAL\n\nfabro-run-01RUNNING\nfabro-run-01RUNNABLE\n"
# `docker inspect` renders `.Name` with a leading slash, and renders an
# unreadable field as `<no value>` rather than omitting the line.
_INSPECT_STDOUT = (
    f"/fabro-run-01TERMINAL\t{_LIMIT}\n"
    "/fabro-run-01RUNNING\t0\n"
    "/fabro-run-01RUNNABLE\t<no value>\n"
)
_LIVE_STATUSES = {
    "01TERMINAL": "failed",
    "01RUNNING": "running",
    "01RUNNABLE": "runnable",
}
# The daemon every port here is opened onto. The sweep addresses the surveyed
# FACTORY's daemon rather than the reconciling host's, so a port cannot be
# built without naming one.
_DOCKER_HOST = "ssh://cwoolley@hp-xubuntu.example"


@dataclass(kw_only=True)
class _Docker:
    """One fake `docker` CLI, keyed by the verb the argv names.

    The verb is MEMBERSHIP-tested rather than read at a fixed index: every
    argv opens with the global `--host <daemon>` pair that names the factory
    host's daemon, so an index-keyed fake would read the daemon address as the
    verb and answer every call the same way.
    """

    ps_stdout: str = ""
    ps_exit_code: int = 0
    inspect_stdout: str = ""
    inspect_exit_code: int = 0
    rm_exit_code: int = 0
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
        if "ps" in argv:
            return CommandResult(exit_code=self.ps_exit_code, stdout=self.ps_stdout, stderr="")
        if "inspect" in argv:
            return CommandResult(
                exit_code=self.inspect_exit_code,
                stdout=self.inspect_stdout,
                stderr="",
            )
        return CommandResult(exit_code=self.rm_exit_code, stdout="", stderr="")


def _sweep(
    *,
    runner: _Docker,
    tmp_path: Path,
    status_by_run: dict[str, str],
    dry_run: bool = False,
) -> Any:
    """Drive the reclaim through its own port, which must exist on disk first.

    The existence assertion is the Red: at the Red commit no module file is
    there, so this fails as a genuine assertion rather than at collection.
    """
    for name in _MODULE_NAMES:
        module_path = _COMMANDS_DIR / f"{name}.py"
        assert module_path.is_file(), f"{module_path} does not exist yet"
    port_module = importlib.import_module(f"{_PACKAGE}._dispatcher_sandbox_container_port")
    reclaim = importlib.import_module(f"{_PACKAGE}._dispatcher_sandbox_container_reclaim")
    return reclaim.reclaim_terminal_run_containers(
        port=port_module.SandboxContainerPort(
            runner=runner, cwd=tmp_path, docker_host=_DOCKER_HOST
        ),
        status_by_run=status_by_run,
        dry_run=dry_run,
    )


def _removed_names(*, runner: _Docker) -> list[str]:
    return [argv[-1] for argv in runner.calls if "rm" in argv]


def test_the_sweep_removes_a_terminal_runs_container_and_spares_the_live_ones(
    tmp_path: Path,
) -> None:
    """The acceptance assertion: terminal out, running and runnable left alone."""
    runner = _Docker(ps_stdout=_PS_STDOUT, inspect_stdout=_INSPECT_STDOUT)

    sweep = _sweep(runner=runner, tmp_path=tmp_path, status_by_run=_LIVE_STATUSES)

    assert _removed_names(runner=runner) == ["fabro-run-01TERMINAL"]
    assert [(run.container_name, run.run_status_kind, run.removed) for run in sweep.reclaimed] == [
        ("fabro-run-01TERMINAL", "failed", True)
    ]
    assert [(run.container_name, run.hold_reason) for run in sweep.held] == [
        ("fabro-run-01RUNNING", "run-live"),
        ("fabro-run-01RUNNABLE", "run-live"),
    ]
    assert sweep.observed is True


def test_a_container_whose_run_no_surveyed_server_reports_is_held(tmp_path: Path) -> None:
    """Fail-closed on an ABSENT status: unobservable is not terminal.

    A pruned run record, or a run served by a factory this pass did not
    survey, reads here as a container with no status at all. Removing it
    would be a removal decided by a measurement nobody took.
    """
    runner = _Docker(
        ps_stdout="fabro-run-01PRUNED\n",
        inspect_stdout=f"/fabro-run-01PRUNED\t{_LIMIT}\n",
    )

    sweep = _sweep(runner=runner, tmp_path=tmp_path, status_by_run={})

    assert _removed_names(runner=runner) == []
    assert [(run.container_name, run.hold_reason) for run in sweep.held] == [
        ("fabro-run-01PRUNED", "run-unobserved")
    ]


def test_a_container_whose_run_reports_an_unrecognised_status_is_held(tmp_path: Path) -> None:
    """Fail-closed on an UNKNOWN status, which is why terminal is an allow-list.

    Read as the complement of the known-live set, a status kind this build has
    never seen would classify as terminal and the sweep would kill a live
    sandbox. The hold reason is its own value rather than `run-live`, because
    the two support different conclusions about the engine.
    """
    runner = _Docker(
        ps_stdout="fabro-run-01FUTURE\n",
        inspect_stdout=f"/fabro-run-01FUTURE\t{_LIMIT}\n",
    )

    sweep = _sweep(
        runner=runner,
        tmp_path=tmp_path,
        status_by_run={"01FUTURE": "queued"},
    )

    assert _removed_names(runner=runner) == []
    assert [(run.container_name, run.hold_reason) for run in sweep.held] == [
        ("fabro-run-01FUTURE", "run-status-unrecognised")
    ]


def test_an_unreadable_inventory_removes_nothing_and_reports_that_it_saw_nothing(
    tmp_path: Path,
) -> None:
    """An absent or refusing `docker` is reported, never read as an empty host.

    `observed` is the field that separates the two, and it is the whole reason
    the inventory carries one: without it a host whose daemon could not be
    asked is byte-identical to a host with no leaked container on it.
    """
    runner = _Docker(ps_exit_code=127)

    sweep = _sweep(runner=runner, tmp_path=tmp_path, status_by_run=_LIVE_STATUSES)

    assert _removed_names(runner=runner) == []
    assert (sweep.reclaimed, sweep.held, sweep.observed) == ((), (), False)
    assert "127" in sweep.detail


def test_an_empty_inventory_is_observed_and_costs_no_inspect(tmp_path: Path) -> None:
    """The ordinary healthy host: nothing leaked, and no second round trip."""
    runner = _Docker(ps_stdout="\n")

    sweep = _sweep(runner=runner, tmp_path=tmp_path, status_by_run=_LIVE_STATUSES)

    assert [argv[3] for argv in runner.calls] == ["ps"]
    assert (sweep.reclaimed, sweep.held, sweep.observed) == ((), (), True)


def test_an_unreadable_memory_limit_is_reported_absent_and_does_not_block_removal(
    tmp_path: Path,
) -> None:
    """The limit is a RECORD field, never a safety input.

    So an `inspect` that fails still removes the container, and reports the
    limit as `None` — absent, rather than a zero that would read as a measured
    container with no limit of its own.
    """
    runner = _Docker(
        ps_stdout="fabro-run-01TERMINAL\n",
        inspect_exit_code=1,
    )

    sweep = _sweep(
        runner=runner,
        tmp_path=tmp_path,
        status_by_run={"01TERMINAL": "succeeded"},
    )

    assert _removed_names(runner=runner) == ["fabro-run-01TERMINAL"]
    assert [(run.removed, run.memory_limit_bytes) for run in sweep.reclaimed] == [(True, None)]


def test_a_limit_the_daemon_reports_as_unlimited_is_zero_rather_than_absent(
    tmp_path: Path,
) -> None:
    """Zero is a MEASUREMENT — "no per-container limit" — and `None` is not.

    The daemon spells an unbounded container `0`, so collapsing it onto `None`
    would lose the one reading that says this container was free to consume
    the whole slice.
    """
    runner = _Docker(
        ps_stdout="fabro-run-01RUNNING\n",
        inspect_stdout="/fabro-run-01RUNNING\t0\n",
    )

    sweep = _sweep(
        runner=runner,
        tmp_path=tmp_path,
        status_by_run={"01RUNNING": "running"},
    )

    assert [(run.container_name, run.memory_limit_bytes) for run in sweep.held] == [
        ("fabro-run-01RUNNING", 0)
    ]


def test_a_dry_run_decides_without_removing(tmp_path: Path) -> None:
    """A projection of what WOULD be reclaimed, taken without reclaiming it."""
    runner = _Docker(ps_stdout=_PS_STDOUT, inspect_stdout=_INSPECT_STDOUT)

    sweep = _sweep(
        runner=runner,
        tmp_path=tmp_path,
        status_by_run=_LIVE_STATUSES,
        dry_run=True,
    )

    assert _removed_names(runner=runner) == []
    assert [(run.container_name, run.removed) for run in sweep.reclaimed] == [
        ("fabro-run-01TERMINAL", False)
    ]
    assert sweep.dry_run is True


def test_a_removal_the_daemon_refused_is_reported_rather_than_claimed(tmp_path: Path) -> None:
    """`removed` is read off the exit code, so a refusal cannot read as a reclaim."""
    runner = _Docker(
        ps_stdout="fabro-run-01TERMINAL\n",
        inspect_stdout=f"/fabro-run-01TERMINAL\t{_LIMIT}\n",
        rm_exit_code=1,
    )

    sweep = _sweep(
        runner=runner,
        tmp_path=tmp_path,
        status_by_run={"01TERMINAL": "cancelled"},
    )

    assert _removed_names(runner=runner) == ["fabro-run-01TERMINAL"]
    assert [(run.removed, run.memory_limit_bytes) for run in sweep.reclaimed] == [(False, _LIMIT)]
    assert "1" in sweep.reclaimed[0].detail
