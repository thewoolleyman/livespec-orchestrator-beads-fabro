"""An incomplete Green turn re-enters green once, then fails naming partial progress.

`SPECIFICATION/contracts.md` section "Self-contained plugin dispatch" -> "An
implement turn that ends incomplete does not succeed": a `green` turn whose
completion field reports the work incomplete re-enters `green` while its budget
remains, and once that budget is spent the stage ends failed with a cause naming
partial progress. The split graph realizes the decision in the
`green_incomplete_route` command node, whose script runs here against a scratch
repository exactly as the engine runs it, read from the committed graph.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_ROOT = Path(__file__).resolve().parents[2]
_GRAPH = _ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
_NODE = "green_incomplete_route"
_PARTIAL = (
    "LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS: the implement turn completion field does not "
    "state the work-item Definition of Done complete"
)


def _run(*, cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, check=False, capture_output=True, text=True)


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    _ = _run(cwd=tmp_path, args=["git", "init", "-q", str(repo)])
    return repo


def _script() -> str:
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    return str(graph.nodes[_NODE]["script"])


def test_the_first_incomplete_turn_re_enters_green_and_clears_its_record(tmp_path: Path) -> None:
    """The first incomplete ending is a re-entry, with the previous turn's record cleared."""
    repo = _repo(tmp_path=tmp_path)
    git_dir = repo / ".git"
    (git_dir / "livespec-stage-cause").write_text(
        f"stage: implement\ncause: {_PARTIAL}\n", encoding="utf-8"
    )
    (git_dir / "livespec-implement-completion").write_text(
        '{"definition_of_done_complete": false}\n', encoding="utf-8"
    )

    result = _run(cwd=repo, args=["sh", "-c", _script()])

    facts = (
        result.returncode == 0,
        "LIVESPEC_GREEN_INCOMPLETE_REENTER" in result.stderr,
        (git_dir / "livespec-green-incomplete-reentries").read_text(encoding="utf-8") == "1\n",
        not (git_dir / "livespec-stage-cause").exists(),
        not (git_dir / "livespec-implement-completion").exists(),
    )
    assert all(facts), (facts, result.stderr)


def test_a_spent_reentry_fails_with_the_partial_progress_cause_standing(tmp_path: Path) -> None:
    """Once the re-entry is spent the node fails and the cause names partial progress."""
    repo = _repo(tmp_path=tmp_path)
    git_dir = repo / ".git"
    (git_dir / "livespec-green-incomplete-reentries").write_text("1\n", encoding="utf-8")
    (git_dir / "livespec-stage-cause").write_text(
        f"stage: implement\ncause: {_PARTIAL}\n", encoding="utf-8"
    )

    result = _run(cwd=repo, args=["sh", "-c", _script()])

    cause = (git_dir / "livespec-stage-cause").read_text(encoding="utf-8")
    facts = (
        result.returncode != 0,
        _PARTIAL in result.stderr,
        _PARTIAL in cause,
    )
    assert all(facts), (facts, result.stderr, cause)


def test_a_spent_reentry_with_no_recorded_cause_still_names_partial_progress(
    tmp_path: Path,
) -> None:
    """A missing cause file never leaves the failed stage without a partial-progress cause."""
    repo = _repo(tmp_path=tmp_path)
    git_dir = repo / ".git"
    (git_dir / "livespec-green-incomplete-reentries").write_text("1\n", encoding="utf-8")

    result = _run(cwd=repo, args=["sh", "-c", _script()])

    cause = (git_dir / "livespec-stage-cause").read_text(encoding="utf-8")
    facts = (
        result.returncode != 0,
        "LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS" in result.stderr,
        "stage: implement\ncause: LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS" in cause,
    )
    assert all(facts), (facts, result.stderr, cause)
