"""Attach each ACP node's candidate chain to its resolved primary."""

from __future__ import annotations

from collections.abc import Mapping

from livespec_orchestrator_beads_fabro.commands._acp_builtin_candidates import (
    builtin_acp_identities,
)
from livespec_orchestrator_beads_fabro.commands._acp_catalogs import AcpCatalogs
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import (
    AcpChainResolution,
    attach_acp_chains,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpNodeOverlay
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import AcpNodeResolution
from livespec_orchestrator_beads_fabro.commands._acp_node_repository import repository_acp_chains

__all__: list[str] = ["resolve_chains"]


def resolve_chains(
    *,
    block: dict[str, object],
    catalogs: AcpCatalogs,
    resolution: AcpNodeResolution,
    dispatch: Mapping[str, AcpNodeOverlay],
    workflow_inputs: Mapping[str, str],
) -> AcpChainResolution | str:
    """Attach each node's candidate chain to its resolved primary, or refuse.

    The chain is attached STRICTLY AFTER `resolve_acp_nodes` has finished,
    which is the ordering `SPECIFICATION/contracts.md` section
    "Factory-configurable ACP fallback priority" requires: candidate zero
    comes through the existing layers first, and identity or fallback
    metadata may only attach to what those layers produced.

    The BLOCK and the CATALOGS are the caller's, resolved once for the whole
    dispatch. Re-reading them here would make the chain resolve against a
    second read of the same file, which nothing can prove agrees with the first
    -- and the disagreement would be invisible, because both reads produce a
    perfectly well-formed catalog.

    What comes back is the WHOLE attached resolution, because the caller
    needs two projections of it that must agree: the REDACTED structural
    record each new-grammar-enabled node journals, and the SELECTED
    candidate identity each node's run labels name. Returning one
    projection and re-deriving the other from a second attach would give
    the journal and the labels independent answers about which candidate
    one dispatch rendered, with nothing announcing the divergence.
    """
    declared = repository_acp_chains(block=block, catalogs=catalogs)
    if isinstance(declared, str):
        return declared
    attached = attach_acp_chains(
        resolution=resolution,
        chains=declared,
        dispatch=dispatch,
        builtins=builtin_acp_identities(workflow_inputs=workflow_inputs),
    )
    return attached
