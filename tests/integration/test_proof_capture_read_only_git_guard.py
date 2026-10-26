"""The proof-capture adapter refuses Git writes before repository hooks run.

`proof_capture` may upload a proof asset through GitHub, but the tree is
read-only.  A normal Git hook is too late to express that rule: the repository's
own commit and push hooks can consume the entire turn before a prompt-only
instruction is obeyed.  This test puts markers in those repository hooks, then
uses the adapter environment a materialized proof-capture node receives.  The
absence of markers is therefore evidence that the stage-specific hooks path won
before either repository hook began.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_graph_adapters import (
    guarded_adapter_commands,
)

_ROOT = Path(__file__).resolve().parents[2]
_PROOF_CAPTURE_HOOKS = (
    _ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "proof-capture-hooks"
)
_PROOF_CAPTURE_ADAPTER = "proof_capture_adapter"
_IMPLEMENT_ADAPTER = "implement_adapter"
_FIX_ADAPTER = "fix_adapter"
_ADAPTER = "ANTHROPIC_MODEL=claude-opus-4-8 claude-agent-acp"


def test_proof_capture_git_writes_refuse_before_repository_hooks_but_implement_and_fix_run_them(
    tmp_path: Path,
) -> None:
    """A protected turn refuses quickly; ordinary implementation turns keep hooks."""
    assert _PROOF_CAPTURE_HOOKS.is_dir(), "proof_capture needs its dedicated Git hooks"
    commands = guarded_adapter_commands(
        run_inputs=tuple(
            f"{name}={_ADAPTER}"
            for name in (_PROOF_CAPTURE_ADAPTER, _IMPLEMENT_ADAPTER, _FIX_ADAPTER)
        )
    )
    proof_environment = _adapter_environment(command=commands[_PROOF_CAPTURE_ADAPTER])
    _assert_proof_capture_configuration(environment=proof_environment)
    _assert_empty_proof_capture_adapter_is_guarded()
    _assert_empty_command_has_no_adapter_environment()
    _assert_ordinary_configuration(commands=commands)

    work, marker = _repository(tmp_path=tmp_path)
    shutil.copytree(
        _PROOF_CAPTURE_HOOKS,
        work / ".claude-plugin/.fabro/workflows/implement-work-item/proof-capture-hooks",
    )
    _install_repository_hook(repo=work, hook="pre-commit", marker=marker)
    _install_repository_hook(repo=work, hook="pre-push", marker=marker)

    _assert_proof_capture_refusals(repo=work, marker=marker, environment=proof_environment)
    _assert_ordinary_turns_run_repository_hooks(repo=work, commands=commands)
    assert marker.read_text(encoding="utf-8").splitlines() == [
        "pre-commit",
        "pre-push",
        "pre-commit",
        "pre-push",
    ]


def _assert_proof_capture_configuration(*, environment: Mapping[str, str]) -> None:
    """The protected adapter selects its private hooks path through Git config."""
    assert environment["GIT_CONFIG_COUNT"] == "1"
    assert environment["GIT_CONFIG_KEY_0"] == "core.hooksPath"
    assert (
        environment["GIT_CONFIG_VALUE_0"]
        == ".claude-plugin/.fabro/workflows/implement-work-item/proof-capture-hooks"
    )


def _assert_empty_proof_capture_adapter_is_guarded() -> None:
    """The guard remains well-formed when a repository declares no adapter argv."""
    command = guarded_adapter_commands(run_inputs=(f"{_PROOF_CAPTURE_ADAPTER}=",))[
        _PROOF_CAPTURE_ADAPTER
    ]
    _assert_proof_capture_configuration(environment=_adapter_environment(command=command))


def _assert_empty_command_has_no_adapter_environment() -> None:
    """A command with no tokens has no leading adapter assignments to read."""
    assert "GIT_CONFIG_COUNT" not in _adapter_environment(command="")


def _assert_ordinary_configuration(*, commands: Mapping[str, str]) -> None:
    """The node-specific guard does not leak into implementation or fix adapters."""
    assert "GIT_CONFIG_COUNT" not in _adapter_environment(command=commands[_IMPLEMENT_ADAPTER])
    assert "GIT_CONFIG_COUNT" not in _adapter_environment(command=commands[_FIX_ADAPTER])


def _assert_proof_capture_refusals(
    *, repo: Path, marker: Path, environment: dict[str, str]
) -> None:
    """Commit and push both stop before the repository's corresponding hook."""
    _ = (repo / "proof.txt").write_text("proof\n", encoding="utf-8")
    _ = _git("add", "proof.txt", repo=repo, environment=environment)
    _assert_git_write_is_refused(
        argv=("commit", "-m", "proof capture must stay read-only"),
        repo=repo,
        marker=marker,
        environment=environment,
    )
    _assert_git_write_is_refused(
        argv=("push", "origin", "HEAD:refs/heads/proof-capture"),
        repo=repo,
        marker=marker,
        environment=environment,
    )


def _assert_git_write_is_refused(
    *, argv: tuple[str, ...], repo: Path, marker: Path, environment: dict[str, str]
) -> None:
    """One protected Git write stops before either repository hook can start."""
    started = time.monotonic()
    refused = _git(*argv, repo=repo, environment=environment)
    assert time.monotonic() - started < 10
    assert refused.returncode != 0
    assert "proof_capture is read-only" in refused.stderr
    assert "preferred_label=fix" in refused.stderr
    assert not marker.exists()


def _assert_ordinary_turns_run_repository_hooks(*, repo: Path, commands: Mapping[str, str]) -> None:
    """Implement and fix retain the repository commit and push hook behavior."""
    implement = _adapter_environment(command=commands[_IMPLEMENT_ADAPTER])
    _ = _git("commit", "-m", "implement remains hook-protected", repo=repo, environment=implement)
    _ = _git("push", "origin", "HEAD:refs/heads/implement", repo=repo, environment=implement)
    _ = (repo / "fix.txt").write_text("fix\n", encoding="utf-8")
    fix = _adapter_environment(command=commands[_FIX_ADAPTER])
    _ = _git("add", "fix.txt", repo=repo, environment=fix)
    _ = _git("commit", "-m", "fix remains hook-protected", repo=repo, environment=fix)
    _ = _git("push", "origin", "HEAD:refs/heads/fix", repo=repo, environment=fix)


def _adapter_environment(*, command: str) -> dict[str, str]:
    """The leading adapter assignments, against a neutral Git config environment."""
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_CONFIG_")
    }
    for token in shlex.split(command):
        if "=" not in token:
            break
        key, value = token.split("=", 1)
        environment[key] = value
    return environment


def _repository(*, tmp_path: Path) -> tuple[Path, Path]:
    """A worktree with a pushed base and a marker its repository hooks append to."""
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    _ = _git("init", "--bare", str(remote), repo=tmp_path, environment=None)
    _ = _git("init", str(work), repo=tmp_path, environment=None)
    _ = _git("config", "user.name", "Test User", repo=work, environment=None)
    _ = _git("config", "user.email", "test@example.invalid", repo=work, environment=None)
    _ = (work / "base.txt").write_text("base\n", encoding="utf-8")
    _ = _git("add", "base.txt", repo=work, environment=None)
    _ = _git("commit", "-m", "base", repo=work, environment=None)
    _ = _git("remote", "add", "origin", str(remote), repo=work, environment=None)
    _ = _git("push", "origin", "HEAD:refs/heads/main", repo=work, environment=None)
    return work, tmp_path / "repository-hooks-ran"


def _install_repository_hook(*, repo: Path, hook: str, marker: Path) -> None:
    """A visible repository hook, used to prove the read-only hooks supersede it."""
    path = repo / ".git" / "hooks" / hook
    _ = path.write_text(
        "#!/bin/sh\n" + f"printf '%s\\n' {shlex.quote(hook)} >> {shlex.quote(str(marker))}\n",
        encoding="utf-8",
    )
    _ = path.chmod(0o755)


def _git(
    *argv: str, repo: Path, environment: Mapping[str, str] | None
) -> subprocess.CompletedProcess[str]:
    """Run Git and make every test command's result available to its assertion."""
    return subprocess.run(
        ["git", *argv],
        cwd=repo,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )
