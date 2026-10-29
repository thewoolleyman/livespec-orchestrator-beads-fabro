"""The `needs_human` node's own timeout rides the hook-limit figures file.

Work-item `bd-ib-ptnxyg`, Scenario 192. The node sizes the wait it spends on a cut
turn's commit runs from `LIVESPEC_NEEDS_HUMAN_LIMIT_SECONDS`, so the figure must be
read off the graph the run will execute, rendered into the same sourceable file the
publication guard reads, and independent of the publication figures in both
directions: a withheld publish limit must not cost the node its bound, and the
needs-human figure must not appear when the node's timeout cannot be read.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_limit_program import (
    HOOK_LIMIT_LIMITS_FILENAME,
    hook_limit_graph_prepare_steps_block,
    hook_limit_prepare_steps_block,
    resolve_needs_human_limit,
)

_GRAPH = """digraph g {
    needs_human [
        label="Needs human"
        timeout="1800s"
    ]
    publish_draft [
        label="Publish"
        timeout="3600s"
    ]
}
"""


def test_the_limit_is_read_off_the_absolute_graph_the_run_will_use(tmp_path: Path) -> None:
    """Scenario 192: the node's own rendered timeout, in seconds."""
    graph = tmp_path / "workflow.fabro"
    _ = graph.write_text(_GRAPH, encoding="utf-8")

    assert resolve_needs_human_limit(
        graph_artifact=graph, written_graph=Path("workflow.fabro")
    ) == (1800)
    assert resolve_needs_human_limit(graph_artifact=None, written_graph=graph) == 1800


def test_a_relative_or_unreadable_graph_withholds_the_limit(tmp_path: Path) -> None:
    """Scenario 192: a name that may open a different graph, or none, yields no figure."""
    graph = tmp_path / "workflow.fabro"
    _ = graph.write_text(_GRAPH, encoding="utf-8")

    assert (
        resolve_needs_human_limit(graph_artifact=None, written_graph=Path("workflow.fabro")) is None
    )
    assert (
        resolve_needs_human_limit(graph_artifact=tmp_path / "absent.fabro", written_graph=graph)
        is None
    )


def test_the_figure_is_written_beside_or_without_the_publication_figures() -> None:
    """Scenario 192: either figure alone still lands the file, and neither lands nothing."""
    both = hook_limit_prepare_steps_block(limit_seconds=3600, needs_human_limit_seconds=1800)
    only_node = hook_limit_prepare_steps_block(limit_seconds=None, needs_human_limit_seconds=1800)
    only_publish = hook_limit_prepare_steps_block(limit_seconds=3600)
    neither = hook_limit_prepare_steps_block(limit_seconds=None)

    assert "LIVESPEC_NEEDS_HUMAN_LIMIT_SECONDS=1800" in both
    assert "LIVESPEC_PUBLISH_DRAFT_LIMIT_SECONDS=3600" in both
    assert "LIVESPEC_NEEDS_HUMAN_LIMIT_SECONDS=1800" in only_node
    assert "LIVESPEC_PUBLISH_DRAFT" not in only_node
    assert "LIVESPEC_NEEDS_HUMAN_LIMIT_SECONDS" not in only_publish
    assert HOOK_LIMIT_LIMITS_FILENAME not in neither


def test_the_graph_block_renders_both_figures_from_one_graph(tmp_path: Path) -> None:
    """Scenario 192: the overlay's single call reads each node's own literal."""
    graph = tmp_path / "workflow.fabro"
    _ = graph.write_text(_GRAPH, encoding="utf-8")

    block = hook_limit_graph_prepare_steps_block(
        graph_artifact=graph, written_graph=Path("workflow.fabro"), warn=None
    )

    assert "LIVESPEC_NEEDS_HUMAN_LIMIT_SECONDS=1800" in block
    assert "LIVESPEC_PUBLISH_DRAFT_LIMIT_SECONDS=3600" in block
