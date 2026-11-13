"""A product blob the probe cannot read is unobserved, never an empty file.

Beside `test_dispatcher_cycle_probe_edges`, this file pins the distinction the
per-path read must keep: a path the pair ADDED is absent at the parent and a path
it DELETED is absent at the commit, both ordinary measurable changes, while a
path the tree names but whose object cannot be read is missing source evidence.
Reporting the second as an empty file would fabricate a numeric size.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_completed_cycles import (
    UNOBSERVED_SOURCE_TREE,
    CompletedCycleSeries,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_probe import (
    gather_completed_cycle_series,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.types import WorkItem

_DISPATCH_ID = "5fe8e3dfbfd54faa979e85364d8e9863"
_SOURCE_TREE = "src/pkg"
_PYPROJECT = (
    "[tool.livespec_dev_tooling]\n"
    f'mirror_pairings = [{{source_tree = "{_SOURCE_TREE}", test_tree = "tests/pkg"}}]\n'
)


@dataclass(kw_only=True)
class _ForgeRunner:
    """A CommandRunner that answers the `gh` probe and nothing else."""

    stdout: str = ""
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        assert timeout_seconds > 0
        assert isinstance(cwd, Path)
        assert env is None
        self.calls.append(argv)
        return CommandResult(exit_code=0, stdout=self.stdout, stderr="")


def _item() -> WorkItem:
    return WorkItem(  # pyright: ignore[reportArgumentType]
        id="bd-ib-z2y4ca",
        type="feature",
        status="active",
        title="Feed per-cycle progress signals into the bounce",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a5",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-09T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        acceptance_criteria="- One assertion.\n",
    )


def _git(*, repo: Path, argv: list[str]) -> str:
    return subprocess.run(
        ["git", *argv], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "clone"
    repo.mkdir()
    _git(repo=repo, argv=["init", "--initial-branch", "work"])
    _git(repo=repo, argv=["config", "user.email", "fixture@example.com"])
    _git(repo=repo, argv=["config", "user.name", "Fixture"])
    (repo / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    (repo / _SOURCE_TREE).mkdir(parents=True)
    (repo / _SOURCE_TREE / "thing.py").write_text("value = 1\n", encoding="utf-8")
    _git(repo=repo, argv=["add", "-A"])
    _git(repo=repo, argv=["commit", "-m", "chore: seed"])
    return repo


def _pair_commit(*, repo: Path, files: dict[str, str]) -> str:
    for name, text in files.items():
        (repo / _SOURCE_TREE / name).write_text(text, encoding="utf-8")
    _git(repo=repo, argv=["add", "-A"])
    _git(
        repo=repo,
        argv=[
            "commit",
            "-m",
            "feat(pkg): one assertion\n\n"
            "TDD-Red-Test-File-Checksum: sha256:one\n"
            "TDD-Red-Captured-At: 2026-10-01T10:00:00Z\n"
            f"Factory-Run-Id: {_DISPATCH_ID}\n"
            "TDD-Green-Verified-At: 2026-10-01T10:04:10Z",
        ],
    )
    return _git(repo=repo, argv=["rev-parse", "HEAD"])


def _payload(*, repo: Path, sha: str) -> str:
    return json.dumps(
        {
            "commits": [
                {
                    "oid": sha,
                    "messageHeadline": _git(repo=repo, argv=["log", "-1", "--format=%s", sha]),
                    "messageBody": _git(repo=repo, argv=["log", "-1", "--format=%b", sha]),
                }
            ]
        }
    )


def _series(*, repo: Path, sha: str) -> CompletedCycleSeries:
    return gather_completed_cycle_series(
        repo=repo,
        item=_item(),
        pr_number=4242,
        dispatch_id=_DISPATCH_ID,
        runner=_ForgeRunner(stdout=_payload(repo=repo, sha=sha)),
    )


def test_a_path_the_pair_added_measures_its_lines_against_an_absent_parent(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    sha = _pair_commit(repo=repo, files={"fresh.py": "a = 1\nb = 2\n"})

    series = _series(repo=repo, sha=sha)

    assert series.completed_count == 1
    assert series.cycles[0].product_lloc_changed == 2


def test_a_product_blob_the_tree_names_but_the_clone_cannot_read_is_unobserved(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    sha = _pair_commit(repo=repo, files={"thing.py": "value = 2\nother = 3\n"})
    blob = _git(repo=repo, argv=["rev-parse", f"{sha}:{_SOURCE_TREE}/thing.py"])
    loose = repo / ".git" / "objects" / blob[:2] / blob[2:]
    loose.unlink()

    series = _series(repo=repo, sha=sha)

    assert series.completed_count == 1
    assert series.cycles[0].product_lloc_changed is None
    assert series.cycles[0].product_lloc_unobserved_reason == UNOBSERVED_SOURCE_TREE
