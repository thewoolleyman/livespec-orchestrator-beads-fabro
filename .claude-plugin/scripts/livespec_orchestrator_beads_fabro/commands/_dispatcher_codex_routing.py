"""Whether ONE dispatch routes any node to Codex, and what decided it.

The ONE place that question is answered, and the predicate the three host Codex
credential surfaces consult: the pre-claim freshness gate
(`_dispatcher_codex_credential_gate`), the post-claim projection leg
(`_dispatcher_codex_overlay_leg`), and the sandbox credential-use enforcement
the launch wrap carries (`_dispatcher_credential_use_guard`). Each of those used
to apply to EVERY dispatch, so a dispatch whose every resolved ACP node runs
`claude-acp` was refused as a Codex token aged although no run would have used
it, and its node timeouts were capped by the credential-lifetime floor a
credential nothing consumed.

PURE, over the candidate set `_dispatcher_acp_preflight.resolve_dispatch_
candidates` reads off disk. The decision is a pure function of that set, and a
predicate that reached for the configuration itself would be a SECOND reading of
the same files that could not be proven to agree with the first -- the
resolve-once reason the ACP resolution already gives.

EVERY ARM THAT CANNOT ESTABLISH "NO CODEX" ANSWERS YES, and that direction is
the whole safety of this module. Three of them:

- An UNRESOLVABLE resolution (`None`) is the absence of a measurement rather
  than an answer about candidates, and the two owe opposite treatments. A
  dispatch nobody could observe keeps the protection it had.
- An EMPTY set is likewise unreadable rather than empty. `resolve_dispatch_
  candidates` never returns one -- a workflow declaring no adapter input for any
  node yields no chains, which it reports as `None` -- but a caller assembling
  candidates another way can, and an empty set covers nothing, which would read
  as a confident "no Codex" about adapters that were never observed.
- An IDENTITY-LESS candidate is the conservative legacy posture: an arbitrary
  adapter this build never rendered, carrying no key to read and no provenance
  to consult. Nothing about it says which provider it spends.

AND THE AFFIRMATIVE ARM READS BOTH KEYS, which is not redundancy. The two
spellings a Codex candidate reaches a dispatch under are produced by different
machinery and only one of them names the agent:

- A PINNED Codex adapter arrives as a STRUCTURED entry, whose `candidate_key` is
  derived as the canonical `<agent>/<provider>/<model>` triple -- so it begins
  with `codex-acp` and the agent id is readable straight off it.
- The UN-PINNED Codex bases are BUILT-IN, and `_acp_builtin_candidates` keys a
  built-in identity on a DIGEST of its own rendered bytes, precisely so that
  nothing infers an identity from command text. That key is
  `builtin-codex-<digest>`, which does not name the agent at all. What it does
  carry is that agent's own account domain as its `availability_key`, and
  reading that is what keeps the un-pinned opt-out postures protected.

KNOWN LIMIT, recorded rather than hidden. A candidate carrying an OPERATOR-
CHOSEN identity that happens to launch a Codex adapter is not recognised here,
and cannot be: identity is never inferred from command text -- that rule is the
contract's, not a convenience -- and an operator's own `candidate_key` and
`availability_key` are free text. Such a dispatch is graded as routing no node
to Codex, so it projects no Codex credential and launches with no credential-use
deadline; its Codex adapter then fails to authenticate inside the sandbox rather
than being refused before the claim. An operator spelling their own Codex
candidate who wants the host credential graded for it declares the Codex account
domain as that candidate's `availability_key`, which is the one surface this
module reads.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_agent_catalog import CODEX_AGENT_ID
from livespec_orchestrator_beads_fabro.commands._acp_builtin_candidates import CODEX_DOMAIN
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidateIdentity
from livespec_orchestrator_beads_fabro.commands._acp_dispatch_coverage import RenderedCandidate

__all__: list[str] = [
    "UNMEASURED_CODEX_ROUTING",
    "CodexRouting",
    "codex_routing_for",
]

# The `<agent>/...` prefix a derived candidate key carries for the Codex agent.
# Matched as a prefix rather than by substring, because the agent id is the FIRST
# component of the canonical triple and a substring test would also match a model
# or provider name that happened to contain it.
_CODEX_KEY_PREFIX = f"{CODEX_AGENT_ID}/"

# What an identity-less candidate reports. Spelled once, because it is the one
# arm whose text says that the measurement was impossible rather than negative.
_IDENTITY_LESS_DETAIL = (
    "a resolved ACP candidate carries no identity, which is the legacy posture for "
    "an arbitrary adapter this build never rendered, so which provider it spends "
    "cannot be established"
)


@dataclass(frozen=True, kw_only=True)
class CodexRouting:
    """Whether one dispatch routes any node to Codex, and the evidence for it.

    `detail` is not decoration: a dispatch that routes no node to Codex has its
    credential gate SKIPPED, and the journal record saying so has to name the
    routing that decided it. A record reporting only "not applied" cannot be
    audited against anything, so the detail enumerates the resolved candidate
    keys the decision was taken over -- or, on each fail-closed arm, which
    measurement was missing.
    """

    routes_codex: bool
    detail: str


def codex_routing_for(*, candidates: Sequence[RenderedCandidate] | None) -> CodexRouting:
    """Decide whether this dispatch's resolved candidates route any node to Codex.

    ANY, never EVERY: one Codex launch is one credential use, so a single Codex
    candidate standing beside seven Claude ones routes Codex. The mirror of that
    asymmetry is what makes the negative answer meaningful -- it is reached only
    when every resolved candidate carries an identity and none of them names
    Codex.
    """
    if not candidates:
        return UNMEASURED_CODEX_ROUTING
    resolved: set[str] = set()
    codex: set[str] = set()
    for rendered in candidates:
        identity = rendered.candidate.identity
        if identity is None:
            return CodexRouting(routes_codex=True, detail=_IDENTITY_LESS_DETAIL)
        resolved.add(identity.candidate_key)
        if _names_codex(identity=identity):
            codex.add(identity.candidate_key)
    if codex:
        return CodexRouting(
            routes_codex=True,
            detail=(
                f"resolved ACP candidates naming the {CODEX_AGENT_ID} agent or its "
                f"{CODEX_DOMAIN} account domain: {', '.join(sorted(codex))}"
            ),
        )
    return CodexRouting(
        routes_codex=False,
        detail=(
            f"no resolved ACP candidate names the {CODEX_AGENT_ID} agent or its "
            f"{CODEX_DOMAIN} account domain; resolved candidate keys: "
            f"{', '.join(sorted(resolved))}"
        ),
    )


def _names_codex(*, identity: AcpCandidateIdentity) -> bool:
    """Whether one candidate identity names the Codex agent, by either key.

    The candidate key answers it for a STRUCTURED entry, whose derived key opens
    with the agent id; the availability key answers it for a BUILT-IN un-pinned
    base, whose key is a digest and whose domain is the Codex account. Reading
    only the first leaves the un-pinned opt-out postures unprotected, which is
    the direction that launches a Codex adapter with no graded credential.
    """
    return (
        identity.candidate_key == CODEX_AGENT_ID
        or identity.candidate_key.startswith(_CODEX_KEY_PREFIX)
        or identity.availability_key == CODEX_DOMAIN
    )


# What a caller wiring NO routing measurement inherits, and what an unresolvable
# or empty resolution answers. It is the protected answer rather than a
# convenience: a default that exempted an unmeasured dispatch would make
# forgetting to wire the routing indistinguishable from establishing that no node
# routes to Codex.
UNMEASURED_CODEX_ROUTING = CodexRouting(
    routes_codex=True,
    detail=(
        "this dispatch's ACP candidates could not be resolved, so whether any node "
        "routes to Codex was not measured"
    ),
)
