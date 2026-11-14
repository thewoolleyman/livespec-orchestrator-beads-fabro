"""Scenario 204 — incomplete turns reach the incomplete route without tripping Petri's breaker.

The completion gate must report an incomplete turn as a successful routing label:
repeated identical non-zero completion-gate exits are a deterministic-failure
cycle before `green_incomplete_route` can spend its one re-entry and fail with the
partial-progress cause at `needs_human`. The single-turn `implement_hook_route`
this once covered was removed with the red/green split (work-item bd-ib-vvzd3v).
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
# The split graph's incomplete-turn route (Scenario 285), which the gate reaches.
_GREEN_ROUTE = "green_incomplete_route"
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


def test_incomplete_visits_are_successful_routes_to_the_green_incomplete_route(
    tmp_path: Path,
) -> None:
    """Each incomplete visit avoids the breaker and selects the incomplete-turn route.

    In the split graph the gate's `incomplete` label reaches `green_incomplete_route`.
    """
    graph = _parsed_graph()
    assert graph.nodes[_COMPLETION].get("output_schema") == "routing"
    assert (_GREEN_ROUTE, "preferred_label=incomplete") in _targets(source=_COMPLETION)
    assert (_NEEDS_HUMAN, "outcome=failed") in _targets(source=_GREEN_ROUTE)

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
