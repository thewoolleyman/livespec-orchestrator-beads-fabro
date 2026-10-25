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

WHY THE GREEN LEG IS NOT THE WHOLE TEST, and why the broken-launcher arm is the
one that carries the clause's last sentence. A green run of a check proves the
check RAN; it cannot distinguish a harness that exercises five gates from one
that exercises none, because both exit zero. The clause's own second scenario is
therefore the load-bearing assertion: a launcher mutated to count a retired
factory's board as UNKNOWN — the exact 2026-10-24 defect `fleet-launch/README.md`
records, where a launcher read a stopped factory's board as unknown and launched
nothing for ninety minutes — must turn the check red. That arm runs against a
COPY of the committed tree, so the assertion is about the committed harness's
sensitivity and nothing in this repository is mutated.

AND THE MUTATION IS PROVED TO HAVE LANDED. A `sed`-style edit whose pattern
matches nothing leaves the script unmodified, and the harness then passes — the
identical observation to a harness that cannot detect the defect, and the
identical exit code. So the edit is applied by counting the target text before
and after and asserting it went from present to absent; without that control the
red arm could only ever report a pass as a pass.

The harness is driven through `bash`, not through `sys.executable`, so no
instrumented Python child is spawned and the
`check-tests-no-subprocess-spawn` guard's coverage-race rationale does not
apply. It is driven at all — rather than re-implemented here — because the
shipped driver is what `just check` runs, and a second account of the two legs
would be a different measurement from the one that gates master.
"""

from __future__ import annotations

import os
import shutil
import signal
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

# The early return in `board_rows` that makes an idle board a reading of ZERO.
# Removing it is what makes the launcher read a retired factory's board as
# unknown, which is Scenario 242's defect verbatim.
_IDLE_BOARD_IS_ZERO = '[ -z "$out" ] && return 0'

# The five gates the clause names, each as the harness's own section line.
_REQUIRED_GATE_SECTIONS = (
    "reads a stub factory board",
    "refuses a launch when the shared fleet cap is reached",
    "launches two queued tickets in FIFO order",
    "holds a launch while the hold file exists",
    "counts a retired factory's board as zero, not as unknown",
)

# The green harness drives real one-second polls and two concurrent FIFO
# launchers, measured at about 25 seconds. The broken-launcher arm shortens its
# copied harness deadlines, while this parent timeout reaps its process group if
# a future regression bypasses those bounds.
_TIMEOUT_SECONDS = 60


def _run(
    *,
    argv: list[str],
    cwd: Path,
    overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = {
        name: value
        for name, value in os.environ.items()
        if name != "COVERAGE_PROCESS_START" and not name.startswith("COV_CORE_")
    }
    environment.update(overrides or {})
    process = subprocess.Popen(
        argv,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        pytest.fail("timed out while running " + " ".join(argv) + "\n" + stdout + stderr)
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


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

    done = _run(
        argv=["bash", str(copied / "test" / "run-tests.sh")],
        cwd=tmp_path,
        overrides={
            "FLEET_LAUNCH_HARNESS_FIFO_MAX_WAIT_S": "4",
            "FLEET_LAUNCH_HARNESS_FIFO_AWAIT_S": "6",
            "FLEET_LAUNCH_HARNESS_WAIT_S": "2",
        },
    )
    combined = done.stdout + done.stderr
    assert (
        done.returncode != 0
    ), f"the harness passed against a launcher that reads an idle board as unknown: {combined}"
    assert "an idle board was not counted as zero" in combined, combined


def test_scenario242_the_harness_and_its_driver_are_committed_and_executable() -> None:
    """Both legs are tracked files, so `just check` cannot resolve to an absent script."""
    tracked = _run(
        argv=["git", "ls-files", "--error-unmatch", str(_HARNESS), str(_DRIVER)], cwd=_REPO_ROOT
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
    """Each script marks itself provisional and names its first-class replacements.

    The banner is read with its comment markers REMOVED before the lines are
    joined, because `config.sh` and `dispatch-dual.sh` wrap the phrase "console
    application" across two comment lines: a raw newline join misses it while a
    join of the marker-stripped text finds it.
    """
    script = _REPO_ROOT / relative_path
    comment = " ".join(
        line.lstrip().lstrip("#").strip()
        for line in script.read_text(encoding="utf-8").splitlines()
        if line.lstrip().startswith("#") or not line.strip()
    )
    assert "PROVISIONAL" in comment and "EXPERIMENTAL" in comment, relative_path
    assert "console application" in comment, relative_path
    assert "bd-ib-jr6w7v" in comment, relative_path
