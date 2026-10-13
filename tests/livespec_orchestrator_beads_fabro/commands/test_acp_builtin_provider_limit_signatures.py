"""The built-in signature tables carry EVERY measured provider-limit form.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "Every provider-limit mapping MUST exist as a `protocol.message`
signature, and additionally as a `protocol.machine_code` signature where the
adapter emits a structured token, so that detection survives an engine that
keeps only message text." It then fixes the measured minimum set, "each `cause:
quota` and `scope: availability-domain`", and requires that "Every listed
measured form MUST be exercised against its recorded executed candidate,
including message-only payloads and both structured Codex spellings."
Scenario 127 governs the registry; Scenario 65's outline grades the forms.

WHAT THE TABLES CARRIED. For the Anthropic domain, one signature: "monthly
spend limit". So Claude's session ceiling, the Petri-era generic limit wording
and the organisation form as the contract spells it were all absent, and the
Codex domain carried the usage-limit SENTENCE with no structured token at all
-- which is the mapping that has to survive an engine keeping only message
text, and equally the one that has to work when only the token survives.

TWO CONTROLS, and they test opposite directions. Scope: a quota mapping that
was CANDIDATE-scoped would hold one model while the spent allowance belongs to
the whole account, so every sibling candidate on the same provider would keep
dispatching into the same refusal -- so every quota signature in both tables
is asserted domain-scoped, not just the ones added here. And matching: an
ordinary provider message must still classify as `unmatched`, or a table that
claimed every diagnostic would satisfy all of the positives above.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._acp_builtin_candidates import (
    ANTHROPIC_DOMAIN,
    CODEX_DOMAIN,
)
from livespec_orchestrator_beads_fabro.commands._acp_builtin_signatures import (
    builtin_availability_signatures,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidate,
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_signatures import (
    AcpAvailabilitySignature,
)
from livespec_orchestrator_beads_fabro.commands._acp_failure_classifier import (
    DOMAIN_SCOPE,
    AcpAvailabilityFailure,
    AcpNonEligibleFailure,
    classify_acp_failure,
)
from livespec_orchestrator_beads_fabro.commands._acp_failure_signals import AcpFailureSignal
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter

_MESSAGE_SOURCE = "protocol.message"
_MACHINE_CODE_SOURCE = "protocol.machine_code"
_QUOTA = "quota"

# The measured minimum set, transcribed from the contract clause quoted above.
_CLAUDE_MESSAGE_FORMS: tuple[tuple[str, ...], ...] = (
    ("hit your session limit",),
    ("hit your limit", "resets"),
    ("hit your usage limit",),
    ("org", "spend limit"),
)
_CODEX_MESSAGE_FORMS: tuple[tuple[str, ...], ...] = (
    ("hit your usage limit",),
    ("usage limit exceeded",),
)
_CODEX_MACHINE_CODES: tuple[str, ...] = ("usageLimitExceeded", "usage_limit_exceeded")

# One measured sentence per message form, as it arrives on an engine that kept
# no structured payload at all.
_CLAUDE_MESSAGES: tuple[str, ...] = (
    "You've hit your session limit · resets 3:40am (UTC)",
    "You've hit your limit · resets Jul 31, 5am (UTC)",
    "You've hit your usage limit · resets Jul 31, 5am (UTC)",
    "You've hit your org's monthly spend limit · ask your admin to raise it "
    "at claude.ai/settings/usage",
)
_CODEX_MESSAGES: tuple[str, ...] = (
    "You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage "
    "to purchase more credits or try again at Aug 20th, 2026 3:33 AM.",
    "the agent answered `session/prompt` with an error: usage limit exceeded",
)
_ORDINARY_MESSAGE = "the agent answered `session/prompt` with an error: stream ended early"


def _signatures_for(
    *, availability_key: str, source: str, discriminator: frozenset[str] | str
) -> list[AcpAvailabilitySignature]:
    """Every built-in signature of this source matching exactly this discriminator.

    The whole list is returned rather than the first element so each caller
    asserts the COUNT: a mapping declared twice with the same disposition is
    merely redundant to the classifier, but as a registry claim "this form is
    carried once" is what a reader can check against the contract's list.
    """
    return [
        signature
        for signature in builtin_availability_signatures(availability_key=availability_key)
        if signature.source == source
        and (
            signature.machine_code
            if source == _MACHINE_CODE_SOURCE
            else frozenset(signature.all_literals)
        )
        == discriminator
    ]


def _candidate(*, availability_key: str) -> AcpCandidate:
    """A built-in candidate in one domain, declaring no signatures of its own."""
    return AcpCandidate(
        adapter=AcpAdapter(command="adapter", env={}, args=()),
        identity=AcpCandidateIdentity(
            display_name=f"built-in {availability_key} ACP adapter",
            candidate_key=f"builtin-{availability_key}-0000000000000000",
            availability_key=availability_key,
        ),
        signatures=(),
    )


def test_every_measured_message_form_is_a_builtin_quota_signature() -> None:
    """Each measured sentence form exists once, as `protocol.message` quota."""
    for availability_key, forms in (
        (ANTHROPIC_DOMAIN, _CLAUDE_MESSAGE_FORMS),
        (CODEX_DOMAIN, _CODEX_MESSAGE_FORMS),
    ):
        for literals in forms:
            matches = _signatures_for(
                availability_key=availability_key,
                source=_MESSAGE_SOURCE,
                discriminator=frozenset(literals),
            )
            assert len(matches) == 1, (availability_key, literals)
            assert matches[0].cause == _QUOTA, (availability_key, literals)
            assert matches[0].scope == DOMAIN_SCOPE, (availability_key, literals)


def test_both_codex_structured_spellings_are_builtin_machine_code_signatures() -> None:
    """The token survives as a machine code in both spellings the adapter emits."""
    for code in _CODEX_MACHINE_CODES:
        matches = _signatures_for(
            availability_key=CODEX_DOMAIN, source=_MACHINE_CODE_SOURCE, discriminator=code
        )
        assert len(matches) == 1, code
        assert matches[0].cause == _QUOTA, code
        assert matches[0].scope == DOMAIN_SCOPE, code
        assert matches[0].all_literals == (), code


def test_every_builtin_quota_signature_is_scoped_to_its_availability_domain() -> None:
    """CONTROL: a spent allowance belongs to the account, never to one model."""
    for availability_key in (ANTHROPIC_DOMAIN, CODEX_DOMAIN):
        quota = [
            signature
            for signature in builtin_availability_signatures(availability_key=availability_key)
            if signature.cause == _QUOTA
        ]
        assert quota, availability_key
        for signature in quota:
            assert signature.scope == DOMAIN_SCOPE, (availability_key, signature)
            assert signature.hold_key is None, (availability_key, signature)


def test_a_message_only_payload_classifies_as_quota_for_both_builtin_candidates() -> None:
    """With no structured data left, the sentence alone reaches a typed quota."""
    for availability_key, messages in (
        (ANTHROPIC_DOMAIN, _CLAUDE_MESSAGES),
        (CODEX_DOMAIN, _CODEX_MESSAGES),
    ):
        for message in messages:
            verdict = classify_acp_failure(
                signal=AcpFailureSignal(
                    original_identity="acp-protocol-error",
                    protocol_message=message,
                    turn_started=True,
                ),
                candidate=_candidate(availability_key=availability_key),
                builtin=True,
            )
            assert isinstance(verdict, AcpAvailabilityFailure), (availability_key, message)
            assert verdict.cause == _QUOTA, (availability_key, message)
            assert verdict.scope == DOMAIN_SCOPE, (availability_key, message)
            assert verdict.hold_key == availability_key, (availability_key, message)
            assert verdict.candidate_key is None, (availability_key, message)


def test_either_codex_structured_spelling_classifies_as_quota_on_its_own() -> None:
    """The structured token needs no sentence beside it, in either spelling."""
    for code in _CODEX_MACHINE_CODES:
        verdict = classify_acp_failure(
            signal=AcpFailureSignal(
                original_identity="acp-protocol-error", machine_code=code, turn_started=True
            ),
            candidate=_candidate(availability_key=CODEX_DOMAIN),
            builtin=True,
        )
        assert isinstance(verdict, AcpAvailabilityFailure), code
        assert verdict.cause == _QUOTA, code
        assert verdict.source == _MACHINE_CODE_SOURCE, code
        assert verdict.hold_key == CODEX_DOMAIN, code


def test_an_ordinary_provider_message_still_matches_no_builtin_signature() -> None:
    """CONTROL: the widened tables claim no diagnostic they were not measured on.

    Without this, a table whose literals had been loosened into a broader match
    would satisfy every positive above while holding the whole account over an
    unrelated stream fault.
    """
    for availability_key in (ANTHROPIC_DOMAIN, CODEX_DOMAIN):
        verdict = classify_acp_failure(
            signal=AcpFailureSignal(
                original_identity="acp-protocol-error",
                protocol_message=_ORDINARY_MESSAGE,
                turn_started=True,
            ),
            candidate=_candidate(availability_key=availability_key),
            builtin=True,
        )
        assert isinstance(verdict, AcpNonEligibleFailure), availability_key
        assert verdict.reason == "unmatched", availability_key
        assert verdict.original_identity == "acp-protocol-error", availability_key
