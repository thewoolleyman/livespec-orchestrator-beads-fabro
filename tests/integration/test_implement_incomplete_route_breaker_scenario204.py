"""Scenario 204 — incomplete turns reach the hook route without tripping Petri's breaker.

The settled-commit re-entry permits a third implement visit. The completion
gate must therefore report an incomplete turn as a successful routing label:
three identical non-zero completion-gate exits are a deterministic-failure
cycle before ``implement_hook_route`` can spend its budget and preserve the
failed commit's evidence at ``needs_human``.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GRAPH = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)
_COMPLETION = "implement_completion"
_ROUTE = "implement_hook_route"
_NEEDS_HUMAN = "needs_human"


def _parsed_graph():
    graph = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    return graph


def _targets(*, source: str) -> list[tuple[str, str]]:
    return [
        (edge.destination, edge.attributes.get("condition", ""))
        for edge in _parsed_graph().edges
        if edge.source == source
    ]


def _completion_script() -> str:
    return _parsed_graph().nodes[_COMPLETION]["script"]


def _route_script() -> str:
    return _parsed_graph().nodes[_ROUTE]["script"]


def test_three_incomplete_visits_are_successful_routes_to_needs_human_with_failed_commit_cause(
    tmp_path: Path,
) -> None:
    """Each incomplete visit avoids the breaker and selects the hook route."""
    graph = _parsed_graph()
    assert graph.nodes[_COMPLETION].get("output_schema") == "routing"
    assert (_ROUTE, "preferred_label=incomplete") in _targets(source=_COMPLETION)
    assert (_NEEDS_HUMAN, "") in _targets(source=_ROUTE)

    repo = tmp_path / "clone"
    repo.mkdir()
    subprocess.run(("git", "init", "--quiet"), cwd=repo, check=True)
    for _ in range(3):
        completed = subprocess.run(
            ("sh", "-c", _completion_script()),
            cwd=repo,
            check=False,
            capture_output=True,
            input='{"definition_of_done_complete": false}',
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        assert json.loads(completed.stdout) == {"preferred_next_label": "incomplete"}

    git_dir = repo / ".git"
    (git_dir / "livespec-implement-hook-reentries").write_text("1\n", encoding="utf-8")
    (git_dir / "livespec-implement-live-commit").write_text(
        "failed\n"
        "failed targets: check-types\n\n"
        "Commit run commit-123 ended FAILED with exit status 17; hook rejected changes.\n"
        "module.py:3:1 - error: broken\n",
        encoding="utf-8",
    )

    routed = subprocess.run(
        ("sh", "-c", _route_script()),
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )

    assert routed.returncode != 0, routed.stderr
    cause = (git_dir / "livespec-stage-cause").read_text(encoding="utf-8")
    assert "hook exit status: 17" in cause
    assert "failed targets: check-types" in cause
