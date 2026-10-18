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

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
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
_ROUTE = "proof_grade_route"
_VERIFY = "proof_verify"
_REVIEW = "review"
_FIX = "fix"
_NON_CONVERGED = "non_converged"

# The one value the case configures, chosen so it can equal neither the
# fully-defaulted resolution nor any literal the committed graph happens to
# carry: a figure that collided with either would pass for a node whose timeout
# nothing resolved.
_CONFIGURED_SECONDS = 1234


def _graph_text() -> str:
    return _GRAPH.read_text(encoding="utf-8")


def _edges() -> tuple[tuple[str, str, str], ...]:
    """Every edge of the committed graph as (source, target, condition).

    Read through the PRODUCTION graph reader rather than a regular expression
    here: a reader of this module's own would be a second account of the DOT
    grammar, and the way that fails is that it silently drops an edge — a route
    never offered an alternative looks exactly like a route that rejected it.
    """
    parsed = parse_dot_graph(text=_graph_text())
    assert not isinstance(parsed, str), parsed
    return tuple(
        (edge.source, edge.destination, edge.attributes.get("condition", ""))
        for edge in parsed.edges
    )


def _targets(*, source: str) -> list[tuple[str, str]]:
    """One node's outgoing (target, condition) pairs, in declaration order."""
    return [(target, condition) for one, target, condition in _edges() if one == source]


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


def test_a_grade_failure_re_enters_proof_verify_through_its_own_route_node() -> None:
    """The retry path is `proof_grade_route -> proof_verify`, and nothing else.

    The clause is explicit that "A retry through `proof_grade_route` re-enters
    `proof_verify` DIRECTLY, visits neither `review` nor `fix`, and is charged to
    neither the review-fix budget nor `fix`'s visit cap". That is a claim about
    the GRAPH, so it is read off the committed edges: a route that reached the
    replay by way of `review` would re-review a tree nobody changed and would
    spend one of the three review rounds an item gets for actual findings, while
    one that reached it by way of `fix` would send an implementer to repair code
    the replay already reproduced.

    DIRECTNESS is asserted as the ABSENCE of the two forbidden targets as well as
    the presence of the right one, because "there is an edge to `proof_verify`"
    would be satisfied just as well by a node that also routed to `review` — and
    on this engine an unconditional edge beside a conditional one is reached
    whenever the condition does not match.
    """
    onward = _targets(source=_ROUTE)

    assert (_VERIFY, "") in onward, onward
    assert [target for target, _ in onward if target in (_REVIEW, _FIX)] == []
    assert [target for target, _ in _targets(source=_GRADE) if target == _ROUTE] == [_ROUTE]


def test_the_grade_routes_an_ungradeable_record_to_its_route_node_and_nothing_else() -> None:
    """The failure edge leads to the route node, and the advance stays unconditional.

    Both halves are the assertion, and the second is what keeps the engine
    loading the graph at all: a command node whose every outgoing edge carries a
    condition is rejected outright before anything runs
    (`all_conditional_edges`), which took the whole factory down twice. So the
    ungradeable record is the NAMED exception and `pr_refresh` is the
    fallthrough — never the other way round, which would publish every
    unreadable grade.
    """
    onward = _targets(source=_GRADE)

    assert (_ROUTE, "outcome=failed") in onward, onward
    assert ("pr_refresh", "") in onward, onward
    assert [condition for _, condition in onward if condition == ""] == [""]
