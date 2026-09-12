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
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from livespec_orchestrator_beads_fabro.commands._acp_builtin_candidates import (
    builtin_acp_identities,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_preflight import PreflightInputs
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import (
    ResolvedAcpChain,
    attach_acp_chains,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_ledger import read_acp_hold_ledger
from livespec_orchestrator_beads_fabro.commands._acp_node_chains import AcpNodeChain
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import resolve_acp_nodes
from livespec_orchestrator_beads_fabro.commands._acp_node_repository import repository_acp_chains
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import (
    AcpPreflightVerdict,
    build_acp_preflight_verdict,
    no_fallback_verdict,
)
from livespec_orchestrator_beads_fabro.commands._config import (
    dispatcher_block,
    resolve_acp_node_overlays,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_nodes import (
    workflow_adapter_inputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import workflow_graph_path
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import plugin_root
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_exhaustion import (
    DISPATCH_PROVIDERS,
    active_provider_exhaustion,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_workflow_variant import (
    WorkflowVariantRefusal,
    prepare_workflow_variant,
)
from livespec_orchestrator_beads_fabro.commands._workflow_variants import RESERVED_WORKFLOW_NAME
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "ACP_PREFLIGHT_REFUSAL_STAGE",
    "acp_preflight_refusal",
    "credential_reprobe_wait_applies",
    "resolve_acp_preflight",
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
) -> AcpPreflightVerdict:
    """Grade every ACP node's candidate chain for this repository, once.

    `probe` is the admission-time credential assessment seam. It defaults to
    ABSENT rather than to the host credential probe, because no per-candidate
    credential channel is ratified yet -- "A new provider credential channel
    requires its own ratified change" -- so supplying one here would invent the
    entitlement mapping the contract reserves. Wait attention and idle-factory
    leave it absent by the same default, which is what makes their verdict
    free of any external call.
    """
    block = dispatcher_block(cwd=repo)
    declared = repository_acp_chains(block=block)
    if isinstance(declared, str):
        return AcpPreflightVerdict(fallback_enabled=True, refusal=declared)
    if not any(chain.enabled for chain in declared.values()):
        return no_fallback_verdict()
    resolved = _resolve_chains(repo=repo, block=block, declared=declared)
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
        ),
    )


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
    """The vendors still carrying an unexpired LEGACY provider-exhaustion record."""
    return frozenset(
        provider
        for provider in DISPATCH_PROVIDERS
        if active_provider_exhaustion(provider=provider, journal_path=journal_path, now_iso=now_iso)
        is not None
    )


def _resolve_chains(
    *,
    repo: Path,
    block: dict[str, Any],
    declared: Mapping[str, AcpNodeChain],
) -> tuple[Mapping[str, ResolvedAcpChain], str | None, frozenset[tuple[str, str]]] | str:
    """Resolve each node's primary, attach its chain, and read the graph text."""
    variant = prepare_workflow_variant(repo=repo)
    if isinstance(variant, WorkflowVariantRefusal):
        return f"acp preflight cannot resolve the workflow variant: {variant.detail}"
    manifest = _manifest_path(repo=repo, directory=variant.directory)
    manifest_text = _read(path=manifest)
    if manifest_text is None:
        return f"acp preflight cannot read the workflow config {manifest}"
    workflow_inputs = workflow_adapter_inputs(committed_text=manifest_text)
    overlays = resolve_acp_node_overlays(cwd=repo)
    if isinstance(overlays, str):
        return overlays
    resolution = resolve_acp_nodes(
        workflow_inputs=workflow_inputs, repository=overlays, dispatch={}
    )
    if isinstance(resolution, str):
        return resolution
    builtins = builtin_acp_identities(workflow_inputs=workflow_inputs, block=block)
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
    return plugin_root().joinpath(*_RESERVED_SUBPATH)


def _read(*, path: Path) -> str | None:
    text = attempt(action=lambda: path.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(text, AttemptFailure):
        return None
    return text
