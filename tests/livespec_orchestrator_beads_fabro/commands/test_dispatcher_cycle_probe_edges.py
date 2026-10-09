"""Edge arms of the completed-cycle probe.

Beside `test_dispatcher_cycle_probe`, which exercises the probe against a real
repository, this file covers the arms a malformed forge payload and an unreadable
product source reach: a payload whose `commits` key is not a list, an entry that
is not an object or carries no commit identity, a repository declaring no source
trees, and a product file this measurement's counter cannot read.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_completed_cycles import (
    UNOBSERVED_COUNTING,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_probe import (
    gather_completed_cycle_series,
    parse_provenance_commits,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.types import WorkItem

_DISPATCH_ID = "5fe8e3dfbfd54faa979e85364d8e9863"
_SOURCE_TREE = "src/pkg"


@dataclass(kw_only=True)
class _ForgeRunner:
    """A CommandRunner that answers the `gh` probe and nothing else."""

    stdout: str = ""
    exit_code: int = 0
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
        return CommandResult(exit_code=self.exit_code, stdout=self.stdout, stderr="")


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
        ["git", *argv],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repo(*, tmp_path: Path, pyproject: str | None) -> Path:
    repo = tmp_path / "clone"
    repo.mkdir()
    _git(repo=repo, argv=["init", "--initial-branch", "work"])
    _git(repo=repo, argv=["config", "user.email", "fixture@example.com"])
    _git(repo=repo, argv=["config", "user.name", "Fixture"])
    if pyproject is not None:
        (repo / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    (repo / _SOURCE_TREE).mkdir(parents=True)
    (repo / _SOURCE_TREE / "thing.py").write_text("value = 1\n", encoding="utf-8")
    _git(repo=repo, argv=["add", "-A"])
    _git(repo=repo, argv=["commit", "-m", "chore: seed"])
    return repo


def _pair_commit(*, repo: Path, product: str) -> str:
    (repo / _SOURCE_TREE / "thing.py").write_text(product, encoding="utf-8")
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


def test_a_payload_whose_commits_key_is_not_a_list_is_unreadable() -> None:
    assert parse_provenance_commits(stdout=json.dumps({"commits": "nope"})) is None
    assert parse_provenance_commits(stdout=json.dumps(["not", "an", "object"])) is None


def test_entries_without_an_object_shape_or_a_commit_identity_are_skipped() -> None:
    parsed = parse_provenance_commits(
        stdout=json.dumps(
            {
                "commits": [
                    "not an object",
                    {"messageHeadline": "feat: no oid"},
                    {"oid": "", "messageHeadline": "feat: empty oid"},
                    {"oid": "abc123", "messageHeadline": 7},
                    {"oid": "def456", "messageHeadline": "feat: kept"},
                ]
            }
        )
    )

    assert parsed is not None
    assert [commit.sha for commit in parsed] == ["def456"]
    assert parsed[0].message.startswith("feat: kept")


def test_a_repository_declaring_no_source_trees_measures_no_product_lines(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path, pyproject=None)
    sha = _pair_commit(repo=repo, product="value = 2\n")

    series = gather_completed_cycle_series(
        repo=repo,
        item=_item(),
        pr_number=4242,
        dispatch_id=_DISPATCH_ID,
        runner=_ForgeRunner(stdout=_payload(repo=repo, sha=sha)),
    )

    assert series.completed_count == 1
    assert series.cycles[0].product_lloc_changed == 0


def test_a_product_source_the_counter_cannot_read_reports_unsupported_counting(
    tmp_path: Path,
) -> None:
    repo = _repo(
        tmp_path=tmp_path,
        pyproject=(
            "[tool.livespec_dev_tooling]\n"
            f'mirror_pairings = [{{source_tree = "{_SOURCE_TREE}", test_tree = "tests/pkg"}}]\n'
        ),
    )
    sha = _pair_commit(repo=repo, product="value = (\n")

    series = gather_completed_cycle_series(
        repo=repo,
        item=_item(),
        pr_number=4242,
        dispatch_id=_DISPATCH_ID,
        runner=_ForgeRunner(stdout=_payload(repo=repo, sha=sha)),
    )

    assert series.completed_count == 1
    assert series.cycles[0].product_lloc_changed is None
    assert series.cycles[0].product_lloc_unobserved_reason == UNOBSERVED_COUNTING
