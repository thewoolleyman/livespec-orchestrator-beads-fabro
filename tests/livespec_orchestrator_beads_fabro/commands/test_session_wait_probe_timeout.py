"""A gate-status probe that times out is NO OBSERVATION, not an unavailable gate.

Measured 2026-10-12 and again 2026-10-13 on hosts at load averages 34 and 28:
`session_wait wait` returned `target-ended` with its trigger in state
`UNAVAILABLE` within minutes of arming — once about six hours short of its own
deadline — while `just gate-status` on that same gate reported `state: RUNNING`
and a live pid moments later. The gate was still running every time.

The mechanism is the probe's own budget. A probe is capped at one second, an
ordinary `mise exec -- just gate-status` call measures 0.24s to 0.34s on an
idle host, and a load spike pushes it past the cap. The timed-out probe
returned empty output, no `state:` line was found, and that was recorded as
`UNAVAILABLE` — a state the wait reads as a target that has left `RUNNING`, so
the wait ended on its own instrument's slowness and named the gate as the
thing that woke it.

A probe that timed out never observed the target, so it is not an observation
of that target at all. These cases pin the three outcomes that discrimination
owes: a timed-out probe keeps the wait waiting and a later probe reports
`RUNNING`; a gate that genuinely finishes still wakes the wait with its own
verdict; and a probe that COMPLETED carrying no state line still ends the wait
with the distinct unavailable outcome the contract permits.
"""

from __future__ import annotations

import time
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._session_wait_gate import observe_gate_target
from livespec_orchestrator_beads_fabro.commands.session_wait import (
    GateStatusLauncher,
    GateTarget,
    WaitRequest,
    run_wait,
)

_RUNNING_STATE = "RUNNING"
_UNAVAILABLE_STATE = "UNAVAILABLE"
_FINISHED_STATE = "FAILED"
_FINISHED_EXIT_CODE = 23
# Long enough for the round after a probe's one-second timeout to launch a
# replacement AND for that replacement to be read, with room for two further
# attempts if a loaded host times one of them out too.
_TIMEOUT_DEADLINE_SECONDS = 4.0
# Deadlines for the two cases that must return EARLY, on an observation rather
# than at expiry. Generous on purpose: what they assert is that the wait woke
# before its budget, so the budget has to be nowhere near the return.
_WAKE_DEADLINE_SECONDS = 5.0
_WAKE_CEILING_SECONDS = 3.0
# How long a one-shot observation gives its probe. Far below the one-second
# cap a wait's probe gets, because the hanging helper only has to outlast it.
_ONE_SHOT_TIMEOUT_SECONDS = 0.05
# How long the fast sleeper below really sleeps per round.
_POLL_SECONDS = 0.05

# A gate-status stand-in whose FIRST call hangs past any probe budget and
# whose later calls report the gate as running. The hang is `exec sleep`, so
# the process the probe spawned is the one that hangs and the probe's timeout
# is the only thing that can end it — the first round therefore times out on
# every host rather than on a loaded one. Flipping the mode file before
# hanging is what makes the SECOND probe a different observation: `./mode` is
# read relative to the gate's own directory, which is the cwd the launcher
# runs every probe in.
_HANG_THEN_RUNNING = f"""read mode < ./mode
case "$mode" in
hang-first)
    printf 'running\\n' > ./mode
    exec sleep 60
    ;;
*)
    printf '  state             : {_RUNNING_STATE}\\n'
    ;;
esac
"""
# A gate that has already finished, carrying a verdict and an exit code of its
# own so the wait's outcome label and the gate's exit code stay separable.
_FINISHED = f"""printf '  state             : {_FINISHED_STATE}\\n'
printf '  exit_code         : {_FINISHED_EXIT_CODE}\\n'
"""
# A probe that COMPLETES and prints no state line at all. Nothing timed out
# here, so nobody is owed another round: this gate genuinely could not be read.
_MALFORMED = "printf 'not gate status output\\n'\n"
# A probe that never answers, for the one-shot surface that has no later round.
_HANG = "exec sleep 60\n"


def _fast_sleeper(*, seconds: float) -> None:
    """Sleep well inside the budget the wait asked for.

    Sleeping SHORT cannot change what is under test here. A probe's own budget
    is what the timeout is measured against, and that budget is untouched by
    this: all a short sleep does is bring the round AFTER the timeout forward,
    so the case spends a tenth of the real time it would spend observing a
    one-second production cadence it is not asserting. The sibling cases that
    DO assert the cadence use the production sleeper.
    """
    time.sleep(min(seconds, _POLL_SECONDS))


def _gate(*, gate_store_root: Path, run_id: str, mode: str | None = None) -> GateTarget:
    run_dir = gate_store_root / run_id
    run_dir.mkdir(parents=True)
    _ = (run_dir / "started_at").write_text("generation-one\n", encoding="utf-8")
    if mode is not None:
        _ = (run_dir / "mode").write_text(f"{mode}\n", encoding="utf-8")
    return GateTarget.freeze(gate_store_root=gate_store_root, run_id=run_id)


def _helper(*, tmp_path: Path, name: str, body: str) -> tuple[str, ...]:
    """A POSIX-shell gate-status stand-in, as the launcher's command prefix.

    `/bin/sh` rather than this interpreter, for the reason the sibling gate
    fixtures record: a probe's budget is capped at one second and a cold
    CPython start under coverage tracing can exceed that, which would make
    every one of these gates look timed out for reasons that have nothing to
    do with the behaviour under test.
    """
    helper = tmp_path / name
    _ = helper.write_text(body, encoding="utf-8")
    return ("/bin/sh", str(helper))


def test_a_timed_out_probe_keeps_the_wait_waiting_and_a_later_probe_reads_running(
    *,
    tmp_path: Path,
) -> None:
    """Scenario 154: the instrument's slowness is not a state of the gate.

    The first probe hangs past its own budget and the gate is still running
    throughout, so there is no terminal target for this wait to find: it owes
    the DEADLINE outcome with the gate listed unfinished, and it owes the
    `RUNNING` a later probe actually read rather than the diagnostic a
    timed-out one produced.
    """
    gate_store_root = tmp_path / "gate-runs"
    gate = _gate(gate_store_root=gate_store_root, run_id="timing-out-gate", mode="hang-first")
    wait_store_root = tmp_path / "session-waits"
    wait_store_root.mkdir()

    started = time.monotonic()
    result = run_wait(
        request=WaitRequest(
            wait_id="probe-timeout",
            session_id="probe-timeout-session",
            repository=tmp_path,
            deadline_seconds=_TIMEOUT_DEADLINE_SECONDS,
            targets=(gate,),
        ),
        launcher=GateStatusLauncher(
            repository=tmp_path,
            command_prefix=_helper(
                tmp_path=tmp_path,
                name="hang-then-running.sh",
                body=_HANG_THEN_RUNNING,
            ),
        ),
        wait_store_root=wait_store_root,
        sleeper=_fast_sleeper,
    )
    elapsed = time.monotonic() - started

    # The wait kept waiting: it spent its whole budget rather than returning on
    # the first probe's timeout, which landed at one second.
    assert elapsed >= _TIMEOUT_DEADLINE_SECONDS, f"returned after {elapsed:.2f}s"
    assert result.command_outcome == "deadline"
    assert result.trigger_target is None
    assert result.trigger_exit_code is None
    assert result.unfinished_targets == (gate.identity,)
    # And the state it reports is the one a probe that COMPLETED read, stale
    # because it is the last reading rather than a current one.
    observation = result.observations[gate.identity]
    assert (observation.state, observation.exit_code, observation.fresh) == (
        _RUNNING_STATE,
        None,
        False,
    )


def test_a_gate_that_finishes_still_wakes_the_wait_with_its_own_verdict(
    *,
    tmp_path: Path,
) -> None:
    """Scenario 154: discriminating a timeout must not swallow a real verdict.

    Driven by the PRODUCTION sleeper, so the return is at the shipped polling
    cadence rather than at a cadence this case arranged.
    """
    gate_store_root = tmp_path / "gate-runs"
    gate = _gate(gate_store_root=gate_store_root, run_id="finished-gate")
    wait_store_root = tmp_path / "session-waits"
    wait_store_root.mkdir()

    started = time.monotonic()
    result = run_wait(
        request=WaitRequest(
            wait_id="finished-gate-wake",
            session_id="probe-timeout-session",
            repository=tmp_path,
            deadline_seconds=_WAKE_DEADLINE_SECONDS,
            targets=(gate,),
        ),
        launcher=GateStatusLauncher(
            repository=tmp_path,
            command_prefix=_helper(tmp_path=tmp_path, name="finished.sh", body=_FINISHED),
        ),
        wait_store_root=wait_store_root,
    )
    elapsed = time.monotonic() - started

    assert result.command_outcome == "target-ended"
    assert result.trigger_target == gate.identity
    assert result.trigger_exit_code == _FINISHED_EXIT_CODE
    assert result.unfinished_targets == ()
    observation = result.observations[gate.identity]
    assert (observation.state, observation.exit_code) == (_FINISHED_STATE, _FINISHED_EXIT_CODE)
    # Woken by the observation and nowhere near the budget: a wait that had
    # started discarding real verdicts could only return at expiry.
    assert elapsed < _WAKE_CEILING_SECONDS, f"returned after {elapsed:.2f}s"


def test_a_completed_probe_with_no_state_line_still_ends_the_wait_unavailable(
    *,
    tmp_path: Path,
) -> None:
    """Scenario 154: an unreadable gate keeps its distinct unavailable outcome.

    This is the arm the discrimination must NOT absorb. The probe completed,
    so nobody is owed another round, and the contract's distinct unavailable
    outcome is exactly what a gate nobody could read is owed. The one-shot
    observation at the end is the same obligation on the surface that has no
    later round at all: a probe that times out there cannot be retried, so it
    reports unavailable rather than nothing.
    """
    gate_store_root = tmp_path / "gate-runs"
    gate = _gate(gate_store_root=gate_store_root, run_id="unreadable-gate")
    wait_store_root = tmp_path / "session-waits"
    wait_store_root.mkdir()

    result = run_wait(
        request=WaitRequest(
            wait_id="unreadable-gate-wake",
            session_id="probe-timeout-session",
            repository=tmp_path,
            deadline_seconds=_WAKE_DEADLINE_SECONDS,
            targets=(gate,),
        ),
        launcher=GateStatusLauncher(
            repository=tmp_path,
            command_prefix=_helper(tmp_path=tmp_path, name="malformed.sh", body=_MALFORMED),
        ),
        wait_store_root=wait_store_root,
    )

    assert result.command_outcome == "target-ended"
    assert result.trigger_target == gate.identity
    assert result.trigger_exit_code is None
    assert result.observations[gate.identity].state == _UNAVAILABLE_STATE

    one_shot = observe_gate_target(
        target=gate,
        observed_at=11.0,
        command_prefix=_helper(tmp_path=tmp_path, name="hang.sh", body=_HANG),
        timeout_seconds=_ONE_SHOT_TIMEOUT_SECONDS,
    )
    assert one_shot.state == _UNAVAILABLE_STATE
    assert one_shot.exit_code is None
