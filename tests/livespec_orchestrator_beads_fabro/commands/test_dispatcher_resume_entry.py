"""How one resumed run enters at its unfinished stage, on the published head.

`SPECIFICATION/contracts.md` section "Resume from a published pull request
(`resume --item`)" says the resumed run "MUST run the workflow the earlier run's
dispatch record names, with a sandbox that checks out the publish branch at the
published head, entered at the resumed-at stage; it MUST NOT visit `dod_gate`,
`implement`, or any other node the earlier run completed". It then names the
latitude: "Whether the engine is entered at the resumed-at node directly or
through a graph the Dispatcher derives from that workflow for the one run is
implementation surface", and bounds it — "a derived graph is not a registered
variant, is never selectable by the variant precedence, and is never recorded as
the item's workflow."

THIS MODULE IS THAT DERIVATION, and the two halves it owns are the two ways the
entry can be wrong. The graph rewrite moves the `start` edge and PRUNES what that
move orphans, which is what makes `dod_gate` and `implement` absent rather than
merely unvisited; the prepare step puts the sandbox clone on the published head,
which is what makes the stage it enters at operate on the tree the records
describe.

WHY THE REWRITE IS ASSERTED TO PRUNE THE ORPHANED NODES AND NOT MERELY TO LEAVE
THEM DECLARED. Moving the one edge and leaving every node declared was the
earlier shape here, and it was accepted by the pinned 0.254 engine. The Petri-era
engine's graph validator REJECTS it: measured 2026-10-15T23:36Z against the
hp-candidate server, a `resume --item` died at run-create with
`attractor.unreachable_node: dod_gate is not reachable from the start node`, and
three further nodes named the same way, so no run was ever created. A declared
node with no route from `start` is therefore not a harmless leftover, and these
cases assert the derived graph declares none — the clause's "no such visit"
becomes a property of the graph on BOTH engines rather than a hope about either.

WHY THE COMMITTED GRAPH IS THE SUBJECT OF THAT CASE. The derivation is asserted
against `.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro`
itself, read with `parse_dot_graph` rather than with the derivation's own
patterns: the four nodes the engine named are reachable only through that graph's
real edge set, and a hand-authored fixture carrying a tidier shape cannot fail
for the reason the live dispatch did.

WHY AN UNDECLARED NODE REFUSES. The resumed-at stage can arrive from a factory
run record, which names whatever node that engine was executing — including a
node this workflow does not have, if the earlier run ran a different variant.
Rewriting `start` to point at an undeclared name produces a graph that fails
validation at run-create time, which reads as a Dispatcher fault; refusing here
names the real one, before any run exists.

WHY THE CHECKOUT IS A FETCH OF THE BRANCH AND A RESET TO THE HEAD. Fetching the
SHA alone is not reliably permitted by a forge (`uploadpack.allowReachableSHA1InWant`
is off by default), so the branch is fetched and the head is then checked out from
it — which also proves the head is on that branch rather than merely reachable
somewhere. And the step must FAIL the run when it cannot land: a prepare step that
swallowed the failure would run the resumed stage against whatever the clone
happened to carry, which is the default branch, and publish a `verified` record
for a tree nobody proved.

WHY NO CHECKOUT RENDERS FOR AN ORDINARY DISPATCH. Every dispatch shares this
overlay path, so the no-resume case must render the empty string — byte-for-byte
what the overlay carried before this existed.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_resume_entry.py"
)

_HEAD = "a" * 40
_BRANCH = "feat/bd-ib-fngpwg"

_IMPLEMENT_GRAPH = Path(".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro")
# The stages a resume actually enters at: `pr_refresh` is what an earlier `pr`
# normalizes to, and the other three are the post-implement stages a run that
# died after publishing reports. Each is exercised because the orphaned set
# differs per entry, and a single stage would prove the prune for one shape only.
_RESUMED_AT_STAGES = (
    "publish_draft",
    "proof_capture",
    "proof_verify",
    "pr_refresh",
)
_START_NODE = "start"

_GRAPH = """digraph ImplementWorkItem {
    graph [
        goal="Implement one ready work-item"
        stall_timeout="7200s"
    ]

    start [shape=Mdiamond, label="Start"]
    dod_gate [
        label="Definition-of-Done gate"
        timeout="1800s"
    ]
    implement [
        label="Implement"
        timeout="14400s"
    ]
    pr [
        label="Publish"
        timeout="1800s"
    ]

    start -> dod_gate

    dod_gate -> needs_human [label="Blocked", condition="outcome=failed"]
    dod_gate -> implement
    implement -> pr
}
"""


def _entry_module() -> Any:
    """Import the resume-entry derivation, proving the file exists first."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


def _reachable(*, graph: Any) -> set[str]:
    """Every name a walk from `start` arrives at, over the PARSED edge set.

    Walked here rather than asked of the derivation, so the case is a second
    instrument and not the derivation's own answer read back: a prune computed
    from an edge set a scan had under-read would agree with itself exactly.
    """
    reached = {_START_NODE}
    frontier = [_START_NODE]
    while frontier:
        source = frontier.pop()
        for edge in graph.edges:
            if edge.source == source and edge.destination not in reached:
                reached.add(edge.destination)
                frontier.append(edge.destination)
    return reached


def test_the_start_edge_is_moved_to_the_resumed_at_node() -> None:
    """`start -> dod_gate` becomes `start -> pr`, and the resumed node survives."""
    module = _entry_module()
    derived = module.graph_entered_at(graph_text=_GRAPH, node="pr")
    assert derived is not None
    assert "start -> pr" in derived
    assert "start -> dod_gate" not in derived
    assert "pr [" in derived


def test_the_orphaned_declarations_are_pruned_rather_than_left_unreachable() -> None:
    """A node with no route from `start` is what the Petri-era validator rejects."""
    module = _entry_module()
    derived = module.graph_entered_at(graph_text=_GRAPH, node="pr")
    assert derived is not None
    for declaration in ("dod_gate [", "implement ["):
        assert declaration not in derived


def test_the_committed_graph_derives_with_no_unreachable_declared_node() -> None:
    """Every stage a real resume enters at, read back with the shared parser."""
    module = _entry_module()
    committed = _IMPLEMENT_GRAPH.read_text(encoding="utf-8")
    for node in _RESUMED_AT_STAGES:
        derived = module.graph_entered_at(graph_text=committed, node=node)
        assert derived is not None, node
        graph = parse_dot_graph(text=derived)
        assert not isinstance(graph, str), graph
        assert _reachable(graph=graph) == set(graph.nodes), node


def test_a_graph_the_shared_parser_refuses_is_not_derived_from() -> None:
    """A graph nobody can read is a refusal, not a text edit taken on faith."""
    module = _entry_module()
    unreadable = _GRAPH.replace("    pr [", "    subgraph cluster_pr {}\n    pr [")
    assert module.graph_entered_at(graph_text=unreadable, node="pr") is None


def test_a_node_the_workflow_does_not_declare_refuses() -> None:
    """A stage name from another variant must not produce an invalid graph."""
    module = _entry_module()
    assert module.graph_entered_at(graph_text=_GRAPH, node="review_fix") is None


def test_a_graph_with_no_start_edge_refuses() -> None:
    """Nothing to move is a refusal, not a graph silently left as it was."""
    module = _entry_module()
    without = _GRAPH.replace("    start -> dod_gate\n", "")
    assert module.graph_entered_at(graph_text=without, node="pr") is None


def test_the_checkout_step_fetches_the_branch_and_checks_out_the_head() -> None:
    """The sandbox clone is put on the published head, from the publish branch."""
    module = _entry_module()
    block = module.resume_checkout_prepare_steps_block(
        checkout=module.ResumeCheckout(branch=_BRANCH, head=_HEAD)
    )
    assert "[[run.prepare.steps]]" in block
    assert f"refs/heads/{_BRANCH}" in block
    assert _HEAD in block


def test_the_checkout_step_fails_the_run_when_it_cannot_land() -> None:
    """A swallowed failure would prove a tree nobody published."""
    module = _entry_module()
    block = module.resume_checkout_prepare_steps_block(
        checkout=module.ResumeCheckout(branch=_BRANCH, head=_HEAD)
    )
    assert "set -e" in block


def test_no_resume_renders_no_checkout_step_at_all() -> None:
    """An ordinary dispatch's overlay is byte-for-byte what it always was."""
    module = _entry_module()
    assert module.resume_checkout_prepare_steps_block(checkout=None) == ""


def _committed_graph() -> str:
    """The repository's own `implement-work-item` graph, read from disk.

    Read rather than synthesized, because the claim asserted below is about THIS
    graph: a hand-written fixture would prove the derivation moves an edge and
    say nothing about whether the nodes the clause forbids are genuinely out of
    reach in the graph a resume actually runs.
    """
    graph = (
        Path(__file__).resolve().parents[3]
        / ".claude-plugin"
        / ".fabro"
        / "workflows"
        / "implement-work-item"
        / "workflow.fabro"
    )
    assert graph.is_file()
    return graph.read_text(encoding="utf-8")


def _reachable_from_start(*, graph_text: str) -> set[str]:
    """Every node a run of this graph can visit, walking edges out of `start`.

    REACHABILITY rather than a text search for the forbidden names: every node
    stays DECLARED in a derived graph — deleting one would break the edges
    pointing at it — so a name search finds `dod_gate` in both the derived graph
    and the original and could never fail.
    """
    edges: dict[str, set[str]] = {}
    for line in graph_text.splitlines():
        head, _, tail = line.partition("->")
        source = head.strip()
        target = tail.strip().partition("[")[0].strip().rstrip(";").strip()
        if not source.isidentifier() or not target.isidentifier():
            continue
        edges.setdefault(source, set()).add(target)
    seen: set[str] = set()
    frontier = ["start"]
    while frontier:
        node = frontier.pop()
        for target in edges.get(node, set()):
            if target not in seen:
                seen.add(target)
                frontier.append(target)
    return seen


def test_a_resume_entered_at_proof_capture_can_reach_neither_dod_gate_nor_implement() -> None:
    """Scenario 172: the resumed run enters at capture, and nothing precedes it.

    `janitor` is deliberately NOT asserted unreachable: the clause keeps the
    rework loop intact, so "a `review` that requests changes still re-enters
    `janitor`, `publish_draft` and `proof_capture` before `review`". What the
    clause forbids is a visit BEFORE the entry, which the single outgoing `start`
    edge settles.
    """
    module = _entry_module()
    derived = module.graph_entered_at(graph_text=_committed_graph(), node="proof_capture")
    assert derived is not None
    assert "start -> proof_capture" in derived
    assert "start -> dod_gate" not in derived
    reachable = _reachable_from_start(graph_text=derived)
    assert "proof_capture" in reachable
    assert "dod_gate" not in reachable
    assert "implement" not in reachable
