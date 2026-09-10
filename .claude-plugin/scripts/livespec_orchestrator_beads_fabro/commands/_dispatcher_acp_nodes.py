"""Per-dispatch resolution of every ACP node's adapter, and its journal record.

This is the seam that assembles the three layers `_acp_node_layers` merges:
it reads the WORKFLOW layer out of the committed `workflow.toml`, takes the
REPOSITORY layer from the dispatch target's `.livespec.jsonc`, parses the
DISPATCH layer off the command line, and journals what resolved.

WHY THE WORKFLOW LAYER IS READ FROM THE COMMITTED FILE rather than assumed.
`_dispatcher_paths.workflow_toml` already prefers the dispatch TARGET's own
committed workflow over the plugin's bundled one, so the set of adapter
inputs that exist is a property of the dispatched workflow and not of this
plugin's build. Reading the declarations means a target still carrying the
older four-input graph is sent `acp_adapter=...` while this repo's
six-input graph is sent `implement_adapter=...` -- and neither is ever sent
an `--input` name its own workflow does not declare, which fabro rejects.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._acp_builtin_candidates import (
    builtin_acp_identities,
)
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import attach_acp_chains
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import (
    NODE_INPUT_CANDIDATES,
    AcpNodeOverlay,
    overlay_from_string,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import (
    AcpNodeResolution,
    acp_nodes_journal_record,
    resolve_acp_nodes,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_repository import repository_acp_chains
from livespec_orchestrator_beads_fabro.commands._config import (
    dispatcher_block,
    resolve_acp_node_overlays,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    workflow_declared_inputs,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import JournalWriter

__all__: list[str] = [
    "ACP_NODES_STAGE",
    "dispatch_acp_overlays",
    "prepare_acp_nodes",
    "workflow_adapter_inputs",
]

ACP_NODES_STAGE = "acp-nodes"

# Every adapter input name any node can ride, so the `[run.inputs]` scan
# picks up adapter declarations and ignores the per-item policy inputs
# (`review_fix_visit_cap`, `merge_on_review_cap_outcome`, `merge_hold`)
# sharing the table.
_ADAPTER_INPUT_NAMES: frozenset[str] = frozenset(
    name for candidates in NODE_INPUT_CANDIDATES.values() for name in candidates
)


def workflow_adapter_inputs(*, committed_text: str) -> Mapping[str, str]:
    """The adapter inputs a committed run config declares, with their defaults.

    An absent `[run.inputs]` table yields an empty mapping rather than a
    refusal: the refusal belongs to `resolve_node_inputs`, which can name
    the NODE that ended up without an adapter input instead of reporting a
    missing table the operator would still have to map back to a node.

    The `[run.inputs]` scan itself is SHARED with the integration-contract
    projection, which asks the same question about its own input names; two
    copies of that scan is how the two would come to disagree about what one
    payload declares.
    """
    return {
        key: value
        for key, value in workflow_declared_inputs(committed_text=committed_text).items()
        if key in _ADAPTER_INPUT_NAMES
    }


def dispatch_acp_overlays(*, overrides: tuple[str, ...]) -> Mapping[str, AcpNodeOverlay] | str:
    """Parse `--acp-node <node>=<adapter>` values into per-node overlays.

    The value is a COMPLETE adapter command line -- env assignments,
    command and arguments, exactly as the node will run it. Its command
    replaces the less specific layers' outright, while its env assignments
    MERGE over theirs: moving one node's model for one dispatch must not
    require restating the base URL and auth token that repository's
    configuration already carries for it (Scenario 87).

    A repeated node refuses rather than silently taking the last value: two
    `--acp-node implement=` arguments on one command line is a mistake, and
    guessing which one was meant is the kind of quiet resolution this whole
    surface exists to eliminate.
    """
    overlays: dict[str, AcpNodeOverlay] = {}
    for override in overrides:
        node, separator, value = override.partition("=")
        if separator == "" or node.strip() == "" or value.strip() == "":
            return f"--acp-node expects <node>=<adapter command>; got {override!r}"
        if node in overlays:
            return f"--acp-node names node {node!r} more than once"
        overlays[node] = overlay_from_string(text=value)
    return overlays


def prepare_acp_nodes(
    *,
    repo: Path,
    committed: Path,
    overrides: tuple[str, ...],
    journal: JournalWriter,
    work_item_id: str,
) -> AcpNodeResolution | str:
    """Resolve every node's adapter through the three layers and journal it.

    Returns the resolution, or an actionable refusal message the caller
    reports as a failed dispatch. Every refusal happens BEFORE any Fabro
    run exists, which is the point of resolving here: a node named in
    configuration but absent from the workflow, or a malformed adapter
    table, is a config error, and the honest place to discover one is the
    dispatch that would otherwise have run the default it meant to replace.
    """
    committed_text = attempt(
        action=lambda: committed.read_text(encoding="utf-8"),
        exceptions=(OSError,),
    )
    if isinstance(committed_text, AttemptFailure):
        return f"workflow config {committed} is unreadable: {committed_text.error}"
    repository = resolve_acp_node_overlays(cwd=repo)
    if isinstance(repository, str):
        return repository
    dispatch = dispatch_acp_overlays(overrides=overrides)
    if isinstance(dispatch, str):
        return dispatch
    workflow_inputs = workflow_adapter_inputs(committed_text=committed_text)
    resolution = resolve_acp_nodes(
        workflow_inputs=workflow_inputs,
        repository=repository,
        dispatch=dispatch,
    )
    if isinstance(resolution, str):
        return resolution
    chains = _resolve_chains(
        repo=repo, resolution=resolution, dispatch=dispatch, workflow_inputs=workflow_inputs
    )
    if isinstance(chains, str):
        return chains
    journal.append(
        record={
            "stage": ACP_NODES_STAGE,
            "work_item_id": work_item_id,
            **acp_nodes_journal_record(resolution=resolution, redacted=chains),
        }
    )
    return resolution


def _resolve_chains(
    *,
    repo: Path,
    resolution: AcpNodeResolution,
    dispatch: Mapping[str, AcpNodeOverlay],
    workflow_inputs: Mapping[str, str],
) -> Mapping[str, Mapping[str, object]] | str:
    """Attach each node's candidate chain to its resolved primary, or refuse.

    The chain is attached STRICTLY AFTER `resolve_acp_nodes` has finished,
    which is the ordering `SPECIFICATION/contracts.md` section
    "Factory-configurable ACP fallback priority" requires: candidate zero
    comes through the existing layers first, and identity or fallback
    metadata may only attach to what those layers produced.

    What comes back is the REDACTED structural record for each
    new-grammar-enabled node, which is all this slice's journal needs. The
    resolved chains themselves have no consumer yet -- preflight,
    classification and the runtime transition are later slices -- so the
    value of resolving them here is the set of refusals it fires BEFORE any
    claim or run exists.
    """
    block = dispatcher_block(cwd=repo)
    declared = repository_acp_chains(block=block)
    if isinstance(declared, str):
        return declared
    attached = attach_acp_chains(
        resolution=resolution,
        chains=declared,
        dispatch=dispatch,
        builtins=builtin_acp_identities(workflow_inputs=workflow_inputs, block=block),
    )
    if isinstance(attached, str):
        return attached
    return attached.redacted_nodes
