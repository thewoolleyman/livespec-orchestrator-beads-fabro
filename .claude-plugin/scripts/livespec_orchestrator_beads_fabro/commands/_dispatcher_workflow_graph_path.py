"""Read and resolve the workflow graph declared by a run configuration."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_toml_read import (
    toml_section_string,
)

__all__: list[str] = [
    "absolute_workflow_graph_path",
    "workflow_graph_path",
]


def workflow_graph_path(*, committed_text: str, workflow_dir: Path) -> Path | None:
    """Return the declared graph as an absolute path, or None when absent."""
    graph_value = toml_section_string(text=committed_text, section="workflow", key="graph")
    if graph_value is None:
        return None
    return absolute_workflow_graph_path(graph_value=graph_value, workflow_dir=workflow_dir)


def absolute_workflow_graph_path(*, graph_value: str, workflow_dir: Path) -> Path:
    """Resolve one graph value against the directory of its run configuration."""
    graph_path = Path(graph_value)
    return graph_path if graph_path.is_absolute() else workflow_dir / graph_path
