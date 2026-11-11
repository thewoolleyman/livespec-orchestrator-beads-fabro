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

from argparse import Namespace
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._acp_catalogs import (
    AcpCatalogs,
    resolve_acp_catalogs,
)
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import AcpChainResolution
from livespec_orchestrator_beads_fabro.commands._acp_factory_capabilities import (
    factory_capability_reader,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import (
    AcpNodeOverlay,
    overlay_from_string,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import (
    AcpNodeResolution,
    acp_nodes_journal_record,
    resolve_acp_nodes,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_repository import (
    repository_acp_overlays,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_selection import (
    selected_candidate_identities,
)
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict
from livespec_orchestrator_beads_fabro.commands._acp_structured_render import READ_ONLY_NODES
from livespec_orchestrator_beads_fabro.commands._acp_structured_text import (
    is_structured_text,
    rendered_structured_text,
)
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget, dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_chain_attachment import (
    resolve_chains,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_publication_policy import (
    scoped_repository_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_selection import (
    SelectedAcpNodes,
    factory_name,
    select_and_gate_acp_node_adapters,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_selection_journal import (
    append_acp_node_selection,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_workflow import (
    workflow_adapter_inputs,
    workflow_configuration,
    workflow_layer,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import workflow_toml
from livespec_orchestrator_beads_fabro.errors import LivespecConfigUnreadableError

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import JournalWriter

__all__: list[str] = [
    "ACP_NODES_STAGE",
    "acp_override_refusal",
    "dispatch_acp_overlays",
    "host_dod_gate_resolution",
    "prepare_acp_nodes",
    "workflow_adapter_inputs",
    "workflow_layer",
]

ACP_NODES_STAGE = "acp-nodes"


def dispatch_acp_overlays(
    *, overrides: tuple[str, ...], catalogs: AcpCatalogs
) -> Mapping[str, AcpNodeOverlay] | str:
    """Parse `--acp-node <node>=<value>` values into per-node overlays.

    THE VALUE MAY BE EITHER FORM, and the two behave differently on purpose.

    A MANUAL value is a COMPLETE adapter command line -- env assignments,
    command and arguments, exactly as the node will run it. Its command
    replaces the less specific layers' outright, while its env assignments
    MERGE over theirs: moving one node's model for one dispatch must not
    require restating the base URL and auth token that repository's
    configuration already carries for it (Scenario 87).

    A STRUCTURED value -- a JSON object naming an `agent` and a `model` -- is
    rendered through the catalogs into the manual form first, and REPLACES the
    environment rather than merging into it. The difference is not an
    inconsistency: a rendered structured entry is a whole adapter belonging to
    one agent, so merging the layer beneath it would prefix another provider's
    variables onto that agent's command line. The same reasoning, and the same
    flag, as the repository layer's structured entries.

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
        parsed = _dispatch_overlay(node=node, value=value, catalogs=catalogs)
        if isinstance(parsed, str):
            return parsed
        overlays[node] = parsed
    return overlays


def _dispatch_overlay(*, node: str, value: str, catalogs: AcpCatalogs) -> AcpNodeOverlay | str:
    """One `--acp-node` value in whichever form it is written.

    The discriminator is the same one the workflow layer uses -- an opening
    brace -- and it is complete rather than a heuristic: a manual adapter is a
    command line, whose first token is an environment assignment or an
    executable, and neither can begin with a brace.
    """
    if not is_structured_text(value=value):
        return overlay_from_string(text=value)
    rendered, refusal = rendered_structured_text(
        value=value,
        key=f"--acp-node {node}",
        catalogs=catalogs,
        read_only=node in READ_ONLY_NODES,
    )
    if refusal is not None:
        return refusal
    return overlay_from_string(text=rendered, replaces_env=True)


def prepare_acp_nodes(  # noqa: PLR0913 — kw-only dispatch inputs; each is one INDEPENDENT operand of the one resolution, and grouping any pair into a carrier would invent a relationship the dispatch does not have.
    *,
    repo: Path,
    committed: Path,
    overrides: tuple[str, ...],
    journal: JournalWriter,
    work_item_id: str,
    dispatch_id: str | None = None,
    factory: FactoryTarget | None = None,
    verdict: AcpPreflightVerdict | None = None,
) -> AcpNodeResolution | str:
    """Resolve every node's adapter through the three layers and journal it.

    Returns the resolution, or an actionable refusal message the caller
    reports as a failed dispatch. Every refusal happens BEFORE any Fabro
    run exists, which is the point of resolving here: a node named in
    configuration but absent from the workflow, or a malformed adapter
    table, is a config error, and the honest place to discover one is the
    dispatch that would otherwise have run the default it meant to replace.

    `verdict` is the ADMISSION evaluation this dispatch was admitted by, and it
    decides WHICH candidate of each node's chain is rendered. A dispatch hands
    in the verdict its own `Admission` carried; it is never re-resolved here,
    because the contract makes selection "once per dispatch from one consistent
    read of the availability evidence".

    ITS ABSENCE IS A MEANINGFUL ANSWER AND NOT A GAP: no verdict means no
    selection is applied, so every node keeps the configured primary the three
    layers resolved, byte-identical to section "ACP node adapter configuration".
    That is the contract's additive guarantee, and it is what the reconcile and
    check subcommands -- which evaluate no candidates at all -- depend on. It is
    deliberately NOT the same answer as an empty verdict, which means every
    candidate was filtered out and refuses an admission-required node.
    """
    layered = _layered_acp_nodes(repo=repo, committed=committed, overrides=overrides)
    if isinstance(layered, str):
        return layered
    resolution, chains, not_applied, _workflow_agents = layered
    selected = _select_and_gate(
        resolution=resolution, chains=chains, verdict=verdict, factory=factory
    )
    if isinstance(selected, str):
        return selected
    # The entitlement labels come from the SELECTION and never from the chain's
    # position zero: a label naming a skipped candidate would record a provider
    # ceiling against an allowance this dispatch never spent.
    resolution = replace(
        selected.resolution,
        candidates=selected_candidate_identities(selected=selected.selected),
    )
    record: dict[str, object] = {
        "stage": ACP_NODES_STAGE,
        "work_item_id": work_item_id,
        **acp_nodes_journal_record(resolution=resolution, redacted=chains.redacted_nodes),
    }
    if not_applied:
        record["not_applied"] = list(not_applied)
    journal.append(record=record)
    # The per-node selection, as its own record and after the resolution's. The
    # two answer different questions -- what each node's CHAIN resolved to, and
    # which position of it this dispatch ran -- and a reader triaging a fallback
    # needs the first to make sense of the second.
    append_acp_node_selection(
        journal=journal,
        selected=selected.selected,
        work_item_id=work_item_id,
        dispatch_id=dispatch_id,
    )
    return resolution


def acp_override_refusal(*, repo: Path, committed: Path, overrides: tuple[str, ...]) -> str | None:
    """The refusal `--acp-node` overrides would draw at resolution, or `None`.

    Runs the same layering and chain attachment `prepare_acp_nodes` runs and stops
    short of everything that needs a CLAIMED dispatch: no journal is written, no
    admission verdict is consulted and no factory capability is read. That is the
    point of the split -- an override refused by the resolution grammar is knowable
    from the dispatch's own arguments and the committed configuration, so it can
    refuse BEFORE the claim instead of stranding one.

    No overrides is not a refusal here: a refusal that does not come from an
    override stays with `prepare_acp_nodes` and the stages that own it.
    """
    if not overrides:
        return None
    layered = _layered_acp_nodes(repo=repo, committed=committed, overrides=overrides)
    return layered if isinstance(layered, str) else None


def host_dod_gate_resolution(
    *,
    repo: Path,
    catalog_resolver: Callable[..., AcpCatalogs | str] = resolve_acp_catalogs,
) -> tuple[AcpNodeResolution, AcpChainResolution, Mapping[str, str]] | None:
    """The host judge's dispatch-equivalent resolution with no override layer."""
    committed = workflow_toml(args=Namespace(repo=str(repo), workflow=None))
    try:
        layered = _layered_acp_nodes(
            repo=repo,
            committed=committed,
            overrides=(),
            catalog_resolver=catalog_resolver,
        )
    except LivespecConfigUnreadableError:
        return None
    if isinstance(layered, str):
        return None
    resolution, chains, _not_applied, workflow_agents = layered
    return resolution, chains, workflow_agents


def _layered_acp_nodes(
    *,
    repo: Path,
    committed: Path,
    overrides: tuple[str, ...],
    catalog_resolver: Callable[..., AcpCatalogs | str] | None = None,
) -> (
    tuple[
        AcpNodeResolution,
        AcpChainResolution,
        tuple[dict[str, str], ...],
        Mapping[str, str],
    ]
    | str
):
    """The three-layer resolution and its attached chains, or the first refusal.

    Shared by the claim-time resolution and the pre-claim override check, so the
    two cannot disagree about which override the grammar refuses.
    """
    block = dispatcher_block(cwd=repo)
    configured = _dispatch_workflow_configuration(
        block=block,
        committed=committed,
        catalog_resolver=resolve_acp_catalogs if catalog_resolver is None else catalog_resolver,
    )
    if isinstance(configured, str):
        return configured
    catalogs, workflow_inputs, workflow_kind, workflow_agents = configured
    scoped_block, not_applied = scoped_repository_block(block=block, workflow_kind=workflow_kind)
    layers = _overlay_layers(block=scoped_block, catalogs=catalogs, overrides=overrides)
    if isinstance(layers, str):
        return layers
    repository, dispatch = layers
    resolution = resolve_acp_nodes(
        workflow_inputs=workflow_inputs,
        repository=repository,
        dispatch=dispatch,
    )
    if isinstance(resolution, str):
        return resolution
    chains = resolve_chains(
        block=scoped_block,
        catalogs=catalogs,
        resolution=resolution,
        dispatch=dispatch,
        workflow_inputs=workflow_inputs,
    )
    if isinstance(chains, str):
        return chains
    return resolution, chains, not_applied, workflow_agents


def _overlay_layers(
    *, block: dict[str, object], catalogs: AcpCatalogs, overrides: tuple[str, ...]
) -> tuple[Mapping[str, AcpNodeOverlay], Mapping[str, AcpNodeOverlay]] | str:
    """The two overlay layers, read against ONE catalog snapshot, or a refusal.

    They travel together because they are the same concern -- what, above the
    workflow default, this dispatch has been told to run -- and because both
    render their structured entries through the catalogs the caller resolved
    once. Resolving either against its own catalog read would let a repository
    entry and a `--acp-node` argument for one node resolve through two
    snapshots of one file, and nothing could prove the two agree.
    """
    repository = repository_acp_overlays(block=block, catalogs=catalogs)
    if isinstance(repository, str):
        return repository
    dispatch = dispatch_acp_overlays(overrides=overrides, catalogs=catalogs)
    if isinstance(dispatch, str):
        return dispatch
    return repository, dispatch


def _dispatch_workflow_configuration(
    *,
    block: dict[str, object],
    committed: Path,
    catalog_resolver: Callable[..., AcpCatalogs | str],
) -> tuple[AcpCatalogs, Mapping[str, str], str, Mapping[str, str]] | str:
    """Catalogs and rendered workflow defaults, from ONE read of each source.

    The catalogs come back WITH the workflow layer because the chain reader
    downstream needs the same catalogs the overlay render used -- a fallback and
    its node's primary resolve against one snapshot by contract -- and the KIND
    comes back with them because it is read off the same committed text the
    defaults are, and a second read of that file cannot be proven to agree with
    the first.
    """
    catalogs = catalog_resolver(block=block)
    if isinstance(catalogs, str):
        return catalogs
    configured = workflow_configuration(committed=committed, catalogs=catalogs)
    if isinstance(configured, str):
        return configured
    workflow_inputs, workflow_kind, workflow_agents = configured
    return catalogs, workflow_inputs, workflow_kind, workflow_agents


def _select_and_gate(
    *,
    resolution: AcpNodeResolution,
    chains: AcpChainResolution,
    verdict: AcpPreflightVerdict | None,
    factory: FactoryTarget | None,
) -> SelectedAcpNodes | str:
    """Delegate selection and the factory-capability gate to their shared concern."""
    return select_and_gate_acp_node_adapters(
        resolution=resolution,
        chains=chains,
        verdict=verdict,
        factory_name=factory_name(factory=factory),
        capabilities=factory_capability_reader(factory=factory),
    )
