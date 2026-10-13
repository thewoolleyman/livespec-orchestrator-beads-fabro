"""Which ACP nodes a SUBMITTED graph might run -- the admission-required set.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "The admission-required set is wider: every ACP node potentially
reachable in the submitted graph is admission-required, success-critical or
not. Before submission, every ACP node potentially reachable in the submitted
graph MUST have an eligible candidate. A node proven unreachable in that graph
imposes no candidate requirement. ... It MUST NOT render or start a candidate
covered by a live hold, including for conditional repair or adjudication
nodes."

REACHABILITY IS THE DEFINITION HERE, AND IT IS EXACTLY WHAT DOMINANCE IS NOT.
`_acp_success_critical` derives the nodes on EVERY green path, because that is
the set a run cannot reach its green terminal without. This derivation is the
set a run MIGHT have to run, which is strictly wider: `fix`, `review_fix` and
`disposition` dominate no green path -- a run that never goes Red reaches
`exit` without any of them -- and the engine still has to start their adapters
the moment one of them IS reached. Both sets are therefore computed and both
are carried, because the two questions have different consumers: the reached-
node termination and the attention surfaces read the dominators, and admission
reads this.

WHY THE WIDENING IS NOT MERELY CONSERVATISM. The pre-v127 dominator-only grade
admitted a dispatch whose `fix` chain was wholly held, and the run then paid
for `dod_gate`, `implement` and `janitor` before meeting the first Red and
terminating on a node whose adapter could never have started. The whole visit
was lost to a condition that was observable before the claim. So the narrower
set was not a cheaper approximation of this one; it was a gate that admitted
work the factory already knew it could not finish.

THE START NODE ARRIVES AS A PARAMETER, never re-derived here. Counting the
graph's two ends, and refusing the shapes that carry no single answer, belongs
to `derive_success_critical`: a second derivation of "which node is the start"
could disagree with the first, and the disagreement would be invisible because
each answer is individually well-formed. The caller grades the graph once and
hands this the start it resolved.

AN UNREACHABLE NODE IS NOT REQUIRED, which is the clause's own sentence and
also why this reads the edges rather than `graph.acp_names` alone. A variant
that declares a node and never points at it imposes no candidate requirement,
so a grade over every declared ACP node would refuse dispatches on a chain no
submitted graph can reach.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._acp_success_critical import reachable_from
from livespec_orchestrator_beads_fabro.commands._acp_workflow_graph import WorkflowGraph

__all__: list[str] = [
    "derive_admission_required",
]


def derive_admission_required(*, graph: WorkflowGraph, start: str) -> tuple[str, ...]:
    """Every ACP node this graph can reach from `start`, in declaration order.

    Declaration order rather than discovery order, so a refusal naming the
    nodes reads in the order an operator sees them in the committed file --
    the same ordering guarantee `derive_success_critical` makes about the
    dominator set it returns.
    """
    reachable = frozenset(reachable_from(graph=graph, start=start))
    acp = graph.acp_names
    return tuple(name for name in graph.names if name in acp and name in reachable)
