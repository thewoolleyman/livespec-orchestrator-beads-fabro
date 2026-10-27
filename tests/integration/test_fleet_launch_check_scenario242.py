"""`check-fleet-launch` lints and harnesses the provisional launcher, and a defect reddens it.

Integration-tier acceptance for the provisional-fleet-launch-scripts clause of
`SPECIFICATION/contracts.md` and the Scenario 242 heading of
`SPECIFICATION/scenarios.md`, "The provisional fleet launch check fails the
build on a broken launcher". The clause requires `just check` to
run a `check-fleet-launch` target declared in the justfile's `check:` targets
array, that the target run shellcheck over every shell script under
`fleet-launch/` AND a hermetic harness whose cases cover five named launch
gates, and that "A change to a `fleet-launch/` launcher that breaks any of those
cases MUST make `just check` exit non-zero."
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DRIVER = Path("dev-tooling") / "just-check-fleet-launch.sh"
_TARGET_EXTRACTOR = Path("dev-tooling") / "aggregate-targets.sh"
_LAUNCH_DIR = Path("fleet-launch")
_HARNESS = _LAUNCH_DIR / "test" / "run-tests.sh"
_LAUNCHER = _LAUNCH_DIR / "dispatch-dual.sh"
_SLUG = "check-fleet-launch"
_IDLE_BOARD_IS_ZERO = '[ -z "$out" ] && return 0'
_REQUIRED_GATE_SECTIONS = (
    "reads a stub factory board",
    "refuses a launch when the shared fleet cap is reached",
    "launches two queued tickets in FIFO order",
    "holds a launch while the hold file exists",
    "counts a retired factory's board as zero, not as unknown",
)
_TIMEOUT_SECONDS = 600


def _run(*, argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=_TIMEOUT_SECONDS,
    )


def test_scenario242_the_committed_check_lints_every_shell_script_and_runs_the_harness() -> None:
    """`just check` runs the target, and the target runs both legs over the real tree."""
    executed = _run(argv=["bash", str(_TARGET_EXTRACTOR)], cwd=_REPO_ROOT)
    assert executed.returncode == 0, executed.stderr
    assert (
        _SLUG in executed.stdout.split()
    ), f"{_SLUG} is not in the target list `just check` executes: {executed.stdout}"

    tracked = _run(
        argv=["git", "ls-files", "fleet-launch/*.sh", "fleet-launch/**/*.sh"],
        cwd=_REPO_ROOT,
    )
    assert tracked.returncode == 0, tracked.stderr
    shell_scripts = [line for line in tracked.stdout.splitlines() if line]
    assert shell_scripts, "no tracked shell script under fleet-launch/ to lint"

    done = _run(argv=["bash", str(_DRIVER)], cwd=_REPO_ROOT)
    combined = done.stdout + done.stderr
    assert done.returncode == 0, combined
    assert (
        f"shellcheck clean over {len(shell_scripts)} shell scripts under fleet-launch/" in combined
    ), f"the lint leg did not cover every tracked fleet-launch shell script: {combined}"
    for section in _REQUIRED_GATE_SECTIONS:
        assert section in combined, f"the harness ran no case for '{section}': {combined}"
    assert "0 failed" in combined, combined


def test_scenario242_a_launcher_that_reads_an_idle_board_as_unknown_turns_the_check_red(
    tmp_path: Path,
) -> None:
    """A defect in the launcher makes the committed harness exit non-zero."""
    copied = tmp_path / "fleet-launch"
    shutil.copytree(_REPO_ROOT / _LAUNCH_DIR, copied)
    launcher = copied / _LAUNCHER.name

    before = launcher.read_text(encoding="utf-8")
    assert before.count(_IDLE_BOARD_IS_ZERO) == 1, (
        "the committed launcher no longer carries the idle-board early return this "
        "arm mutates, so the mutation could not have landed"
    )
    _ = launcher.write_text(before.replace(_IDLE_BOARD_IS_ZERO, ":"), encoding="utf-8")
    assert (
        launcher.read_text(encoding="utf-8").count(_IDLE_BOARD_IS_ZERO) == 0
    ), "the mutation did not land, so a passing harness would say nothing"

    done = _run(argv=["bash", str(copied / "test" / "run-tests.sh")], cwd=tmp_path)
    combined = done.stdout + done.stderr
    assert done.returncode != 0, (
        "the harness passed against a launcher that reads an idle board as unknown: " f"{combined}"
    )
    assert "an idle board was not counted as zero" in combined, combined


def test_scenario242_the_harness_and_its_driver_are_committed_and_executable() -> None:
    """Both legs are tracked files, so `just check` cannot resolve to an absent script."""
    tracked = _run(
        argv=["git", "ls-files", "--error-unmatch", str(_HARNESS), str(_DRIVER)],
        cwd=_REPO_ROOT,
    )
    assert tracked.returncode == 0, tracked.stderr
    assert (_REPO_ROOT / _HARNESS).is_file()
    assert (_REPO_ROOT / _DRIVER).is_file()


_PROVISIONAL_SHELL_SCRIPTS = sorted(
    path.relative_to(_REPO_ROOT).as_posix() for path in (_REPO_ROOT / _LAUNCH_DIR).rglob("*.sh")
)


@pytest.mark.parametrize("relative_path", _PROVISIONAL_SHELL_SCRIPTS)
def test_scenario242_every_provisional_shell_script_carries_its_banner(
    relative_path: str,
) -> None:
    """Each script marks itself provisional and names its first-class replacements."""
    script = _REPO_ROOT / relative_path
    comment = " ".join(
        line.lstrip().lstrip("#").strip()
        for line in script.read_text(encoding="utf-8").splitlines()
        if line.lstrip().startswith("#") or not line.strip()
    )
    assert "PROVISIONAL" in comment and "EXPERIMENTAL" in comment, relative_path
    assert "console application" in comment, relative_path
    assert "bd-ib-jr6w7v" in comment, relative_path
