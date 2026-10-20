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
_MACHINE_CODE_SOURCE = "protocol.machine_code"
_TURN_FINAL_OUTPUT_SOURCE = "turn.final_output"
_CANDIDATE_SCOPE = "candidate"
_DOMAIN_SCOPE = "availability-domain"


def _quota_message(*, literals: tuple[str, ...]) -> AcpAvailabilitySignature:
    """One measured provider-limit SENTENCE mapping.

    Every provider-limit mapping exists in this form, because it is the one
    that survives an engine keeping only the failure message text -- which is
    what the Petri-era block carries, and what a run routed through
    `needs_human` can be left with. Quota is DOMAIN-scoped without exception:
    the spent allowance belongs to the account, so holding one candidate would
    leave every sibling on the same provider dispatching into the same refusal.
    """
    return AcpAvailabilitySignature(
        source=_MESSAGE_SOURCE,
        cause="quota",
        scope=_DOMAIN_SCOPE,
        all_literals=literals,
    )


def _quota_machine_code(*, machine_code: str) -> AcpAvailabilitySignature:
    """One measured provider-limit structured TOKEN mapping.

    The mirror of the sentence form, for the engine that preserved the
    provider's structured payload. It is declared in ADDITION to the sentence
    rather than instead of it: a payload can arrive carrying either one
    without the other, and each spelling is an exact code rather than a
    pattern, so a vendor's second spelling needs its own entry here.
    """
    return AcpAvailabilitySignature(
        source=_MACHINE_CODE_SOURCE,
        cause="quota",
        scope=_DOMAIN_SCOPE,
        machine_code=machine_code,
    )


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

# THE MEASURED PROVIDER-LIMIT SET, transcribed from the same contract
# section's measured minimum list rather than invented from a provider's
# documentation. Each form below is a refusal somebody observed, and a
# newly measured form is added by a committed change HERE, never by
# loosening one of these literals into a broader match.
#
# `claude-acp`:
#
# - the SESSION ceiling, "You've hit your session limit - resets 3:40am
#   (UTC)". Measured 2026-08-23, 2026-09-09 (twice) and 2026-10-09; every
#   one arrived with a structured `errorKind` of `rate_limit` and was
#   classified transient with no provider attributed, because this table
#   carried no mapping for it.
# - the GENERIC limit, "You've hit your limit - resets Jul 31, 5am (UTC)",
#   measured on the Petri-era engine where only the message text survives
#   (`plan/fabro-currency/research/004-acp-spend-limit-evidence.json`,
#   mode `usage-cap`). `resets` is the second literal rather than a nicety:
#   "hit your limit" alone is the prefix of sentences that are not ceilings.
# - the USAGE limit, which Claude emits with the same wording Codex does.
#   It belongs in BOTH tables: the contract attributes a shared sentence to
#   "the candidate that actually ran", and a candidate only ever consults
#   its own domain's table, so carrying it twice is what makes each
#   attribution come out right.
# - the ORGANISATION spend ceiling, "You've hit your org's monthly spend
#   limit - ask your admin to raise it at claude.ai/settings/usage"
#   (same evidence file, mode `monthly-cap`), as the measured `org` plus
#   `spend limit` conjunction. That conjunction REPLACES the earlier
#   `monthly spend limit` entry rather than sitting beside it: it is the
#   spelling the contract ratifies, it matches the same measured sentence,
#   and two mappings for one observed refusal is a second place for the
#   measured form to drift from the recorded evidence.
#
# `codex-acp`: the usage-limit sentence measured 2026-08-22 across the 53
# failed hp-factory runs -- ten refusals read "You've hit your usage limit.
# Visit .../codex/settings/usage ... or try again at <date>" -- its
# `usage limit exceeded` prose form, and its structured token in BOTH
# spellings the pinned adapters emit: the August payload carried
# `usage_limit_exceeded` and the October one carries `usageLimitExceeded`.
_ANTHROPIC_SESSION_LIMIT = _quota_message(literals=("hit your session limit",))
_ANTHROPIC_GENERIC_LIMIT = _quota_message(literals=("hit your limit", "resets"))
_ANTHROPIC_USAGE_LIMIT = _quota_message(literals=("hit your usage limit",))
_ANTHROPIC_ORG_SPEND_LIMIT = _quota_message(literals=("org", "spend limit"))
_CODEX_USAGE_LIMIT = _quota_message(literals=("hit your usage limit",))
_CODEX_USAGE_LIMIT_EXCEEDED = _quota_message(literals=("usage limit exceeded",))
_CODEX_USAGE_LIMIT_CAMEL_TOKEN = _quota_machine_code(machine_code="usageLimitExceeded")
_CODEX_USAGE_LIMIT_SNAKE_TOKEN = _quota_machine_code(machine_code="usage_limit_exceeded")

# MEASURED 2026-10-20 on the gmktec review turn of bd-ib-davaxq: the
# codex-acp adapter delivered this refusal directly after its prose, while the
# engine recorded the turn as successful. This is candidate-scoped because the
# refusal names one selected model, not the account's whole allowance.
_CODEX_PROVIDER_CAPACITY = AcpAvailabilitySignature(
    source=_TURN_FINAL_OUTPUT_SOURCE,
    cause="provider_capacity",
    scope=_CANDIDATE_SCOPE,
    final_text="Selected model is at capacity. Please try a different model.",
)

_BUILTIN_SIGNATURES: dict[str, tuple[AcpAvailabilitySignature, ...]] = {
    ANTHROPIC_DOMAIN: (
        _ANTHROPIC_SESSION_LIMIT,
        _ANTHROPIC_GENERIC_LIMIT,
        _ANTHROPIC_USAGE_LIMIT,
        _ANTHROPIC_ORG_SPEND_LIMIT,
    ),
    CODEX_DOMAIN: (
        _CODEX_MODEL_UNSUPPORTED,
        _CODEX_MODEL_NOT_FOUND,
        _CODEX_USAGE_LIMIT,
        _CODEX_USAGE_LIMIT_EXCEEDED,
        _CODEX_USAGE_LIMIT_CAMEL_TOKEN,
        _CODEX_USAGE_LIMIT_SNAKE_TOKEN,
        _CODEX_PROVIDER_CAPACITY,
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
