"""Witnesses for the delegated pre-commit aggregate configuration."""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

from livespec_dev_tooling.config import load_delegated_pre_commit, load_gate_check_suite

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PRE_COMMIT_SCRIPT = _REPO_ROOT / "dev-tooling" / "just-check-pre-commit.sh"
_GATED_TREE_SCRIPT = _REPO_ROOT / "dev-tooling" / "check-pre-commit-gated-tree.sh"


def test_repository_config_opts_in_to_the_repaired_pre_commit_delegate() -> None:
    """The repository selects the released delegate and its staged-tree bootstrap."""
    assert load_delegated_pre_commit(repo_root=_REPO_ROOT) is True
    assert load_gate_check_suite(repo_root=_REPO_ROOT) == (
        "install-worktree-pack",
        "install-commit-refuse-hooks",
        "check-pre-push",
    )

    config = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    tag_match = re.search(
        r'^livespec-dev-tooling = \{ git = "[^"]+", tag = "(v[^"]+)" \}$',
        config,
        flags=re.MULTILINE,
    )
    assert tag_match is not None
    tag = tag_match.group(1)
    assert tuple(int(part) for part in tag.removeprefix("v").split(".")) >= (1, 153, 0)

    lock = (_REPO_ROOT / "uv.lock").read_text(encoding="utf-8")
    assert lock.count(f"tag={tag}") == 2


def _run_pre_commit(
    *, tmp_path: Path, delegate_status: int, gate_context: bool = False
) -> tuple[int, list[str]]:
    """Run the wrapper with logged stand-ins for the delegate and local aggregate."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    tools = {
        "git": """#!/usr/bin/env bash
case "$*" in
  *"config --get --bool livespec.sandboxExempt"*) printf 'false\\n' ;;
  *"diff --cached --name-only --diff-filter=AM"*) printf 'README.md\\n' ;;
esac
""",
        "uv": """#!/usr/bin/env bash
printf 'uv %s\\n' "$*" >> "$FAKE_LOG"
case "$*" in
  *"pre_commit_delegate run"*) exit "$FAKE_DELEGATE_STATUS" ;;
esac
exit 99
""",
        "just": """#!/usr/bin/env bash
printf 'just %s\\n' "$*" >> "$FAKE_LOG"
""",
    }
    for name, body in tools.items():
        tool = bin_dir / name
        tool.write_text(body, encoding="utf-8")
        tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "calls.log"
    log.touch()
    # The gate Job itself exports LIVESPEC_GATE_CONTEXT, so an inherited value
    # would put every case in gate context; only `gate_context` may set it.
    environment = {
        **{key: value for key, value in os.environ.items() if key != "LIVESPEC_GATE_CONTEXT"},
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "FAKE_DELEGATE_STATUS": str(delegate_status),
        "FAKE_LOG": str(log),
    }
    if gate_context:
        environment["LIVESPEC_GATE_CONTEXT"] = "1"
    done = subprocess.run(
        ["bash", str(_PRE_COMMIT_SCRIPT)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    return done.returncode, log.read_text(encoding="utf-8").splitlines()


def test_pre_commit_delegates_before_locally_falling_back(*, tmp_path: Path) -> None:
    """Only the delegate's local-fallback result invokes the local aggregate."""
    assert _PRE_COMMIT_SCRIPT.is_file()

    passed_rc, passed_calls = _run_pre_commit(tmp_path=tmp_path / "passed", delegate_status=0)
    failed_rc, failed_calls = _run_pre_commit(tmp_path=tmp_path / "failed", delegate_status=1)
    local_rc, local_calls = _run_pre_commit(tmp_path=tmp_path / "local", delegate_status=75)
    gated_rc, gated_calls = _run_pre_commit(
        tmp_path=tmp_path / "gated", delegate_status=99, gate_context=True
    )

    assert passed_rc == 0
    assert failed_rc == 1
    assert local_rc == 0
    assert gated_rc == 0
    assert any("pre_commit_delegate run" in call for call in passed_calls)
    assert any("pre_commit_delegate run" in call for call in failed_calls)
    assert any("pre_commit_delegate run" in call for call in local_calls)
    assert not any("pre_commit_delegate run" in call for call in gated_calls)
    assert not any(call.startswith("just") for call in passed_calls)
    assert not any(call.startswith("just") for call in failed_calls)
    assert local_calls[-1] == "just check-pre-commit-doc-only"
    assert gated_calls == ["just check-pre-commit-doc-only"]


def _git(*, repo: Path, arguments: list[str]) -> str:
    """Run git in a throwaway repository and return its standard output."""
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        capture_output=True,
        check=True,
        text=True,
    )
    return completed.stdout.strip()


def _gated_repository(*, tmp_path: Path) -> tuple[Path, str, str]:
    """Create the detached staged-tree commit consumed by the gate recipe."""
    repo = tmp_path / "repository"
    repo.mkdir()
    _git(repo=repo, arguments=["init", "--quiet"])
    _git(repo=repo, arguments=["config", "user.name", "Test User"])
    _git(repo=repo, arguments=["config", "user.email", "test@example.invalid"])
    (repo / "subject.txt").write_text("parent\n", encoding="utf-8")
    _git(repo=repo, arguments=["add", "subject.txt"])
    _git(repo=repo, arguments=["commit", "--quiet", "-m", "parent"])
    parent = _git(repo=repo, arguments=["rev-parse", "HEAD"])
    (repo / "subject.txt").write_text("staged\n", encoding="utf-8")
    _git(repo=repo, arguments=["add", "subject.txt"])
    gated_tree = _git(repo=repo, arguments=["write-tree"])
    gated_commit = _git(
        repo=repo,
        arguments=["commit-tree", gated_tree, "-p", parent, "-m", "staged tree"],
    )
    _git(repo=repo, arguments=["reset", "--hard", "--quiet", gated_commit])
    return repo, parent, gated_tree


def test_gated_tree_recipe_rewinds_one_parent_without_changing_the_index(*, tmp_path: Path) -> None:
    """The gate recipe preserves the staged tree and prevents recursive delegation."""
    assert _GATED_TREE_SCRIPT.is_file()
    repo, parent, gated_tree = _gated_repository(tmp_path=tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    just = bin_dir / "just"
    just.write_text(
        """#!/usr/bin/env bash
test \"$LIVESPEC_GATE_CONTEXT\" = 1
printf '%s %s\\n' \"$*\" \"$(git write-tree)\" > \"$GATE_LOG\"
""",
        encoding="utf-8",
    )
    just.chmod(just.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "gate.log"
    completed = subprocess.run(
        ["bash", str(_GATED_TREE_SCRIPT)],
        cwd=repo,
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "GATE_LOG": str(log),
        },
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert _git(repo=repo, arguments=["rev-parse", "HEAD"]) == parent
    assert _git(repo=repo, arguments=["write-tree"]) == gated_tree
    assert log.read_text(encoding="utf-8") == f"check-pre-commit {gated_tree}\n"
