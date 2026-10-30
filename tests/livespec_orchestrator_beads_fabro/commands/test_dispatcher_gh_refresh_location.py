"""The credential-holding gh-refresh tooling lives outside the run's working tree.

The refreshing `gh` wrapper, its mint helper and the push helper hold or mint
the run's forge credential. While the bundle sat at
`/workspace/.livespec-gh-refresh` it was INSIDE the working tree an agent stage
edits and commits, so a file an agent wrote there acted with the credential the
next time a publication stage ran. The Dispatcher now materializes it beside the
other Dispatcher-materialized sandbox tooling, under the sandbox plugins root.
"""

import os
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_gh_refresh import (
    DEFAULT_SANDBOX_GH_REFRESH_ROOT,
    SANDBOX_GH_REFRESH_ROOT_ENV_VAR,
    refreshing_gh_prepare_steps_block,
    resolve_sandbox_gh_refresh_root,
)

from tests.prepare_step_support import runnable_script, steps_in

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WORKFLOWS = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro",
    _REPO_ROOT / ".fabro" / "workflows" / "groom-work-item" / "workflow.fabro",
)
_PLUGINS_ROOT_EXPRESSION = "${LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT:-$HOME/.claude/plugins}"
_BUNDLE_NAME = "livespec-gh-refresh"
_WORKTREE_TOP = "/workspace"


def test_the_default_bundle_root_is_outside_the_working_tree() -> None:
    root = resolve_sandbox_gh_refresh_root(environ={})

    assert root == f"{_PLUGINS_ROOT_EXPRESSION}/{_BUNDLE_NAME}"
    assert root == DEFAULT_SANDBOX_GH_REFRESH_ROOT
    assert not root.startswith(_WORKTREE_TOP)


def test_the_override_lever_still_wins_over_the_default() -> None:
    root = resolve_sandbox_gh_refresh_root(environ={SANDBOX_GH_REFRESH_ROOT_ENV_VAR: "/elsewhere"})

    assert root == "/elsewhere"


def test_the_prepare_chain_installs_the_bundle_beside_the_plugin_tooling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert not DEFAULT_SANDBOX_GH_REFRESH_ROOT.startswith(_WORKTREE_TOP)
    monkeypatch.setenv("GITHUB_APP_ID", "42")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "stub-pem")
    monkeypatch.delenv(SANDBOX_GH_REFRESH_ROOT_ENV_VAR, raising=False)
    scripts = [
        runnable_script(step=step) for step in steps_in(block=refreshing_gh_prepare_steps_block())
    ]
    clone = tmp_path / "clone"
    clone.mkdir()
    _git("init", "--initial-branch", "master", repo=clone)
    plugins_root = tmp_path / "plugins"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub_gh = bin_dir / "gh"
    stub_gh.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    stub_gh.chmod(0o755)
    env = {
        **os.environ,
        "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(plugins_root),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
    }

    for index, script in enumerate(scripts):
        step = tmp_path / f"prepare-{index}.sh"
        step.write_text(script, encoding="utf-8")
        subprocess.run(
            ["/bin/bash", str(step)],
            cwd=clone,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )

    bundle = plugins_root / _BUNDLE_NAME
    assert (bundle / "bin" / "mint_app_token.py").is_file()
    assert (bundle / "bin" / "push_origin").is_file()
    assert not (plugins_root / f"{_BUNDLE_NAME}.b64").exists()
    assert sorted(path.name for path in clone.iterdir()) == [".git"]
    assert _git_stdout("status", "--porcelain", "--ignored", repo=clone) == ""


@pytest.mark.parametrize("workflow", _WORKFLOWS, ids=lambda path: path.parent.name)
def test_workflow_push_helpers_resolve_the_bundle_outside_the_working_tree(workflow: Path) -> None:
    text = workflow.read_text(encoding="utf-8")

    assert "/workspace/.livespec-gh-refresh" not in text
    assert text.count("push_origin") >= 1
    assert f"{_PLUGINS_ROOT_EXPRESSION}/{_BUNDLE_NAME}" in text


def _git(*argv: str, repo: Path) -> None:
    subprocess.run(["git", *argv], cwd=repo, capture_output=True, text=True, check=True)


def _git_stdout(*argv: str, repo: Path) -> str:
    completed = subprocess.run(
        ["git", *argv],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout
