"""WHICH of one DISPATCH's rendered candidates a legacy provider record covers.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "Legacy provider-only records remain readable, clearable by the
legacy valve, and effective until retirement against built-in candidates whose
compatibility alias names that provider plus identity-less legacy candidates,
which every live legacy record covers. Explicitly identified candidates MUST
NOT be broadened to unrelated identities."

`_acp_hold_coverage.legacy_record_covers_candidate` answers that question for
ONE candidate. This module answers the question the legacy ADMISSION GATE
actually asks -- does a record cover ANYTHING this dispatch's resolved ACP
nodes render? -- and the difference is the whole reason it exists: the gate it
scopes had no candidate set at all. It iterated a hard-coded
`("anthropic", "codex")` tuple, so a record for either vendor refused EVERY
dispatch, including one routed wholly to the other. The providers a dispatch
can be refused on are now DERIVED from the adapters its nodes resolved to,
which is what Scenario 60's "A hold on one provider does not refuse an item
wholly on another" requires.

`builtin` IS THE CALLER'S FACT, carried per candidate rather than re-derived
here, for the reason `_acp_hold_coverage`'s own docstring gives: it is read
from the rendered-bytes table and never inferred from how a key is spelled. A
candidate this build did not render carries an operator's chosen identity, and
broadening a vendor record onto it is the "unrelated identities" case the
contract forbids -- even when the operator happened to spell their key with
the vendor's own word.

A NODE'S FALLBACKS ARE RENDERED CANDIDATES TOO, and they are deliberately in
the set. A legacy provider-only record carries no scope, no candidate key and
no node, so it cannot support a judgement about which position in a chain it
reached; reasoning about chain VIABILITY belongs to the typed preflight
(`_acp_candidate_preflight`), which filters per candidate and refuses only an
exhausted chain. Narrowing this set to primaries would make the coarse legacy
gate quietly more permissive than the typed surface that can actually tell a
held primary from an eligible fallback.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_chain_resolution import ResolvedAcpChain
from livespec_orchestrator_beads_fabro.commands._acp_hold_coverage import (
    legacy_record_covers_candidate,
)

__all__: list[str] = [
    "RenderedCandidate",
    "legacy_record_covers_dispatch",
    "rendered_dispatch_candidates",
]


@dataclass(frozen=True, kw_only=True)
class RenderedCandidate:
    """One candidate a dispatch's resolved ACP nodes render, and its provenance.

    `builtin` says the resolved adapter is one THIS BUILD rendered, so the
    candidate's `availability_key` is the provenance-assigned compatibility
    alias rather than an operator's chosen string. It travels WITH the
    candidate because the rendered-bytes table that answers it is read once,
    where the chains are resolved; a consumer re-deriving it from the identity
    would be inferring provenance from spelling.
    """

    candidate: AcpCandidate
    builtin: bool


def rendered_dispatch_candidates(
    *,
    chains: Mapping[str, ResolvedAcpChain],
    builtin_pairs: frozenset[tuple[str, str]],
) -> tuple[RenderedCandidate, ...]:
    """Every candidate this dispatch's resolved nodes render, in node order.

    Nodes are visited in sorted order so two evaluations of one unchanged
    resolution render the same sequence, which is what lets a refusal built
    from this set be reproducible across dispatches.
    """
    return tuple(
        RenderedCandidate(
            candidate=candidate,
            builtin=_builtin(candidate=candidate, builtin_pairs=builtin_pairs),
        )
        for node in sorted(chains)
        for candidate in (chains[node].primary, *chains[node].fallbacks)
    )


def legacy_record_covers_dispatch(
    *,
    provider: str,
    candidates: tuple[RenderedCandidate, ...],
) -> bool:
    """Whether a live legacy record for `provider` covers ANY rendered candidate.

    ANY rather than EVERY, and the asymmetry is the contract's: one
    identity-less legacy adapter anywhere in the dispatch keeps every live
    record effective, because that posture is the conservative v107 path the
    blanket exists to preserve.

    Whether a dispatch could be READ at all is not this function's question
    and must not be expressed as an empty set here: an empty set covers
    nothing, which is a confident negative, while a dispatch whose adapters
    were never observed supports no verdict either way.
    `_dispatcher_acp_preflight.resolve_dispatch_candidates` is where that
    distinction lives, and it hands this an empty tuple from nowhere.
    """
    return any(
        legacy_record_covers_candidate(
            provider=provider, candidate=rendered.candidate, builtin=rendered.builtin
        )
        for rendered in candidates
    )


def _builtin(*, candidate: AcpCandidate, builtin_pairs: frozenset[tuple[str, str]]) -> bool:
    """Whether this candidate's identity is one of the build's own built-ins."""
    identity = candidate.identity
    return identity is not None and identity.pair in builtin_pairs
