"""Gate observations read the runner's files without spawning a status command."""

import os
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._session_wait_gate import observe_gate_target
from livespec_orchestrator_beads_fabro.commands.session_wait import (
    GateStatusLauncher,
    GateTarget,
    HerdrPaneLauncher,
    RoutingLauncher,
    WaitRequest,
    run_wait,
)


def test_running_gate_is_observed_from_its_frozen_directory_without_commands(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = tmp_path / "tmp/gate-runs/running"
    run_dir.mkdir(parents=True)
    (run_dir / "started_at").write_text("generation-one\n", encoding="utf-8")
    (run_dir / "pid").write_text(f"{os.getpid()}\n", encoding="utf-8")
    target = GateTarget.freeze(gate_store_root=run_dir.parent, run_id=run_dir.name)
    calls: list[list[str]] = []

    def command(
        _self: ShellCommandRunner,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        start_new_session: bool = False,
    ) -> CommandResult:
        del cwd, timeout_seconds, start_new_session
        calls.append(argv)
        return CommandResult(exit_code=0, stdout="state : RUNNING\n", stderr="")

    # Positive control: the spy records calls before it watches the adapter.
    control = command(ShellCommandRunner(), argv=["control"], cwd=tmp_path, timeout_seconds=1.0)
    assert control.stdout == "state : RUNNING\n"
    assert calls == [["control"]]
    calls.clear()
    monkeypatch.setattr(ShellCommandRunner, "run", command)
    result = run_wait(
        request=WaitRequest(
            wait_id="running",
            session_id="files",
            repository=tmp_path,
            deadline_seconds=0.05,
            targets=(target,),
        ),
        launcher=RoutingLauncher(
            gate=GateStatusLauncher(repository=tmp_path),
            pane=HerdrPaneLauncher(),
        ),
        wait_store_root=tmp_path / "tmp/session-waits",
    )
    observation = observe_gate_target(target=target, observed_at=123.0)
    assert calls == [], "observing a gate must never start a command"
    assert result.command_outcome == "deadline"
    assert result.observations[target.identity].state == "RUNNING"
    assert result.observations[target.identity].fresh is False
    assert observation.state == "RUNNING"
    assert observation.exit_code is None
    assert observation.observed_at == 123.0
    assert observation.fresh is True
