"""Resolve the configured Definition-of-Done host-judge candidate chain."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_catalogs import resolve_acp_catalogs
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter
from livespec_orchestrator_beads_fabro.commands._acp_node_repository import (
    repository_acp_chains,
    repository_acp_overlays,
)
from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.errors import LivespecConfigUnreadableError

__all__: list[str] = ["dod_gate_candidates"]


def dod_gate_candidates(*, cwd: Path) -> tuple[AcpCandidate, ...] | None:
    """The resolved `dod_gate` primary followed by its configured fallbacks."""
    try:
        block = dispatcher_block(cwd=cwd)
    except LivespecConfigUnreadableError:
        return None
    catalogs = resolve_acp_catalogs(block=block)
    if isinstance(catalogs, str):
        return None
    overlays = repository_acp_overlays(block=block, catalogs=catalogs)
    chains = repository_acp_chains(block=block, catalogs=catalogs)
    if isinstance(overlays, str) or isinstance(chains, str):
        return None
    chain = chains.get("dod_gate")
    overlay = overlays.get("dod_gate")
    if chain is None or overlay is None or chain.agent_id is None or overlay.command is None:
        return None
    primary = AcpCandidate(
        adapter=AcpAdapter(
            command=overlay.command,
            env=overlay.env,
            args=() if overlay.args is None else overlay.args,
        ),
        agent_id=chain.agent_id,
    )
    return (primary, *chain.fallbacks)
