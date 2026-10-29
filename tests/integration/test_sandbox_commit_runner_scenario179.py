"""Scenario 179 (work-item bd-ib-sufca7) — a sandbox commit whose hook outlasts one tool call.

`SPECIFICATION/contracts.md` "A commit leg completes past one tool call" says an
implement-stage commit started through the sandbox commit runner reaches its
hook's own verdict however long the hook runs. The runner's state machine and
its Dispatcher replay are covered fake-driven at the unit tier; these cases bind
the runner sub-scenarios of `SPECIFICATION/scenarios.md` Scenario 179 against
REAL processes:

- the runner is materialized by EXECUTING the prepare step the plugin renders
  (`commit_runner_prepare_steps_block`), not by writing its source by hand;
- the repository is a real `git init` clone whose real `pre-commit` and
  `commit-msg` hooks are shell scripts;
- the slow hook waits for a release file rather than sleeping a fixed time, so
  "outlasts the first bounded wait" holds on any host load.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner import (
    COMMIT_RUNNER_PROGRAM_FILENAME,
    commit_runner_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR,
)

from tests.prepare_step_support import env_of, steps_in

_RELEASE = "release-hook"
_TRAILERS = (("Hook-Trailer-One", "alpha"), ("Hook-Trailer-Two", "beta"))
_FAILED_TARGET = "check-lint"
_FIRST_WAIT_SECONDS = "1"
_TERMINAL_WAIT_SECONDS = "120"

# The hook polls for the release file, then answers with its content: `pass`
# lets the commit proceed, anything else refuses it with the gate aggregate's
# own failed-targets list.
_PRE_COMMIT = f"""#!/bin/sh
release="$(git rev-parse --git-path {_RELEASE})"
while ! test -f "$release"; do sleep 0.1; done
if test "$(cat "$release")" = pass; then exit 0; fi
printf 'Failed targets (1):\\n  - {_FAILED_TARGET}\\n'
exit 1
"""

_COMMIT_MSG = "#!/bin/sh\n" + "".join(
    f'git interpret-trailers --in-place --trailer "{k}: {v}" "$1"\n' for k, v in _TRAILERS
)


@dataclass(frozen=True, kw_only=True)
class _Sandbox:
    repo: Path
    runner: Path
    env: dict[str, str]


def _git(*, sandbox: _Sandbox, argv: list[str]) -> str:
    completed = subprocess.run(
        ["git", *argv],
        cwd=sandbox.repo,
        env=sandbox.env,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _child_environment(*, home: Path, plugins: Path) -> dict[str, str]:
    """The inherited environment minus git and coverage state, with a fixed identity."""
    kept = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("GIT_", "COV_CORE_")) and name != "COVERAGE_PROCESS_START"
    }
    return {
        **kept,
        "HOME": str(home),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Scenario Author",
        "GIT_AUTHOR_EMAIL": "author@example.invalid",
        "GIT_COMMITTER_NAME": "Scenario Author",
        "GIT_COMMITTER_EMAIL": "author@example.invalid",
        SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR: str(plugins),
    }


def _install_hook(*, repo: Path, name: str, body: str) -> None:
    path = repo / ".git" / "hooks" / name
    _ = path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


@pytest.fixture(name="sandbox")
def _sandbox(tmp_path: Path) -> Iterator[_Sandbox]:
    """A real clone with the plugin-materialized runner and a slow, trailer-writing hook."""
    plugins = tmp_path / "plugins"
    repo = tmp_path / "clone"
    repo.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    env = _child_environment(home=home, plugins=plugins)
    sandbox = _Sandbox(repo=repo, runner=plugins / COMMIT_RUNNER_PROGRAM_FILENAME, env=env)
    _ = subprocess.run(["git", "init", "--quiet"], cwd=repo, env=env, check=True)
    _ = (repo / "module.py").write_text("x = 0\n", encoding="utf-8")
    _ = _git(sandbox=sandbox, argv=["add", "module.py"])
    _ = _git(sandbox=sandbox, argv=["commit", "--quiet", "-m", "chore: baseline"])
    steps = [step for step in steps_in(block=commit_runner_prepare_steps_block()) if step.env]
    assert len(steps) == 1
    materialized = subprocess.run(
        ["sh", "-c", steps[0].script],
        cwd=repo,
        env=env_of(step=steps[0], base=env),
        check=False,
        capture_output=True,
        text=True,
    )
    assert materialized.returncode == 0, materialized.stderr
    assert sandbox.runner.is_file()
    _install_hook(repo=repo, name="pre-commit", body=_PRE_COMMIT)
    _install_hook(repo=repo, name="commit-msg", body=_COMMIT_MSG)
    _ = (repo / "module.py").write_text("x = 1\n", encoding="utf-8")
    _ = _git(sandbox=sandbox, argv=["add", "module.py"])
    yield sandbox
    _stop_live_runs(sandbox=sandbox)


def _runs_directory(*, sandbox: _Sandbox) -> Path:
    return sandbox.repo / _git(
        sandbox=sandbox, argv=["rev-parse", "--git-path", "livespec-commit-runs"]
    )


def _stop_live_runs(*, sandbox: _Sandbox) -> None:
    """Release any hook still polling and end its process group, so no test leaks one."""
    _ = (
        sandbox.repo / _git(sandbox=sandbox, argv=["rev-parse", "--git-path", _RELEASE])
    ).write_text("stop", encoding="utf-8")
    for pid_file in _runs_directory(sandbox=sandbox).glob("*.pid"):
        with contextlib.suppress(OSError, ValueError):
            os.killpg(int(pid_file.read_text(encoding="utf-8").strip()), signal.SIGKILL)


def _runner(*, sandbox: _Sandbox, argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(sandbox.runner), *argv],
        cwd=sandbox.repo,
        env=sandbox.env,
        check=False,
        capture_output=True,
        text=True,
    )


def _start_commit(*, sandbox: _Sandbox, message: str) -> str:
    started = _runner(sandbox=sandbox, argv=["start", "--", "git", "commit", "-m", message])
    assert started.returncode == 0, started.stderr
    run_id = started.stdout.strip()
    assert run_id.startswith("commit-")
    return run_id


def _wait(*, sandbox: _Sandbox, run_id: str, seconds: str) -> dict[str, object]:
    waited = _runner(sandbox=sandbox, argv=["wait", run_id, "--timeout-seconds", seconds])
    assert waited.returncode == 0, waited.stderr
    report: object = json.loads(waited.stdout)
    assert isinstance(report, dict)
    return cast("dict[str, object]", report)


def _release_hook(*, sandbox: _Sandbox, verdict: str) -> None:
    release = sandbox.repo / _git(sandbox=sandbox, argv=["rev-parse", "--git-path", _RELEASE])
    _ = release.write_text(verdict, encoding="utf-8")


def _head(*, sandbox: _Sandbox) -> str:
    return _git(sandbox=sandbox, argv=["rev-parse", "HEAD"])


def test_a_commit_whose_hook_outlasts_the_first_wait_completes_with_the_hooks_verdict(
    sandbox: _Sandbox,
) -> None:
    """A running first wait is not a verdict; a later wait reports passed, the new HEAD and trailers."""
    before = _head(sandbox=sandbox)
    run_id = _start_commit(sandbox=sandbox, message="feat: slow hook commit")

    first = _wait(sandbox=sandbox, run_id=run_id, seconds=_FIRST_WAIT_SECONDS)
    assert first["state"] == "running"
    assert "exit_code" not in first
    assert _head(sandbox=sandbox) == before

    _release_hook(sandbox=sandbox, verdict="pass")
    final = _wait(sandbox=sandbox, run_id=run_id, seconds=_TERMINAL_WAIT_SECONDS)

    assert final["state"] == "passed"
    assert final["exit_code"] == 0
    after = _head(sandbox=sandbox)
    assert after != before
    assert final["head"] == after
    message = _git(sandbox=sandbox, argv=["log", "-1", "--format=%B"])
    assert message.startswith("feat: slow hook commit")
    for key, value in _TRAILERS:
        assert f"{key}: {value}" in message.splitlines()


def test_a_commit_refused_by_its_hook_is_failed_with_the_exit_status_and_head_unchanged(
    sandbox: _Sandbox,
) -> None:
    """The hook's refusal is the commit's failed state, with the process's own exit status."""
    before = _head(sandbox=sandbox)
    run_id = _start_commit(sandbox=sandbox, message="feat: refused commit")

    _release_hook(sandbox=sandbox, verdict="refuse")
    final = _wait(sandbox=sandbox, run_id=run_id, seconds=_TERMINAL_WAIT_SECONDS)

    assert final["state"] == "failed"
    assert final["exit_code"] == 1
    assert final["head"] is None
    assert f"  - {_FAILED_TARGET}" in str(final["output_tail"])
    assert _head(sandbox=sandbox) == before


def test_a_commit_ended_by_a_signal_has_no_verdict_and_is_never_reported_passed(
    sandbox: _Sandbox,
) -> None:
    """Killing the run's whole process group before the hook answers leaves no verdict at all."""
    before = _head(sandbox=sandbox)
    run_id = _start_commit(sandbox=sandbox, message="feat: signalled commit")
    assert _wait(sandbox=sandbox, run_id=run_id, seconds=_FIRST_WAIT_SECONDS)["state"] == "running"

    group = int((_runs_directory(sandbox=sandbox) / f"{run_id}.pid").read_text(encoding="utf-8"))
    os.killpg(group, signal.SIGKILL)

    reports = [
        _wait(sandbox=sandbox, run_id=run_id, seconds=_TERMINAL_WAIT_SECONDS) for _ in range(2)
    ]
    for report in reports:
        assert report["state"] == "no-verdict"
        assert report["exit_code"] is None
        assert report["head"] is None
    assert _head(sandbox=sandbox) == before


def test_a_second_commit_does_not_start_while_the_first_is_still_running(
    sandbox: _Sandbox,
) -> None:
    """The refusal names the running commit run, and it leaves that run to finish alone."""
    before = _head(sandbox=sandbox)
    first_id = _start_commit(sandbox=sandbox, message="feat: first commit")
    assert (
        _wait(sandbox=sandbox, run_id=first_id, seconds=_FIRST_WAIT_SECONDS)["state"] == "running"
    )

    second = _runner(
        sandbox=sandbox, argv=["start", "--", "git", "commit", "-m", "feat: second commit"]
    )

    assert second.returncode == 2
    assert second.stdout == ""
    assert first_id in second.stderr
    assert "still running" in second.stderr
    assert len(list(_runs_directory(sandbox=sandbox).glob("*.json"))) == 1
    assert _head(sandbox=sandbox) == before

    _release_hook(sandbox=sandbox, verdict="pass")
    final = _wait(sandbox=sandbox, run_id=first_id, seconds=_TERMINAL_WAIT_SECONDS)
    assert final["state"] == "passed"
