"""Scenario 195 — the verified record is graded per assertion before publication.

`SPECIFICATION/scenarios.md` "Scenario 195" and the `proof_grade` /
`proof_grade_route` paragraphs of `SPECIFICATION/contracts.md` section
"Self-contained plugin dispatch" -> "The stages" (v156). The incident the slice
repairs is `bd-ib-rszkjc`, merged as pull request 3130 with a `verified` record
carrying no per-assertion verdict at all: every stage went green, the pull
request merged, and the post-merge acceptance pass then parked the item
NEEDS_ATTENTION with all three assertions pending a Proof of Done record.

Two layers are asserted here and neither can establish the other. The committed
GRAPH decides where a grade failure routes and what timeout the node enforces,
which no execution of the program can show; and the shipped PROGRAM BYTES decide
what counts as a per-assertion verdict, which no reading of the graph can show.
The sub-scenarios that need both run the program's own bytes against a real git
clone with the forge stood in at `gh`, so the record the grade reads is the
record a stage would read.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_graph_render import (
    node_timeout_seconds,
    render_workflow_graph,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    DEFAULT_NODE_TIMEOUT_SECONDS,
    node_timeouts_from_block,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PAYLOAD = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_GRAPH = _PAYLOAD / "workflow.fabro"

_GRADE = "proof_grade"

# The one value the case configures, chosen so it can equal neither the
# fully-defaulted resolution nor any literal the committed graph happens to
# carry: a figure that collided with either would pass for a node whose timeout
# nothing resolved.
_CONFIGURED_SECONDS = 1234


def _graph_text() -> str:
    return _GRAPH.read_text(encoding="utf-8")


def test_a_target_naming_proof_grade_in_node_timeouts_is_not_refused() -> None:
    """`dispatcher.node_timeouts.proof_grade` resolves rather than refusing.

    The table is validated before any run exists and its refusal NAMES the key,
    so a node the graph does not declare would be rejected there. This is the
    half of Scenario 89's claim that belongs to the new node: a repository that
    wants a different ceiling for the grade must be able to ask for one.
    """
    resolved = node_timeouts_from_block(block={"node_timeouts": {_GRADE: _CONFIGURED_SECONDS}})

    assert not isinstance(resolved, str), resolved
    assert resolved.seconds_for(node=_GRADE) == _CONFIGURED_SECONDS


def test_the_configured_value_lands_as_the_literal_timeout_of_the_proof_grade_node() -> None:
    """The resolved seconds are WRITTEN IN, and read back off the rendered artifact.

    Read back rather than re-derived from the configuration, which is the whole
    point of Scenario 89: the pinned engine types a quoted duration at PARSE time
    and the template expansion never re-types what it rendered, so a templated
    timeout yields a STRING the node's accessor does not answer for and the node
    runs with NO TIMEOUT AT ALL, silently.

    The DEFAULTED rendering is the control. Without it, "the node carries 1234s"
    is equally consistent with a graph that happens to spell 1234s as its
    committed literal, which the rewrite would then have left untouched.
    """
    committed = _graph_text()
    configured = node_timeouts_from_block(block={"node_timeouts": {_GRADE: _CONFIGURED_SECONDS}})
    defaulted = node_timeouts_from_block(block={})
    assert not isinstance(configured, str), configured
    assert not isinstance(defaulted, str), defaulted

    rendered = render_workflow_graph(committed_text=committed, timeouts=configured)
    control = render_workflow_graph(committed_text=committed, timeouts=defaulted)

    assert not isinstance(rendered, str), rendered
    assert not isinstance(control, str), control
    assert node_timeout_seconds(graph_text=rendered.text, node=_GRADE) == _CONFIGURED_SECONDS
    assert (
        node_timeout_seconds(graph_text=control.text, node=_GRADE) == DEFAULT_NODE_TIMEOUT_SECONDS
    )
    assert rendered.node_seconds[_GRADE] == _CONFIGURED_SECONDS
