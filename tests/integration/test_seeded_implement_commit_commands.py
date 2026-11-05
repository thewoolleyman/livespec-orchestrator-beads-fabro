"""Seed-preservation coverage for the Red and Green command commits."""

from __future__ import annotations

import subprocess
from pathlib import Path

_ROOT = Path(__file__).parents[2]
_RED = _ROOT / "dev-tooling" / "commit-red.sh"
_GREEN = _ROOT / "dev-tooling" / "commit-green.sh"


def _run(*, repo: Path, argv: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=repo, check=check, capture_output=True, text=True)


def _git(*, repo: Path, argv: list[str]) -> str:
    return _run(repo=repo, argv=["git", *argv]).stdout.strip()


def _repository(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repository"
    repo.mkdir()
    _run(repo=repo, argv=["git", "init", "--quiet"])
    _run(repo=repo, argv=["git", "config", "user.name", "Test Author"])
    _run(repo=repo, argv=["git", "config", "user.email", "author@example.invalid"])
    _ = (repo / "implementation.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo=repo, argv=["add", "implementation.py"])
    _git(repo=repo, argv=["commit", "--quiet", "-m", "chore: baseline"])
    return repo


def _checkpoint(*, repo: Path, name: str, run_id: str) -> None:
    _git(
        repo=repo,
        argv=[
            "commit",
            "--all",
            "--allow-empty",
            "--quiet",
            "-m",
            f"fabro({run_id}): {name}",
            "-m",
            f"Fabro-Run: {run_id}",
        ],
    )


def _handoff(*, repo: Path, text: str) -> None:
    path = repo / _git(repo=repo, argv=["rev-parse", "--git-path", "livespec-implement-handoff.md"])
    _ = path.write_text(text, encoding="utf-8")


def test_commit_red_folds_only_the_current_run_checkpoints_of_a_seed(tmp_path: Path) -> None:
    """Seeded product checkpoints remain committed instead of looking like Red writes."""
    repo = _repository(tmp_path=tmp_path)
    _ = (repo / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nsource_trees = ["src/pkg"]\n', encoding="utf-8"
    )
    (repo / "src" / "pkg").mkdir(parents=True)
    _ = (repo / "src" / "pkg" / "seed.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(repo=repo, argv=["add", "--all"])
    _checkpoint(repo=repo, name="preserved", run_id="earlier-run")
    seed = _git(repo=repo, argv=["rev-parse", "HEAD"])
    test_file = repo / "tests" / "test_feature.py"
    test_file.parent.mkdir()
    _ = test_file.write_text("def test_feature() -> None:\n    assert False\n", encoding="utf-8")
    _git(repo=repo, argv=["add", "tests/test_feature.py"])
    _checkpoint(repo=repo, name="red", run_id="current-run")
    _handoff(repo=repo, text="## red\nRed test file: tests/test_feature.py\n")

    completed = _run(repo=repo, argv=["bash", str(_RED)], check=False)

    assert completed.returncode == 0, completed.stderr
    assert _git(repo=repo, argv=["rev-parse", "HEAD^"]) == seed
    assert _git(repo=repo, argv=["show", "--format=", "--name-only", "HEAD"]) == (
        "tests/test_feature.py"
    )


def test_commit_green_folds_a_seeded_open_red_and_its_checkpoints_into_one_pair(
    tmp_path: Path,
) -> None:
    """An open Red below a seed is completed, rather than receiving another Red commit."""
    repo = _repository(tmp_path=tmp_path)
    base = _git(repo=repo, argv=["rev-parse", "HEAD"])
    test_file = repo / "tests" / "test_feature.py"
    test_file.parent.mkdir()
    _ = test_file.write_text("def test_feature() -> None:\n    assert False\n", encoding="utf-8")
    _git(repo=repo, argv=["add", "tests/test_feature.py"])
    _git(
        repo=repo,
        argv=[
            "commit",
            "--quiet",
            "--no-verify",
            "-m",
            "feat: red",
            "-m",
            "TDD-Red-Test-File-Checksum: red",
        ],
    )
    _ = (repo / "implementation.py").write_text("VALUE = 2\n", encoding="utf-8")
    _checkpoint(repo=repo, name="preserved", run_id="earlier-run")
    _checkpoint(repo=repo, name="green", run_id="current-run")
    _handoff(repo=repo, text="## seeded-open-red\n")
    hook = repo / ".git" / "hooks" / "commit-msg"
    _ = hook.write_text(
        "#!/bin/sh\ngit interpret-trailers --in-place --trailer "
        "'TDD-Green-Verified-At: green' \"$1\"\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)

    completed = _run(repo=repo, argv=["bash", str(_GREEN)], check=False)

    assert completed.returncode == 0, completed.stderr
    assert _git(repo=repo, argv=["rev-parse", "HEAD^"]) == base
    assert _git(repo=repo, argv=["show", "--format=", "--name-only", "HEAD"]) == (
        "implementation.py\ntests/test_feature.py"
    )
    message = _git(repo=repo, argv=["log", "-1", "--format=%B"])
    assert "TDD-Red-Test-File-Checksum: red" in message
    assert "TDD-Green-Verified-At: green" in message


def test_commit_green_preserves_replay_evidence_when_a_satisfied_seed_has_checkpoints(
    tmp_path: Path,
) -> None:
    """Seeded work already paired with Green is published on that evidenced commit."""
    repo = _repository(tmp_path=tmp_path)
    base = _git(repo=repo, argv=["rev-parse", "HEAD"])
    _ = (repo / "implementation.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(repo=repo, argv=["add", "implementation.py"])
    _git(
        repo=repo,
        argv=[
            "commit",
            "--quiet",
            "--no-verify",
            "-m",
            "feat: implemented seed",
            "-m",
            "TDD-Red-Test-File-Checksum: red",
            "-m",
            "TDD-Green-Verified-At: green",
        ],
    )
    _ = (repo / "implementation.py").write_text("VALUE = 3\n", encoding="utf-8")
    _checkpoint(repo=repo, name="preserved", run_id="earlier-run")
    _checkpoint(repo=repo, name="green", run_id="current-run")
    _handoff(repo=repo, text="## seeded-already-satisfied\n")

    completed = _run(repo=repo, argv=["bash", str(_GREEN)], check=False)

    assert completed.returncode == 0, completed.stderr
    assert _git(repo=repo, argv=["rev-parse", "HEAD^"]) == base
    assert (repo / "implementation.py").read_text(encoding="utf-8") == "VALUE = 3\n"
    message = _git(repo=repo, argv=["log", "-1", "--format=%B"])
    assert "TDD-Red-Test-File-Checksum: red" in message
    assert "TDD-Green-Verified-At: green" in message
