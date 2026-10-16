"""What the pruned graph a resumed run is handed must be true of, as a graph.

The sibling `test_dispatcher_resume_entry` asserts the DERIVATION — which stage
the run enters at, which declarations the prune removes, which inputs refuse.
This file asserts the properties the PRODUCT of that derivation has to hold,
because they are what the engine's own validator grades and they are not
implied by any one of the derivation's steps.

The two are different claims, and the gap between them is where this slice's
defect lived. Removing a declaration satisfies "declares no unreachable node"
on its own; every edge that pointed AT the removed node is still written down,
naming a node the graph no longer has. On the pinned 0.254 engine that is
accepted. It is not a graph anyone should hand a validator, and it is not what
`SPECIFICATION/contracts.md` section "Resume from a published pull request
(`resume --item`)" describes when it says the derived graph is the workflow
"entered at the resumed-at stage".

EVERY CASE READS THE DERIVED TEXT BACK THROUGH `parse_dot_graph`, never through
the derivation's own patterns. A prune computed from an edge set a scan had
under-read would agree with itself perfectly: the nodes it failed to see
reachable are exactly the ones it removed, so a check that re-used the same
scan would confirm the removal rather than notice the loss. The shared parser
tokenizes the grammar, so it is a second instrument and not the same answer
read twice.

THE SUBJECT IS THE COMMITTED GRAPH. The four nodes the live engine named —
`dod_gate`, `implement`, `implementation_diff`, `dead_implementer` — are
orphaned only through that graph's real edge set, including the
`implementation_diff -> dead_implementer` branch that no tidier fixture
carries, so a hand-authored stand-in cannot fail for the reason the dispatch
did.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry"

_IMPLEMENT_GRAPH = Path(".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro")

# The stages a resume actually enters at, and the two the clause names as the
# ones a resumed run must never reach.
_RESUMED_AT_STAGES = (
    "publish_draft",
    "proof_capture",
    "proof_verify",
    "pr_refresh",
)
_COMPLETED_STAGES = ("dod_gate", "implement")
_START_NODE = "start"

# The stages whose ORPHAN SET reaches a declaration whose attribute body carries a
# `]` inside a quoted value — `publish_draft`, whose script spells
# `${remote_line%%[[:space:]]*}`. Entering this late orphans that node, so these
# are the entries a body pattern ending at the first `]` cuts in half.
#
# Every one of them is reachable as a resumed-at stage. `executing_node_from_payload`
# answers the newest checkpoint's `next_node_id` for whatever node the engine was
# executing, and `normalized_entry_node` rewrites only `pr`, returning "every other
# node UNCHANGED rather than validated against the graph" — so a run that died
# inside `verify_pr`, or that ended at a terminal sentinel, names it here.
_LATE_STAGES = ("verify_pr", "needs_human", "non_converged", "dead_implementer", "exit")

# A stage no workflow in this repository declares, standing in for the stage a
# factory run record names when the earlier run ran a different variant.
_UNDECLARED_STAGE = "triage_findings"

# A graph whose `b -> z` edge names a node nothing declares. The derivation may
# not emit one of these, so it must refuse rather than pass one on: an endpoint
# the graph does not declare is the same class of fault as an unreachable
# declaration, and the engine grades both.
_IMPLICIT_NODE_GRAPH = """digraph Implicit {
    graph [
        goal="one"
        stall_timeout="7200s"
    ]

    start [shape=Mdiamond, label="Start"]
    a [label="a", timeout="1800s"]
    b [label="b", timeout="1800s"]

    start -> a
    a -> b
    b -> z
}
"""


def _derived(*, node: str) -> str:
    """The committed graph derived for one resumed-at stage, proved non-None."""
    module: Any = importlib.import_module(_MODULE_NAME)
    derived = module.graph_entered_at(
        graph_text=_IMPLEMENT_GRAPH.read_text(encoding="utf-8"), node=node
    )
    assert derived is not None, node
    return derived


def _parsed(*, text: str) -> Any:
    """The derived text read back through the shared parser, proved parseable."""
    graph = parse_dot_graph(text=text)
    assert not isinstance(graph, str), graph
    return graph


def test_every_edge_of_the_derived_graph_names_a_node_it_declares() -> None:
    """A surviving edge pointing at a pruned node is a graph nobody wrote."""
    for node in _RESUMED_AT_STAGES:
        graph = _parsed(text=_derived(node=node))
        endpoints = {
            endpoint for edge in graph.edges for endpoint in (edge.source, edge.destination)
        }
        assert endpoints <= set(graph.nodes), (node, sorted(endpoints - set(graph.nodes)))


def test_the_derived_graph_enters_at_the_resumed_at_stage() -> None:
    """`start`'s one route is the stage the resume was asked for."""
    for node in _RESUMED_AT_STAGES:
        graph = _parsed(text=_derived(node=node))
        assert [edge.destination for edge in graph.edges if edge.source == _START_NODE] == [node]


def test_the_derived_graph_mentions_neither_completed_stage_at_all() -> None:
    """Not merely unvisited: absent from the declarations AND from every edge."""
    for node in _RESUMED_AT_STAGES:
        graph = _parsed(text=_derived(node=node))
        named = set(graph.nodes) | {
            endpoint for edge in graph.edges for endpoint in (edge.source, edge.destination)
        }
        for completed in _COMPLETED_STAGES:
            assert completed not in named, (node, completed)


def test_an_undeclared_resumed_at_stage_is_refused_on_the_committed_graph() -> None:
    """The prune must not have made a previously-refused stage derivable.

    The refusal an operator READS — the payload message that names the stage,
    before any run exists — is asserted by the wiring sibling against a fixture.
    What is asserted here is that the COMMITTED graph still produces it: the
    prune added a reachability walk and a postcondition between the declaration
    test and the returned text, and a stage the workflow does not declare must
    still refuse at the first of those rather than reach either of the others.
    """
    module: Any = importlib.import_module(_MODULE_NAME)
    assert (
        module.graph_entered_at(
            graph_text=_IMPLEMENT_GRAPH.read_text(encoding="utf-8"), node=_UNDECLARED_STAGE
        )
        is None
    )


def test_a_graph_naming_an_undeclared_endpoint_is_refused() -> None:
    """The derivation emits a graph whose edges all resolve, or it emits none."""
    module: Any = importlib.import_module(_MODULE_NAME)
    assert module.graph_entered_at(graph_text=_IMPLICIT_NODE_GRAPH, node="a") is None


def test_a_stage_whose_orphan_carries_a_bracketed_script_still_derives() -> None:
    """A `]` inside a quoted attribute value must not end the body being pruned.

    The prune LOCATES each orphaned declaration by pattern and leaves the
    postcondition to catch what it fails to locate, so a body that ends at the
    first `]` fails CLOSED — which is the safe direction and is why no invalid
    graph ever reached the engine. It is still a refusal for work that should
    derive: the tail of the half-deleted script survives as graph syntax, the
    reparse fails, and the operator reads "declares no node 'verify_pr'" about a
    graph that declares it on line one of its own node list.

    Asserted as DERIVING rather than as "the reparse succeeds", because the
    refusal is indistinguishable at the payload surface from the genuinely
    undeclared stage the sibling case covers — and those two owe opposite
    remedies.
    """
    module: Any = importlib.import_module(_MODULE_NAME)
    committed = _IMPLEMENT_GRAPH.read_text(encoding="utf-8")
    for node in _LATE_STAGES:
        derived = module.graph_entered_at(graph_text=committed, node=node)
        assert derived is not None, node
        graph = _parsed(text=derived)
        assert [edge.destination for edge in graph.edges if edge.source == _START_NODE] == [node]
        endpoints = {
            endpoint for edge in graph.edges for endpoint in (edge.source, edge.destination)
        }
        assert endpoints <= set(graph.nodes), (node, sorted(endpoints - set(graph.nodes)))


def test_the_pruned_declaration_leaves_no_tail_of_its_own_script_behind() -> None:
    """The control that names the mechanism, not just the symptom.

    Without it, the case above could pass for any reason that made the reparse
    succeed. `[[:space:]` is the prefix of `publish_draft`'s bracketed shell
    idiom and occurs EXACTLY ONCE in the committed graph: a body pattern that
    stopped at the inner `]` deleted everything up to it and left the remainder —
    beginning `]*}` — standing in the derived text, so that fragment's absence is
    what distinguishes a whole-declaration prune from a reparse that happened to
    recover.

    The node's NAME is deliberately not asserted absent. The prune removes
    declarations and edges and preserves comments by design, and this graph
    discusses `publish_draft` in twenty-one of them, so a name search would fail
    against a correct derivation — the mirror of the trap the sibling module's
    docstring records, where a name present in both the derived graph and the
    original could never fail. The script fragment is the token that cannot
    survive unless the body was cut short.
    """
    module: Any = importlib.import_module(_MODULE_NAME)
    committed = _IMPLEMENT_GRAPH.read_text(encoding="utf-8")
    assert committed.count("[[:space:]") == 1
    derived = module.graph_entered_at(graph_text=committed, node="verify_pr")
    assert derived is not None
    assert "publish_draft" not in set(_parsed(text=derived).nodes)
    assert "[[:space:]" not in derived
