"""`check-fleet-launch` shellchecks the provisional launchers and harnesses them.

Binds the provisional-fleet-launch-scripts clause of `SPECIFICATION/contracts.md`
and "Scenario 242 — The provisional fleet launch check fails the build on a
broken launcher" in `SPECIFICATION/scenarios.md`: `just check` must run a
`check-fleet-launch` target, declared in the justfile's `check:` targets array,
that runs shellcheck over every shell script under `fleet-launch/` AND runs a
hermetic harness exercising the launcher against stub factory boards and
throwaway queue, lock, in-flight and state directories — and a change to a
launcher that breaks one of those cases must make `just check` exit non-zero.

WHY THE DECLARATION IS READ THROUGH THE RUNNER'S OWN EXTRACTOR. The clause's
first obligation is about `just check`, not about a line in a file, and those
two came apart here before: a hardcoded target list inside
`dev-tooling/just-check.sh` left ten DECLARED slugs unrun for eight weeks
(work-item `bd-ib-mxqrr4`). So membership is asserted through
`bash dev-tooling/aggregate-targets.sh` — the parse `just-check.sh` executes —
rather than by grepping the array, which would certify a declaration the runner
might not read.

WHY THE RED PROOF MUTATES A COPY AND PROVES THE MUTATION LANDED. Scenario 242's
second scenario is a NEGATIVE one: the check must FAIL on a broken launcher. A
harness run against an unmodified tree reports exactly what a surviving mutant
reports — `AGENTS.md` records a mutation campaign in this repository where three
of five `sed` patterns silently matched nothing and the suite's green was read as
five killed mutants. Each case below therefore asserts the edit CHANGED the
bytes it meant to change before it believes the run that follows.

WHY THE MUTATION IS THE RETIRED-BOARD ONE. Scenario 242 names it outright ("a
change that makes the launcher count a retired factory's board as unknown"), and
it is the launcher's most load-bearing single line: `board_rows` returns the bare
token `U` for a board it cannot read, every gate treats `U` as never-green, and
an empty board — which is what a retired factory's board is — exits 0 with
nothing on stdout. Drop the early return that distinguishes those two and the
launcher stops launching entirely, silently, with no error anywhere.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXTRACTOR = Path("dev-tooling") / "aggregate-targets.sh"
_GATE = Path("dev-tooling") / "just-check-fleet-launch.sh"
_HARNESS = Path("dev-tooling") / "fleet-launch-harness.sh"
_LAUNCHER_DIR = Path("fleet-launch")
_SLUG = "check-fleet-launch"
_RECIPE = f"{_SLUG}:"

# The env var both legs honour so a case can point them at a mutated copy. It
# carries the `FLEET_LAUNCH_` prefix the clause requires of every overridable
# value the provisional scripts read.
_TARGET_DIR_ENV_VAR = "FLEET_LAUNCH_HARNESS_DIR"

# How long a harness leg that must LAUNCH waits for that launch. The mutated
# launcher cannot launch at all, so every such leg waits its whole deadline out;
# shortening it for the negative case below turns a multi-minute run into a
# short one. It can only make a launch leg fail SOONER, never pass, so it cannot
# manufacture the red this case asserts — the harness's own header records that
# argument where the knob is read.
_LAUNCH_DEADLINE_ENV_VAR = "FLEET_LAUNCH_HARNESS_LAUNCH_DEADLINE_S"

# The five cases the clause enumerates, by the name the harness reports them
# under. Named here rather than derived from the harness's own output: a set
# read off the thing under test cannot report a case that went missing.
_DECLARED_CASES = (
    "board-read",
    "fleet-cap-refusal",
    "fifo-two-tickets",
    "hold-file",
    "retired-board-zero",
)

# The ONE line of `board_rows` that makes an empty board a reading of zero
# instead of an unreadable board. Scenario 242's mutation deletes it.
_EMPTY_BOARD_EARLY_RETURN = '[ -z "$out" ] && return 0'

_TIMEOUT_SECONDS = 600.0


def _run(*, argv: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """One gate or harness invocation, from the repository root.

    The child environment is scrubbed of `COVERAGE_PROCESS_START` and the
    `COV_CORE_*` family that `pytest-cov`'s pth hook exports: a self-
    instrumenting child writes `.coverage.*` files that race the concurrent
    coverage runs `just check` drives, which is the flake
    `tests_no_subprocess_spawn` exists to prevent. These children are `bash`,
    not Python, but the harness spawns `python3` of its own for the stub
    plugin-registry read, so the scrub is load-bearing rather than ceremonial.
    """
    child = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    }
    child.update(env or {})
    return subprocess.run(
        argv,
        cwd=_REPO_ROOT,
        env=child,
        capture_output=True,
        text=True,
        check=False,
        timeout=_TIMEOUT_SECONDS,
    )


def _declared_targets() -> list[str]:
    """The aggregate's target list, as the `just check` runner itself parses it."""
    completed = _run(argv=["bash", str(_EXTRACTOR)])
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.split()


def _launcher_copy(*, tmp_path: Path) -> Path:
    """A throwaway copy of `fleet-launch/`, for a case that mutates a launcher."""
    target = tmp_path / "fleet-launch"
    shutil.copytree(_REPO_ROOT / _LAUNCHER_DIR, target)
    return target


def _case_verdicts(*, stdout: str) -> dict[str, str]:
    """Each `CASE <name>: <verdict>` line the harness reported, name to verdict."""
    verdicts: dict[str, str] = {}
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped.startswith("CASE "):
            continue
        name, _, rest = stripped[len("CASE ") :].partition(":")
        verdicts[name.strip()] = rest.strip().split()[0] if rest.strip() else ""
    return verdicts


def test_the_check_aggregate_declares_and_runs_the_fleet_launch_target() -> None:
    """`just check` runs a `check-fleet-launch` target it declares in `targets=(...)`."""
    assert _SLUG in _declared_targets()
    justfile = (_REPO_ROOT / "justfile").read_text(encoding="utf-8")
    recipes = [line for line in justfile.splitlines() if line.startswith(_RECIPE)]
    assert recipes == [_RECIPE], recipes
    assert (_REPO_ROOT / _GATE).is_file()
    assert (_REPO_ROOT / _HARNESS).is_file()


def test_the_gate_shellchecks_every_shell_script_under_fleet_launch(tmp_path: Path) -> None:
    """A shellcheck-dirty script anywhere under the tree turns the gate red.

    The dirty script is planted under `wrappers/` rather than at the top level,
    because a leg that globbed only `fleet-launch/*.sh` would pass the top-level
    case and silently never read the subdirectory — a scope hole that reports as
    a clean run. The positive control is the REAL tree, so the leg cannot earn
    its green by finding nothing anywhere.
    """
    copied = _launcher_copy(tmp_path=tmp_path)
    dirty = copied / "wrappers" / "planted-unused-assignment.sh"
    # SC2034, which shellcheck 0.11.0 raises at `warning` — above the floor the
    # leg states, which is the floor the fleet's own `check-shell-quality`
    # applies (it fails on `error` and `warning`, passes `info` and `style`).
    # The first plant tried here was SC2086, an unquoted `$1`; shellcheck rates
    # that `info`, so the leg correctly passed and the case asserted a red that
    # was never owed. The plant therefore has to be chosen against the floor, not
    # against how wrong the line looks.
    dirty.write_text(
        "#!/usr/bin/env bash\nset -eu\nunused_state_dir=$1\nexec echo ready\n",
        encoding="utf-8",
    )

    red = _run(argv=["bash", str(_GATE)], env={_TARGET_DIR_ENV_VAR: str(copied)})
    assert red.returncode != 0
    assert "planted-unused-assignment.sh" in red.stdout + red.stderr

    dirty.unlink()
    green = _run(argv=["bash", str(_GATE)], env={_TARGET_DIR_ENV_VAR: str(copied)})
    assert green.returncode == 0, green.stdout + green.stderr


def test_the_harness_covers_every_case_the_clause_enumerates() -> None:
    """The hermetic harness reports a PASS for each of the five declared cases."""
    completed = _run(argv=["bash", str(_HARNESS)])
    verdicts = _case_verdicts(stdout=completed.stdout)
    assert set(verdicts) == set(_DECLARED_CASES), verdicts
    assert all(verdict == "PASS" for verdict in verdicts.values()), (
        verdicts,
        completed.stdout,
        completed.stderr,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_a_launcher_that_counts_a_retired_board_as_unknown_turns_the_check_red(
    tmp_path: Path,
) -> None:
    """Scenario 242's mutation: drop the empty-board early return, go red.

    Both halves are asserted. The mutation must LAND — the early return present
    before and absent after — because a `sed` that matched nothing would leave
    the harness exercising an unmodified launcher and report its honest green as
    a killed mutant. And the gate, not merely the harness, must be the surface
    that goes red, since the clause's obligation is on `just check`.
    """
    copied = _launcher_copy(tmp_path=tmp_path)
    launcher = copied / "dispatch-dual.sh"
    before = launcher.read_text(encoding="utf-8")
    assert before.count(_EMPTY_BOARD_EARLY_RETURN) == 1
    launcher.write_text(before.replace(_EMPTY_BOARD_EARLY_RETURN, ":"), encoding="utf-8")
    after = launcher.read_text(encoding="utf-8")
    assert _EMPTY_BOARD_EARLY_RETURN not in after
    assert after != before

    completed = _run(
        argv=["bash", str(_GATE)],
        env={_TARGET_DIR_ENV_VAR: str(copied), _LAUNCH_DEADLINE_ENV_VAR: "8"},
    )
    assert completed.returncode != 0, completed.stdout + completed.stderr
    verdicts = _case_verdicts(stdout=completed.stdout)
    assert verdicts.get("retired-board-zero") == "FAIL", (verdicts, completed.stdout)


@pytest.mark.parametrize("case", _DECLARED_CASES)
def test_the_harness_names_each_declared_case(case: str) -> None:
    """Each enumerated case is named in the harness source, so none can be dropped.

    A cheap structural companion to the behavioural run above: the run asserts
    the five cases PASS, and this asserts the harness still declares all five,
    so deleting a case cannot turn the behavioural assertion green by making its
    verdict set smaller.
    """
    assert case in (_REPO_ROOT / _HARNESS).read_text(encoding="utf-8")
