"""A gate-status probe that TIMED OUT is no observation of its gate."""

from __future__ import annotations

import time
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._session_wait_gate import observe_gate_target
from livespec_orchestrator_beads_fabro.commands.session_wait import (
    GateStatusLauncher,
    GateTarget,
    HerdrPaneLauncher,
    RoutingLauncher,
    WaitRequest,
    run_wait,
)

# Longer than the one-second budget `GateStatusLauncher.launch` clamps every
# probe to, so the FIRST round's probe cannot answer inside its own budget and
# is reaped by it. The duration itself is not what the timeout is measured
# against — the parent holds that clock — so this only has to exceed one
# second while staying short enough that a leaked child self-terminates.
_SLOW_PROBE_SLEEP = "5"
# The marker the slow arm drops before it hangs. Its presence is what proves
# the slow arm RAN, so a fixture whose first probe answered normally fails here
# instead of passing on an arm that was never exercised.
_FIRST_PROBE_MARKER = "first-probe-started"
# A bounded deadline the wait is expected to spend in full: the gate under test
# stays RUNNING, so a wait that keeps waiting can only return at expiry. Short,
# because what is asserted is the OUTCOME and the reported state rather than a
# duration.
_RUNNING_DEADLINE_SECONDS = 4.0
# A deadline long enough that a wait returning on its target's own verdict
# returns nowhere near it, so "returned because the gate finished" and
# "returned because the budget ran out" cannot be confused.
_FINISHING_DEADLINE_SECONDS = 10.0
# How long a wait over an already-answerable gate may take. One poll round
# separates the launch of a probe from the reading of its result, and the
# cadence is capped at one second, so two rounds is the budget and three
# seconds leaves room for a loaded host without admitting an expiry.
_CADENCE_ALLOWANCE_SECONDS = 3.0
_FINISHED_GATE_STATE = "PASSED"
_FINISHED_GATE_EXIT_CODE = 23
# The poll cadence these waits actually run at. The contract requires a
# cadence no SLOWER than one second, so compressing it is conformant — and it
# is what keeps a test that must observe several consecutive rounds (a probe
# reaped by its budget, the round that retires it, the fresh probe, and the
# reading of that probe) from needing a deadline measured in tens of seconds.
_TIGHT_POLL_SECONDS = 0.1


def _tight_sleeper(*, seconds: float) -> None:
    """Sleep no longer than the compressed cadence, never longer than asked."""
    time.sleep(min(seconds, _TIGHT_POLL_SECONDS))


def _target(*, gate_store_root: Path, run_id: str) -> GateTarget:
    run_dir = gate_store_root / run_id
    run_dir.mkdir(parents=True)
    _ = (run_dir / "started_at").write_text(f"started-{run_id}\n", encoding="utf-8")
    return GateTarget.freeze(gate_store_root=gate_store_root, run_id=run_id)


def _helper(*, repository: Path, name: str, body: str) -> Path:
    """One scripted gate-status command, standing in for a real gate run.

    A POSIX SHELL rather than this interpreter, for the reason the sibling
    fixtures record: a probe's budget is clamped to one second and a cold
    CPython under coverage tracing cannot reach its first statement inside
    that, so a Python fixture would time out for a reason that has nothing to
    do with the behaviour under test. The adapter appends the bare run id and
    runs the child in the gate's own directory, so `$1` is that run id and a
    relative path resolves inside the gate directory.
    """
    helper = repository / name
    _ = helper.write_text(body, encoding="utf-8")
    return helper


def _launcher(*, repository: Path, helper: Path) -> RoutingLauncher:
    return RoutingLauncher(
        gate=GateStatusLauncher(
            repository=repository,
            command_prefix=("/bin/sh", str(helper)),
        ),
        pane=HerdrPaneLauncher(),
    )


def test_a_probe_reaped_by_its_budget_keeps_the_wait_and_reports_running(
    *,
    tmp_path: Path,
) -> None:
    """A probe timeout is not an observation, so the wait keeps waiting.

    Measured 2026-10-12 and again 2026-10-13 on a loaded host: two bounded
    waits returned `target-ended` with their trigger in state `UNAVAILABLE`,
    one of them almost six hours short of its deadline, while `gate-status`
    reported `RUNNING` for the same gate moments afterwards and the gate's
    runner process was alive. A `gate-status` call measures about 0.3s there
    against the one-second per-probe budget, so an ordinary load spike reaps
    the probe — and a reaped probe never observed the gate at all.

    The fixture's first probe hangs past that budget and every later one
    answers `RUNNING`, so a wait that reads its own instrument's slowness as a
    verdict ends within a second or two of arming, and one that treats it as
    no observation spends its whole deadline and reports the state a later
    probe actually read.
    """
    gate_store_root = tmp_path / "gate-runs"
    target = _target(gate_store_root=gate_store_root, run_id="slow-first-probe-gate")
    helper = _helper(
        repository=tmp_path,
        name="slow-then-running-gate-status.sh",
        body=f"""if [ ! -f {_FIRST_PROBE_MARKER} ]; then
    : > {_FIRST_PROBE_MARKER}
    exec sleep {_SLOW_PROBE_SLEEP}
fi
printf '  state             : RUNNING\\n'
""",
    )

    started = time.monotonic()
    result = run_wait(
        request=WaitRequest(
            wait_id="slow-first-probe",
            session_id="gate-probe-timeout",
            repository=tmp_path,
            deadline_seconds=_RUNNING_DEADLINE_SECONDS,
            targets=(target,),
        ),
        launcher=_launcher(repository=tmp_path, helper=helper),
        wait_store_root=tmp_path / "session-waits",
        sleeper=_tight_sleeper,
    )
    elapsed = time.monotonic() - started

    # The slow arm ran, so the timed-out probe this asserts about really happened.
    assert (gate_store_root / target.run_id / _FIRST_PROBE_MARKER).is_file()
    # The gate never finished, so the only honest ending is expiry — and the
    # wait held its own bound rather than being pushed out by the slow probe.
    assert result.command_outcome == "deadline"
    assert result.trigger_target is None
    assert result.unfinished_targets == (target.identity,)
    assert elapsed >= _RUNNING_DEADLINE_SECONDS
    # A later probe DID read the gate, and that reading is what is reported:
    # stale, because the wait returned at expiry rather than on it.
    observation = result.observations[target.identity]
    assert observation.state == "RUNNING"
    assert observation.fresh is False


def test_a_gate_that_finishes_returns_its_own_state_and_exit_code(*, tmp_path: Path) -> None:
    """Treating a timeout as no observation must not blind the wait to a verdict.

    The complementary risk to the defect above: a fix that simply refused to
    end a wait on anything but a terminal-looking state would also stop
    reporting the verdict a gate genuinely printed. This gate answers at once,
    so the wait must return its ACTUAL state and exit code, within a poll
    round or two of arming rather than at its deadline.
    """
    gate_store_root = tmp_path / "gate-runs"
    target = _target(gate_store_root=gate_store_root, run_id="finishing-gate")
    helper = _helper(
        repository=tmp_path,
        name="finished-gate-status.sh",
        body=(
            f"printf '  state             : {_FINISHED_GATE_STATE}\\n'\n"
            f"printf '  exit_code         : {_FINISHED_GATE_EXIT_CODE}\\n'\n"
        ),
    )

    started = time.monotonic()
    result = run_wait(
        request=WaitRequest(
            wait_id="finishing-gate",
            session_id="gate-probe-timeout",
            repository=tmp_path,
            deadline_seconds=_FINISHING_DEADLINE_SECONDS,
            targets=(target,),
        ),
        launcher=_launcher(repository=tmp_path, helper=helper),
        wait_store_root=tmp_path / "session-waits",
    )
    elapsed = time.monotonic() - started

    assert result.command_outcome == "target-ended"
    assert result.trigger_target == target.identity
    assert result.trigger_exit_code == _FINISHED_GATE_EXIT_CODE
    observation = result.observations[target.identity]
    assert observation.state == _FINISHED_GATE_STATE
    assert observation.exit_code == _FINISHED_GATE_EXIT_CODE
    assert observation.fresh is True
    assert elapsed < _CADENCE_ALLOWANCE_SECONDS, f"returned after {elapsed:.2f}s"


def test_a_completed_probe_with_no_state_line_ends_the_wait_as_unavailable(
    *,
    tmp_path: Path,
) -> None:
    """A gate that cannot be READ keeps the distinct unavailable outcome.

    This is the state the defect's symptom was indistinguishable from, and the
    contract keeps it: a target whose status output carries no state line is
    genuinely unreadable, and `SPECIFICATION/contracts.md` requires a state
    outside the still-running predicate to end the wait with the actual
    verdict or a distinct unavailable outcome rather than be waited out. Only
    a probe that never COMPLETED is excluded, because it measured nothing at
    all.
    """
    gate_store_root = tmp_path / "gate-runs"
    target = _target(gate_store_root=gate_store_root, run_id="unreadable-gate")
    helper = _helper(
        repository=tmp_path,
        name="unreadable-gate-status.sh",
        body="printf 'not gate status output\\n'\n",
    )

    started = time.monotonic()
    result = run_wait(
        request=WaitRequest(
            wait_id="unreadable-gate",
            session_id="gate-probe-timeout",
            repository=tmp_path,
            deadline_seconds=_FINISHING_DEADLINE_SECONDS,
            targets=(target,),
        ),
        launcher=_launcher(repository=tmp_path, helper=helper),
        wait_store_root=tmp_path / "session-waits",
    )
    elapsed = time.monotonic() - started

    assert result.command_outcome == "target-ended"
    assert result.trigger_target == target.identity
    assert result.trigger_exit_code is None
    assert result.observations[target.identity].state == "UNAVAILABLE"
    assert elapsed < _CADENCE_ALLOWANCE_SECONDS, f"returned after {elapsed:.2f}s"


def test_a_synchronous_one_shot_read_reports_a_reaped_probe_unavailable(
    *,
    tmp_path: Path,
) -> None:
    """One blocking reading has no later round, so a timeout is unavailable there.

    The retry the bounded wait performs is what makes "no observation" a
    useful answer: there is a next round to take one in. A single synchronous
    observation — what `inventory` and `check` take — has none, so it reports
    the unreadable-target diagnostic rather than inventing a state or
    returning nothing a caller could render.
    """
    gate_store_root = tmp_path / "gate-runs"
    target = _target(gate_store_root=gate_store_root, run_id="one-shot-gate")

    observation = observe_gate_target(
        target=target,
        observed_at=1.0,
        command_prefix=("/bin/sh", "-c", f"sleep {_SLOW_PROBE_SLEEP}"),
        timeout_seconds=0.05,
    )

    assert observation.state == "UNAVAILABLE"
    assert observation.exit_code is None
    assert observation.observed_at == 1.0
    assert observation.fresh is True
