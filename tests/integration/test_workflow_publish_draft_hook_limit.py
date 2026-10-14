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
one thing under test.

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

# A limit whose reserve leaves a one-second bound, so the over-limit arm is
# reached in about a second instead of in about an hour. The figure goes through
# the SAME arithmetic the Dispatcher uses, so the test cannot pass against a
# bound the production path would never compute.
_TEST_LIMIT_SECONDS = 121


def _git(cwd: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *argv], cwd=str(cwd), check=True, text=True, capture_output=True)


def _publish_script() -> str:
    block = _NODE.search(_WORKFLOW.read_text(encoding="utf-8"))
    assert block is not None
    attr = _SCRIPT.search(block.group("body"))
    assert attr is not None
    return attr.group("value").replace(r"\"", '"').replace("{{ inputs.default_branch }}", "master")


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
    """A real pre-push hook, so git builds the process tree under test."""
    hooks = run / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "pre-push"
    _ = hook.write_text(f"#!/bin/sh\nsleep {seconds}\nexit 0\n", encoding="utf-8")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)


def _sandbox_helpers(*, tmp_path: Path, limit_seconds: int | None) -> Path:
    """The plugins root the Dispatcher's prepare step would have populated."""
    root = tmp_path / "plugins"
    root.mkdir()
    _ = (root / HOOK_LIMIT_PROGRAM_FILENAME).write_text(
        hook_limit_program_source(), encoding="utf-8"
    )
    if limit_seconds is not None:
        budget = push_observation_budget_seconds(limit_seconds=limit_seconds)
        _ = (root / HOOK_LIMIT_LIMITS_FILENAME).write_text(
            f"LIVESPEC_PUBLISH_DRAFT_LIMIT_SECONDS={limit_seconds}\n"
            f"LIVESPEC_PUBLISH_DRAFT_PUSH_BUDGET_SECONDS={budget}\n",
            encoding="utf-8",
        )
    return root


def _forge_double(*, tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    _ = gh.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
    return bin_dir


def _publish(
    *, tmp_path: Path, run: Path, limit_seconds: int | None
) -> subprocess.CompletedProcess[str]:
    bin_dir = _forge_double(tmp_path=tmp_path)
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
