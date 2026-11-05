"""Reading ONE repository's ACP chain configuration off disk.

Split out of `_dispatcher_acp_preflight` by cohesion: that module GRADES a
repository's chains and offers the two consumers that act on the verdict, while
this one answers the narrower question of what this repository's chain
configuration actually IS -- the workflow-scoped dispatcher block, the resolved
per-node primaries, the attached chains and identities, and the graph text.

ALL THREE PUBLIC RESOLVERS NEXT DOOR READ IT THROUGH THESE TWO ENTRY POINTS, so
the scoping and the resolution happen once per caller rather than once per
concern. Only the two PUBLIC names cross the boundary; the manifest-path
precedence, the chain attachment and the fail-soft read stay private here,
because each is used by `repository_acp_chain_sources` alone.

THE REFUSALS STAY STRINGS. Every arm returns either a resolution or the text
explaining why it could not be read, and the CHOICE of what to do with that
text belongs to the caller: admission refuses before claim on it, while the
post-run projection deliberately treats it as the empty answer. A module that
raised here would take that choice away from both.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_builtin_candidates import (
    builtin_acp_identities,
)
from livespec_orchestrator_beads_fabro.commands._acp_catalogs import AcpCatalogs
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import (
    ResolvedAcpChain,
    attach_acp_chains,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_chains import AcpNodeChain
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import (
    AcpNodeResolution,
    resolve_acp_nodes,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_repository import (
    repository_acp_overlays,
)
from livespec_orchestrator_beads_fabro.commands._acp_workflow_defaults import (
    rendered_workflow_defaults,
)
from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_nodes import (
    workflow_adapter_inputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_publication_policy import (
    scoped_repository_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import workflow_graph_path
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
    executing_payload_root,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_workflow_variant import (
    WorkflowVariantRefusal,
    prepare_workflow_variant,
)
from livespec_orchestrator_beads_fabro.commands._workflow_variant_kind import variant_kind
from livespec_orchestrator_beads_fabro.commands._workflow_variants import (
    RESERVED_WORKFLOW_NAME,
    workflow_variant_from_block,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "repository_acp_chain_sources",
    "workflow_scoped_dispatcher_block",
]

_WORKFLOW_MANIFEST = "workflow.toml"
_RESERVED_SUBPATH = (".fabro", "workflows", RESERVED_WORKFLOW_NAME, _WORKFLOW_MANIFEST)


def workflow_scoped_dispatcher_block(*, repo: Path) -> dict[str, object]:
    """The repository block as it applies to the workflow this target would run.

    Every read of this repository's chain configuration -- the catalogs, the
    declared chains, the resolved primaries -- has to see the SAME block, which
    is why the scoping happens here at the one read rather than per consumer.
    A repository-level `pr` entry is
    compatibility configuration for a groom-kind variant
    (`_dispatcher_acp_publication_policy`), so on an implementation workflow it
    must reach none of them: left in, it makes this preflight refuse for naming
    a node the implementation workflow declares no adapter input for, and before
    that it would have required a provider credential for a command stage --
    both of which the ratified clause forbids in as many words.

    The not-applied audit row is deliberately DISCARDED here. This surface
    refuses and reports; the row belongs to the dispatch that actually resolves
    the nodes (`_dispatcher_acp_nodes.prepare_acp_nodes`), and journaling it
    twice would make one ignored entry read as two.
    """
    block = dispatcher_block(cwd=repo)
    variant = workflow_variant_from_block(block=block)
    scoped, _not_applied = scoped_repository_block(
        block=block,
        workflow_kind=variant_kind(repo=repo, variant=variant),
    )
    return scoped


def repository_acp_chain_sources(
    *,
    repo: Path,
    block: dict[str, object],
    declared: Mapping[str, AcpNodeChain],
    catalogs: AcpCatalogs,
) -> tuple[Mapping[str, ResolvedAcpChain], str | None, frozenset[tuple[str, str]]] | str:
    """Resolve each node's primary, attach its chain, and read the graph text."""
    variant = prepare_workflow_variant(repo=repo)
    if isinstance(variant, WorkflowVariantRefusal):
        return f"acp preflight cannot resolve the workflow variant: {variant.detail}"
    manifest = _manifest_path(repo=repo, directory=variant.directory)
    manifest_text = _read(path=manifest)
    if manifest_text is None:
        return f"acp preflight cannot read the workflow config {manifest}"
    workflow_inputs = rendered_workflow_defaults(
        declared=workflow_adapter_inputs(committed_text=manifest_text), catalogs=catalogs
    )
    if isinstance(workflow_inputs, str):
        return workflow_inputs
    overlays = repository_acp_overlays(block=block, catalogs=catalogs)
    if isinstance(overlays, str):
        return overlays
    resolution = resolve_acp_nodes(
        workflow_inputs=workflow_inputs, repository=overlays, dispatch={}
    )
    if isinstance(resolution, str):
        return resolution
    return _attached_chains(
        resolution=resolution,
        declared=declared,
        workflow_inputs=workflow_inputs,
        manifest=manifest,
        manifest_text=manifest_text,
    )


def _attached_chains(
    *,
    resolution: AcpNodeResolution,
    declared: Mapping[str, AcpNodeChain],
    workflow_inputs: Mapping[str, str],
    manifest: Path,
    manifest_text: str,
) -> tuple[Mapping[str, ResolvedAcpChain], str | None, frozenset[tuple[str, str]]] | str:
    """Attach each node's chain to its resolved primary and read the graph text.

    Split from the primary resolution above because the two are separate
    concerns -- resolving WHAT each node runs, then attaching the chain and the
    identities that describe it -- and because keeping them together put the
    function over the return-count ceiling with no seam a reader could name.
    """
    builtins = builtin_acp_identities(workflow_inputs=workflow_inputs)
    attached = attach_acp_chains(
        resolution=resolution,
        chains=declared,
        dispatch={},
        builtins=builtins,
    )
    if isinstance(attached, str):
        return attached
    graph = workflow_graph_path(committed_text=manifest_text, workflow_dir=manifest.parent)
    return (
        attached.chains,
        None if graph is None else _read(path=graph),
        frozenset(identity.pair for identity in builtins.values()),
    )


def _manifest_path(*, repo: Path, directory: str | None) -> Path:
    """The default variant's manifest, by the same precedence a dispatch uses."""
    if directory is not None:
        return repo / directory / _WORKFLOW_MANIFEST
    repo_local = repo.joinpath(*_RESERVED_SUBPATH)
    if repo_local.is_file():
        return repo_local
    # The bundled fallback is an ASSET read, so it resolves under the payload
    # this process is executing rather than under the installation, which the
    # harness may already have evicted.
    return executing_payload_root().joinpath(*_RESERVED_SUBPATH)


def _read(*, path: Path) -> str | None:
    text = attempt(action=lambda: path.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(text, AttemptFailure):
        return None
    return text
