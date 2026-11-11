"""Resolve the configured Definition-of-Done host-judge candidate chain."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_catalogs import resolve_acp_catalogs
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import WORKFLOW_LAYER
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_nodes import (
    host_dod_gate_resolution,
)

__all__: list[str] = ["dod_gate_candidates"]


def dod_gate_candidates(*, cwd: Path) -> tuple[AcpCandidate, ...] | None:
    """The resolved `dod_gate` primary followed by its configured fallbacks."""
    resolved = host_dod_gate_resolution(repo=cwd, catalog_resolver=resolve_acp_catalogs)
    if resolved is None:
        return None
    nodes, chains, workflow_agents = resolved
    chain = chains.chains.get("dod_gate")
    node = nodes.nodes.get("dod_gate")
    input_name = nodes.inputs.get("dod_gate")
    if chain is None or node is None or input_name is None:
        return None
    primary = chain.primary
    if primary.agent_id is None and node.command_layer == WORKFLOW_LAYER:
        agent_id = workflow_agents.get(input_name)
        if agent_id is not None:
            primary = replace(primary, agent_id=agent_id)
    return None if primary.agent_id is None else (primary, *chain.fallbacks)
