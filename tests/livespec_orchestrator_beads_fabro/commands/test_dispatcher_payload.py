"""Mirror test module for dispatch payload rendering."""

from livespec_orchestrator_beads_fabro.commands._dispatcher_payload import _rendered_graph


def test_rendered_graph_is_importable() -> None:
    """The implement-prompt tests exercise the graph rendering seam."""
    assert callable(_rendered_graph)
