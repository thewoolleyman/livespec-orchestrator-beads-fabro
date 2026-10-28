"""The review turn is refused every command that moves the branch or runs the whole suite.

Work-item `bd-ib-azxvoo`. Measured on run 01M5Y3EGXZSS (work-item
`bd-ib-davaxq`, orchestrator v0.243.14): implement, review, recapture and the
second proof capture all succeeded, then `review@2` ran `git rebase
origin/master` and `mise exec -- just check`, the check never returned inside
the 1800 s turn allowance, and the run ended at `needs_human` with no verdict.
Review is a GRADING role -- the commit hooks and the post-merge janitor own the
whole-suite gate and `pr_refresh` owns the rebase -- so the sandbox projects a
`PreToolUse` Bash hook that refuses both, for the `review` stage only.

The guard is stdlib-only source the prepare step writes into the sandbox, so
these cases exec that exact source in-process and drive its `main` with a fake
stdin and environment: `check-tests-no-subprocess-spawn` forbids a real spawn.
The program is imported through `importlib` inside each case, with the module's
existence as the first assertion, so a missing module is a failed assertion
rather than a collection error.
"""

from __future__ import annotations

import importlib
import io
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import tomli
from livespec_orchestrator_beads_fabro.commands._dispatcher_harness_shell_policy import (
    harness_settings_merge_program,
)

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_review_guard.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_review_guard"
_BLOCKING_EXIT_CODE = 2


def _guard_module() -> ModuleType:
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist"
    return importlib.import_module(_MODULE_NAME)


def _program() -> dict[str, Any]:
    """The guard's exact shipped source, loaded into a fresh namespace."""
    namespace: dict[str, Any] = {"__name__": "livespec_review_guard_under_test"}
    source: str = _guard_module().review_guard_program_source()
    exec(compile(source, "livespec-review-guard.py", "exec"), namespace)  # noqa: S102
    return namespace


def _run(*, command: str, stage: str | None = "review") -> tuple[int, str]:
    """Drive the program as the harness hook does: tool JSON on stdin, env, stderr."""
    environ = {} if stage is None else {"LIVESPEC_AGENT_STAGE": stage}
    stderr = io.StringIO()
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    status = _program()["main"](payload, environ, stderr)
    return status, stderr.getvalue()


_MOVES_THE_BRANCH = [
    "git rebase origin/master",
    "git fetch origin && git rebase origin/master",
    "mise exec -- git rebase origin/master",
    "git -C /workspace commit -m 'x'",
    "git commit --amend --no-edit",
    "git push origin HEAD:refs/heads/feat/x",
    "git reset --hard HEAD~1",
    "git merge origin/master",
    "git cherry-pick abc1234",
    "git checkout origin/master",
    "git pull --rebase",
    "git -c core.hooksPath=/dev/null rebase --continue",
    "sh -c 'git rebase origin/master'",
    'bash -lc "cd . && git commit -am x"',
    "env GIT_EDITOR=true git rebase -i HEAD~3",
    "echo $(git rebase origin/master)",
    "true; git stash",
    "git update-ref refs/heads/x HEAD",
    "/usr/bin/git rebase origin/master",
]

_RUNS_THE_WHOLE_SUITE = [
    "just check",
    "mise exec -- just check",
    "uv run just check",
    "just --justfile justfile check",
    "livespec-implement-check-suite",
    '"${LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT:-$HOME/.claude/plugins}/livespec-implement-check-suite"',
    "cd /workspace && mise exec -- just check 2>&1 | tail -50",
]

_PERMITTED = [
    "git diff origin/master...HEAD",
    "git log --oneline -5",
    "git show HEAD:README.md",
    "git status --short",
    "git fetch --quiet origin feat/bd-ib-azxvoo",
    "git diff --quiet abc1234 HEAD && echo current",
    "git branch --show-current",
    "git stash list",
    "gh pr view 5 --json comments",
    "gh pr comment 5 --body-file /tmp/review.md",
    "mise exec -- pytest tests/test_one.py::test_named_case",
    "just --list",
    "just check-types",
    "grep -n 'git rebase' notes.md",
    'echo "run just check and git rebase later"',
    "cat <<'EOF' > /tmp/review.md\n[BLOCKING] a.py:1 - ran git rebase and just check\nEOF",
]


@pytest.mark.parametrize("command", _MOVES_THE_BRANCH)
def test_a_review_turn_command_that_moves_or_edits_the_branch_is_refused(command: str) -> None:
    status, message = _run(command=command)
    assert status == _BLOCKING_EXIT_CODE, command
    assert "LIVESPEC_REVIEW_GUARD_REFUSED" in message
    assert "pr_refresh" in message
    assert "verdict" in message


@pytest.mark.parametrize("command", _RUNS_THE_WHOLE_SUITE)
def test_a_review_turn_whole_suite_check_is_refused_with_the_named_test_id_remedy(
    command: str,
) -> None:
    status, message = _run(command=command)
    assert status == _BLOCKING_EXIT_CODE, command
    assert "LIVESPEC_REVIEW_GUARD_REFUSED" in message
    assert "named test id" in message
    assert "verdict" in message


@pytest.mark.parametrize("command", _PERMITTED)
def test_a_review_turn_read_only_command_is_permitted(command: str) -> None:
    status, message = _run(command=command)
    assert (status, message) == (0, ""), command


@pytest.mark.parametrize("stage", ["implement", "review_fix", "fix", "pr_refresh", None])
def test_the_guard_binds_the_review_stage_only(stage: str | None) -> None:
    for command in ("git rebase origin/master", "just check"):
        assert _run(command=command, stage=stage) == (0, ""), (stage, command)


@pytest.mark.parametrize("payload", ["", "not json", "[]", '{"tool_input": 5}', "{}"])
def test_the_guard_never_blocks_on_input_it_cannot_read(payload: str) -> None:
    stderr = io.StringIO()
    status = _program()["main"](payload, {"LIVESPEC_AGENT_STAGE": "review"}, stderr)
    assert status == 0
    assert stderr.getvalue() == ""


def test_the_hook_declaration_is_a_pretooluse_bash_hook_that_cannot_block_on_a_missing_program() -> (
    None
):
    module = _guard_module()
    declaration = module.review_guard_hook_declaration()
    assert list(declaration) == ["PreToolUse"]
    (group,) = declaration["PreToolUse"]
    assert group["matcher"] == "Bash"
    (entry,) = group["hooks"]
    command = str(entry["command"])
    assert module.REVIEW_GUARD_PROGRAM_FILENAME in command
    assert "test -f" in command
    assert entry["timeout"] == module.REVIEW_GUARD_HOOK_TIMEOUT_SECONDS


def test_the_prepare_step_writes_the_exact_guard_source_into_the_plugins_root() -> None:
    module = _guard_module()
    block = module.review_guard_prepare_steps_block()
    (step,) = tomli.loads(block)["run"]["prepare"]["steps"]
    script = str(step["script"])
    assert module.REVIEW_GUARD_PROGRAM_FILENAME in script
    assert "<<" not in script
    assert step["env"] == {"LIVESPEC_PREPARE_PAYLOAD": module.review_guard_program_source()}


def test_the_settings_merge_program_installs_the_guard_beside_the_gate() -> None:
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist"
    program = harness_settings_merge_program()
    assert "livespec-run-plugin-gate.py" in program
    assert "livespec-review-guard.py" in program
