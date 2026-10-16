"""The dispatch-side step that turns a selection into the adapters a run gets.

Split from `_dispatcher_acp_nodes` by cohesion. That module ASSEMBLES the three
configuration layers -- workflow defaults, the repository table, the per-dispatch
argument -- and journals what resolved. This one answers the question that comes
strictly after: of the candidates each node declares, WHICH ONE does this
dispatch render, and what does the resolution look like once it does.

THE ORDER HERE IS THE CONTRACT'S ORDER, not a convenience. `SPECIFICATION/
contracts.md` section "Factory-configurable ACP fallback priority" opens with
"Resolve the primary before attaching the chain", and its "Per-node selection"
paragraph comes after both -- so the sequence is layer merge, chain attach,
selection, render. Selecting earlier would mean choosing between candidates one
of which had not finished resolving; rendering earlier would mean rendering a
candidate nobody had chosen.

THE SELECTION IS A PURE DECISION AND IT STAYS NEXT DOOR. `_acp_node_selection`
is handed the chains and the verdict and returns a position per node; this module
is what APPLIES that decision to the resolution a dispatch carries. Keeping the
two apart is what lets the decision be exercised across every state the clause
distinguishes without a repository on disk.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import AcpChainResolution
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import (
    AcpNodeResolution,
    resolution_with_adapters,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_selection import (
    SelectedAcpCandidate,
    select_acp_candidates,
)
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict

__all__: list[str] = [
    "SelectedAcpNodes",
    "select_acp_node_adapters",
]


@dataclass(frozen=True, kw_only=True)
class SelectedAcpNodes:
    """One dispatch's resolution once per-node selection has been applied.

    `selected` rides along beside the resolution because two surfaces downstream
    must agree about it -- the record that says which candidate ran, and the run
    labels that name its entitlement -- and a surface that re-derived the answer
    from a second selection would give the journal and the labels independent
    accounts of one dispatch, with nothing announcing the divergence.
    """

    resolution: AcpNodeResolution
    selected: Mapping[str, SelectedAcpCandidate]


def select_acp_node_adapters(
    *,
    resolution: AcpNodeResolution,
    chains: AcpChainResolution,
    verdict: AcpPreflightVerdict | None,
) -> SelectedAcpNodes | str:
    """Render each node's selected candidate as its adapter, or refuse.

    Returns the resolution the dispatch should carry, or the actionable refusal
    the selection produced -- which the caller reports as a failed dispatch
    before any Fabro run exists, exactly as every other pre-run refusal in this
    seam does.
    """
    selected = select_acp_candidates(chains=chains.chains, verdict=verdict)
    if isinstance(selected, str):
        return selected
    return SelectedAcpNodes(
        resolution=resolution_with_adapters(
            resolution=resolution,
            adapters={node: one.candidate.adapter for node, one in selected.items()},
        ),
        selected=selected,
    )
