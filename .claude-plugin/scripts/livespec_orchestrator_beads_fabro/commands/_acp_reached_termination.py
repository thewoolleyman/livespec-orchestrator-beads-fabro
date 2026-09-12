"""A REACHED node whose chain is empty: terminate typed, before any adapter.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "A conditional repair or adjudication node may have an empty
filtered chain at preflight, but if reached it MUST terminate the run before
starting an adapter with the typed availability cause surfaced. It MUST NOT
traverse a continuation/failure edge into janitor, non-convergence, or
`needs_human`, and the Dispatcher MUST NOT reclassify it as deterministic work
failure."

WHY THIS IS A SEPARATE OUTCOME AND NOT A FAILED NODE. `fix`, `review_fix` and
`disposition` are conditional: a run reaches none of them when the work is
clean, so holding admission until their chains are viable would park healthy
work on an outage that may never be met. The price of admitting anyway is that
the run CAN arrive at a node with nothing to run, and the honest report of that
is "the provider entitlement this node needed is unavailable" -- not "the fix
attempt failed", which is what every edge out of those nodes says. Routing to
`janitor` would re-run the gate that was already Red; routing to
`non_converged` would claim a fix loop was exhausted when none ran; routing to
`needs_human` would ask a human to adjudicate a provider outage. All three
describe the work, and the work was never the problem.

THE FORBIDDEN SUCCESSORS ARE NAMED, NOT INFERRED. `FORBIDDEN_SUCCESSORS` is the
contract's own list, and `successor` is unconditionally `None` -- a termination
traverses no edge at all. Naming the three anyway makes the prohibition
assertable from outside rather than being a property of an absence, which is
what lets a test prove the rule instead of proving that nothing happened.

NOTHING HERE STARTS AN ADAPTER, AND NOTHING HERE CAN. The decision is a pure
function of the node's own preflight, taken from values recorded when each
candidate was skipped, so it is reachable before any process is spawned. S4
owns the runtime transition that consumes it; this slice owns the decision.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_candidate_preflight import (
    NodePreflight,
    SkippedCandidate,
)

__all__: list[str] = [
    "FORBIDDEN_SUCCESSORS",
    "TERMINATION_STAGE",
    "UNATTRIBUTED_CAUSE",
    "AcpChainExhaustedTermination",
    "reached_node_termination",
]

# The journal stage a reached empty chain terminates under. Distinct from every
# work-failure stage on purpose: a reader filtering the journal for work that
# failed must not sweep up a provider outage, and a reader looking for provider
# outages must not have to exclude work failures by hand.
TERMINATION_STAGE = "acp-chain-exhausted"

# The three routes the contract forbids by name.
FORBIDDEN_SUCCESSORS: tuple[str, ...] = ("janitor", "non_converged", "needs_human")

# What a termination reports when every skip was ephemeral -- a probe refusal
# carries a condition rather than a typed availability cause, and inventing one
# of the eight typed causes to fill the field would make an ephemeral local
# fault indistinguishable from an observed provider outage.
UNATTRIBUTED_CAUSE = "unattributed"


@dataclass(frozen=True, kw_only=True)
class AcpChainExhaustedTermination:
    """The typed terminal a reached empty chain produces."""

    node: str
    cause: str
    scope: str | None
    hold_key: str | None
    candidate_key: str | None
    skipped: tuple[SkippedCandidate, ...]

    @property
    def stage(self) -> str:
        """The journal stage this terminal is recorded under."""
        return TERMINATION_STAGE

    @property
    def successor(self) -> None:
        """No edge is traversed: the run terminates at this node."""
        return None

    @property
    def is_deterministic_work_failure(self) -> bool:
        """Always false -- the work never ran, so it cannot have failed."""
        return False

    @property
    def detail(self) -> str:
        """The deterministic line naming the node, the cause and the skip count."""
        return (
            f"acp chain exhausted at node {self.node}: no candidate remains "
            f"(cause={self.cause}, {len(self.skipped)} skipped); "
            "terminating before adapter startup"
        )


def reached_node_termination(*, preflight: NodePreflight) -> AcpChainExhaustedTermination | None:
    """The terminal for a REACHED node, or `None` when a candidate remains.

    The cause is taken from the FIRST skipped candidate carrying a typed one --
    configured order, so that is the primary's cause when the primary was
    held -- because that is the entitlement the node was configured to prefer
    and the one an operator will act on.
    """
    if not preflight.exhausted:
        return None
    for skip in preflight.skipped:
        cause = skip.cause
        if cause is not None:
            return AcpChainExhaustedTermination(
                node=preflight.node,
                cause=cause,
                scope=skip.scope,
                hold_key=skip.hold_key,
                candidate_key=skip.candidate_key,
                skipped=preflight.skipped,
            )
    return AcpChainExhaustedTermination(
        node=preflight.node,
        cause=UNATTRIBUTED_CAUSE,
        scope=None,
        hold_key=None,
        candidate_key=None,
        skipped=preflight.skipped,
    )
