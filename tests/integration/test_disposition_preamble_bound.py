"""The disposition node's prompt is bounded independently of the review's context.

Work-item bd-ib-7zxqyl. Measured 2026-10-14 on the hp-candidate Petri-era
engine, run 01M4XNM4BBMYFPQDA6X5JCBDYM (plugin v0.196.12): `review` SUCCEEDED
with blocking findings and `disposition` then FAILED before deciding anything,
its ACP prompt rejected with `Internal error: Prompt is too long`
(`errorKind invalid_request`). The run's `attractor.thread` events show every
agent node carrying the DEFAULT `compact` fidelity, so disposition's preamble
was a compact carry of a review turn that had itself reported about 361000
tokens of context — against the 200000-token window of disposition's configured
`claude-sonnet-4-6`. Every Petri-era run whose review context outgrows that
window could therefore never reach a disposition decision.

WHY THE NODE ATTRIBUTE IS THE SUBJECT AND NOT A PROMPT EDIT. Fabro's documented
fidelity modes (docs.fabro.sh/execution/context) split into two families, and
only one of them is bounded. `full` injects no preamble at all and continues the
SAME conversation thread, so it carries the complete prior context; `compact`
--- the default --- is a nested-bullet summary with handler-specific details and
declares NO size target, so its size grows with the volume of the stages behind
it. `summary:high`, `summary:medium` (~1500 tokens) and `summary:low` (~600
tokens) are summarizations with a TARGET, which is the property the Definition
of Done asks for: a preamble whose size does not scale with how large the review
stage's context grew. `truncate` carries only the goal and the run id.

WHY A BOUNDED PREAMBLE STILL LEAVES DISPOSITION ABLE TO DECIDE. The review
stage's verdict and findings do NOT reach disposition through the preamble.
`review` persists them into the run-context key `review_findings_r<N>` through
its routing JSON's `context_updates`, and the disposition prompt is required to
read that key and to fail closed when it is absent. Context updates are merged
into the shared run context regardless of fidelity mode, so bounding the
preamble narrows what disposition is TOLD ABOUT the prior stages without
touching the dataflow it adjudicates from. That is why the second case here
asserts the two halves of that key agree: a bounded preamble is only safe while
the findings travel by the route the prompt actually reads.
"""

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_workflow_graph import parse_workflow_graph

_BUNDLE = Path(".claude-plugin/.fabro/workflows/implement-work-item")

# The fidelity modes that carry a size TARGET, so a node declaring one of them
# has a preamble whose size does not grow with the stages behind it.
_BOUNDED_FIDELITIES = ("summary:high", "summary:medium", "summary:low", "truncate")

# The two modes whose size scales with the prior context: `full` continues the
# same thread with everything in it, and `compact` --- the DEFAULT, and what the
# measured run carried --- declares no target at all.
_UNBOUNDED_FIDELITIES = ("full", "compact")

# The run-context key the review stage writes its findings to and the
# disposition stage reads them from. Spelled without the round suffix because
# both prompts template that suffix per round.
_FINDINGS_KEY = "review_findings_r"


def _graph_text() -> str:
    return (_BUNDLE / "workflow.fabro").read_text(encoding="utf-8")


def test_disposition_declares_a_bounded_preamble_no_edge_can_restore() -> None:
    """The node's own fidelity is a size-targeted one, and nothing overrides it.

    The incoming-edge half is not decoration: an edge-level `fidelity` outranks
    the node's in Fabro, so a node correctly declaring a bounded mode is still
    served a compact preamble when the edge that reached it says so. `review` is
    asserted to BE a predecessor first, because an edge scan over a node nothing
    routes to finds no offenders and reports clean.
    """
    text = _graph_text()
    graph = parse_workflow_graph(text=text)

    assert "disposition" in graph.successors(node="review")
    disposition = next(node for node in graph.nodes if node.name == "disposition")
    declared = disposition.attributes.get("fidelity")
    assert declared in _BOUNDED_FIDELITIES, declared
    assert declared not in _UNBOUNDED_FIDELITIES, declared

    sources = graph.predecessors(node="disposition")
    assert "review" in sources
    incoming = [
        line
        for line in text.splitlines()
        if line.strip().startswith(tuple(f"{source} -> disposition" for source in sources))
    ]
    assert incoming
    assert all(
        "fidelity=" not in edge or f'fidelity="{declared}"' in edge for edge in incoming
    ), incoming


def test_the_review_findings_reach_disposition_through_the_run_context_key() -> None:
    """The verdict and findings travel by `context_updates`, not by the preamble.

    Both halves are asserted together because either alone is vacuous: a review
    stage persisting a key nothing reads, and a disposition stage reading a key
    nothing writes, each satisfy a one-sided check while the dataflow is broken.
    """
    # Both prompts are hard-wrapped, so every whitespace run is collapsed before
    # matching: a needle straddling a line break fails while the prose says
    # exactly the thing, which is a probe that can only fail silently.
    review = " ".join((_BUNDLE / "prompts" / "review.md").read_text(encoding="utf-8").split())
    disposition = " ".join(
        (_BUNDLE / "prompts" / "disposition.md").read_text(encoding="utf-8").split()
    )

    assert "context_updates" in review
    assert _FINDINGS_KEY in review
    assert _FINDINGS_KEY in disposition
    assert "do NOT scrape raw Fabro event logs" in disposition
    assert '"outcome": "failed"' in disposition
