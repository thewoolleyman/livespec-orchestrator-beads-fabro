"""Real-repository coverage for the implement stage's command commits.

The workflow graph invokes these scripts in a sandbox clone.  These tests use
ordinary temporary repositories instead, so checkpoint folding, index shaping,
commit hooks, and the append-only handoff are all observed at the git boundary.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_ROOT = Path(__file__).parents[2]
_RED = _ROOT / "dev-tooling" / "commit-red.sh"
_GREEN = _ROOT / "dev-tooling" / "commit-green.sh"


def _run(*, repo: Path, argv: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run one git or command-script invocation in the temporary repository."""
    return subprocess.run(argv, cwd=repo, check=check, capture_output=True, text=True)


def _git(*, repo: Path, argv: list[str]) -> str:
    """Run git successfully and return its stripped standard output."""
    return _run(repo=repo, argv=["git", *argv]).stdout.strip()


def _initialize_repository(*, tmp_path: Path) -> Path:
    """Make a real repository with an ordinary baseline commit and identity."""
    repo = tmp_path / "repository"
    repo.mkdir()
    _run(repo=repo, argv=["git", "init", "--quiet"])
    _run(repo=repo, argv=["git", "config", "user.name", "Test Author"])
    _run(repo=repo, argv=["git", "config", "user.email", "author@example.invalid"])
    _ = (repo / "implementation.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo=repo, argv=["add", "implementation.py"])
    _git(repo=repo, argv=["commit", "--quiet", "-m", "chore: baseline"])
    return repo


def _checkpoint(*, repo: Path, name: str) -> None:
    """Commit the current tree in the shape the engine leaves between nodes."""
    _git(
        repo=repo,
        argv=[
            "commit",
            "--all",
            "--quiet",
            "-m",
            f"fabro(run): {name}",
            "-m",
            "Fabro-Run: run",
        ],
    )


def _handoff(*, repo: Path, text: str) -> Path:
    """Write the local, never-committed handoff file the command consumes."""
    path = repo / _git(repo=repo, argv=["rev-parse", "--git-path", "livespec-implement-handoff.md"])
    _ = path.write_text(text, encoding="utf-8")
    return path


def test_commit_red_folds_checkpoints_stages_only_the_named_red_test_and_runs_hooks(
    tmp_path: Path,
) -> None:
    """The Red command lands directly on the base with only the named test staged."""
    assert _RED.is_file()
    repo = _initialize_repository(tmp_path=tmp_path)
    base = _git(repo=repo, argv=["rev-parse", "HEAD"])
    test_file = repo / "tests" / "test_feature.py"
    test_file.parent.mkdir()
    _ = test_file.write_text("def test_feature() -> None:\n    assert False\n", encoding="utf-8")
    _ = (repo / "implementation.py").write_text("VALUE = 2\n", encoding="utf-8")
    _checkpoint(repo=repo, name="red")
    handoff = _handoff(repo=repo, text="## red\nRed test file: tests/test_feature.py\n")
    hook = repo / ".git" / "hooks" / "pre-commit"
    _ = hook.write_text("#!/bin/sh\nprintf 'hook ran\\n' >> hook.log\n", encoding="utf-8")
    hook.chmod(0o755)

    completed = _run(repo=repo, argv=["bash", str(_RED)], check=False)

    assert completed.returncode == 0, completed.stderr
    assert _git(repo=repo, argv=["rev-parse", "HEAD^"]) == base
    assert (
        _git(repo=repo, argv=["show", "--format=", "--name-only", "HEAD"])
        == "tests/test_feature.py"
    )
    assert (repo / "hook.log").read_text(encoding="utf-8") == "hook ran\n"
    assert "## commit_red" in handoff.read_text(encoding="utf-8")
    assert "Exit status: 0" in handoff.read_text(encoding="utf-8")


def test_commit_green_folds_checkpoints_and_amends_the_unpaired_red_with_hooks(
    tmp_path: Path,
) -> None:
    """The Green command folds the engine checkpoint back onto its Red commit."""
    assert _GREEN.is_file()
    repo = _initialize_repository(tmp_path=tmp_path)
    base = _git(repo=repo, argv=["rev-parse", "HEAD"])
    test_file = repo / "tests" / "test_feature.py"
    test_file.parent.mkdir()
    _ = test_file.write_text("def test_feature() -> None:\n    assert True\n", encoding="utf-8")
    _ = (repo / "implementation.py").write_text("VALUE = 2\n", encoding="utf-8")
    _checkpoint(repo=repo, name="red")
    _handoff(repo=repo, text="## red\nRed test file: tests/test_feature.py\n")
    hook = repo / ".git" / "hooks" / "commit-msg"
    _ = hook.write_text(
        "#!/bin/sh\ngit interpret-trailers --in-place --trailer "
        "'TDD-Red-Test-File-Checksum: red' \"$1\"\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    assert _run(repo=repo, argv=["bash", str(_RED)], check=False).returncode == 0
    _checkpoint(repo=repo, name="green")
    _ = hook.write_text(
        "#!/bin/sh\ngit interpret-trailers --in-place --trailer "
        "'TDD-Green-Verified-At: green' \"$1\"\n",
        encoding="utf-8",
    )

    completed = _run(repo=repo, argv=["bash", str(_GREEN)], check=False)

    assert completed.returncode == 0, completed.stderr
    assert _git(repo=repo, argv=["rev-parse", "HEAD^"]) == base
    assert _git(repo=repo, argv=["show", "--format=", "--name-only", "HEAD"]) == (
        "implementation.py\ntests/test_feature.py"
    )
    message = _git(repo=repo, argv=["log", "-1", "--format=%B"])
    assert "TDD-Red-Test-File-Checksum: red" in message
    assert "TDD-Green-Verified-At: green" in message
