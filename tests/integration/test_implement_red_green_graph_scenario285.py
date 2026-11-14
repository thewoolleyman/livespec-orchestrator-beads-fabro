"""Scenario 285 — the implement stage is a Red/Green command graph."""

from __future__ import annotations

import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_already_satisfied import (
    already_satisfied_base_from_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_ROOT = Path(__file__).resolve().parents[2]
_GRAPH = _ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
_RESET = _ROOT / "dev-tooling/reset-test-wrong-to-dispatch-base.sh"


def _run(*, cwd: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, check=check, text=True, capture_output=True)


def _graph() -> object:
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    return graph


def _scratch_repo(*, tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    repo = tmp_path / "repo"
    _run(cwd=tmp_path, args=["git", "init", "-q", str(repo)])
    _run(cwd=repo, args=["git", "config", "user.name", "Scenario 285"])
    _run(cwd=repo, args=["git", "config", "user.email", "scenario285@example.test"])
    (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
    _run(cwd=repo, args=["git", "add", "tracked.txt"])
    _run(cwd=repo, args=["git", "commit", "-qm", "base"])
    _run(cwd=repo, args=["git", "remote", "add", "origin", str(repo)])
    _run(cwd=repo, args=["git", "fetch", "origin", "master:refs/remotes/origin/master"])
    return repo


def test_scenario285_routes_each_implement_commit_through_red_and_green_command_nodes() -> None:
    """The split replaces ``implement`` and admissions name exhausted bounds."""
    graph = _graph()
    assert "implement" not in graph.nodes
    assert {
        "red_admission",
        "red",
        "commit_red",
        "green_admission",
        "green",
        "commit_green",
        "test_wrong_reset",
    } <= set(graph.nodes)
    edges = {
        (edge.source, edge.destination, edge.attributes.get("condition")) for edge in graph.edges
    }
    assert ("dod_gate_mutation_guard", "red_admission", None) in edges
    assert ("red_admission", "red", None) in edges
    assert ("red", "commit_red", None) in edges
    assert ("commit_red", "red_admission", "outcome=failed") in edges
    assert ("commit_red", "green_admission", None) in edges
    assert ("green_admission", "green", None) in edges
    assert ("green", "test_wrong_reset", "preferred_label=test-wrong") in edges
    assert ("test_wrong_reset", "red_admission", None) in edges
    assert ("commit_green", "green_admission", "outcome=failed") in edges
    assert ("commit_green", "implementation_diff", None) in edges
    assert graph.nodes["commit_red"]["script"] == "bash dev-tooling/commit-red.sh"
    assert graph.nodes["commit_green"]["script"] == "bash dev-tooling/commit-green.sh"
    assert "commit-runner.py" not in graph.nodes["red"].get("prompt", "")
    assert "commit-runner.py" not in graph.nodes["green"].get("prompt", "")


def test_scenario285_test_wrong_reset_restores_the_dispatch_base(tmp_path: Path) -> None:
    """A test-wrong lap leaves its handoff but removes all branch changes."""
    repo = _scratch_repo(tmp_path=tmp_path)
    (repo / "tracked.txt").write_text("wrong test\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("remove me\n", encoding="utf-8")

    reset = _run(cwd=repo, args=[str(_RESET), "master"], check=False)

    assert reset.returncode == 0, reset.stderr
    assert (repo / "tracked.txt").read_text(encoding="utf-8") == "base\n"
    assert not (repo / "untracked.txt").exists()


# The handoff as the four nodes write it: each ACP section records its last gate
# preview, and each command-node section is `commit-red.sh` / `commit-green.sh`'s
# `append_verdict` format. Every value is unique to its section, so a cause that
# quoted the wrong section, or fell back to "absent", cannot carry it.
_HANDOFF = (
    "## red\npreview exit status: 5; failed targets: check-format\n\n"
    "## commit_red\n\nExit status: 7\nFailed targets:\n  - check-lint\n"
    "Hook output (last 80 lines):\n```text\nlint refused\n```\n\n"
    "## green\npreview exit status: 6; failed targets: check-arch\n\n"
    "## commit_green\n\nExit status: 9\nFailed targets:\n  - check-types\n"
    "Hook output (last 80 lines):\n```text\ntypes refused\n```\n\n"
    "## test-wrong\nRed test is wrong.\n"
)

# Per exhausted node: its counter, the value that exhausts it, and the values of
# the section(s) its cause must quote. The admissions quote their command node's
# record ("the exhausted command node's recorded exit status and failed
# targets"); the test-wrong route quotes the latest red and green sections.
_EXHAUSTIONS = (
    ("red_admission", "livespec-red-admission-count", "3\n", ("Exit status: 7", "check-lint")),
    ("green_admission", "livespec-green-admission-count", "3\n", ("Exit status: 9", "check-types")),
    (
        "test_wrong_reset",
        "livespec-implement-test-wrong-reentries",
        "2\n",
        ("exit status: 5", "check-format", "exit status: 6", "check-arch"),
    ),
)


def _exhaust(*, tmp_path: Path, node: str, counter: str, count: str, handoff: str) -> str:
    repo = _scratch_repo(tmp_path=tmp_path / node)
    git_dir = repo / ".git"
    (git_dir / counter).write_text(count, encoding="utf-8")
    (git_dir / "livespec-implement-handoff.md").write_text(handoff, encoding="utf-8")
    script = _graph().nodes[node]["script"].replace("{{ inputs.default_branch }}", "master")

    result = _run(cwd=repo, args=["sh", "-c", script], check=False)

    assert result.returncode != 0, result.stderr
    assert "EXHAUSTED" in result.stderr
    return (git_dir / "livespec-stage-cause").read_text(encoding="utf-8")


def test_scenario285_exhausted_admissions_write_the_handoff_evidence(tmp_path: Path) -> None:
    """Every exhausted loop's cause quotes the values of the section it must carry."""
    for node, counter, count, values in _EXHAUSTIONS:
        cause = _exhaust(
            tmp_path=tmp_path, node=node, counter=counter, count=count, handoff=_HANDOFF
        )

        assert "absent" not in cause, f"{node} found no handoff section: {cause}"
        for value in values:
            assert value in cause, f"{node} cause omits {value!r}: {cause}"


def test_scenario285_a_missing_handoff_section_is_named_absent(tmp_path: Path) -> None:
    """Control: with no section to read, the cause says so and carries none of the values."""
    for node, counter, count, values in _EXHAUSTIONS:
        cause = _exhaust(
            tmp_path=tmp_path / "empty", node=node, counter=counter, count=count, handoff=""
        )

        assert "absent" in cause, f"{node} did not name the missing section: {cause}"
        for value in values:
            assert value not in cause, f"{node} cause carries {value!r} from no section"


def test_scenario285_already_satisfied_prints_the_ending_the_dispatcher_reads(
    tmp_path: Path,
) -> None:
    """On the unchanged base the node succeeds naming that base, in the Dispatcher's own parse."""
    repo = _scratch_repo(tmp_path=tmp_path)
    base = _run(cwd=repo, args=["git", "rev-parse", "origin/master"]).stdout.strip()
    script = (
        _graph()
        .nodes["already_satisfied"]["script"]
        .replace("{{ inputs.default_branch }}", "master")
    )

    result = _run(cwd=repo, args=["sh", "-c", script], check=False)

    assert result.returncode == 0, result.stderr
    assert already_satisfied_base_from_text(text=result.stderr) == base


def test_scenario285_an_unprovable_already_satisfied_claim_fails(tmp_path: Path) -> None:
    """With work above the base, the node fails and prints nothing the Dispatcher reads as the ending."""
    repo = _scratch_repo(tmp_path=tmp_path)
    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    _run(cwd=repo, args=["git", "commit", "-qam", "above base"])
    script = (
        _graph()
        .nodes["already_satisfied"]["script"]
        .replace("{{ inputs.default_branch }}", "master")
    )

    result = _run(cwd=repo, args=["sh", "-c", script], check=False)

    assert result.returncode != 0
    assert already_satisfied_base_from_text(text=result.stderr) is None
