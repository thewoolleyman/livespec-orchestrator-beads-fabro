"""The graph shapes the setup-node splice refuses (work-item bd-ib-dpsiwz).

A companion to `test_dispatcher_setup_nodes`, whose Red bytes are fixed: this case
was found by a coverage measurement taken after that Red was authored. A graph whose
LAST closing brace sits in a trailing comment takes the splice inside the comment, so
the result no longer re-parses to the nodes intended, and the splice must say so
rather than hand back a graph that dropped every step.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_prepare_payload import PrepareStep
from livespec_orchestrator_beads_fabro.commands._dispatcher_setup_nodes import (
    splice_setup_nodes,
)

_GRAPH = """digraph G {
    start [shape=Mdiamond, label="Start"]
    exit [shape=Msquare, label="Exit"]
    start -> exit
}
"""


def test_a_brace_in_a_trailing_comment_is_refused_not_spliced_into_the_comment() -> None:
    commented = _GRAPH + "// the closing brace } of a comment\n"
    assert splice_setup_nodes(graph_text=commented, steps=[PrepareStep(script="a")]) is None


def test_the_same_graph_without_the_comment_is_spliced() -> None:
    spliced = splice_setup_nodes(graph_text=_GRAPH, steps=[PrepareStep(script="a")])
    assert spliced is not None
    assert "run_prepare_1 [" in spliced
