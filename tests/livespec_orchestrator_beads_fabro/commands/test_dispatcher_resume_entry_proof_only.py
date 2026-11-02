"""The proof-only graph refuses source or output it cannot constrain exactly."""

from __future__ import annotations

import importlib
from typing import Any

import pytest

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry"

_CHAINED_EDGE_GRAPH = """digraph ProofOnly {
    start [shape=Mdiamond]
    exit [shape=Msquare]
    proof_capture [label="Capture"]
    proof_verify [label="Verify"]
    proof_grade [label="Grade"]

    start -> proof_capture -> proof_verify -> proof_grade -> exit
}
"""


def _module() -> Any:
    """Load the graph builder from the plugin package."""
    return importlib.import_module(_MODULE)


def _no_declarations(*, graph_text: str, names: frozenset[str]) -> list[tuple[int, int, str]]:
    """Stand in for a failed declaration locator without weakening the product guard."""
    _ = graph_text, names
    return []


def test_proof_only_graph_refuses_an_unreadable_source() -> None:
    """A proof-only route is never invented from text the shared parser rejects."""
    module = _module()
    assert module.proof_only_graph(graph_text="not a DOT graph") is None


def test_proof_only_graph_refuses_an_output_that_kept_an_unpruned_chained_edge() -> None:
    """An edge the line-splice cannot remove must fail the exact-route postcondition."""
    module = _module()
    assert module.proof_only_graph(graph_text=_CHAINED_EDGE_GRAPH) is None


def test_proof_only_graph_refuses_when_a_node_declaration_survives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The postcondition fails closed if a declaration survives the prune."""
    module = _module()
    extra_node = _CHAINED_EDGE_GRAPH.replace(
        "    start -> proof_capture -> proof_verify -> proof_grade -> exit\n",
        "".join(
            (
                '    other [label="Other"]\n',
                "    start -> proof_capture\n",
                "    proof_capture -> proof_verify\n",
                "    proof_verify -> proof_grade\n",
                "    proof_grade -> exit\n",
            )
        ),
    )
    monkeypatch.setattr(module, "_declaration_spans", _no_declarations)
    assert module.proof_only_graph(graph_text=extra_node) is None
