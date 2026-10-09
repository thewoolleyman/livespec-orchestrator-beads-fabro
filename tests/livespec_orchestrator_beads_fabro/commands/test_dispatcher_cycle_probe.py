"""Gathering one dispatch's completed-cycle series from real git provenance.

The IO half of Scenario 165's first three assertions. The probe reads the
dispatch's own commit series through the forge, selects it by the
`Factory-Run-Id` trailer exactly as the TDD signal probe does, and measures each
verified pair's changed product logical lines out of the two source trees the
pair spans — against a REAL git repository built in `tmp_path`, carrying real
Red-Green trailers, so the measurement is exercised through the same objects a
live dispatch reads rather than through a stub.

The discriminations under test: a run that never merged still has a measurable
series; a commit series carrying no verified pair is an OBSERVED EMPTY series; a
commit whose objects are absent from this clone keeps its pair and reports its
size unobserved with a reason; and an unidentifiable series is UNREADABLE rather
than empty.
"""

from __future__ import annotations

import importlib
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

from livespec_orchestrator_beads_fabro.commands._dispatcher_completed_cycles import (
    UNOBSERVED_SOURCE_TREE,
    UNREADABLE_PROVENANCE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_probe"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_cycle_probe.py"
)

_DISPATCH_ID = "5fe8e3dfbfd54faa979e85364d8e9863"
_OTHER_DISPATCH_ID = "0000e8dfbfd54faa979e85364d8e9863"
_SOURCE_TREE = "src/pkg"
_PYPROJECT = (
    "[tool.livespec_dev_tooling]\n"
    f'mirror_pairings = [{{source_tree = "{_SOURCE_TREE}", test_tree = "tests/pkg"}}]\n'
)


def _module() -> ModuleType:
    """Import the module under test, asserting it exists first."""
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


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


def _item(*, criteria: str = "- One assertion.\n- Two assertions.\n") -> WorkItem:
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
        acceptance_criteria=criteria,
    )


def _git(*, repo: Path, argv: list[str]) -> str:
    return subprocess.run(
        ["git", *argv],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "clone"
    repo.mkdir()
    _git(repo=repo, argv=["init", "--initial-branch", "work"])
    _git(repo=repo, argv=["config", "user.email", "fixture@example.com"])
    _git(repo=repo, argv=["config", "user.name", "Fixture"])
    (repo / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    (repo / _SOURCE_TREE).mkdir(parents=True)
    (repo / _SOURCE_TREE / "thing.py").write_text('"""Doc."""\n\nvalue = 1\n', encoding="utf-8")
    _git(repo=repo, argv=["add", "-A"])
    _git(repo=repo, argv=["commit", "-m", "chore: seed"])
    return repo


def _commit_cycle(
    *,
    repo: Path,
    product: str,
    red_at: str,
    green_at: str,
    checksum: str,
    dispatch_id: str = _DISPATCH_ID,
) -> str:
    """Author one Green-amended-shaped commit carrying a real trailer block."""
    (repo / _SOURCE_TREE / "thing.py").write_text(product, encoding="utf-8")
    (repo / "tests").mkdir(exist_ok=True)
    (repo / "tests" / f"test_{checksum}.py").write_text(
        f'"""Test for {checksum}."""\n\nassert True\n', encoding="utf-8"
    )
    _git(repo=repo, argv=["add", "-A"])
    message = "\n".join(
        [
            "feat(pkg): one assertion",
            "",
            "Body prose.",
            "",
            f"TDD-Red-Test-File-Checksum: {checksum}",
            f"TDD-Red-Captured-At: {red_at}",
            f"Factory-Run-Id: {dispatch_id}",
            f"TDD-Green-Verified-At: {green_at}",
        ]
    )
    _git(repo=repo, argv=["commit", "-m", message])
    return _git(repo=repo, argv=["rev-parse", "HEAD"])


def _payload(*, repo: Path, shas: list[str]) -> str:
    commits: list[dict[str, str]] = []
    for sha in shas:
        headline = _git(repo=repo, argv=["log", "-1", "--format=%s", sha])
        body = _git(repo=repo, argv=["log", "-1", "--format=%b", sha])
        commits.append({"oid": sha, "messageHeadline": headline, "messageBody": body})
    return json.dumps({"commits": commits})


def test_an_unmerged_run_still_measures_its_preserved_pairs(tmp_path: Path) -> None:
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    first = _commit_cycle(
        repo=repo,
        product='"""Doc."""\n\nvalue = 2\n',
        red_at="2026-10-01T10:00:00Z",
        green_at="2026-10-01T10:04:10Z",
        checksum="sha256:one",
    )
    second = _commit_cycle(
        repo=repo,
        product='"""Doc."""\n\nvalue = 2\nother = 3\n',
        red_at="2026-10-01T11:00:00Z",
        green_at="2026-10-01T11:01:00Z",
        checksum="sha256:two",
    )

    series = module.gather_completed_cycle_series(
        repo=repo,
        item=_item(),
        pr_number=4242,
        dispatch_id=_DISPATCH_ID,
        runner=_ForgeRunner(stdout=_payload(repo=repo, shas=[second, first])),
    )

    assert series.observed
    assert series.completed_count == 2
    assert series.assertion_count == 2
    assert [cycle.ordinal for cycle in series.cycles] == [1, 2]
    assert [cycle.commit for cycle in series.cycles] == [first, second]
    assert [cycle.elapsed_seconds for cycle in series.cycles] == [250, 60]
    # First cycle: `value = 1` became `value = 2` — one removed, one added. The
    # docstring is unchanged and the test file is excluded as a non-product path.
    assert series.cycles[0].product_lloc_changed == 2
    # Second cycle: one added logical line, nothing removed.
    assert series.cycles[1].product_lloc_changed == 1
    assert all(cycle.product_lloc_unobserved_reason is None for cycle in series.cycles)


def test_a_series_carrying_no_verified_pair_is_observed_and_empty(tmp_path: Path) -> None:
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    (repo / _SOURCE_TREE / "thing.py").write_text('"""Doc."""\n\nvalue = 9\n', encoding="utf-8")
    _git(repo=repo, argv=["add", "-A"])
    _git(
        repo=repo,
        argv=[
            "commit",
            "-m",
            f"chore(pkg): suite green\n\nTDD-Suite-Green-Captured-At: 2026-10-01T10:00:00Z\nFactory-Run-Id: {_DISPATCH_ID}",
        ],
    )
    sha = _git(repo=repo, argv=["rev-parse", "HEAD"])

    series = module.gather_completed_cycle_series(
        repo=repo,
        item=_item(),
        pr_number=4242,
        dispatch_id=_DISPATCH_ID,
        runner=_ForgeRunner(stdout=_payload(repo=repo, shas=[sha])),
    )

    assert series.observed
    assert series.completed_count == 0
    assert series.unreadable_reason is None


def test_a_commit_absent_from_this_clone_keeps_its_pair_and_reports_a_reason(
    tmp_path: Path,
) -> None:
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    absent = "0" * 40
    payload = json.dumps(
        {
            "commits": [
                {
                    "oid": absent,
                    "messageHeadline": "feat(pkg): one assertion",
                    "messageBody": (
                        "TDD-Red-Test-File-Checksum: sha256:gone\n"
                        "TDD-Red-Captured-At: 2026-10-01T10:00:00Z\n"
                        f"Factory-Run-Id: {_DISPATCH_ID}\n"
                        "TDD-Green-Verified-At: 2026-10-01T10:04:10Z\n"
                    ),
                }
            ]
        }
    )

    series = module.gather_completed_cycle_series(
        repo=repo,
        item=_item(),
        pr_number=4242,
        dispatch_id=_DISPATCH_ID,
        runner=_ForgeRunner(stdout=payload),
    )

    assert series.completed_count == 1
    assert series.cycles[0].product_lloc_changed is None
    assert series.cycles[0].product_lloc_unobserved_reason == UNOBSERVED_SOURCE_TREE
    assert series.cycles[0].elapsed_seconds == 250


def test_an_unidentifiable_series_is_unreadable_rather_than_empty(tmp_path: Path) -> None:
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    first = _commit_cycle(
        repo=repo,
        product='"""Doc."""\n\nvalue = 2\n',
        red_at="2026-10-01T10:00:00Z",
        green_at="2026-10-01T10:04:10Z",
        checksum="sha256:one",
        dispatch_id=_OTHER_DISPATCH_ID,
    )

    for series in (
        module.gather_completed_cycle_series(
            repo=repo,
            item=_item(),
            pr_number=None,
            dispatch_id=_DISPATCH_ID,
            runner=_ForgeRunner(),
        ),
        module.gather_completed_cycle_series(
            repo=repo,
            item=_item(),
            pr_number=4242,
            dispatch_id=None,
            runner=_ForgeRunner(),
        ),
        module.gather_completed_cycle_series(
            repo=repo,
            item=_item(),
            pr_number=4242,
            dispatch_id=_DISPATCH_ID,
            runner=_ForgeRunner(exit_code=1),
        ),
        module.gather_completed_cycle_series(
            repo=repo,
            item=_item(),
            pr_number=4242,
            dispatch_id=_DISPATCH_ID,
            runner=_ForgeRunner(stdout="not json"),
        ),
        module.gather_completed_cycle_series(
            repo=repo,
            item=_item(),
            pr_number=4242,
            dispatch_id=_DISPATCH_ID,
            runner=_ForgeRunner(stdout=_payload(repo=repo, shas=[first])),
        ),
    ):
        assert not series.observed
        assert series.completed_count is None
        assert series.unreadable_reason == UNREADABLE_PROVENANCE
        assert series.assertion_count == 2
