"""A turn cut by its node timeout leaves its commit run to finish or be named.

Binds `SPECIFICATION/scenarios.md` Scenario 192 for work-item ``bd-ib-ptnxyg``.
The cases execute the committed ``needs_human`` shell body against a real
throwaway origin, a REAL repository hook and the REAL materialized commit runner,
the way ``test_workflow_publish_draft_hook_limit.py`` does for Scenario 177; only
the engine's cut itself is doubled, by simply running the node while the work a
cut turn would have left is still going.

WHY REAL PROCESSES. The claims are about what is running at the instant the
preservation commit would start: a commit run that must have finished, been
stopped, or be named, and a hook run that must be gone before the next commit. A
doubled process table could not tell a stopped hook from one never started.

THE HOST HALF IS CLOSED IN THE SAME CASES. Each case feeds the script's stderr to
the Dispatcher's own reader and asserts the cause or event it yields, so the
sentinel the sandbox prints and the line the host parses cannot drift apart
unnoticed.
"""

from __future__ import annotations

import json
import os
import re
import select
import stat
import subprocess
import sys
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_program import (
    COMMIT_RUNNER_PROGRAM_FILENAME,
    commit_runner_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_limit_program import (
    HOOK_LIMIT_LIMITS_FILENAME,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_node_timeout_cut import (
    node_timeout_cut,
    node_timeout_cut_cause_lines,
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
_NODE = re.compile(r"^\s*needs_human\s*\[(?P<body>.*?)^\s*\]", re.DOTALL | re.MULTILINE)
_SCRIPT = re.compile(r'script="(?P<value>(?:[^"\\]|\\.)*)"')
_RUN_ID = "01M63TESTRUN"
_TIMED_OUT = "ACP turn timed out after 55 tool call(s) and 840 session update(s)"
_PRESERVED_REF = f"refs/heads/needs-human/{_RUN_ID}"


def _clean_environment() -> dict[str, str]:
    """The host environment minus everything that would aim a child at the OUTER repository.

    This suite can itself run under a commit hook, whose `GIT_INDEX_FILE` would point a
    fixture commit at the repository being committed, and the coverage variables would
    make every Python child instrument itself and race.
    """
    return {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith(("COV_CORE", "GIT_"))
    }


def _git(cwd: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *argv],
        cwd=str(cwd),
        env=_clean_environment(),
        check=True,
        text=True,
        capture_output=True,
    )


def _node_script() -> str:
    block = _NODE.search(_WORKFLOW.read_text(encoding="utf-8"))
    assert block is not None
    attr = _SCRIPT.search(block.group("body"))
    assert attr is not None
    return attr.group("value").replace(r"\"", '"').replace("{{ inputs.default_branch }}", "master")


def _run_clone(*, tmp_path: Path) -> tuple[Path, Path]:
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "-b", "master", str(origin))
    run = tmp_path / "run"
    _git(tmp_path, "clone", str(origin), str(run))
    for key, value in (("user.name", "cut-test"), ("user.email", "cut-test@example.invalid")):
        _git(run, "config", key, value)
    _ = (run / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(run, "add", "seed.txt")
    _git(run, "commit", "-m", "seed")
    _git(run, "push", "-u", "origin", "master")
    _git(run, "switch", "-c", "fabro/run/cut")
    _git(run, "config", "livespec.factoryRunId", _RUN_ID)
    return origin, run


def _duration(seconds: int) -> str:
    """A sleep duration carrying this process's id, so only THIS suite's hooks match it.

    A bare `sleep 119` is a string any other process on the host may carry, and the
    cases assert that none survives.
    """
    return f"{seconds}.{os.getpid()}"


def _install_pre_commit(*, run: Path, seconds: int, announce: bool = False) -> None:
    """A real pre-commit hook shaped like this repository's: it execs into a runner.

    With `announce` the hook says so on a FIFO before it sleeps, which is what lets a
    case wait for "the hook is executing" without polling the process table.
    """
    hooks = run / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    runner = run / ".git" / "hook-runner-stand-in"
    start = ""
    if announce:
        fifo = run / ".git" / "hook-started"
        os.mkfifo(fifo)
        start = f'echo started > "{fifo}"\n'
    _ = runner.write_text(
        f"#!/bin/sh\n{start}sleep {_duration(seconds)}\nexit 0\n", encoding="utf-8"
    )
    runner.chmod(runner.stat().st_mode | stat.S_IXUSR)
    hook = hooks / "pre-commit"
    _ = hook.write_text(
        f'#!/bin/sh\nexec "{runner}" run --no-auto-install pre-commit "$@"\n', encoding="utf-8"
    )
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)


def _environment(*, root: Path) -> dict[str, str]:
    env = _clean_environment()
    env.update(
        {
            "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(root),
            "LIVESPEC_GIT_AUTHOR_NAME": "cut-test",
            "LIVESPEC_GIT_AUTHOR_EMAIL": "cut-test@example.invalid",
        }
    )
    return env


def _plugins_root(*, tmp_path: Path, needs_human_limit: int | None) -> Path:
    root = tmp_path / "plugins"
    root.mkdir()
    _ = (root / COMMIT_RUNNER_PROGRAM_FILENAME).write_text(
        commit_runner_program_source(), encoding="utf-8"
    )
    if needs_human_limit is not None:
        _ = (root / HOOK_LIMIT_LIMITS_FILENAME).write_text(
            f"LIVESPEC_NEEDS_HUMAN_LIMIT_SECONDS={needs_human_limit}\n", encoding="utf-8"
        )
    return root


def _stage_work(*, run: Path) -> None:
    _ = (run / "repair.txt").write_text("a proved repair\n", encoding="utf-8")
    _git(run, "add", "repair.txt")


def _start_commit_run(*, run: Path, root: Path) -> str:
    started = subprocess.run(
        [
            sys.executable,
            str(root / COMMIT_RUNNER_PROGRAM_FILENAME),
            *("start", "--", "git", "commit", "-m", "the proved repair"),
        ],
        cwd=str(run),
        env=_environment(root=root),
        text=True,
        capture_output=True,
        check=True,
    )
    return started.stdout.strip()


def _node(*, run: Path, root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-c", _node_script()],
        cwd=str(run),
        env=_environment(root=root),
        input="\n",
        text=True,
        capture_output=True,
        check=False,
    )


def _processes_named(*, needle: bytes, proc_root: Path = Path("/proc")) -> list[int]:
    found: list[int] = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        if needle in cmdline.replace(b"\0", b" "):
            found.append(int(entry.name))
    return found


def _await_hook_start(*, run: Path) -> None:
    """Block until the repository hook has begun, with no polling and no sleep.

    The hook announces itself on a FIFO as its first act. The read end is opened
    non-blocking and waited on with a bound, so a hook that never starts fails the
    case in a minute instead of hanging it; the announcement is READ before the
    descriptor closes, because a writer whose reader vanished mid-write is killed by
    SIGPIPE and the hook would die with it.
    """
    descriptor = os.open(run / ".git" / "hook-started", os.O_RDONLY | os.O_NONBLOCK)
    try:
        readable, _, _ = select.select([descriptor], [], [], 60)
        assert readable, "the repository hook never started"
        assert os.read(descriptor, 16) == b"started\n"
    finally:
        os.close(descriptor)


def _is_ancestor(*, origin: Path, commit: str, ref: str) -> bool:
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, ref],
            cwd=str(origin),
            env=_clean_environment(),
            check=False,
            capture_output=True,
        ).returncode
        == 0
    )


def test_a_commit_run_that_passes_after_the_cut_is_preserved_and_named(tmp_path: Path) -> None:
    """Scenario 192: the passed run's HEAD is in the preserved history and the cause names it."""
    origin, run = _run_clone(tmp_path=tmp_path)
    _install_pre_commit(run=run, seconds=3)
    root = _plugins_root(tmp_path=tmp_path, needs_human_limit=1800)
    _stage_work(run=run)
    run_id = _start_commit_run(run=run, root=root)

    result = _node(run=run, root=root)

    assert f"LIVESPEC_NODE_CUT_COMMIT_RUN: run={run_id} state=passed" in result.stderr
    assert f"LIVESPEC_NEEDS_HUMAN_PRESERVED: {_PRESERVED_REF}" in result.stderr
    record = json.loads(
        (run / ".git" / "livespec-commit-runs" / f"{run_id}.json").read_text(encoding="utf-8")
    )
    assert record["state"] == "passed"
    assert _is_ancestor(origin=origin, commit=record["head"], ref=_PRESERVED_REF)
    cut = node_timeout_cut(
        text=result.stderr,
        stage="fix",
        cause=_TIMED_OUT,
        timeout_seconds=3600,
        started_run_ids=(run_id,),
    )
    body = "\n".join(node_timeout_cut_cause_lines(cut=cut))
    assert "node-timeout" in body
    assert f"{run_id}: passed" in body


def test_a_commit_run_still_running_at_the_bound_is_stopped_before_preservation(
    tmp_path: Path,
) -> None:
    """Scenario 192: the run is stopped first, named no-verdict, and the tree is still preserved."""
    _, run = _run_clone(tmp_path=tmp_path)
    _install_pre_commit(run=run, seconds=119, announce=True)
    root = _plugins_root(tmp_path=tmp_path, needs_human_limit=302)
    _stage_work(run=run)
    run_id = _start_commit_run(run=run, root=root)
    _await_hook_start(run=run)

    result = _node(run=run, root=root)

    stderr = result.stderr
    assert f"LIVESPEC_NODE_CUT_COMMIT_RUN: run={run_id} state=no-verdict" in stderr
    assert stderr.index("LIVESPEC_NODE_CUT_COMMIT_RUN") < stderr.index("LIVESPEC_NEEDS_HUMAN_")
    assert f"LIVESPEC_NEEDS_HUMAN_PRESERVED: {_PRESERVED_REF}" in stderr
    assert _processes_named(needle=f"sleep {_duration(119)}".encode()) == []
    cut = node_timeout_cut(
        text=stderr, stage="fix", cause=_TIMED_OUT, timeout_seconds=3600, started_run_ids=(run_id,)
    )
    assert f"{run_id}: no-verdict" in "\n".join(node_timeout_cut_cause_lines(cut=cut))


def test_an_in_turn_commit_whose_hook_is_executing_is_named_and_ended(tmp_path: Path) -> None:
    """Scenario 192: a hook-over-limit event for the fix node, and no hook run survives."""
    _, run = _run_clone(tmp_path=tmp_path)
    _install_pre_commit(run=run, seconds=118, announce=True)
    root = _plugins_root(tmp_path=tmp_path, needs_human_limit=300)
    _stage_work(run=run)
    commit = subprocess.Popen(
        ["git", "commit", "-m", "an in-turn commit"],
        cwd=str(run),
        env=_environment(root=root),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _await_hook_start(run=run)

    result = _node(run=run, root=root)

    _ = commit.wait(timeout=60)
    assert _processes_named(needle=f"sleep {_duration(118)}".encode()) == []
    assert f"LIVESPEC_NEEDS_HUMAN_PRESERVED: {_PRESERVED_REF}" in result.stderr
    cut = node_timeout_cut(
        text=result.stderr,
        stage="fix",
        cause=_TIMED_OUT,
        timeout_seconds=3600,
        started_run_ids=(),
    )
    assert cut is not None
    event = cut.hook_over_limit
    assert event is not None, result.stderr
    assert (event.node, event.operation, event.limit_seconds) == ("fix", "commit", 3600)
    assert event.hook_elapsed_ms > 0


def test_a_run_with_nothing_left_running_names_nothing(tmp_path: Path) -> None:
    """Scenario 192: no commit run and no hook run means no sentinel and an ordinary preservation."""
    _, run = _run_clone(tmp_path=tmp_path)
    root = _plugins_root(tmp_path=tmp_path, needs_human_limit=None)

    result = _node(run=run, root=root)

    assert "LIVESPEC_NODE_CUT_" not in result.stderr
    assert f"LIVESPEC_NEEDS_HUMAN_PRESERVED: {_PRESERVED_REF}" in result.stderr


def test_the_process_scan_skips_what_it_cannot_read_and_names_what_matches(
    tmp_path: Path,
) -> None:
    """The scan under the other cases is itself right: a vanished entry is not a match."""
    (tmp_path / "self").mkdir()
    (tmp_path / "111").mkdir()
    (tmp_path / "222").mkdir()
    _ = (tmp_path / "222" / "cmdline").write_bytes(f"sleep\x00{_duration(119)}\x00".encode())
    (tmp_path / str(os.getpid())).mkdir()
    _ = (tmp_path / str(os.getpid()) / "cmdline").write_bytes(
        f"sleep\x00{_duration(119)}\x00".encode()
    )

    assert _processes_named(needle=f"sleep {_duration(119)}".encode(), proc_root=tmp_path) == [222]
