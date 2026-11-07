"""The recovery seed stays in a dispatched sandbox's committed lineage."""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path
from typing import Any

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_seeded_lineage"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_seeded_lineage.py"
)


def _module() -> Any:
    """Import only after proving the absent module is the failed behaviour."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


def _git(repo: Path, *args: str) -> str:
    """Run one fixture git command and return its stripped stdout."""
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _commit(*, repo: Path, path: Path, content: str, message: str) -> str:
    """Write one fixture revision through git's normal commit path."""
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", path.name)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _fixture(*, tmp_path: Path) -> tuple[Path, str, str]:
    """A base, seed, and unrelated branch tip for ancestry discrimination."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=master")
    _git(repo, "config", "user.name", "Fixture")
    _git(repo, "config", "user.email", "fixture@example.test")
    tracked = repo / "tracked.txt"
    base = _commit(repo=repo, path=tracked, content="before\nremoved\n", message="base")
    _git(repo, "checkout", "-b", "seed")
    seed = _commit(repo=repo, path=tracked, content="before\nadded\n", message="seed")
    _git(repo, "checkout", "-b", "other", base)
    other = _commit(repo=repo, path=tracked, content="before\nremoved\nother\n", message="other")
    return repo, seed, other


def test_a_seeded_prepare_places_the_seed_before_the_first_agent_node(tmp_path: Path) -> None:
    """The guard refuses an initial head that does not descend from the seed."""
    module = _module()
    repo, seed, other = _fixture(tmp_path=tmp_path)

    result = module.check_prepare(repo=repo, seed=seed, head=other)

    assert result.ok is False
    assert seed in result.cause
    assert other in result.cause


def test_a_settle_accepts_seed_ancestry_and_carried_seed_content(tmp_path: Path) -> None:
    """Lineage is primary, while a complete carried patch advances the reference."""
    module = _module()
    repo, seed, other = _fixture(tmp_path=tmp_path)
    carried = _commit(
        repo=repo,
        path=repo / "tracked.txt",
        content="before\nadded\nother\n",
        message="carry seed",
    )

    ancestral = module.check_settle(repo=repo, expected=seed, settled=seed)
    carried_result = module.check_settle(repo=repo, expected=seed, settled=carried)
    dropped = module.check_settle(repo=repo, expected=seed, settled=other)

    assert ancestral.ok is True
    assert ancestral.next_expected == seed
    assert carried_result.ok is True
    assert carried_result.carried is True
    assert carried_result.next_expected == carried
    assert dropped.ok is False
    assert seed in dropped.cause
    assert other in dropped.cause
    assert "first seed change" in dropped.cause


def test_a_later_settle_accepts_the_carried_commit_and_publish_refuses_a_drop(
    tmp_path: Path,
) -> None:
    """A carried commit becomes the reference and publication checks it before rebasing."""
    module = _module()
    repo, seed, other = _fixture(tmp_path=tmp_path)
    carried = _commit(
        repo=repo,
        path=repo / "tracked.txt",
        content="before\nadded\nother\n",
        message="carry seed",
    )
    successor = _commit(
        repo=repo,
        path=repo / "tracked.txt",
        content="before\nadded\nother\nnext\n",
        message="successor",
    )

    first = module.check_settle(repo=repo, expected=seed, settled=carried)
    later = module.check_settle(repo=repo, expected=first.next_expected, settled=successor)
    publish = module.check_publish(repo=repo, expected=first.next_expected, tip=other)

    assert later.ok is True
    assert publish.ok is False
    assert first.next_expected in publish.cause
    assert other in publish.cause
