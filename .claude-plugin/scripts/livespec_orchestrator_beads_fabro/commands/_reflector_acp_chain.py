"""Ordered candidate selection for the reflector's ACP host judgement."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_catalogs import resolve_acp_catalogs
from livespec_orchestrator_beads_fabro.commands._acp_node_repository import repository_acp_chains
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_chain_sources import (
    repository_acp_chain_sources,
    workflow_scoped_dispatcher_block,
)

__all__: list[str] = ["first_verdict", "resolve_dod_gate_candidates"]

CandidateInvoker = Callable[..., str | None]
VerdictParser = Callable[[str], bool]


def first_verdict(
    *, candidates: Sequence[AcpCandidate], invoke: CandidateInvoker, is_verdict: VerdictParser
) -> str | None:
    """Return the first structured verdict in declared candidate order."""
    for candidate in candidates:
        reply = invoke(candidate=candidate)
        if reply is not None and is_verdict(reply):
            return reply
    return None


def resolve_dod_gate_candidates(*, repo: Path) -> tuple[AcpCandidate, ...]:
    """Resolve the governed ``dod_gate`` primary and fallbacks for ``repo``."""
    block = workflow_scoped_dispatcher_block(repo=repo)
    catalogs = resolve_acp_catalogs(block=block)
    if isinstance(catalogs, str):
        return ()
    declared = repository_acp_chains(block=block, catalogs=catalogs)
    if isinstance(declared, str):
        return ()
    resolved = repository_acp_chain_sources(
        repo=repo, block=block, declared=declared, catalogs=catalogs
    )
    if isinstance(resolved, str):
        return ()
    chains, _graph, _builtins = resolved
    chain = chains.get("dod_gate")
    return () if chain is None else (chain.primary, *chain.fallbacks)
