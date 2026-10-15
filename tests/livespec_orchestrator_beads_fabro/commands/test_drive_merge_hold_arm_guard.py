"""The two arms of the release arm guard that the valve's own cases cannot reach.

`test_drive_merge_hold_valve.py` drives this guard END TO END through the real
`set-merge-hold:<id>:off` action, which is where every verdict and every refusal
message belongs: the guard exists to stop a valve from arming, and a case that
called it directly would certify a decision while leaving the wiring unexercised.

What is left for this module is the pair of arms that action cannot take.

THE DEFAULT RUNNER is the production path a HUMAN takes — `drive` passes no
runner, so the guard reaches the forge and the engine through its own
`subprocess.run`. The valve's cases all inject a runner, by design, because a
case that shelled out could not drive a forge transition on demand. So the
adapter's no-runner arm needs its own case, and it is driven by monkeypatching
the spawn rather than by a real `gh`: the claim is that the adapter CALLS the
spawn with the argv it was given and returns the completed result in the shape
the port and the record reader take, not that `gh` is installed.

THE UNREPORTED HEAD is the arm the valve's view cannot produce. The valve asks
for `headRefOid` in the ONE view it takes, so a `None` head there means the forge
answered with a payload carrying no head at all — reachable in production (an
older forge, a truncated payload) and not reachable through a fixture that also
has to parse as a pull-request view with a number and a state. Driving it here
keeps the refusal honest: the clause forbids claiming a mismatch that was not
measured, and this is the one input whose absence makes the comparison
impossible.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _drive_merge_hold_arm_guard as guard
from livespec_orchestrator_beads_fabro.commands._drive_merge_hold_arm_guard import (
    ARM_REFUSAL_UNPROVED_HEAD,
    arm_refusal_for_release,
)

_ITEM_ID = "bd-ib-guarded"


@dataclass(frozen=True, kw_only=True)
class _Run:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class _Runner:
    """The injected valve seam, replaying one canned result per call."""

    def __init__(self, *, results: list[_Run]) -> None:
        self.results = results
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> _Run:
        self.calls.append(argv)
        _ = cwd
        return self.results.pop(0)


def test_an_unreported_head_is_refused_without_claiming_a_mismatch(tmp_path: Path) -> None:
    """A head the forge did not report is an absent measurement, not a differing head.

    The refusal has to say the comparison could not be TAKEN. Claiming a
    mismatch would point an operator at a pull request whose head moved when
    nothing of the kind was observed, and the clause forbids exactly that
    direction. The liveness arm is satisfied first, with an answering factory
    holding nothing, so the refusal is attributable to the head reading alone.
    """
    runner = _Runner(results=[_Run(returncode=0, stdout="[]")])

    refusal = arm_refusal_for_release(
        repo=tmp_path,
        work_item_id=_ITEM_ID,
        pr_number=11,
        pr_head=None,
        runner=runner,
    )

    assert refusal is not None
    assert refusal.error == ARM_REFUSAL_UNPROVED_HEAD
    assert "did not report the pull request's current head" in refusal.message
    # The records were never asked for: there is nothing to compare them against.
    assert not any(call[:3] == ("gh", "pr", "view") for call in runner.calls)


def test_the_default_runner_spawns_the_argv_it_was_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no injected runner the adapter spawns, and reports what the spawn said.

    Both halves are asserted because either alone passes while the adapter is
    broken: a spawn whose argv was rebuilt would reach a different engine, and a
    result whose exit code was dropped would make an unanswered `fabro ps` read
    as an answering factory holding nothing — the fail-open this guard's whole
    liveness arm exists to avoid.
    """
    spawned: list[tuple[object, ...]] = []

    def fake_run(*args: object, **kwargs: object) -> _Run:
        spawned.append(args)
        assert kwargs["check"] is False
        assert kwargs["capture_output"] is True
        assert kwargs["cwd"] == tmp_path
        return _Run(returncode=3, stderr="the engine refused")

    monkeypatch.setattr(guard, "run", fake_run)

    refusal = arm_refusal_for_release(
        repo=tmp_path,
        work_item_id=_ITEM_ID,
        pr_number=11,
        pr_head="c" * 40,
        runner=None,
    )

    assert refusal is not None
    assert "did not answer" in refusal.message
    assert spawned, "the adapter never spawned"
    argv = spawned[0][0]
    assert isinstance(argv, list)
    assert argv[1:4] == ["ps", "-a", "--json"]
