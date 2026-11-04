"""The sandbox's history-preparation step deepens a shallow clone and spares a complete one.

Covers work-item bd-ib-ukht2p. Its Definition of Done references
`SPECIFICATION/contracts.md` section "Self-contained plugin dispatch", which makes
the sandbox prepare steps target-toolchain facts the dispatch must carry and run,
and `SPECIFICATION/scenarios.md` "Scenario 54 -- Host-side dispatch runs a released
payload, never the working tree", which is why the end-to-end form of this
behaviour is a HOST-CAPTURED assertion of the same work-item rather than anything
below. The heading bindings themselves stay exactly as `tests/heading-coverage.json`
records them; nothing here claims one.

WHAT WAS MEASURED. The first `[[run.prepare.steps]]` entry of the shipped
implement-work-item run config ran `git fetch --unshallow --quiet`
UNCONDITIONALLY. That command is an ERROR on a complete repository -- `fatal:
--unshallow on a complete repository does not make sense`, exit 128 -- and Fabro's
sandbox clone is taken at a hardcoded depth of ten, so a depth-ten clone of a
governed repository with ten or fewer commits is already COMPLETE. Preparation
therefore died before any model stage ran, for any such repository. Measured twice
on the private fixture `thewoolleyman/livespec-tdd-proof`, which has seven genuine
setup commits: hp run 01M4VXN5BGZQJQTT57WSXFEEBD at 2026-10-14T01:48:26Z under
released 0.196.1, and hp run 01M5EM5NZYSM, which died in two seconds.

WHY THESE CASES EXECUTE THE STEP RATHER THAN MATCH ITS TEXT. The assertion under
grade is what the step DOES to a clone, and no reading of the command line
establishes that: a conditional that inspects the wrong thing, or one that
swallows a failure behind a successful fallback, reads as correct and is not. So
each case provisions a real origin and a real clone -- one complete, one shallow --
and runs the script read verbatim out of the committed run config under `/bin/sh`.

THE MEASURED FAILURE IS ITSELF A CASE, because the complete-clone case alone cannot
say the fixture is capable of showing the defect: a fixture whose clone happened to
be shallow would satisfy it just as well. `test_the_retired_unconditional_fetch...`
runs the exact retired command line against the same complete fixture and requires
git's own refusal, which is what makes the positive reading evidence of the repair.

THE TWO FAILURE CONTROLS ARE SEPARATE CASES because the step has two commands that
can fail and one exit code between them. Each control reads the recorded `git`
argv to say WHICH command was reached, so "preparation stopped" is distinguished
from "preparation stopped at the step we think it did" -- a fail-closed posture
that only inspected, or only fetched, would pass a single merged case.

HOW THE `git` ARGV IS OBSERVED. A shim named `git`, first on the child `PATH`,
appends its own argv to a log and `exec`s the real binary. Every provisioning call
in this module invokes the real binary by ABSOLUTE PATH instead, so the log holds
exactly what the script under test invoked and nothing else. That is what lets the
complete-clone case assert no `--unshallow` was ATTEMPTED, rather than only that
the clone survived -- a step that attempted it and ignored the failure would leave
an identical clone behind.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomli

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHIPPED_RUN_CONFIG = (
    _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"
)

# The command line the step carried before this repair, measured failing twice.
# Held as a constant rather than read from the payload so the control keeps
# reproducing the defect after the payload stops carrying it.
_RETIRED_UNCONDITIONAL_FETCH = "git fetch --unshallow --quiet"
_COMPLETE_REPOSITORY_FATAL = "--unshallow on a complete repository does not make sense"
_NOT_A_REPOSITORY_FATAL = "not a git repository"
_GIT_FATAL = "fatal:"
_UNSHALLOW_FLAG = "--unshallow"
_IS_SHALLOW_QUERY = "rev-parse --is-shallow-repository"
_COMPLETE_REPOSITORY_EXIT = 128

# Fabro's clone depth is hardcoded at ten, so the complete fixture is a depth-ten
# clone of a SHORTER history -- the real sandbox shape of the measured failure,
# not a full clone that could never have been shallow.
_SANDBOX_CLONE_DEPTH = 10
_COMPLETE_HISTORY_COMMITS = 3
# Longer than the clone depth, so the shallow fixture's depth-one clone is
# genuinely missing history that the step has to bring in.
_SHALLOW_HISTORY_COMMITS = 12
_DEFAULT_BRANCH = "trunk"

_GIT_SHIM = """#!/bin/sh
printf '%s\\n' "$*" >> "$LIVESPEC_RECORDED_GIT_ARGV"
exec {real_git} "$@"
"""


def test_the_shipped_step_leaves_a_complete_clone_complete_and_attempts_no_unshallow(
    tmp_path: Path,
) -> None:
    """Assertion 1: exit 0, no `git fetch --unshallow` attempted, clone still complete.

    All three halves are asserted, because each alone is satisfiable by a build that
    is still broken: a step that exits 0 may have attempted the fetch and swallowed
    its refusal, a step that attempted nothing may have exited non-zero on a
    mis-read inspection, and a readable history is what says the clone was not
    damaged on the way through. The history count is compared against the fixture's
    own commit total rather than a literal, so a step that truncated the clone
    cannot pass by matching a number this module hard-coded.
    """
    fixture = _provision(tmp_path=tmp_path, complete=True)

    completed = _run_script(script=_history_preparation_script(), fixture=fixture)

    assert completed.returncode == 0, completed.stderr
    assert not _recorded_git_argv(fixture=fixture, containing=_UNSHALLOW_FLAG)
    assert _is_shallow(fixture=fixture) == "false"
    assert _commit_count(fixture=fixture) == _COMPLETE_HISTORY_COMMITS


def test_the_retired_unconditional_fetch_still_refuses_that_same_complete_clone(
    tmp_path: Path,
) -> None:
    """The measured failure, reproduced: the control for the case above.

    Identical fixture; the ONE thing varied is which command line runs in it. Both
    the exit code and git's own message are asserted, because a non-zero exit alone
    would not say the clone was refused for being COMPLETE -- an unreachable origin
    exits non-zero too, and that is the other control's subject.
    """
    fixture = _provision(tmp_path=tmp_path, complete=True)

    completed = _run_script(script=_RETIRED_UNCONDITIONAL_FETCH, fixture=fixture)

    assert completed.returncode == _COMPLETE_REPOSITORY_EXIT, completed.stderr
    assert _COMPLETE_REPOSITORY_FATAL in completed.stderr, completed.stderr


def test_the_shipped_step_expands_a_shallow_clone_to_its_complete_history(
    tmp_path: Path,
) -> None:
    """Assertion 2: exit 0, and the inspection then reports the clone complete.

    The commit count rides beside the shallowness flag because they answer different
    questions: a clone can report complete while holding only the single commit it
    was cloned at, which is what a step that dropped the shallow marker without
    fetching would leave. `_provision` has already asserted this fixture started
    shallow and one commit deep, so the arrival at twelve is an expansion rather
    than a clone that was always whole.
    """
    fixture = _provision(tmp_path=tmp_path, complete=False)

    completed = _run_script(script=_history_preparation_script(), fixture=fixture)

    assert completed.returncode == 0, completed.stderr
    assert _is_shallow(fixture=fixture) == "false"
    assert _commit_count(fixture=fixture) == _SHALLOW_HISTORY_COMMITS


def test_a_failing_shallowness_inspection_stops_the_step_and_surfaces_gits_message(
    tmp_path: Path,
) -> None:
    """Assertion 3, inspection leg: non-zero, git's own message, and no fetch reached.

    The working directory is a plain directory inside the fixture root, and
    `GIT_CEILING_DIRECTORIES` stops discovery at that root (see `_child_env` for
    what measured the wrong repository without it), so
    `git rev-parse --is-shallow-repository` cannot answer. Asserting that no
    `--unshallow` argv was recorded is what makes this the INSPECTION leg rather
    than a merged "something failed" case: a step that ran the fetch anyway, on an
    unknown shallowness, would exit non-zero here as well.
    """
    fixture = _provision(tmp_path=tmp_path, complete=True)
    outside = fixture.clone.parent / "not-a-repository"
    outside.mkdir()

    completed = _run_script(script=_history_preparation_script(), fixture=fixture, cwd=outside)

    assert completed.returncode != 0
    assert _NOT_A_REPOSITORY_FATAL in completed.stderr, completed.stderr
    assert _recorded_git_argv(fixture=fixture, containing=_IS_SHALLOW_QUERY)
    assert not _recorded_git_argv(fixture=fixture, containing=_UNSHALLOW_FLAG)


def test_a_failing_unshallow_fetch_stops_the_step_and_surfaces_gits_message(
    tmp_path: Path,
) -> None:
    """Assertion 3, fetch leg: non-zero, git's own message, and the clone left shallow.

    The origin is REMOVED after the shallow clone is taken, so the inspection still
    answers `true` and the fetch is the command that fails. Both recorded argv are
    asserted, which is what separates this from the inspection leg; and the clone is
    still shallow afterwards, which says the step refused rather than half-deepening
    the clone and reporting the failure anyway.
    """
    fixture = _provision(tmp_path=tmp_path, complete=False)
    shutil.rmtree(fixture.origin)

    completed = _run_script(script=_history_preparation_script(), fixture=fixture)

    assert completed.returncode != 0
    assert _GIT_FATAL in completed.stderr, completed.stderr
    assert _recorded_git_argv(fixture=fixture, containing=_IS_SHALLOW_QUERY)
    assert _recorded_git_argv(fixture=fixture, containing=_UNSHALLOW_FLAG)
    assert _is_shallow(fixture=fixture) == "true"


@dataclass(frozen=True, kw_only=True)
class _Fixture:
    """A provisioned clone, its origin, the child environment, and the argv log."""

    clone: Path
    origin: Path
    env: dict[str, str]
    recorded_git_argv: Path


def _history_preparation_script() -> str:
    """The FIRST prepare step's script, parsed as the engine parses the run config.

    Parsed with `tomli` rather than grepped: the property under grade is the value
    the engine resolves, and a line-shaped read would happily return a commented-out
    declaration. The step is asserted to bind no rendered input, because this
    caller EXECUTES what it returns -- a step carrying an unexpanded token would run
    as whatever the shell made of the literal rather than as what a dispatch runs.
    """
    document: dict[str, Any] = tomli.loads(_SHIPPED_RUN_CONFIG.read_text(encoding="utf-8"))
    steps: list[dict[str, Any]] = document["run"]["prepare"]["steps"]
    script: str = steps[0]["script"]
    assert "inputs." not in script, script
    return script


def _provision(*, tmp_path: Path, complete: bool) -> _Fixture:
    """Build a sandbox-shaped clone whose shallowness is OBSERVED, not assumed.

    The complete leg clones a three-commit history at Fabro's hardcoded depth of
    ten, which is exactly the measured failure's shape; the shallow leg clones a
    twelve-commit history at depth one. Each leg asserts the state it was built for
    before returning, because a fixture that silently came out the other way would
    make its case pass against the defect fully present.

    Every provisioning call runs the real `git` by absolute path, so the shim's log
    holds only what the script under test invoked.
    """
    root = tmp_path
    env = _child_env(root=root)
    commits = _COMPLETE_HISTORY_COMMITS if complete else _SHALLOW_HISTORY_COMMITS
    origin = root / "origin.git"
    _git(argv=["init", "--quiet", "--bare", "-b", _DEFAULT_BRANCH, str(origin)], cwd=root, env=env)

    seed = root / "seed"
    seed.mkdir()
    _git(argv=["init", "--quiet", "-b", _DEFAULT_BRANCH, "."], cwd=seed, env=env)
    for index in range(commits):
        _ = (seed / f"file-{index}.txt").write_text(f"line {index}\n", encoding="utf-8")
        _git(argv=["add", "--all"], cwd=seed, env=env)
        _git(argv=_commit_argv(message=f"seed commit {index}"), cwd=seed, env=env)
    _git(argv=["push", "--quiet", str(origin), _DEFAULT_BRANCH], cwd=seed, env=env)

    clone = root / "clone"
    depth = _SANDBOX_CLONE_DEPTH if complete else 1
    _git(
        argv=["clone", "--quiet", f"--depth={depth}", origin.as_uri(), str(clone)],
        cwd=root,
        env=env,
    )
    fixture = _Fixture(
        clone=clone,
        origin=origin,
        env=env,
        recorded_git_argv=Path(env["LIVESPEC_RECORDED_GIT_ARGV"]),
    )
    assert _is_shallow(fixture=fixture) == ("false" if complete else "true")
    assert _commit_count(fixture=fixture) == (commits if complete else 1)
    return fixture


def _child_env(*, root: Path) -> dict[str, str]:
    """An EXPLICIT child environment whose `git` is the recording shim.

    `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM` are pointed at `/dev/null` so the
    runner's own configuration -- including whatever the enclosing factory run set --
    cannot change what the step observes. `GIT_TERMINAL_PROMPT` is off so the
    fetch-failure control fails instead of blocking on a credential prompt.

    `GIT_CEILING_DIRECTORIES` is LOAD-BEARING, and it was added because the
    inspection-failure control silently measured the wrong repository without it.
    This suite's pytest basetemp carries a `.git` of its own (a session-scoped
    fixture creates it), and that directory is an ANCESTOR of every `tmp_path`. So
    git's upward discovery walked out of the fixture and answered for the suite's
    repository instead: the control ran in a directory holding no repository and
    git reported `--unshallow on a complete repository does not make sense` --
    a plausible, confident reading of a population the case was not about. Pinning
    the ceiling at the fixture root stops discovery at the one tree under test.
    """
    bin_dir = root / "bin"
    bin_dir.mkdir()
    shim = bin_dir / "git"
    _ = shim.write_text(_GIT_SHIM.format(real_git=_real_git()), encoding="utf-8")
    shim.chmod(0o755)
    home = root / "home"
    home.mkdir()
    return {
        "PATH": f"{bin_dir}:/usr/local/bin:/usr/bin:/bin",
        "HOME": str(home),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CEILING_DIRECTORIES": str(root),
        "LIVESPEC_RECORDED_GIT_ARGV": str(root / "recorded-git-argv.txt"),
    }


def _run_script(
    *, script: str, fixture: _Fixture, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run one prepare-step script under `/bin/sh`, as the engine runs it."""
    return subprocess.run(
        ["/bin/sh", "-c", script],
        cwd=str(cwd if cwd is not None else fixture.clone),
        env=fixture.env,
        capture_output=True,
        text=True,
        check=False,
        input="",
    )


def _recorded_git_argv(*, fixture: _Fixture, containing: str) -> list[str]:
    """Every `git` argv the script invoked that carries `containing`.

    The log is read unconditionally rather than behind an existence guard: every
    case runs a script that invokes `git` at least once, so an absent log is a
    broken shim rather than an empty recording, and surfacing that as a read error
    is the honest outcome. A guard returning the empty list would instead report a
    dead shim as "no such invocation" — which is what three of these cases assert.
    """
    recorded = fixture.recorded_git_argv.read_text(encoding="utf-8").splitlines()
    return [line for line in recorded if containing in line]


def _is_shallow(*, fixture: _Fixture) -> str:
    """`git rev-parse --is-shallow-repository` in the fixture clone, verbatim."""
    return _git_stdout(argv=["rev-parse", "--is-shallow-repository"], fixture=fixture)


def _commit_count(*, fixture: _Fixture) -> int:
    """How many commits the fixture clone can actually read from its head."""
    return int(_git_stdout(argv=["rev-list", "--count", "HEAD"], fixture=fixture))


def _git_stdout(*, argv: list[str], fixture: _Fixture) -> str:
    """Read-back through the real binary, so no observation lands in the argv log."""
    completed = _git(argv=argv, cwd=fixture.clone, env=fixture.env)
    return completed.stdout.strip()


def _commit_argv(*, message: str) -> list[str]:
    """A commit whose identity is supplied PER INVOCATION, leaving the config empty."""
    return [
        "-c",
        "user.name=livespec-prepare-fixture",
        "-c",
        "user.email=prepare@livespec.invalid",
        "commit",
        "--quiet",
        "--message",
        message,
    ]


def _git(*, argv: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Invoke the REAL git by absolute path, bypassing the recording shim."""
    completed = subprocess.run(
        [_real_git(), *argv],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed


def _real_git() -> str:
    """The git binary the shim delegates to, resolved off the runner's own PATH."""
    resolved = shutil.which("git")
    assert resolved is not None
    return resolved
