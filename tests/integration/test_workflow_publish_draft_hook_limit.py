"""The publish push is bounded, and an over-limit pre-push hook is named.

Binds the sandbox half of `SPECIFICATION/scenarios.md` Scenario 177's
over-limit-push sub-scenarios, for work-item ``bd-ib-xi63mq``. The cases
execute the committed ``publish_draft`` shell body against a real throwaway
origin with a REAL pre-push hook installed, the way
``test_workflow_publish_draft_refresh.py`` does; the forge is the only doubled
boundary.

WHY A REAL HOOK AND A REAL PUSH. The whole claim is about what a hook run's
processes are doing at the moment a bound ends the push that started them, and
every part of that is a property of the process tree git actually builds. A
doubled `git push` would let the double decide whether a hook ran, which is the
one thing under test. The hook is also shaped like this repository's -- it execs
into a runner rather than doing its work in place -- because that is the shape
an observer keyed on the installed path cannot see; see `_install_pre_push`.

THE NEGATIVE CASE IS WHAT MAKES THE POSITIVE ONE EVIDENCE. A script that printed
the sentinel on any slow push would satisfy the positive assertion exactly as a
correct one does. The second case gives the same script a hook that finishes
immediately and requires it to say nothing -- which is the clause's "keeps its
existing failure classification".
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_limit_program import (
    HOOK_LIMIT_LIMITS_FILENAME,
    HOOK_LIMIT_PROGRAM_FILENAME,
    hook_limit_program_source,
    push_observation_budget_seconds,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_over_limit import (
    HOOK_OVER_LIMIT_SENTINEL,
    hook_over_limit_from_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_record_file_regeneration import (
    RECORD_FILE_PROGRAM_FILENAME,
    record_file_program_source,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)
_PUBLISH_BRANCH = "feat/bd-ib-xi63mq"
_NODE = re.compile(r"^\s*publish_draft\s*\[(?P<body>.*?)^\s*\]", re.DOTALL | re.MULTILINE)
_SCRIPT = re.compile(r'script="(?P<value>(?:[^"\\]|\\.)*)"')

# A limit whose reserve leaves a fifteen-second bound, so the over-limit arm is
# reached in seconds instead of in about an hour. The figure goes through the
# SAME arithmetic the Dispatcher uses, so the test cannot pass against a bound
# the production path would never compute.
#
# FIFTEEN, NOT ONE: the bound starts when the publish script starts `git push`,
# and the observer can only name a hook that is RUNNING when it ends. A
# one-second bound measured git's own startup as much as the hook. On a
# saturated host (load 45 on 18 cores, 2026-10-25) the bound fired before git
# had launched the pre-push hook, so the observer correctly reported that no
# hook was running and the test failed for a reason that had nothing to do with
# the behaviour under test. The hook below still sleeps 90 seconds, six times
# this bound, so it outlives it by a wide margin and the assertion is unchanged.
_TEST_LIMIT_SECONDS = 135


def _git(cwd: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *argv], cwd=str(cwd), check=True, text=True, capture_output=True)


def _publish_script() -> str:
    block = _NODE.search(_WORKFLOW.read_text(encoding="utf-8"))
    assert block is not None
    attr = _SCRIPT.search(block.group("body"))
    assert attr is not None
    return (
        attr.group("value")
        .replace(r"\"", '"')
        .replace("{{ inputs.default_branch }}", "master")
        .replace("{{ inputs.sandbox_check_suite }}", "true")
    )


def _run_clone(*, tmp_path: Path) -> tuple[Path, Path]:
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "-b", "master", str(origin))
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-b", "master")
    _git(seed, "config", "user.name", "hook-limit-test")
    _git(seed, "config", "user.email", "hook-limit-test@example.invalid")
    _ = (seed / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(seed, "add", "seed.txt")
    _git(seed, "commit", "-m", "seed")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-u", "origin", "master")

    run = tmp_path / "run"
    _git(tmp_path, "clone", str(origin), str(run))
    _git(run, "config", "user.name", "hook-limit-test")
    _git(run, "config", "user.email", "hook-limit-test@example.invalid")
    _git(run, "switch", "-c", "fabro/run/hook-limit")
    _ = (run / "work.txt").write_text("run work\n", encoding="utf-8")
    _git(run, "add", "work.txt")
    _git(run, "commit", "-m", "run work")
    return origin, run


def _install_pre_push(*, run: Path, seconds: int) -> None:
    """A real pre-push hook, so git builds the process tree under test.

    SHAPED LIKE THIS REPOSITORY'S, which is what makes the tree the one that
    matters: `.git/hooks/pre-push` here ends in
    `exec mise exec -- lefthook run --no-auto-install "$hook_name" "$@"`, so the
    hook process EXECS away from its own path before the suite that outlives a
    limit begins, and its argv then names the runner and carries the hook name
    as an argument. A hook that merely slept under its installed path would
    exercise a shape no clone of this repository has, and an observer blind to
    the exec'd one would pass against it.
    """
    hooks = run / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    runner = run / ".git" / "hook-runner-stand-in"
    _ = runner.write_text(f"#!/bin/sh\nsleep {seconds}\nexit 0\n", encoding="utf-8")
    runner.chmod(runner.stat().st_mode | stat.S_IXUSR)
    hook = hooks / "pre-push"
    _ = hook.write_text(
        f'#!/bin/sh\nexec "{runner}" run --no-auto-install pre-push "$@"\n',
        encoding="utf-8",
    )
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)


def _sandbox_helpers(*, tmp_path: Path, limit_seconds: int | None) -> Path:
    """The plugins root the Dispatcher's prepare step would have populated."""
    root = tmp_path / "plugins"
    root.mkdir()
    _ = (root / HOOK_LIMIT_PROGRAM_FILENAME).write_text(
        hook_limit_program_source(), encoding="utf-8"
    )
    _ = (root / RECORD_FILE_PROGRAM_FILENAME).write_text(
        record_file_program_source(), encoding="utf-8"
    )
    if limit_seconds is not None:
        budget = push_observation_budget_seconds(limit_seconds=limit_seconds)
        _ = (root / HOOK_LIMIT_LIMITS_FILENAME).write_text(
            f"LIVESPEC_PUBLISH_DRAFT_LIMIT_SECONDS={limit_seconds}\n"
            f"LIVESPEC_PUBLISH_DRAFT_PUSH_BUDGET_SECONDS={budget}\n",
            encoding="utf-8",
        )
    return root


def _forge_double(*, tmp_path: Path, merged_query_delay_seconds: int = 0) -> Path:
    """The forge boundary; its merged-pull-request query is the stage's pre-push work.

    `livespec_landed_check` asks the forge that query once, before the push and
    after the refresh, so a delay on exactly that call is stage time spent
    ahead of the push -- the shape a slow refresh rebase gives the real stage.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    _ = gh.write_text(
        "#!/bin/sh\n"
        f'case "$*" in *"--state merged"*) sleep {merged_query_delay_seconds} ;; esac\n'
        "exit 0\n",
        encoding="utf-8",
    )
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
    return bin_dir


def _publish(
    *,
    tmp_path: Path,
    run: Path,
    limit_seconds: int | None,
    pre_push_work_seconds: int = 0,
) -> subprocess.CompletedProcess[str]:
    bin_dir = _forge_double(tmp_path=tmp_path, merged_query_delay_seconds=pre_push_work_seconds)
    root = _sandbox_helpers(tmp_path=tmp_path, limit_seconds=limit_seconds)
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE")
    }
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
            "LIVESPEC_PUBLISH_BRANCH": _PUBLISH_BRANCH,
            "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(root),
        }
    )
    return subprocess.run(
        ["sh", "-c", _publish_script()],
        cwd=str(run),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _remote_branch(*, run: Path) -> str:
    return _git(run, "ls-remote", "origin", f"refs/heads/{_PUBLISH_BRANCH}").stdout.strip()


def test_a_pre_push_hook_outliving_the_bound_is_named_and_nothing_is_published(
    tmp_path: Path,
) -> None:
    """Scenario 177: the event is named, and the run publishes nothing."""
    _, run = _run_clone(tmp_path=tmp_path)
    _install_pre_push(run=run, seconds=90)

    result = _publish(tmp_path=tmp_path, run=run, limit_seconds=_TEST_LIMIT_SECONDS)

    assert result.returncode != 0, result.stderr
    event = hook_over_limit_from_text(text=result.stderr)
    assert event is not None, result.stderr
    assert event.node == "publish_draft"
    assert event.operation == "push"
    assert event.limit_seconds == _TEST_LIMIT_SECONDS
    assert event.hook_elapsed_ms > 0, event.hook_elapsed_ms
    # The push is reported as ended by its bound, and the branch never appears
    # on origin: a half-published head would leave a pull request the capture
    # could post onto with no verified tree behind it.
    assert "LIVESPEC_PUBLISH_DRAFT_PUSH_OVER_LIMIT" in result.stderr
    assert _remote_branch(run=run) == ""


def test_a_hook_that_finishes_leaves_the_push_unremarked(tmp_path: Path) -> None:
    """Scenario 177: a push whose hook had finished reports no event."""
    _, run = _run_clone(tmp_path=tmp_path)
    _install_pre_push(run=run, seconds=0)

    result = _publish(tmp_path=tmp_path, run=run, limit_seconds=_TEST_LIMIT_SECONDS)

    assert result.returncode == 0, result.stderr
    assert HOOK_OVER_LIMIT_SENTINEL not in result.stderr
    assert "LIVESPEC_PUBLISH_DRAFT_PUSH_OVER_LIMIT" not in result.stderr
    assert _remote_branch(run=run) != ""


def test_withheld_figures_leave_the_push_exactly_as_it_was(tmp_path: Path) -> None:
    """A dispatch that could not read the node's limit still publishes.

    The designed degradation, and the arm most worth a case of its own: the
    Dispatcher withholds the figures rather than inventing a limit, so this
    script must fall through to the unbounded push it performed before any of
    this existed -- not refuse, and not bound the push at a number nobody chose.
    """
    _, run = _run_clone(tmp_path=tmp_path)
    _install_pre_push(run=run, seconds=0)

    result = _publish(tmp_path=tmp_path, run=run, limit_seconds=None)

    assert result.returncode == 0, result.stderr
    assert HOOK_OVER_LIMIT_SENTINEL not in result.stderr
    assert _remote_branch(run=run) != ""


# A limit whose push bound is 35 seconds, with 20 of them spent before the push
# starts. The bound that fires on the clock the STAGE keeps is therefore 15
# seconds after the push begins; a bound counted from the push start would be
# 35. The hook below outlives both, so the only difference between a correct
# script and the measured defect is WHEN the observer is asked.
_LATE_PUSH_LIMIT_SECONDS = 155
_LATE_PUSH_PRE_PUSH_WORK_SECONDS = 20
_LATE_PUSH_HOOK_ELAPSED_CEILING_MS = 25_000


def test_a_push_starting_late_in_the_stage_is_ended_by_the_bound_the_stage_leaves(
    tmp_path: Path,
) -> None:
    """Scenario 177: stage time spent before the push comes off the push's bound.

    Measured 2026-11-04 on run 01M6HWJFSTQXB1YRN4QQSTJZB7: a refresh rebase used
    part of publish_draft's hour, the push's bound was counted from the push
    start, and the engine's stage timeout killed the script before the bound
    could name the ending. Here the same shape is run at small scale: the hook
    has been running for the bound's remainder, not for the full bound, when the
    observer is asked.
    """
    _, run = _run_clone(tmp_path=tmp_path)
    _install_pre_push(run=run, seconds=90)

    result = _publish(
        tmp_path=tmp_path,
        run=run,
        limit_seconds=_LATE_PUSH_LIMIT_SECONDS,
        pre_push_work_seconds=_LATE_PUSH_PRE_PUSH_WORK_SECONDS,
    )

    assert result.returncode != 0, result.stderr
    event = hook_over_limit_from_text(text=result.stderr)
    assert event is not None, result.stderr
    assert event.node == "publish_draft"
    assert event.operation == "push"
    assert event.limit_seconds == _LATE_PUSH_LIMIT_SECONDS
    assert event.hook_elapsed_ms < _LATE_PUSH_HOOK_ELAPSED_CEILING_MS, event.hook_elapsed_ms
    assert _remote_branch(run=run) == ""


def test_an_over_limit_push_records_a_cause_naming_the_event_and_not_a_repair_miss(
    tmp_path: Path,
) -> None:
    """Scenario 177: the needs-human cause names hook-over-limit, the node and the operation."""
    _, run = _run_clone(tmp_path=tmp_path)
    _install_pre_push(run=run, seconds=90)

    result = _publish(tmp_path=tmp_path, run=run, limit_seconds=_TEST_LIMIT_SECONDS)

    assert result.returncode != 0, result.stderr
    reason_path = Path(
        _git(
            run, "rev-parse", "--path-format=absolute", "--git-path", "livespec-needs-human-reason"
        ).stdout.strip()
    )
    assert reason_path.is_file(), result.stderr
    reason = reason_path.read_text(encoding="utf-8")
    assert "hook-over-limit" in reason
    assert "publish_draft" in reason
    assert "push" in reason
    assert f"{_TEST_LIMIT_SECONDS}s" in reason
    assert "LIVESPEC_REFRESH_REPAIR_ABSENT" not in reason
