"""The MEASURED availability signatures the built-in candidates carry.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "Built-in Claude and Codex candidates MUST carry exact,
measured mappings for stable diagnostics exposed by the pinned adapters,
including the recorded ChatGPT-account diagnostic that names the
requested model as unsupported. The generic HTTP 400 remains
non-eligible; the exact model-naming discriminator is candidate-scoped."

EVERY ENTRY BELOW IS A MEASUREMENT, NOT A GUESS, and each cites where it
was measured. A signature invented from a provider's documentation is the
same defect as inferring identity from command text: it claims a
diagnostic nobody has seen this adapter emit, and the first time it is
wrong it fails a candidate over somebody else's sentence.

THE 400 CASE IS THE WHOLE POINT OF THE SLICE. The v107 `pr`-node outage
was `HTTP 400 'model is not supported when using Codex with a ChatGPT
account'` after `gpt-5.4-mini` left the ChatGPT-account catalog
(`SPECIFICATION/history/v107/proposed_changes/pr-node-default-claude-haiku.md`).
The eligible discriminator is the SENTENCE, never the status: the
signature conjoins "requested model" with the unsupported clause, so it
names the model the account asked for. A 400 carrying neither literal
stays generic and terminates with its own identity, which
`_acp_failure_matching.generic_status_reason` is what enforces.

SCOPE IS NOT DECORATION. A removed or unentitled model is CANDIDATE-
scoped: the account is fine, this one model is not, and a domain hold
would strand every sibling candidate on the same provider over one
missing slug. A usage or spend ceiling is DOMAIN-scoped for the mirror
reason: the allowance is the account's, so every candidate drawing on it
is equally gone.

THE DOMAIN NAMES ARE THE LEGACY PROVIDER ALIASES (`anthropic`, `codex`)
that `_acp_builtin_candidates` already assigns by provenance. Reusing
them is what lets an unexpired legacy provider record keep covering a
built-in candidate until retirement, which the contract requires.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._acp_builtin_candidates import (
    ANTHROPIC_DOMAIN,
    CODEX_DOMAIN,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_candidate_signatures import (
    AcpAvailabilitySignature,
)

__all__: list[str] = [
    "builtin_availability_signatures",
    "effective_signatures",
]

_TERMINAL_SOURCE = "process.terminal_diagnostic"
_MESSAGE_SOURCE = "protocol.message"
_CANDIDATE_SCOPE = "candidate"
_DOMAIN_SCOPE = "availability-domain"

# MEASURED 2026-09-09, the `pr`-node outage that motivated this contract:
# the pinned Codex adapter returned HTTP 400 naming the requested model as
# unsupported for a ChatGPT account. Candidate-scoped: the account works,
# this one slug does not.
_CODEX_MODEL_UNSUPPORTED = AcpAvailabilitySignature(
    source=_TERMINAL_SOURCE,
    cause="model_unsupported",
    scope=_CANDIDATE_SCOPE,
    all_literals=(
        "requested model",
        "is not supported when using codex with a chatgpt account",
    ),
)

# MEASURED 2026-08 on the Wave B fork validation (`plan/archive/
# fabro-fork-control-plane-gaps/research/005-...`): `-m gpt-5.5` returned
# `404 Not Found: The model 'gpt-5.5' does not exist or you do not have
# access to it`. The model-naming clause is the discriminator; the bare
# 404 around it is not.
_CODEX_MODEL_NOT_FOUND = AcpAvailabilitySignature(
    source=_TERMINAL_SOURCE,
    cause="model_not_found",
    scope=_CANDIDATE_SCOPE,
    all_literals=("the model", "does not exist or you do not have access to it"),
)

# MEASURED 2026-08-22 across the 53 failed hp-factory runs recorded in
# `_fabro_port_records`: ten Codex refusals read "You've hit your usage
# limit. Visit .../codex/settings/usage ... or try again at <date>".
# Domain-scoped -- the allowance belongs to the account, not the model.
_CODEX_USAGE_LIMIT = AcpAvailabilitySignature(
    source=_MESSAGE_SOURCE,
    cause="quota",
    scope=_DOMAIN_SCOPE,
    all_literals=("hit your usage limit",),
)

# MEASURED in the same sweep: the eleventh refusal was the Anthropic form,
# "You've hit your org's monthly spend limit". The narrower "monthly spend
# limit" is used rather than the bare "spend limit" that
# `_fabro_port_records` also accepts, because this table mints a TYPED
# hold keyed on an entitlement, and the broader hint was written for a
# cause-text heuristic that only had to name a vendor.
_ANTHROPIC_SPEND_LIMIT = AcpAvailabilitySignature(
    source=_MESSAGE_SOURCE,
    cause="quota",
    scope=_DOMAIN_SCOPE,
    all_literals=("monthly spend limit",),
)

_BUILTIN_SIGNATURES: dict[str, tuple[AcpAvailabilitySignature, ...]] = {
    ANTHROPIC_DOMAIN: (_ANTHROPIC_SPEND_LIMIT,),
    CODEX_DOMAIN: (
        _CODEX_MODEL_UNSUPPORTED,
        _CODEX_MODEL_NOT_FOUND,
        _CODEX_USAGE_LIMIT,
    ),
}


def builtin_availability_signatures(
    *, availability_key: str
) -> tuple[AcpAvailabilitySignature, ...]:
    """The measured table for one built-in domain, or none for any other key.

    An unknown key returns the EMPTY tuple rather than a default set: a
    repository that named its own `availability_key` declares its own
    signatures, and lending it Codex's measurements would classify its
    failures against diagnostics its adapter never emits.
    """
    return _BUILTIN_SIGNATURES.get(availability_key, ())


def effective_signatures(
    *, candidate: AcpCandidate, builtin: bool
) -> tuple[AcpAvailabilitySignature, ...]:
    """The signatures that actually classify this candidate's failures.

    `builtin` is supplied by the caller -- which already holds the
    rendered-bytes table `_acp_builtin_candidates` produces -- and is NEVER
    derived from the candidate's keys here. Reading built-in-ness out of a
    key's spelling is inference from text, the one thing that table was
    built to avoid, and a repository is free to choose `availability_key:
    "codex"` for an adapter this build did not render.

    Configured signatures come FIRST so an operator's own measurement of a
    built-in adapter is visible to the ambiguity rule rather than silently
    losing to, or overriding, the shipped one. Two signatures that match
    the same diagnostic with different dispositions must surface as
    ambiguous; ordering them to make one win is the first-match choice the
    contract forbids.
    """
    identity = candidate.identity
    if not builtin or identity is None:
        return candidate.signatures
    return (
        *candidate.signatures,
        *builtin_availability_signatures(availability_key=identity.availability_key),
    )
