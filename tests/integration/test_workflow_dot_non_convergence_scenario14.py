"""Integration-tier acceptance for the Fabro workflow-DOT non-convergence exit.

Binds SPECIFICATION/scenarios.md "Scenario 14 — Fabro non-convergence routes
back to the Dispatcher" and the contracts.md §"Gap-detectable behavior clauses"
clause (work-item livespec-impl-beads-rw75ym, gap-f7kcvboh):

    The single Fabro workflow-DOT tweak MUST stay within Fabro's existing DOT
    vocabulary — a fix-loop cap plus a "non-converged" exit edge that routes
    back to the Dispatcher (→ needs-regroom), reusing Fabro's existing
    verify→fix-loop nodes and max_node_visits governor — and MUST NOT require
    any Fabro platform or setup change.

The acceptance target is the SHIPPED workflow graph at
`.fabro/workflows/implement-work-item/workflow.fabro`: the test reads it and
asserts (1) the fix-loop CAP is the existing janitor visit-count governor, (2)
a `non_converged` terminal node exists within the existing DOT node vocabulary
(a plain command node, like `abandon`), (3) the janitor's exhausted edge routes
to `non_converged` (the non-converged exit edge back to the Dispatcher), NOT to
the in-loop human gate, and (4) the terminal node emits the SAME
`NON_CONVERGED_MARKER` sentinel the Dispatcher's `is_non_convergence_outcome`
matches — proving the DOT-side producer and the Dispatcher-side consumer share
one literal.
"""

from __future__ import annotations

import re
from pathlib import Path

from livespec_impl_beads.commands._dispatcher_plan import NON_CONVERGED_MARKER

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_DOT = _REPO_ROOT / ".fabro" / "workflows" / "implement-work-item" / "workflow.fabro"


def _dot_text() -> str:
    return _WORKFLOW_DOT.read_text(encoding="utf-8")


def test_workflow_dot_ships_and_is_a_digraph() -> None:
    text = _dot_text()
    assert "digraph ImplementWorkItem" in text


def test_fix_loop_cap_is_the_existing_visit_count_governor() -> None:
    """The fix-loop CAP is the janitor visit-count guard (no new governor)."""
    text = _dot_text()
    # The janitor->fix edge is gated on the node-visit governor (two fix
    # attempts, then the third Red exits the loop) — Fabro's existing
    # max_node_visits / node_visit_count machinery, not a new mechanism.
    assert "context.internal.node_visit_count < 3" in text


def test_non_converged_terminal_node_exists_in_existing_vocabulary() -> None:
    """A `non_converged` command node exists (same shape as the abandon terminal)."""
    text = _dot_text()
    assert re.search(r"\bnon_converged\s*\[", text) is not None
    # A plain command node within the existing DOT vocabulary — it carries a
    # `script` (like the `abandon` terminal), not a bespoke Fabro construct,
    # so no Fabro platform or setup change is required.
    node_block = re.search(r"\bnon_converged\s*\[(?P<body>.*?)\]", text, re.DOTALL)
    assert node_block is not None
    assert "script=" in node_block.group("body")


def test_exhausted_edge_routes_to_non_converged_not_the_human_gate() -> None:
    """The janitor's exhausted (fix-loop-cap) edge routes back to the Dispatcher."""
    text = _dot_text()
    # The non-converged EXIT EDGE: the janitor's exhausted outcome routes to
    # `non_converged` (which terminates non-green, routing control back to the
    # Dispatcher), NOT to `escalate` (the in-loop human gate).
    assert re.search(r"janitor\s*->\s*non_converged\b", text) is not None
    assert re.search(r"janitor\s*->\s*escalate\b", text) is None


def test_non_converged_node_emits_the_shared_dispatcher_sentinel() -> None:
    """The DOT terminal emits the SAME sentinel the Dispatcher consumer matches."""
    text = _dot_text()
    node_block = re.search(r"\bnon_converged\s*\[(?P<body>.*?)\]", text, re.DOTALL)
    assert node_block is not None
    # One shared literal across the DOT-side producer and the Dispatcher-side
    # consumer (commands/_dispatcher_plan.is_non_convergence_outcome) — the
    # join that turns the DOT exit edge into a needs-regroom bounce.
    assert NON_CONVERGED_MARKER in node_block.group("body")
