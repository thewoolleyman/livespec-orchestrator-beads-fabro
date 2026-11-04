"""Successful command-route labels keep ordinary workflow laps out of failure handling.

The Petri circuit breaker groups deterministic command failures by node.  A
command route whose ordinary branch exits non-zero therefore becomes a terminal
failure after three otherwise healthy visits.  These cases execute the committed
command scripts in real throwaway repositories and then resolve the emitted
route label through the committed graph, so they bind both halves of the
contract: successful script completion and the destination that label selects.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GRAPH_PATH = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)
_MERGED_RECONCILE_MARKER = "livespec-merged-reconcile"
_PUBLISH_MERGED_ROUTE = "publish_merged_reconcile_route"
_REFRESH_MERGED_ROUTE = "pr_refresh_merged_reconcile_route"
_PR_ROUTE = "pr_route"


def _graph():
    """The committed graph, refusing malformed payload rather than guessing."""
    graph = parse_dot_graph(text=_GRAPH_PATH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    return graph


def _run_node(
    *, root: Path, node: str, marker: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run one committed command node in its own real git repository."""
    checkout = root / node
    subprocess.run(("git", "init", "--quiet", str(checkout)), check=True)
    state = checkout / ".git" / "livespec-publication"
    if marker is not None:
        state.mkdir(parents=True)
        (state / marker).write_text("present\n", encoding="utf-8")
    script = _graph().nodes[node]["script"]
    return subprocess.run(
        ("sh", "-c", script),
        check=False,
        cwd=checkout,
        capture_output=True,
        text=True,
    )


def _route_label(*, result: subprocess.CompletedProcess[str]) -> str:
    """The final routing object a successful command node reports."""
    lines = [line for line in result.stdout.splitlines() if line]
    assert lines, result.stderr
    payload = json.loads(lines[-1])
    assert set(payload) == {"preferred_next_label"}
    label = payload["preferred_next_label"]
    assert isinstance(label, str)
    return label


def _destination(*, source: str, preferred_label: str) -> str:
    """Resolve one preferred label using the same conditional-over-fallthrough rule."""
    graph = _graph()
    matching = [
        edge.destination
        for edge in graph.edges
        if edge.source == source
        and edge.attributes.get("condition") == f"preferred_label={preferred_label}"
    ]
    fallthrough = [
        edge.destination
        for edge in graph.edges
        if edge.source == source and "condition" not in edge.attributes
    ]
    assert len(matching) <= 1
    assert len(fallthrough) == 1
    return matching[0] if matching else fallthrough[0]


def test_merged_reconcile_routes_succeed_on_every_ordinary_lap_and_select_the_right_arm(
    *, tmp_path: Path
) -> None:
    """Three unmerged laps fall through; a merged publication selects verification."""
    for node, ordinary_destination in (
        (_PUBLISH_MERGED_ROUTE, "proof_capture"),
        (_REFRESH_MERGED_ROUTE, "pr_refresh_head"),
    ):
        assert _graph().nodes[node].get("output_schema") == "routing"
        for visit in range(3):
            ordinary = _run_node(root=tmp_path / f"{node}-{visit}", node=node)
            assert ordinary.returncode == 0, ordinary.stderr
            assert (
                _destination(source=node, preferred_label=_route_label(result=ordinary))
                == ordinary_destination
            )

        merged = _run_node(
            root=tmp_path / f"{node}-merged",
            node=node,
            marker=_MERGED_RECONCILE_MARKER,
        )
        assert merged.returncode == 0, merged.stderr
        assert _destination(source=node, preferred_label=_route_label(result=merged)) == "verify_pr"


def test_pr_route_refresh_laps_are_successful_and_select_pr_refresh(*, tmp_path: Path) -> None:
    """The adjacent refresh route cannot consume the same three-failure budget."""
    assert _graph().nodes[_PR_ROUTE].get("output_schema") == "routing"
    for visit in range(3):
        root = tmp_path / f"pr-route-{visit}"
        checkout = root / _PR_ROUTE
        subprocess.run(("git", "init", "--quiet", str(checkout)), check=True)
        state = checkout / ".git" / "livespec-publication"
        state.mkdir(parents=True)
        (state / "livespec-pr-visit-count").write_text(f"{visit}\n", encoding="utf-8")
        (state / "livespec-pr-refresh-route").write_text(f"{visit}:advance\n", encoding="utf-8")
        result = subprocess.run(
            ("sh", "-c", _graph().nodes[_PR_ROUTE]["script"]),
            check=False,
            cwd=checkout,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert (
            _destination(source=_PR_ROUTE, preferred_label=_route_label(result=result))
            == "pr_refresh"
        )
