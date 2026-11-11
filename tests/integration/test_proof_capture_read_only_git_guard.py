"""The proof-capture adapter refuses Git writes before repository hooks run.

`proof_capture` may upload a proof asset through GitHub, but the tree is
read-only. A normal Git hook is too late to express that rule: the repository's
own commit and push hooks can consume the entire turn before a prompt-only
instruction is obeyed. This test puts markers in those repository hooks, then
uses the adapter environment a materialized proof-capture node receives. The
absence of markers is therefore evidence that the stage-specific launcher won
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

from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard import (
    guard_script_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_graph_adapters import (
    guarded_adapter_commands,
)

_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_PROOF_CAPTURE_HOOKS = (
    _ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "proof-capture-hooks"
)
_SOURCE_PROOF_CAPTURE_BIN = _SOURCE_PROOF_CAPTURE_HOOKS.parent / "proof-capture-bin"
_DISPATCHER_PROOF_CAPTURE_ROOT = "/workspace/.livespec"
_DISPATCHER_PROOF_CAPTURE_HOOKS = f"{_DISPATCHER_PROOF_CAPTURE_ROOT}/proof-capture-hooks"
_DISPATCHER_PROOF_CAPTURE_BIN = f"{_DISPATCHER_PROOF_CAPTURE_ROOT}/proof-capture-bin"
_PROOF_CAPTURE_ADAPTER = "proof_capture_adapter"
_IMPLEMENT_ADAPTER = "implement_adapter"
_FIX_ADAPTER = "fix_adapter"
_ADAPTER = "ANTHROPIC_MODEL=claude-opus-4-8 claude-agent-acp"
_PROTECTED_CHECKOUT_ENV_VAR = "LIVESPEC_PROOF_CAPTURE_PROTECTED_CHECKOUT"


def test_proof_capture_git_writes_refuse_before_repository_hooks_but_implement_and_fix_run_them(
    tmp_path: Path,
) -> None:
    """A protected turn refuses quickly; ordinary implementation turns keep hooks."""
    assert _SOURCE_PROOF_CAPTURE_HOOKS.is_dir(), "proof_capture needs its dedicated Git hooks"
    assert _SOURCE_PROOF_CAPTURE_BIN.is_dir(), "proof_capture needs its dedicated Git launcher"
    commands = guarded_adapter_commands(
        run_inputs=tuple(
            f"{name}={_ADAPTER}"
            for name in (_PROOF_CAPTURE_ADAPTER, _IMPLEMENT_ADAPTER, _FIX_ADAPTER)
        )
    )
    proof_environment = _adapter_environment(command=commands[_PROOF_CAPTURE_ADAPTER])
    _ = proof_environment.pop("LIVESPEC_CREDENTIAL_USE_DEADLINE_EPOCH", None)
    proof_environment["LIVESPEC_CREDENTIAL_USE_UNPROTECTED"] = "1"
    _assert_proof_capture_configuration(environment=proof_environment)
    _assert_empty_proof_capture_adapter_is_guarded()
    _assert_empty_command_has_no_adapter_environment()
    _assert_ordinary_configuration(commands=commands)

    work, marker = _repository(tmp_path=tmp_path)
    assert not (work / ".claude-plugin").exists()
    proof_environment[_PROTECTED_CHECKOUT_ENV_VAR] = str(work)
    guard = _install_proof_capture_launcher(tmp_path=tmp_path)
    _install_repository_hook(repo=work, hook="pre-commit", marker=marker)
    _install_repository_hook(repo=work, hook="pre-push", marker=marker)

    _assert_proof_capture_refusals(
        repo=work,
        marker=marker,
        environment=proof_environment,
        guard=guard,
    )
    _assert_ordinary_turns_run_repository_hooks(repo=work, commands=commands)
    assert marker.read_text(encoding="utf-8").splitlines() == [
        "pre-commit",
        "pre-push",
        "pre-commit",
        "pre-push",
    ]


def test_proof_capture_scratch_repository_commits_keep_their_hooks_and_the_checkout_stays_read_only(
    tmp_path: Path,
) -> None:
    """Only the run's checkout is the tree: a scratch repository commits normally."""
    commands = guarded_adapter_commands(
        run_inputs=(f"{_PROOF_CAPTURE_ADAPTER}={_ADAPTER}", f"{_IMPLEMENT_ADAPTER}={_ADAPTER}")
    )
    environment = _adapter_environment(command=commands[_PROOF_CAPTURE_ADAPTER])
    _ = environment.pop("LIVESPEC_CREDENTIAL_USE_DEADLINE_EPOCH", None)
    environment["LIVESPEC_CREDENTIAL_USE_UNPROTECTED"] = "1"
    (tmp_path / "run").mkdir()
    (tmp_path / "scratch").mkdir()
    work, checkout_marker = _repository(tmp_path=tmp_path / "run")
    environment[_PROTECTED_CHECKOUT_ENV_VAR] = str(work)
    _ = _install_proof_capture_launcher(tmp_path=tmp_path)
    # The launcher is put on PATH directly: the credential-use guard prefers the
    # sandbox's own materialized launcher at its production path when one exists.
    environment["PATH"] = os.pathsep.join(
        (str(tmp_path / ".livespec" / "proof-capture-bin"), os.environ["PATH"])
    )
    _install_repository_hook(repo=work, hook="pre-commit", marker=checkout_marker)
    scratch, scratch_marker = _repository(tmp_path=tmp_path / "scratch")
    _install_repository_hook(repo=scratch, hook="pre-commit", marker=scratch_marker)
    _install_repository_hook(repo=scratch, hook="commit-msg", marker=scratch_marker)
    _install_repository_hook(repo=scratch, hook="pre-push", marker=scratch_marker)

    _assert_scratch_commit_runs_its_own_hooks(
        scratch=scratch, marker=scratch_marker, environment=environment
    )
    _assert_scratch_commit_through_the_hooks_path_runs_its_own_pre_commit(
        tmp_path=tmp_path, scratch=scratch, marker=scratch_marker, environment=environment
    )
    _assert_checkout_commits_refuse_however_they_are_addressed(
        tmp_path=tmp_path,
        work=work,
        scratch=scratch,
        marker=checkout_marker,
        environment=environment,
    )
    _assert_protected_and_unsafe_pushes_are_refused(
        tmp_path=tmp_path,
        work=work,
        scratch=scratch,
        marker=checkout_marker,
        environment=environment,
    )
    _assert_scratch_push_to_temporary_bare_repository_is_allowed(
        scratch=scratch,
        marker=scratch_marker,
        environment=environment,
    )


def _assert_scratch_commit_runs_its_own_hooks(
    *, scratch: Path, marker: Path, environment: dict[str, str]
) -> None:
    """Through the launcher, a scratch commit succeeds and runs its own hooks."""
    _ = (scratch / "scratch.txt").write_text("scratch\n", encoding="utf-8")
    _ = _git("add", "scratch.txt", repo=scratch, environment=environment)
    started = time.monotonic()
    committed = _git("commit", "-m", "scratch", repo=scratch, environment=environment)
    assert time.monotonic() - started < 10
    assert committed.returncode == 0, committed.stderr
    assert "proof_capture is read-only" not in committed.stderr
    assert marker.read_text(encoding="utf-8").splitlines() == ["pre-commit", "commit-msg"]
    _ = marker.unlink()


def _assert_scratch_commit_through_the_hooks_path_runs_its_own_pre_commit(
    *, tmp_path: Path, scratch: Path, marker: Path, environment: dict[str, str]
) -> None:
    """Without the launcher, the private hooks path hands a scratch repo its own hook."""
    hooks = tmp_path / ".livespec" / "proof-capture-hooks"
    direct = {**environment, "GIT_CONFIG_VALUE_0": str(hooks), "PATH": os.environ["PATH"]}
    _ = (scratch / "direct.txt").write_text("direct\n", encoding="utf-8")
    _ = _git("add", "direct.txt", repo=scratch, environment=direct)
    committed = _git("commit", "-m", "direct", repo=scratch, environment=direct)
    assert committed.returncode == 0, committed.stderr
    assert "proof_capture is read-only" not in committed.stderr
    assert marker.read_text(encoding="utf-8").splitlines() == ["pre-commit"]
    _ = marker.unlink()


def _assert_checkout_commits_refuse_however_they_are_addressed(
    *,
    tmp_path: Path,
    work: Path,
    scratch: Path,
    marker: Path,
    environment: dict[str, str],
) -> None:
    """The checkout refuses by cwd, -C, --git-dir, GIT_DIR and linked worktree."""
    linked = tmp_path / "linked-worktree"
    _ = _git("worktree", "add", "-b", "linked", str(linked), repo=work, environment=None)
    _ = (work / "w.txt").write_text("w\n", encoding="utf-8")
    _ = (linked / "l.txt").write_text("l\n", encoding="utf-8")
    for repo, argv, extra in (
        (work, ("commit", "-m", "x"), {}),
        (scratch, ("-C", str(work), "commit", "-m", "x"), {}),
        (scratch, ("--git-dir", str(work / ".git"), "commit", "-m", "x"), {}),
        (
            scratch,
            ("--git-dir", str(work / ".git"), "--work-tree", str(work), "commit", "-m", "x"),
            {},
        ),
        (scratch, ("commit", "-m", "x"), {"GIT_DIR": str(work / ".git")}),
        (linked, ("commit", "-m", "x"), {}),
        (scratch, ("-C", str(linked), "commit", "-m", "x"), {}),
    ):
        _assert_git_write_is_refused(
            argv=argv,
            repo=repo,
            marker=marker,
            environment={**environment, **extra},
            guard=None,
        )


def _assert_scratch_push_to_temporary_bare_repository_is_allowed(
    *, scratch: Path, marker: Path, environment: dict[str, str]
) -> None:
    """A scratch repository may push to a temporary bare repository by path."""
    remote = scratch.parent / "remote.git"
    pushed = _git(
        "push",
        str(remote),
        "HEAD:refs/heads/scratch",
        repo=scratch,
        environment=environment,
    )
    assert pushed.returncode == 0, pushed.stderr
    arrived = _git("rev-parse", "refs/heads/scratch", repo=remote, environment=None)
    assert arrived.returncode == 0, arrived.stderr
    assert marker.read_text(encoding="utf-8").splitlines() == ["pre-push"]
    _ = marker.unlink()
    named = _git(
        "push",
        "origin",
        "HEAD:refs/heads/scratch-by-name",
        repo=scratch,
        environment=environment,
    )
    assert named.returncode == 0, named.stderr
    named_arrival = _git("rev-parse", "refs/heads/scratch-by-name", repo=remote, environment=None)
    assert named_arrival.returncode == 0, named_arrival.stderr
    assert marker.read_text(encoding="utf-8").splitlines() == ["pre-push"]


def _assert_protected_and_unsafe_pushes_are_refused(
    *, tmp_path: Path, work: Path, scratch: Path, marker: Path, environment: dict[str, str]
) -> None:
    """Only scratch-to-temporary-bare pushes can reach Git."""
    temporary_remote = scratch.parent / "remote.git"
    linked = tmp_path / "linked-push-worktree"
    _ = _git("worktree", "add", "-b", "linked-push", str(linked), repo=work, environment=None)
    for repo, argv, extra in (
        (work, ("push", str(temporary_remote), "HEAD:refs/heads/protected"), {}),
        (scratch, ("-C", str(work), "push", str(temporary_remote), "HEAD:refs/heads/by-c"), {}),
        (
            scratch,
            (
                "--git-dir",
                str(work / ".git"),
                "push",
                str(temporary_remote),
                "HEAD:refs/heads/by-dir",
            ),
            {},
        ),
        (linked, ("push", str(temporary_remote), "HEAD:refs/heads/linked"), {}),
        (scratch, ("push", "https://example.invalid/proof.git"), {}),
        (scratch, ("push", "ssh://example.invalid/proof.git"), {}),
        (scratch, ("push", "git://example.invalid/proof.git"), {}),
        (scratch, ("push", "example.invalid:proof.git"), {}),
    ):
        _assert_git_write_is_refused(
            argv=argv,
            repo=repo,
            marker=marker,
            environment={**environment, **extra},
            guard=None,
        )
    temporary_root = tmp_path / "temporary-root"
    temporary_root.mkdir()
    outside = tmp_path / "outside.git"
    _ = _git("init", "--bare", str(outside), repo=tmp_path, environment=None)
    _assert_git_write_is_refused(
        argv=("push", str(outside), "HEAD:refs/heads/outside"),
        repo=scratch,
        marker=marker,
        environment={**environment, "TMPDIR": str(temporary_root)},
        guard=None,
    )
    _assert_git_write_is_refused(
        argv=("push", str(work / ".git"), "HEAD:refs/heads/shared"),
        repo=scratch,
        marker=marker,
        environment=environment,
        guard=None,
    )
    for option in ("--receive-pack=/bin/true", "--exec=/bin/true"):
        _assert_git_write_is_refused(
            argv=("push", option, str(temporary_remote), "HEAD:refs/heads/option"),
            repo=scratch,
            marker=marker,
            environment=environment,
            guard=None,
        )


def _assert_proof_capture_configuration(*, environment: Mapping[str, str]) -> None:
    """The protected adapter selects its private hook and launcher boundaries."""
    assert environment["GIT_CONFIG_COUNT"] == "1"
    assert environment["GIT_CONFIG_KEY_0"] == "core.hooksPath"
    assert environment["GIT_CONFIG_VALUE_0"] == _DISPATCHER_PROOF_CAPTURE_HOOKS
    assert environment["LIVESPEC_PROOF_CAPTURE_GIT_READ_ONLY"] == "1"
    assert environment[_PROTECTED_CHECKOUT_ENV_VAR] == "/workspace"


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
    *, repo: Path, marker: Path, environment: dict[str, str], guard: Path
) -> None:
    """Commit and push both stop before the repository's corresponding hook."""
    _ = (repo / "proof.txt").write_text("proof\n", encoding="utf-8")
    _ = _git("add", "proof.txt", repo=repo, environment=environment)
    _assert_git_write_is_refused(
        argv=(
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "-m",
            "proof capture must stay read-only",
        ),
        repo=repo,
        marker=marker,
        environment=environment,
        guard=guard,
    )
    _assert_git_write_is_refused(
        argv=(
            "-c",
            "core.hooksPath=/dev/null",
            "push",
            "origin",
            "HEAD:refs/heads/proof-capture",
        ),
        repo=repo,
        marker=marker,
        environment=environment,
        guard=guard,
    )


def _assert_git_write_is_refused(
    *,
    argv: tuple[str, ...],
    repo: Path,
    marker: Path,
    environment: dict[str, str],
    guard: Path | None,
) -> None:
    """One protected Git write stops before either repository hook can start."""
    started = time.monotonic()
    refused = _git(*argv, repo=repo, environment=environment, guard=guard)
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


def _install_proof_capture_launcher(*, tmp_path: Path) -> Path:
    """Materialize the stage guard and Git boundary outside the scratch clone."""
    dispatcher_root = tmp_path / ".livespec"
    shutil.copytree(
        _SOURCE_PROOF_CAPTURE_BIN,
        dispatcher_root / "proof-capture-bin",
    )
    shutil.copytree(
        _SOURCE_PROOF_CAPTURE_HOOKS,
        dispatcher_root / "proof-capture-hooks",
    )
    guard = tmp_path / "credential-use-guard.sh"
    _ = guard.write_text(guard_script_text(), encoding="utf-8")
    _ = guard.chmod(0o755)
    return guard


def _git(
    *argv: str, repo: Path, environment: Mapping[str, str] | None, guard: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run Git and make every test command's result available to its assertion."""
    return subprocess.run(
        (["/bin/sh", str(guard), "--", "git", *argv] if guard is not None else ["git", *argv]),
        cwd=repo,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )
