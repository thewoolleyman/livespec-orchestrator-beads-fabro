"""The config-reading seams for one dispatch target's ACP adapter resolution.

Split out of `_config` by cohesion: that module resolves the beads CONNECTION
descriptor, the factory target, the credential wrapper and the sandbox image --
the general per-invocation configuration -- while the ACP adapter layer is a
policy of its own, already owned by `_acp_node_repository` and the two catalogs.
`_config` keeps the generic `dispatcher_block` read these two functions compose;
what lives here is only the pairing of that read with the ACP policy.

THE TWO FUNCTIONS BELONG TOGETHER because they must read ONE block. A structured
`acp_nodes` entry renders against the catalogs the dispatch target's own
configuration produces, and its node's fallback chain resolves against the SAME
snapshot by contract (`SPECIFICATION/contracts.md` section "ACP node adapter
configuration" -> the determinism clause, and section "Factory-configurable ACP
fallback priority" -> "Resolve the primary before attaching the chain"). Two
independent reads of one file cannot be proven to agree, and the failure is
silent: the primary would render against one catalog and its fallbacks against
another, with nothing in the rendered bytes to show it.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_catalogs import (
    AcpCatalogs,
    resolve_acp_catalogs,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpNodeOverlay
from livespec_orchestrator_beads_fabro.commands._acp_node_repository import (
    repository_acp_overlays,
)
from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block

__all__: list[str] = [
    "resolve_acp_catalogs_for",
    "resolve_acp_node_overlays",
]


def resolve_acp_node_overlays(*, cwd: Path) -> Mapping[str, AcpNodeOverlay] | str:
    """Resolve the dispatch target's per-node adapter overlays from its .livespec.jsonc.

    The policy itself -- the two ratified forms, the catalog render behind the
    structured one, and the `codex_models` shorthand -- lives in
    `_acp_node_repository`; this is the config-reading seam that feeds it. A
    refusal comes back as its message so the caller can report it as a failed
    dispatch before any run exists.

    The CATALOGS are resolved from the SAME block, in the same read, for the
    reason the module docstring records.
    """
    block = dispatcher_block(cwd=cwd)
    catalogs = resolve_acp_catalogs(block=block)
    if isinstance(catalogs, str):
        return catalogs
    return repository_acp_overlays(block=block, catalogs=catalogs)


def resolve_acp_catalogs_for(*, cwd: Path) -> AcpCatalogs | str:
    """Resolve the dispatch target's agent and model catalogs from its .livespec.jsonc.

    Offered beside the overlay resolver because the chain reader needs the SAME
    catalogs the overlay render used.
    """
    return resolve_acp_catalogs(block=dispatcher_block(cwd=cwd))
