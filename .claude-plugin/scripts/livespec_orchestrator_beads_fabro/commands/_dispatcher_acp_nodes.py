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
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._acp_builtin_candidates import (
    builtin_acp_identities,
)
from livespec_orchestrator_beads_fabro.commands._acp_catalogs import (
    AcpCatalogs,
    resolve_acp_catalogs,
)
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import (
    AcpChainResolution,
    attach_acp_chains,
)
from livespec_orchestrator_beads_fabro.commands._acp_factory_capabilities import (
    factory_capability_reader,
)
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
from livespec_orchestrator_beads_fabro.commands._acp_node_repository import (
    repository_acp_chains,
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
from livespec_orchestrator_beads_fabro.commands._acp_workflow_defaults import (
    rendered_workflow_defaults,
)
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget, dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_publication_policy import (
    GROOM_ONLY_ACP_NODES,
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    workflow_declared_inputs,
)
from livespec_orchestrator_beads_fabro.commands._workflow_variant_kind import (
    WORKFLOW_KIND_IMPLEMENT,
    declared_workflow_kind,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import JournalWriter

__all__: list[str] = [
    "ACP_NODES_STAGE",
    "dispatch_acp_overlays",
    "prepare_acp_nodes",
    "workflow_adapter_inputs",
    "workflow_layer",
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
    block = dispatcher_block(cwd=repo)
    configured = _dispatch_workflow_configuration(block=block, committed=committed)
    if isinstance(configured, str):
        return configured
    catalogs, workflow_inputs, workflow_kind = configured
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
    chains = _resolve_chains(
        block=scoped_block,
        catalogs=catalogs,
        resolution=resolution,
        dispatch=dispatch,
        workflow_inputs=workflow_inputs,
    )
    if isinstance(chains, str):
        return chains
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
    *, block: dict[str, object], committed: Path
) -> tuple[AcpCatalogs, Mapping[str, str], str] | str:
    """Catalogs and rendered workflow defaults, from ONE read of each source.

    The catalogs come back WITH the workflow layer because the chain reader
    downstream needs the same catalogs the overlay render used -- a fallback and
    its node's primary resolve against one snapshot by contract -- and the KIND
    comes back with them because it is read off the same committed text the
    defaults are, and a second read of that file cannot be proven to agree with
    the first.
    """
    catalogs = resolve_acp_catalogs(block=block)
    if isinstance(catalogs, str):
        return catalogs
    configured = _workflow_configuration(committed=committed, catalogs=catalogs)
    if isinstance(configured, str):
        return configured
    workflow_inputs, workflow_kind = configured
    return catalogs, workflow_inputs, workflow_kind


def workflow_layer(*, committed: Path, catalogs: AcpCatalogs) -> Mapping[str, str] | str:
    """The workflow layer's adapter inputs, read and RENDERED, or a refusal.

    Reading the committed text and rendering its structured entries is ONE
    concern -- "what does the least specific layer declare" -- so they live
    together and every caller gets the rendered answer or a refusal, never the
    raw text to render for itself.

    The render happens HERE, as the inputs are read, because section "ACP node
    adapter configuration" requires a structured entry rendered into the manual
    form "before any layer merge, journal, digest or run input". It also keeps
    the built-in identity table honest: that table keys on EXACT RENDERED BYTES,
    so raw structured JSON reaching it would key on text no resolved node can
    equal, and every built-in identity would silently stop attaching.
    """
    configured = _workflow_configuration(committed=committed, catalogs=catalogs)
    return configured if isinstance(configured, str) else configured[0]


def _workflow_configuration(
    *, committed: Path, catalogs: AcpCatalogs
) -> tuple[Mapping[str, str], str] | str:
    """The rendered adapter defaults AND the workflow kind, from one read.

    THE KIND IS WHAT RETIRES AN ADAPTER INPUT RATHER THAN THE INPUT'S ABSENCE.
    A groom-kind workflow legitimately declares `pr_adapter`, and an
    implementation workflow must render none -- so an implementation payload
    that still declared one (a variant copied from the groom directory, say)
    would otherwise have it rendered and merged, giving a command stage an
    adapter nothing reads. Dropping every GROOM-ONLY node's input candidates
    here, by kind, is what makes the retirement a property of the ratified cut
    instead of a property of what each payload happens to declare.

    An unreadable or absent kind declaration reads as the IMPLEMENT kind, which
    is the direction `variant_kind` defaults in and for the same reason: the
    kind that unlocks a door is the one that has to be said.
    """
    committed_text = attempt(
        action=lambda: committed.read_text(encoding="utf-8"),
        exceptions=(OSError,),
    )
    if isinstance(committed_text, AttemptFailure):
        return f"workflow config {committed} is unreadable: {committed_text.error}"
    kind = declared_workflow_kind(committed_text=committed_text) or WORKFLOW_KIND_IMPLEMENT
    declared = workflow_adapter_inputs(committed_text=committed_text)
    if kind == WORKFLOW_KIND_IMPLEMENT:
        retired = {name for node in GROOM_ONLY_ACP_NODES for name in NODE_INPUT_CANDIDATES[node]}
        declared = {name: value for name, value in declared.items() if name not in retired}
    rendered = rendered_workflow_defaults(declared=declared, catalogs=catalogs)
    return rendered if isinstance(rendered, str) else (rendered, kind)


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


def _resolve_chains(
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
