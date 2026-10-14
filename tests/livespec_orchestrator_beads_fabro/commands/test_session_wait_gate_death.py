"""Exited gates are terminal even while their unreaped PIDs remain addressable."""

import os
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands.session_wait import (
    GateStatusLauncher,
    GateTarget,
    HerdrPaneLauncher,
    RoutingLauncher,
    WaitRequest,
    run_wait,
)


@pytest.mark.parametrize("process_state", ["Z", "X", "x"])
def test_an_unreaped_exit_without_a_verdict_is_never_still_running(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, process_state: str
) -> None:
    pid = 987654321
    run_dir = tmp_path / "tmp/gate-runs/dead"
    run_dir.mkdir(parents=True)
    (run_dir / "started_at").write_text("generation\n", encoding="utf-8")
    (run_dir / "pid").write_text(f"{pid}\n", encoding="utf-8")
    target = GateTarget.freeze(gate_store_root=run_dir.parent, run_id=run_dir.name)
    stat_path = Path(f"/proc/{pid}/stat")
    observed: list[Path] = []
    read_text = Path.read_text

    def still_addressable(probed_pid: int, signal: int) -> None:
        assert (probed_pid, signal) == (pid, 0)

    def proc_text(path: Path, *, encoding: str | None = None, errors: str | None = None) -> str:
        if path == stat_path:
            observed.append(path)
            # The comm field may contain spaces and parentheses.
            return f"{pid} (gate (runner)) {process_state} 1 1 1\n"
        return read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(os, "kill", still_addressable)
    monkeypatch.setattr(Path, "read_text", proc_text)
    result = run_wait(
        request=WaitRequest(
            wait_id="dead",
            session_id="files",
            repository=tmp_path,
            deadline_seconds=0.2,
            targets=(target,),
        ),
        launcher=RoutingLauncher(
            gate=GateStatusLauncher(repository=tmp_path), pane=HerdrPaneLauncher()
        ),
        wait_store_root=tmp_path / "tmp/session-waits",
    )
    assert result.observations[target.identity].state == "DIED_WITHOUT_VERDICT"
    assert result.command_outcome == "target-ended"
    assert result.trigger_target == target.identity
    assert result.trigger_exit_code is None
    assert result.observations[target.identity].fresh is True
    assert observed == [stat_path]
    assert not (run_dir / "exit_code").exists()
