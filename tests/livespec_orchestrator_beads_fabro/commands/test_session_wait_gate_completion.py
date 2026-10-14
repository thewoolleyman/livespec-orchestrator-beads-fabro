"""A runner's atomic verdict wins over a concurrent process exit."""

import os
from itertools import count
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands.session_wait import (
    GateStatusLauncher,
    GateTarget,
    HerdrPaneLauncher,
    RoutingLauncher,
    WaitRequest,
    WaitResult,
    run_wait,
)


def _target(*, repository: Path) -> GateTarget:
    run_dir = repository / "tmp/gate-runs/completing"
    run_dir.mkdir(parents=True)
    (run_dir / "started_at").write_text("generation\n", encoding="utf-8")
    (run_dir / "pid").write_text(f"{os.getpid()}\n", encoding="utf-8")
    return GateTarget.freeze(gate_store_root=run_dir.parent, run_id=run_dir.name)


def _publish(*, target: GateTarget, code: int) -> int:
    """Land the verdict atomically and report the code it carries.

    The code is reported rather than an instant, because every claim below is
    about WHICH observation round read the verdict — a count of rounds and of
    sleeper calls — and never about how many seconds the host took to answer.
    """
    partial = target.gate_store_root / target.run_id / "exit_code.partial"
    partial.write_text(f"{code}\n", encoding="utf-8")
    partial.replace(partial.with_name("exit_code"))
    return code


def _assert_verdict(*, result: WaitResult, target: GateTarget, code: int, state: str) -> None:
    assert result.command_outcome == "target-ended"
    assert result.trigger_target == target.identity
    assert result.trigger_exit_code == code
    assert result.observations[target.identity].state == state
    assert result.observations[target.identity].fresh is True


@pytest.mark.parametrize(
    ("code", "state"), [(0, "PASSED"), (23, "FAILED"), (143, "DIED_WITHOUT_VERDICT")]
)
def test_verdict_published_during_pid_probe_is_returned_without_a_further_round(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int, state: str
) -> None:
    target = _target(repository=tmp_path)
    completed: list[int] = []
    sleeps: list[float] = []

    def exit_during_probe(pid: int, signal: int) -> None:
        assert (pid, signal) == (os.getpid(), 0)
        completed.append(_publish(target=target, code=code))
        raise ProcessLookupError

    monkeypatch.setattr(os, "kill", exit_during_probe)
    result = run_wait(
        request=WaitRequest(
            wait_id="completion-race",
            session_id="files",
            repository=tmp_path,
            deadline_seconds=5.0,
            targets=(target,),
        ),
        launcher=RoutingLauncher(
            gate=GateStatusLauncher(repository=tmp_path), pane=HerdrPaneLauncher()
        ),
        wait_store_root=tmp_path / "tmp/session-waits",
        # This checks which round read the verdict, not host scheduling latency.
        # Advance logical time and record the sleeps without taking them, so a
        # loaded host cannot turn the racing round into a deadline expiry. The
        # recorder is an expression because this test's claim is that it never
        # runs; test_verdict_written_between_rounds_wakes_on_the_next_round
        # below exercises the same record-and-do-not-wait sleeper when it does.
        monotonic=count(start=0.0, step=0.01).__next__,
        sleeper=lambda *, seconds: sleeps.append(seconds),
    )
    assert completed == [code]
    # The verdict was published inside the round's own probe, so that round
    # returned it and no round-gap sleep was ever asked for.
    assert sleeps == []
    _assert_verdict(result=result, target=target, code=code, state=state)


def test_verdict_written_between_rounds_wakes_on_the_next_round(*, tmp_path: Path) -> None:
    target = _target(repository=tmp_path)
    completed: list[int] = []
    sleeps: list[float] = []

    def finish_while_sleeping(*, seconds: float) -> None:
        sleeps.append(seconds)
        completed.append(_publish(target=target, code=7))

    result = run_wait(
        request=WaitRequest(
            wait_id="completion-between-rounds",
            session_id="files",
            repository=tmp_path,
            deadline_seconds=5.0,
            targets=(target,),
        ),
        launcher=RoutingLauncher(
            gate=GateStatusLauncher(repository=tmp_path), pane=HerdrPaneLauncher()
        ),
        wait_store_root=tmp_path / "tmp/session-waits",
        # Same reason as the sibling above: the claim is that the round AFTER
        # the publish reads the verdict. Logical time plus a sleeper that
        # records its budget instead of consuming it keeps that claim free of
        # the host's scheduling, which is what made the wall-clock form flake.
        monotonic=count(start=0.0, step=0.01).__next__,
        sleeper=finish_while_sleeping,
    )
    assert completed == [7]
    # Exactly one round-gap sleep, asked for at the one-second cadence cap:
    # the first round saw the target running, the verdict landed in that gap,
    # and the very next round returned it.
    assert sleeps == [1.0]
    _assert_verdict(result=result, target=target, code=7, state="FAILED")
