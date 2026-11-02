"""Graph-path resolution shared by run-overlay rendering and its consumers.

The overlay assembly needs to translate a committed relative graph name into a
path the Dispatcher can read.  That resolution is also a public read surface
for payload and admission code, so it stays together here rather than adding
another concern to the overlay's large rendering pipeline.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_toml_read import (
    toml_section_string,
)

__all__: list[str] = [
    "absolute_graph_path",
    "workflow_graph_path",
]


def workflow_graph_path(*, committed_text: str, workflow_dir: Path) -> Path | None:
    """Return a committed run config's absolute graph path, or None when absent."""
    graph_value = toml_section_string(text=committed_text, section="workflow", key="graph")
    if graph_value is None:
        return None
    return absolute_graph_path(graph_value=graph_value, workflow_dir=workflow_dir)


def absolute_graph_path(*, graph_value: str, workflow_dir: Path) -> Path:
    """Resolve a graph declaration against the directory that owns the config."""
    graph_path = Path(graph_value)
    return graph_path if graph_path.is_absolute() else workflow_dir / graph_path
