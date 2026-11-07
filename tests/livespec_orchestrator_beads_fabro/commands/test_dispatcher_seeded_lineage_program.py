"""Command-boundary coverage for the seeded-lineage guard."""

from __future__ import annotations

import importlib
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandResult

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_seeded_lineage"


class _FailingRunner:
    """A command-runner seam that makes a Git read fail unexpectedly."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        """Return the injected failure without invoking a process."""
        _ = argv, cwd, timeout_seconds, env, stdin
        return CommandResult(exit_code=2, stdout="", stderr="unexpected Git failure")


class _BlankLineRunner:
    """A seam response that exercises Git's blank-line normalization."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        """Model a non-ancestor followed by otherwise blank Git output."""
        _ = cwd, timeout_seconds, env, stdin
        if argv[1:3] == ["merge-base", "--is-ancestor"]:
            return CommandResult(exit_code=1, stdout="", stderr="")
        return CommandResult(exit_code=0, stdout="\n", stderr="")


def _module() -> Any:
    """Import the command module under test."""
    return importlib.import_module(_MODULE_NAME)


def _git(*, repo: Path, args: str) -> str:
    """Run one git fixture command."""
    completed = subprocess.run(
        ["git", *args.split()], cwd=repo, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def _commit(*, repo: Path, content: str, message: str) -> str:
    """Commit a single tracked fixture file."""
    tracked = repo / "tracked.txt"
    _ = tracked.write_text(content, encoding="utf-8")
    _ = _git(repo=repo, args="add tracked.txt")
    _ = _git(repo=repo, args=f"commit -m {message}")
    return _git(repo=repo, args="rev-parse HEAD")


def _repo(*, tmp_path: Path) -> tuple[Path, str, str]:
    """Build a seed and an unrelated head for command-boundary checks."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = _git(repo=repo, args="init --initial-branch=master")
    _ = _git(repo=repo, args="config user.name Fixture")
    _ = _git(repo=repo, args="config user.email fixture@example.test")
    base = _commit(repo=repo, content="before\nremoved\n", message="base")
    _ = _git(repo=repo, args="checkout -b seed")
    seed = _commit(repo=repo, content="before\nadded\n", message="seed")
    _ = _git(repo=repo, args=f"checkout -b other {base}")
    other = _commit(repo=repo, content="before\nremoved\nother\n", message="other")
    return repo, seed, other


def test_main_skips_plain_runs_and_records_a_prepared_seed(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Only a seeded run creates the private expected-reference state."""
    module = _module()
    repo, seed, _ = _repo(tmp_path=tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.delenv("LIVESPEC_SEEDED_LINEAGE_SEED", raising=False)

    assert module.main(argv=["prepare"]) == 0

    monkeypatch.setenv("LIVESPEC_SEEDED_LINEAGE_SEED", seed)
    _ = _git(repo=repo, args="checkout seed")
    assert module.main(argv=["prepare"]) == 0
    assert (repo / ".git" / "livespec-seeded-lineage-reference").read_text(
        encoding="utf-8"
    ) == f"{seed}\n"


def test_main_refuses_a_bad_prepare_and_advances_for_carried_content(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A failed placement stops before implement; carried content advances state."""
    module = _module()
    repo, seed, other = _repo(tmp_path=tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("LIVESPEC_SEEDED_LINEAGE_SEED", seed)

    assert module.main(argv=["prepare"]) == 1
    assert seed in capsys.readouterr().err

    _ = _git(repo=repo, args="checkout seed")
    assert module.main(argv=["prepare"]) == 0
    _ = _git(repo=repo, args=f"checkout {other}")
    carried = _commit(repo=repo, content="before\nadded\nother\n", message="carried")

    assert module.main(argv=["settle"]) == 0
    assert "CONTENT_CARRIED" in capsys.readouterr().err
    assert (repo / ".git" / "livespec-seeded-lineage-reference").read_text(
        encoding="utf-8"
    ) == f"{carried}\n"


def test_main_accepts_the_seeded_publish_head(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Publication reads the prepared seed reference and accepts its descendant."""
    module = _module()
    repo, seed, _ = _repo(tmp_path=tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("LIVESPEC_SEEDED_LINEAGE_SEED", seed)
    _ = _git(repo=repo, args="checkout seed")

    assert module.main(argv=["prepare"]) == 0
    assert module.main(argv=["settle"]) == 0
    assert module.main(argv=["publish"]) == 0


def test_a_seed_added_file_must_be_present_on_carried_content(tmp_path: Path) -> None:
    """A whole carried patch includes files added by the preservation seed."""
    module = _module()
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = _git(repo=repo, args="init --initial-branch=master")
    _ = _git(repo=repo, args="config user.name Fixture")
    _ = _git(repo=repo, args="config user.email fixture@example.test")
    base = _commit(repo=repo, content="before\n", message="base")
    _ = _git(repo=repo, args="checkout -b seed")
    added = repo / "added.txt"
    _ = added.write_text("preserved\n", encoding="utf-8")
    _ = _git(repo=repo, args="add added.txt")
    _ = _git(repo=repo, args="commit -m seed")
    seed = _git(repo=repo, args="rev-parse HEAD")
    _ = _git(repo=repo, args=f"checkout -b other {base}")
    other = _commit(repo=repo, content="other\n", message="other")

    result = module.check_settle(repo=repo, expected=seed, settled=other)

    assert result.ok is False
    assert "added.txt: added line 'preserved'" in result.cause


def test_carried_content_cannot_restore_a_line_the_seed_removed(tmp_path: Path) -> None:
    """The fallback rejects a branch that keeps even one removed seed line."""
    module = _module()
    repo, seed, other = _repo(tmp_path=tmp_path)
    _ = _git(repo=repo, args=f"checkout {other}")
    restored = _commit(
        repo=repo,
        content="before\nremoved\nadded\nother\n",
        message="restored-removal",
    )

    result = module.check_settle(repo=repo, expected=seed, settled=restored)

    assert result.ok is False
    assert "removed line 'removed' remains" in result.cause


def test_blank_git_output_does_not_count_as_a_seed_change(tmp_path: Path) -> None:
    """Blank diff output is normalized away before the carried-content decision."""
    module = _module()
    repo, _, _ = _repo(tmp_path=tmp_path)

    result = module.check_settle(
        repo=repo,
        expected="seed",
        settled="settled",
        runner=_BlankLineRunner(),
    )

    assert result.ok is True
    assert result.carried is True


def test_private_git_helpers_raise_for_an_unexpected_failure(tmp_path: Path) -> None:
    """A Git failure other than ancestry's ordinary false result remains a bug."""
    module = _module()
    repo, _, _ = _repo(tmp_path=tmp_path)

    with pytest.raises(RuntimeError, match="unexpected Git failure"):
        _ = module.check_prepare(
            repo=repo,
            seed="seed",
            head="head",
            runner=_FailingRunner(),
        )


def test_only_a_seeded_recovery_projects_the_seed_environment() -> None:
    """Resume placement alone does not opt into preservation-lineage enforcement."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry"
    )
    seeded = module.ResumeCheckout(
        branch="feat/bd-ib-azhnw5",
        head="a" * 40,
        fetch_ref="refs/heads/needs-human/example",
    )

    assert module.seeded_lineage_env_lines(checkout=None) == ""
    assert module.seeded_lineage_env_lines(checkout=seeded) == (
        'LIVESPEC_SEEDED_LINEAGE_SEED = "' + "a" * 40 + '"\n'
    )
