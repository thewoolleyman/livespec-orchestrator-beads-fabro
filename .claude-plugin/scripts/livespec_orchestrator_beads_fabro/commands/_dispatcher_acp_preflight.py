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

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._acp_availability_wait import (
    AvailabilityWait,
    availability_wait,
    availability_wait_refusal_fields,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_preflight import PreflightInputs
from livespec_orchestrator_beads_fabro.commands._acp_catalogs import resolve_acp_catalogs
from livespec_orchestrator_beads_fabro.commands._acp_dispatch_coverage import (
    RenderedCandidate,
    rendered_dispatch_candidates,
)
from livespec_orchestrator_beads_fabro.commands._acp_hold_ledger import read_acp_hold_ledger
from livespec_orchestrator_beads_fabro.commands._acp_node_repository import repository_acp_chains
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import (
    AcpPreflightVerdict,
    build_acp_preflight_verdict,
    no_fallback_verdict,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import SessionHeadroomPolicy
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_records import (
    headroom_refusal_fields,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_chain_sources import (
    repository_acp_chain_sources,
    workflow_scoped_dispatcher_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    DEFAULT_CREDENTIAL_REPROBE_INTERVAL_SECONDS,
    resolve_credential_reprobe_interval_seconds,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_exhaustion import (
    live_provider_exhaustions,
)

__all__: list[str] = [
    "ACP_PREFLIGHT_REFUSAL_STAGE",
    "acp_preflight_refusal",
    "credential_reprobe_wait_applies",
    "resolve_acp_preflight",
    "resolve_acp_primary_generations",
    "resolve_availability_wait",
    "resolve_dispatch_candidates",
]

# The journal stage a before-claim preflight refusal is recorded under.
ACP_PREFLIGHT_REFUSAL_STAGE = "acp-preflight-refusal"


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
    block = workflow_scoped_dispatcher_block(repo=repo)
    catalogs = resolve_acp_catalogs(block=block)
    if isinstance(catalogs, str):
        return AcpPreflightVerdict(fallback_enabled=True, refusal=catalogs)
    declared = repository_acp_chains(block=block, catalogs=catalogs)
    if isinstance(declared, str):
        return AcpPreflightVerdict(fallback_enabled=True, refusal=declared)
    if not any(chain.enabled for chain in declared.values()):
        return no_fallback_verdict()
    resolved = repository_acp_chain_sources(
        repo=repo, block=block, declared=declared, catalogs=catalogs
    )
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
    block = workflow_scoped_dispatcher_block(repo=repo)
    catalogs = resolve_acp_catalogs(block=block)
    if isinstance(catalogs, str):
        return {}
    declared = repository_acp_chains(block=block, catalogs=catalogs)
    if isinstance(declared, str) or not any(chain.enabled for chain in declared.values()):
        return {}
    resolved = repository_acp_chain_sources(
        repo=repo, block=block, declared=declared, catalogs=catalogs
    )
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
    block = workflow_scoped_dispatcher_block(repo=repo)
    catalogs = resolve_acp_catalogs(block=block)
    if isinstance(catalogs, str):
        return None
    declared = repository_acp_chains(block=block, catalogs=catalogs)
    if isinstance(declared, str):
        return None
    resolved = repository_acp_chain_sources(
        repo=repo, block=block, declared=declared, catalogs=catalogs
    )
    if isinstance(resolved, str):
        return None
    chains, _graph_text, builtin_pairs = resolved
    rendered = rendered_dispatch_candidates(chains=chains, builtin_pairs=builtin_pairs)
    return rendered or None


def resolve_availability_wait(
    *, repo: Path, verdict: AcpPreflightVerdict, now_iso: str
) -> AvailabilityWait | None:
    """Schedule the next admission evaluation this verdict owes, or `None`.

    The ONLY read this adds is the repository's own
    `dispatcher.credential_reprobe_interval_seconds` cadence. The availability
    EVIDENCE is taken off the verdict, which carries the holds its own nodes
    were filtered against -- a second ledger walk here would be a second
    measurement of one evaluation, and the two could disagree about a record
    that retired between them.

    An unreadable cadence key falls back to the ratified default rather than
    refusing. The wait is not a gate: it is the instant a refusal ALREADY taken
    reports, so failing here would replace an actionable refusal with a
    traceback about the file it was about to name.
    """
    interval = unsafe_perform_io(
        resolve_credential_reprobe_interval_seconds(cwd=repo).value_or(
            DEFAULT_CREDENTIAL_REPROBE_INTERVAL_SECONDS
        )
    )
    return availability_wait(
        verdict=verdict,
        holds=verdict.holds,
        now_iso=now_iso,
        reprobe_interval_seconds=interval,
    )


def acp_preflight_refusal(
    *,
    work_item_id: str,
    verdict: AcpPreflightVerdict,
    journal: JournalWriter,
    wait: AvailabilityWait | None = None,
) -> DispatchOutcome | None:
    """Refuse one candidate before claim when a success-critical chain is gone.

    Returns `None` for a viable verdict, which is every verdict a repository
    with no fallback configuration can produce. The refusal names the verdict's
    own deterministic explanation rather than re-deriving one, so the journal
    line and the operator-visible detail cannot disagree.

    The session-headroom block is MERGED IN rather than branched on here, and it
    is empty unless headroom actually emptied an exhausted node -- see
    `headroom_refusal_fields`. That keeps every pre-existing refusal record
    byte-identical, which is what makes this clause additive to a repository
    that never assesses a covered candidate.

    The SCHEDULED WAIT is merged the same way and for the same reason, and it
    is `None` on exactly the two refusals that are not availability waits: a
    configuration refusal, which waiting cannot repair, and a verdict whose
    clock could not be read. `SPECIFICATION/contracts.md` section "Provider
    spend containment" requires a containment refusal to carry the governing
    condition, the admission-required node lacking an eligible candidate and
    the scheduled reevaluation instant -- so the fields are the wait's own
    projection rather than three values re-derived at this call site, which is
    what keeps the journal line and the instant a later pass honours identical.
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
            **headroom_refusal_fields(verdict=verdict),
            **availability_wait_refusal_fields(wait=wait),
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
