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

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_capability_gate import (
    acp_capability_refusal,
)
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
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget

__all__: list[str] = [
    "SelectedAcpNodes",
    "factory_name",
    "select_acp_node_adapters",
    "select_and_gate_acp_node_adapters",
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
    rendered = resolution_with_adapters(
        resolution=resolution,
        adapters={node: one.candidate.adapter for node, one in selected.items()},
    )
    if isinstance(rendered, str):
        return rendered
    return SelectedAcpNodes(resolution=rendered, selected=selected)


def factory_name(*, factory: FactoryTarget | None) -> str:
    """The resolved factory's name for a refusal message.

    A dispatch path always pins one; the fallback covers the non-dispatching
    entry points that reach this code with a Namespace that never carried it,
    so a refusal names something rather than crashing on `None`.
    """
    return "(unresolved)" if factory is None else factory.name


def select_and_gate_acp_node_adapters(
    *,
    resolution: AcpNodeResolution,
    chains: AcpChainResolution,
    verdict: AcpPreflightVerdict | None,
    factory_name: str,
    capabilities: Callable[[], frozenset[str] | None],
) -> SelectedAcpNodes | str:
    """Choose each node's candidate, then refuse one the factory cannot configure.

    WHICH candidate of each node's chain this dispatch renders, folded onto the
    finished resolution rather than resolved beside it, so the launch reads the
    adapters from the same object the record was projected from. A launch that
    selected its own would be a second read of one configuration, and the
    disagreement would be invisible: both reads produce a perfectly well-formed
    candidate.

    THE CAPABILITY GATE SITS HERE, AFTER THE SELECTION, because the one
    remaining engine capability gates the candidate this dispatch RENDERS: an
    unselected fallback's `config_options` is a request no engine is asked to
    honour here, so gating on it would refuse a dispatch that would have run
    correctly. It is still before any Fabro run exists, exactly as every other
    refusal in this seam is -- the move is a few lines within one pre-run
    function, so nothing about its position relative to the claim changes.

    ONE reader, built here and passed in, so the dispatch issues at most one
    `GET /system/info` however many nodes are in question.
    """
    selected = select_acp_node_adapters(resolution=resolution, chains=chains, verdict=verdict)
    if isinstance(selected, str):
        return selected
    uncapable = acp_capability_refusal(
        selected=selected.selected,
        factory_name=factory_name,
        capabilities=capabilities,
    )
    if uncapable is not None:
        return uncapable
    return selected
