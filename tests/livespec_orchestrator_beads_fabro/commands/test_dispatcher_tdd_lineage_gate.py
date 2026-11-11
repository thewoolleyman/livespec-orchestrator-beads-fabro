"""Publication-time TDD lineage validation (bd-ib-tqnvj7)."""

from __future__ import annotations

import importlib
import stat
import subprocess
from pathlib import Path


def _git(*, repo: Path, argv: list[str]) -> str:
    """Run one fixture git command and return its standard output."""
    completed = subprocess.run(
        ["git", *argv],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def _commit(*, repo: Path, message: str, name: str, text: str) -> str:
    """Commit one fixture change with the supplied evidence message."""
    _ = (repo / name).write_text(text, encoding="utf-8")
    _git(repo=repo, argv=["add", name])
    _git(repo=repo, argv=["commit", "-m", message])
    return _git(repo=repo, argv=["rev-parse", "HEAD"])


def _repository(*, tmp_path: Path) -> tuple[Path, str]:
    """Build a rebased Green commit retaining a Red recorded on another parent."""
    repo = tmp_path / "repository"
    repo.mkdir()
    _git(repo=repo, argv=["init", "-b", "master"])
    _git(repo=repo, argv=["config", "user.name", "Lineage Test"])
    _git(repo=repo, argv=["config", "user.email", "lineage@example.invalid"])
    base = _commit(repo=repo, message="base", name="base.txt", text="base\n")
    _git(repo=repo, argv=["switch", "-c", "work"])
    red = _commit(
        repo=repo,
        message=(
            "feat: original Green\n\n"
            "TDD-Red-Test: tests/test_widget.py\n"
            "TDD-Red-Test-File-Checksum: sha256:unused\n"
            "TDD-Green-Verified-At: 2026-11-11T00:00:00Z\n"
            f"TDD-Green-Parent-Reflog: {base}\n"
        ),
        name="widget.py",
        text="def widget() -> int:\n    return 1\n",
    )
    _git(repo=repo, argv=["switch", "master"])
    _ = _commit(repo=repo, message="base moved", name="moved.txt", text="moved\n")
    _git(repo=repo, argv=["cherry-pick", red])
    return repo, _git(repo=repo, argv=["merge-base", "HEAD", "master"])


def test_a_rebased_green_commit_is_refused_before_publication(tmp_path: Path) -> None:
    """A Green record from another parent cannot publish after a history rewrite."""
    source_path = (
        Path(__file__).parents[3]
        / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
        / "_dispatcher_tdd_lineage_gate.py"
    )
    assert source_path.is_file()
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_lineage_gate"
    )
    program = tmp_path / "livespec-tdd-lineage-gate.py"
    _ = program.write_text(module.tdd_lineage_gate_program_source(), encoding="utf-8")
    program.chmod(program.stat().st_mode | stat.S_IXUSR)
    repo, base = _repository(tmp_path=tmp_path)

    completed = subprocess.run(
        [str(program), base],
        cwd=repo,
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode != 0
    assert _git(repo=repo, argv=["rev-parse", "HEAD"]) in completed.stderr
    assert "parent" in completed.stderr
