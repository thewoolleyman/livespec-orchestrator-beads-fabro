"""Resolving ONE repository's ACP preflight verdict, and refusing on it.

This is the I/O half of the preflight: it reads the committed chain
configuration, the workflow graph, and the live availability records, hands
them to the pure verdict in `_acp_preflight_verdict`, and offers the two
consumers that ACT on it -- the admission refusal, and the gate on the legacy
credential re-probe wait.

THE READ IS LAZY, AND THAT IS WHAT MAKES THIS ADDITIVE. A repository that
declares no fallback configuration never gets past the first branch: no
workflow variant is resolved, no graph is parsed, no journal is walked, and
the verdict is the viable no-op. `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority" opens by requiring exactly that --
"when no fallback metadata is present, or `fallbacks` is an empty array,
adapter resolution and rendered command bytes MUST remain byte-identical" --
and an early return is a far stronger guarantee of it than a chain of
conditions that happen to evaluate false.

WHICH GRAPH IS GRADED, AND WHY IT IS THE DEFAULT ONE. Admission happens before
a work-item is claimed, and a registry variant is selected per DISPATCH, so
there is no per-item graph to read yet. What is graded is the repository's
DEFAULT variant -- the graph every unattended drain runs. A dispatch that names
`--workflow` or a registry variant resolves and refuses on its own graph later,
at materialization, where the variant is known; this gate is not a substitute
for that and does not claim to be one.

THE CONFIGURATION REFUSAL IS FAIL-CLOSED ON PURPOSE. "Unknown, duplicate-key,
incomplete, wrong-typed, or conflicting fallback configuration refuses before
claim or run." A malformed chain table is refused here rather than waved
through to the dispatch path, because before-claim is strictly earlier than
before-run and a claim taken on configuration that cannot resolve has to be
released again.

ONE MORE CONSUMER READS THE SAME RESOLUTION: the LEGACY provider gate, through
`resolve_dispatch_candidates`. It needs no verdict and no graph -- only the
candidates this repository's resolved node adapters render, so it can tell a
vendor record that covers one of them from a record that covers none. It is
answered here rather than beside that gate because the resolution is this
module's, and a second one would be a second reading of the same files that
could not be proven to agree with the first.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._acp_builtin_candidates import (
    builtin_acp_identities,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_preflight import PreflightInputs
from livespec_orchestrator_beads_fabro.commands._acp_catalogs import (
    AcpCatalogs,
    resolve_acp_catalogs,
)
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import (
    ResolvedAcpChain,
    attach_acp_chains,
)
from livespec_orchestrator_beads_fabro.commands._acp_dispatch_coverage import (
    RenderedCandidate,
    rendered_dispatch_candidates,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_ledger import read_acp_hold_ledger
from livespec_orchestrator_beads_fabro.commands._acp_node_chains import AcpNodeChain
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import (
    AcpNodeResolution,
    resolve_acp_nodes,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_repository import (
    repository_acp_chains,
    repository_acp_overlays,
)
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import (
    AcpPreflightVerdict,
    build_acp_preflight_verdict,
    no_fallback_verdict,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import SessionHeadroomPolicy
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import workflow_graph_path
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
    executing_payload_root,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_exhaustion import (
    live_provider_exhaustions,
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
    "ACP_PREFLIGHT_REFUSAL_STAGE",
    "acp_preflight_refusal",
    "credential_reprobe_wait_applies",
    "resolve_acp_preflight",
    "resolve_acp_primary_generations",
    "resolve_dispatch_candidates",
]

# The journal stage a before-claim preflight refusal is recorded under.
ACP_PREFLIGHT_REFUSAL_STAGE = "acp-preflight-refusal"

_WORKFLOW_MANIFEST = "workflow.toml"
_RESERVED_SUBPATH = (".fabro", "workflows", RESERVED_WORKFLOW_NAME, _WORKFLOW_MANIFEST)


class JournalWriter(Protocol):
    def append(self, *, record: dict[str, object]) -> None:
        """Persist one journal record."""
        ...


def resolve_acp_preflight(
    *,
    repo: Path,
    journal_path: Path | None,
    now_iso: str,
    probe: Callable[[str], str] | None = None,
    headroom: SessionHeadroomPolicy | None = None,
) -> AcpPreflightVerdict:
    """Grade every ACP node's candidate chain for this repository, once.

    `probe` is the admission-time credential assessment seam. It defaults to
    ABSENT rather than to the host credential probe, because no per-candidate
    credential channel is ratified yet -- "A new provider credential channel
    requires its own ratified change" -- so supplying one here would invent the
    entitlement mapping the contract reserves. Wait attention and idle-factory
    leave it absent by the same default, which is what makes their verdict
    free of any external call.

    `headroom` is the admission session-headroom policy, and it defaults to
    ABSENT for exactly the same reason one clause over: "Snapshot composition
    MUST NOT issue a live usage request", so wait attention and idle-factory
    resolve a verdict with no policy and the filter becomes a total no-op. Only
    the admission pass supplies one.
    """
    block = _workflow_scoped_block(repo=repo)
    catalogs = resolve_acp_catalogs(block=block)
    if isinstance(catalogs, str):
        return AcpPreflightVerdict(fallback_enabled=True, refusal=catalogs)
    declared = repository_acp_chains(block=block, catalogs=catalogs)
    if isinstance(declared, str):
        return AcpPreflightVerdict(fallback_enabled=True, refusal=declared)
    if not any(chain.enabled for chain in declared.values()):
        return no_fallback_verdict()
    resolved = _resolve_chains(repo=repo, block=block, declared=declared, catalogs=catalogs)
    if isinstance(resolved, str):
        return AcpPreflightVerdict(fallback_enabled=True, refusal=resolved)
    chains, graph_text, builtin_pairs = resolved
    # ONE ledger read for one evaluation: the verdict's unobservable set and the
    # filter's live records must come from the same walk, or a record retiring
    # between two reads would be surfaced by one half and acted on by the other.
    ledger = read_acp_hold_ledger(journal_path=journal_path, now_iso=now_iso)
    return build_acp_preflight_verdict(
        chains=chains,
        graph_text=graph_text,
        ledger=ledger,
        inputs=PreflightInputs(
            holds=ledger.holds,
            legacy_providers=_legacy_providers(journal_path=journal_path, now_iso=now_iso),
            builtin_pairs=builtin_pairs,
            probe=probe,
            headroom=headroom,
        ),
    )


def resolve_acp_primary_generations(*, repo: Path) -> Mapping[str, str]:
    """Each fallback-enabled node's CURRENT primary-generation fingerprint.

    The event projection needs this for two different questions, and
    answering both from one resolution is what keeps them consistent: the
    KEYS are the nodes a projection-failure fact may be reported for, and
    the VALUES are what the model-fallback supersede pass compares each
    live warning's recorded generation against.

    It is deliberately the same lazy, fail-soft shape as
    `resolve_acp_preflight` above. A repository declaring no fallback
    metadata short-circuits to the empty mapping before any workflow
    variant, graph or journal is touched -- so projection is a total
    no-op on the v107 path -- and a configuration that will not resolve
    also yields the empty mapping rather than a refusal. That direction is
    chosen: the refusal belongs to admission, which runs before claim,
    while this runs AFTER a run has already finished, where refusing would
    strand the very evidence an operator needs. An empty mapping retires
    no warning and reports no fact, which is the conservative answer.
    """
    block = _workflow_scoped_block(repo=repo)
    catalogs = resolve_acp_catalogs(block=block)
    if isinstance(catalogs, str):
        return {}
    declared = repository_acp_chains(block=block, catalogs=catalogs)
    if isinstance(declared, str) or not any(chain.enabled for chain in declared.values()):
        return {}
    resolved = _resolve_chains(repo=repo, block=block, declared=declared, catalogs=catalogs)
    if isinstance(resolved, str):
        return {}
    chains, _graph_text, _builtin_pairs = resolved
    return {node: chain.primary_generation for node, chain in chains.items() if chain.enabled}


def resolve_dispatch_candidates(*, repo: Path) -> tuple[RenderedCandidate, ...] | None:
    """Every candidate this repository's resolved ACP nodes render, or `None`.

    `None` says the resolution could not be READ, and the legacy gate treats
    it as the absence of a measurement rather than as an answer about
    candidates, because those two owe opposite treatments. So this returns a
    NON-EMPTY set or says it has none, and never a plausible empty one.

    AN EMPTY RESOLUTION IS UNREADABLE, NOT EMPTY, and that arm is the one most
    easily mistaken for a result. A workflow that declares no adapter input
    for any node yields no chains at all -- `resolve_acp_nodes` carries one
    entry per declared input -- which means this dispatch OVERRIDES no adapter
    and the run executes whatever the graph itself bakes in. The domains it
    spends are then real but invisible from here, so reporting the empty set
    would say "this dispatch renders nothing a record covers" about a dispatch
    whose adapters were never observed.

    It is NOT lazy on the fallback metadata the way its two siblings above
    are, and that difference is load-bearing. Their question only exists for
    a fallback-enabled repository; this one's question -- which domains does
    this dispatch spend -- exists for EVERY repository, including the v107
    path where each node resolves to exactly one built-in candidate. Short-
    circuiting here would hand the gate `None` for the common case and refuse
    every dispatch any live record happened to find, which is the behaviour
    being retired.

    The block is the WORKFLOW-SCOPED one, exactly as its two siblings read it.
    A repository-level `pr` entry is compatibility configuration for a
    groom-kind variant, so on an implementation workflow it must reach none of
    the reads below: left in, `_resolve_chains` refuses for naming a node the
    implementation workflow declares no adapter input for, and every refusal
    here becomes `None` -- which withholds a verdict for every dispatch in a
    repository carrying the ratified entry, and says nothing on any surface.
    """
    block = _workflow_scoped_block(repo=repo)
    catalogs = resolve_acp_catalogs(block=block)
    if isinstance(catalogs, str):
        return None
    declared = repository_acp_chains(block=block, catalogs=catalogs)
    if isinstance(declared, str):
        return None
    resolved = _resolve_chains(repo=repo, block=block, declared=declared, catalogs=catalogs)
    if isinstance(resolved, str):
        return None
    chains, _graph_text, builtin_pairs = resolved
    rendered = rendered_dispatch_candidates(chains=chains, builtin_pairs=builtin_pairs)
    return rendered or None


def acp_preflight_refusal(
    *,
    work_item_id: str,
    verdict: AcpPreflightVerdict,
    journal: JournalWriter,
) -> DispatchOutcome | None:
    """Refuse one candidate before claim when a success-critical chain is gone.

    Returns `None` for a viable verdict, which is every verdict a repository
    with no fallback configuration can produce. The refusal names the verdict's
    own deterministic explanation rather than re-deriving one, so the journal
    line and the operator-visible detail cannot disagree.
    """
    if verdict.viable:
        return None
    outcome = DispatchOutcome(
        work_item_id=work_item_id,
        status="failed",
        stage=ACP_PREFLIGHT_REFUSAL_STAGE,
        pr_number=None,
        merge_sha=None,
        detail=f"acp preflight refusal: {verdict.detail}",
    )
    journal.append(
        record={
            "stage": ACP_PREFLIGHT_REFUSAL_STAGE,
            "work_item_id": work_item_id,
            "detail": verdict.detail,
            "success_critical": list(verdict.success_critical),
            "exhausted": list(verdict.exhausted),
            "unobservable_observations": len(verdict.unobservable),
        }
    )
    return outcome


def credential_reprobe_wait_applies(*, verdict: AcpPreflightVerdict) -> bool:
    """Whether the legacy credential re-probe wait may hold the loop.

    "The re-probe wait applies to a legacy single candidate and a genuinely
    exhausted fallback chain, never a primary-only probe refusal with a viable
    fallback." Both admitted cases are read straight off the verdict: a
    repository with no fallback configuration is the legacy single candidate,
    and a non-viable verdict is the genuinely exhausted chain. The forbidden
    case -- fallback enabled and still viable -- is the one remaining
    combination, so it needs no condition of its own.
    """
    return not verdict.fallback_enabled or not verdict.viable


def _legacy_providers(*, journal_path: Path | None, now_iso: str) -> frozenset[str]:
    """The vendors still carrying an unexpired LEGACY provider-exhaustion record.

    Read off the journal's own live records rather than by asking about a list
    of vendor names, so the per-candidate filter below sees a record naming a
    provider this build never anticipated. Asking name by name could only ever
    return the names it already held.
    """
    return frozenset(
        record.provider
        for record in live_provider_exhaustions(journal_path=journal_path, now_iso=now_iso)
    )


def _workflow_scoped_block(*, repo: Path) -> dict[str, object]:
    """The repository block as it applies to the workflow this target would run.

    Every read in this module -- the catalogs, the declared chains, the resolved
    primaries -- has to see the SAME block, which is why the scoping happens here
    at the one read rather than per consumer. A repository-level `pr` entry is
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


def _resolve_chains(
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
