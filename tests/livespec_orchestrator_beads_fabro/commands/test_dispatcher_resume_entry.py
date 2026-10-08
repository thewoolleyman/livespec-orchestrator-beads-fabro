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
entry can be wrong. The graph rewrite moves the `start` edge, which is what makes
`dod_gate` and `implement` unreachable rather than merely unvisited; the prepare
step puts the sandbox clone on the published head, which is what makes the stage
it enters at operate on the tree the records describe.

WHY THE REWRITE IS ASSERTED TO MOVE THE `start` EDGE AND NOT TO DELETE NODES. A
derivation that deleted `dod_gate` and `implement` would satisfy "no visit" and
break every edge pointing at them — `implement -> needs_human`,
`implementation_diff -> dead_implementer` — so the graph would stop validating.
Moving the one edge leaves every node declared and simply unreachable from
`start`, which is the minimum change that makes the clause's "no such visit" a
property of the graph rather than a hope about the engine.

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

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_resume_entry.py"
)

_HEAD = "a" * 40
_BRANCH = "feat/bd-ib-fngpwg"

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


def test_the_start_edge_is_moved_to_the_resumed_at_node() -> None:
    """`start -> dod_gate` becomes `start -> pr`, and nothing else moves."""
    module = _entry_module()
    derived = module.graph_entered_at(graph_text=_GRAPH, node="pr")
    assert derived is not None
    assert "start -> pr" in derived
    assert "start -> dod_gate" not in derived
    assert "dod_gate -> implement" in derived


def test_every_node_stays_declared_so_the_graph_still_validates() -> None:
    """Unreachable, never deleted: a deleted node breaks the edges pointing at it."""
    module = _entry_module()
    derived = module.graph_entered_at(graph_text=_GRAPH, node="pr")
    assert derived is not None
    for declaration in ("dod_gate [", "implement [", "pr ["):
        assert declaration in derived


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
