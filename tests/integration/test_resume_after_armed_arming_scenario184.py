"""Where a resume enters after a run armed auto-merge and exited.

Scenario 184's "Resuming an overtaken armed pull request disarms it before
refreshing" sub-scenario, and the v145 "Armed pull request overtaken by the
default branch" clause that routes an operator there: the dispatch rests the
item at `blocked / needs-human`, the operator releases it and resumes, and
"the resumed run enters `pr_refresh` at the default branch's advanced tip".

WHY THE EXIT NODE IS THE CASE THAT MATTERS, AND WHY IT IS NOT THE RETIRED `pr`
ENTRY ALREADY HANDLED. The ending this clause exists for happens AFTER the run
finished: `pr` armed auto-merge, `pr_route` and `verify_pr` passed, the run
reached its terminal `exit`, and only then did a later default-branch commit
overtake the armed pull request. So the factory's own record — the newest
checkpoint's `next_node_id`, which is the precise source the resume prefers
whenever the factory still holds the run — names a node AT OR AFTER the
arming, and for the ordinary case of this ending it names the terminal. The
existing normalization corrects the retired `pr` entry and nothing else, so
every one of those answers is carried through unchanged.

WHAT THAT COSTS, WHICH IS WHY THIS IS ITS OWN MODULE. Each post-arming node
reached directly by a resumed run is a different wrong outcome and none of
them is loud. Entering `exit` terminates the run immediately: the dispatch
reports a green resume, the pull request is still armed, still conflicting,
and nothing disarmed or refreshed it — the operator's recovery chain ran to
completion and changed nothing. Entering `verify_pr` verifies that the branch
is published, which it is, and exits the same way. Entering `pr_route`
consumes a marker no `pr` visit of the resumed run wrote and falls through to
`verify_pr`. All three skip the one thing the clause requires of the resumed
run, which is `pr_refresh`'s disarm before any rebase.

THE POST-ARMING SET IS DERIVED FROM THE COMMITTED GRAPH, never listed here.
A literal list is a second account of the publication tail, and the defect it
would hide is the one this module is about: a node added to that tail later
would be absent from the list, carried through unnormalized, and resume into
exactly the silent no-op above.

THE DERIVATION IS "ON A PATH FROM `pr` TO THE SUCCESS TERMINAL", and that
phrasing is load-bearing rather than one way of saying reachability. A forward
walk filtered on edge POLARITY cannot express it, because the committed graph
uses both polarities on this tail: `pr`'s refusal carries
`condition="outcome=failed"` while `verify_pr`'s refusal is the UNCONDITIONAL
fallback its conditional success edge outranks. A "non-failure edges" walk
therefore drags `needs_human` in — a terminal that preserves work and ends the
run, which a resume never re-enters and which must NOT normalize, because the
many needs-human endings that are not about an armed pull request would then
resume straight into publication. Pathfinding to `exit` answers it with no
special-casing, since nothing downstream of a terminal leads anywhere.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_VERIFIED,
    ProofRecord,
)

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor"

_IMPLEMENT_GRAPH = Path(".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro")

# Spelled as LITERALS rather than read off the module under test, so no
# assertion below can be satisfied by a constant compared with itself.
_PR = "pr"
_PR_REFRESH = "pr_refresh"
_SUCCESS_TERMINAL = "exit"
_HEAD = "f4e0538675a6a27767a0fe92c3f992239c388da5"

# The preservation terminal, named so the instrument case can assert it is OUT
# of the derived chain. A resume never re-enters it, and the many needs-human
# endings that have nothing to do with an armed pull request would resume
# straight into publication if it normalized.
_PRESERVATION_TERMINAL = "needs_human"

# Nodes BEFORE the arming, which must be carried through UNCHANGED. Without
# them a normalizer answering `pr_refresh` for every input would satisfy every
# positive assertion in this module while sending a run that died in `review`
# to publication with its findings unanswered.
_PRE_ARMING_NODES = ("proof_capture", "review", "proof_verify", "fix", "janitor")


def _anchor_module() -> Any:
    return importlib.import_module(_MODULE_NAME)


def _graph() -> Any:
    graph = parse_dot_graph(text=_IMPLEMENT_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    return graph


def _reaches_success_terminal(*, graph: Any) -> frozenset[str]:
    """Every node with some path to the success terminal, walked backward from it."""
    found: set[str] = set()
    frontier = [_SUCCESS_TERMINAL]
    while frontier:
        node = frontier.pop()
        if node in found:
            continue
        found.add(node)
        frontier.extend(edge.source for edge in graph.edges if edge.destination == node)
    return frozenset(found)


def _post_arming_nodes() -> frozenset[str]:
    """The onward publication chain from `pr`, as the committed graph declares it.

    `pr` itself is included, because it is the node that ARMS and a resume
    entering it reads a published head out of refresh provenance the resumed
    run has not established. `_SUCCESS_TERMINAL` is included for the mirror
    reason: it is where an armed run that published actually ends, so it is the
    answer the factory's own record carries for the ordinary case of this
    ending.

    TWO EDGE FILTERS, because the tail's two refusals do not share a shape and
    neither filter alone is enough. A `condition="outcome=failed"` edge is a
    REFUSAL rather than a step along the chain, which drops both `pr`'s route
    to the preservation terminal and `pr_route`'s route BACK to `pr_refresh` —
    the second being why this walk does not swallow the whole refresh loop. And
    an edge whose destination cannot reach the success terminal leads out of
    the chain whatever its polarity, which is what drops `verify_pr`'s
    unconditional fallback to that same terminal.
    """
    graph = _graph()
    onward = _reaches_success_terminal(graph=graph)

    # A FIXPOINT rather than a worklist, so the walk carries no
    # already-visited guard: the chain is a straight line, so such a guard is a
    # branch no graph can take, and a per-file coverage gate reads an
    # untakeable branch in a fixture exactly as it reads one in the product.
    chain = frozenset({_PR})
    while True:
        grown = chain | {
            edge.destination
            for edge in graph.edges
            if edge.source in chain
            and edge.attributes.get("condition") != "outcome=failed"
            and edge.destination in onward
        }
        if grown == chain:
            return chain
        chain = grown


def test_the_publication_tail_this_module_is_about_is_the_shape_it_expects() -> None:
    """The derivation is the test's own instrument, so it is checked first.

    An empty or near-empty set would make every assertion below vacuous, and
    the vacuous version passes. `pr_refresh` must NOT be in it: the node the
    normalization answers with cannot also be one of the nodes it rewrites, or
    the rule would be circular and a resume could never reach the refresh.
    """
    tail = _post_arming_nodes()

    assert _PR in tail
    assert _SUCCESS_TERMINAL in tail
    assert _PR_REFRESH not in tail
    assert _PRESERVATION_TERMINAL not in tail
    # The arming node plus the breaker chain behind it. More than one, because a
    # derivation that stopped at `pr` would make this module assert only what
    # the existing normalization already does.
    assert len(tail) >= 3, sorted(tail)
    for pre_arming in _PRE_ARMING_NODES:
        assert pre_arming not in tail, pre_arming


def test_every_post_arming_node_normalizes_to_pr_refresh() -> None:
    """The assertion: a resume anchored at or after the arming enters the refresh.

    Graded over the whole derived tail rather than over the terminal alone,
    because the three post-arming answers are reached by the same reader and
    differ only in which node the earlier run's newest checkpoint happened to
    name.
    """
    module = _anchor_module()

    for node in sorted(_post_arming_nodes()):
        assert module.normalized_entry_node(node=node) == _PR_REFRESH, node


def test_a_node_before_the_arming_is_carried_through_unchanged() -> None:
    """The control: normalization is a correction, not a redirect of everything."""
    module = _anchor_module()

    for node in _PRE_ARMING_NODES:
        assert module.normalized_entry_node(node=node) == node, node


def test_the_terminal_anchor_of_an_armed_run_resumes_at_the_refresh() -> None:
    """End to end through the reader a resume actually calls.

    `resume_anchor` is what the resume observation consumes, and it is the
    layer where the factory's answer outranks the verdict fallback — so a
    normalization applied only to the fallback would leave the ordinary case
    of this ending, where the factory still holds the exited run, entering the
    terminal.
    """
    module = _anchor_module()
    record = ProofRecord(
        verdict=VERDICT_VERIFIED,
        run_id="01M509QRWWNKK6H8VK865JGFC9",
        timestamp="2026-10-15T23:00:00Z",
        url="https://example.invalid/c/1",
        body=f"Publish-branch head: {_HEAD}\n",
    )

    # The terminal is the node the chain ends at, taken off the chain itself
    # rather than named again here, so this case cannot pass for a tail whose
    # end moved.
    graph = _graph()
    sources = {edge.source for edge in graph.edges}
    terminal = next(node for node in sorted(_post_arming_nodes()) if node not in sources)
    assert terminal == _SUCCESS_TERMINAL
    anchor = module.resume_anchor(records=[record], executing_node=terminal)

    assert anchor is not None
    assert anchor.resumed_at == _PR_REFRESH
    assert anchor.head == _HEAD
    assert anchor.source == module.SOURCE_FACTORY_RUN


def test_the_normalized_target_is_a_node_the_committed_graph_declares() -> None:
    """A normalization naming a node the graph does not declare refuses at dispatch."""
    graph = _graph()

    assert _PR_REFRESH in graph.nodes
