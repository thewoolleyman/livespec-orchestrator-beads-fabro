"""Codex's structured usage-limit token is read as a FIELD, in both spellings.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "Structured fields MUST be parsed as fields, independent of JSON
whitespace and key order, never matched as a byte substring", and the measured
minimum set names the usage-limit field "in BOTH its camelCase spelling
(`codexErrorInfo` carrying `usageLimitExceeded`) and its snake_case spelling
(`codex_error_info` carrying `usage_limit_exceeded`)". Scenario 65's outline
grades all three shapes below, the reordered-and-respaced one included.

WHAT THE BYTE STRING COULD NOT SEE. Detection matched the literal bytes
`"codex_error_info": "usage_limit_exceeded"` against the whitespace-collapsed
cause, so it recognised exactly one serialization of one spelling. The October
Codex payload carries the camelCase spelling (investigation D2(c),
`plan/factory-configurable-model-fallback-priority/research/
dispatcher-fallback-downsides-2026-10-12.md`), which that string
cannot match; and a serializer that emits no space after the colon, or orders
`codex_error_info` before `message`, defeats it on the one spelling it DOES
know.

EVERY STRUCTURED FIXTURE CARRIES A MUTE MESSAGE, and that is the point. A real
refusal carries the provider's sentence too, so a fixture carrying both would
pass on the prose hint whether or not the field was ever parsed -- the prose
fallback is exactly what "saved" the camelCase payload while leaving the
structured path broken. Replacing the sentence with text matching no hint
makes the field the only evidence there is.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._fabro_port_permanent_failure import (
    fabro_permanent_cause,
    fabro_usage_limit_provider,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_failure_detail_from_payload,
)

_ACP_WRAPPER = "ACP protocol error"
_SPAWNED_AT = (
    "/home/u/.cargo/registry/src/index.crates.io-1949cf8c/"
    "agent-client-protocol-0.11.1/src/session.rs:567:14"
)
# No hint matches this, so it cannot stand in for the structured field.
_MUTE_MESSAGE = "The provider refused this request."

# The October spelling, in the serialization the measured payload uses.
_CODEX_CAMEL_CASE = (
    f'Internal error: {{\n  "spawned_at": "{_SPAWNED_AT}",\n'
    f'  "data": {{\n    "message": "{_MUTE_MESSAGE}",\n'
    '    "codexErrorInfo": "usageLimitExceeded"\n  }\n}'
)
# The spelling the byte string knew, in the serialization it used.
_CODEX_SNAKE_CASE = (
    f'Internal error: {{\n  "spawned_at": "{_SPAWNED_AT}",\n'
    f'  "data": {{\n    "message": "{_MUTE_MESSAGE}",\n'
    '    "codex_error_info": "usage_limit_exceeded"\n  }\n}'
)
# The SAME spelling with the keys reordered and every space removed: a
# well-formed payload the byte string cannot match.
_CODEX_SNAKE_CASE_RESERIALIZED = (
    'Internal error: {"data":{"codex_error_info":"usage_limit_exceeded",'
    f'"message":"{_MUTE_MESSAGE}"}},"spawned_at":"{_SPAWNED_AT}"}}'
)
# CONTROL: the measured field name carrying a value that is not the measured
# token. Matching the key alone would claim every Codex error as a ceiling.
_CODEX_OTHER_ERROR_INFO = (
    f'Internal error: {{\n  "data": {{\n    "message": "{_MUTE_MESSAGE}",\n'
    '    "codex_error_info": "stream_disconnected"\n  }\n}'
)

_MEASURED_CODEX_STRUCTURED_FORMS = (
    _CODEX_CAMEL_CASE,
    _CODEX_SNAKE_CASE,
    _CODEX_SNAKE_CASE_RESERIALIZED,
)

# The Codex message forms, as they arrive on an engine that kept no payload.
_CODEX_USAGE_LIMIT_SENTENCE = (
    "You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage "
    "to purchase more credits or try again at Aug 20th, 2026 3:33 AM."
)
_CODEX_USAGE_LIMIT_EXCEEDED = (
    "the agent answered `session/prompt` with an error: usage limit exceeded"
)

_TRANSIENT_SIGNATURE = "implement|transient_infra|acp turn failed"
_PERMANENT_SIGNATURE = "implement|deterministic|acp turn failed"


def _chain_payload(*, cause: str) -> list[object]:
    """A pinned-engine inspect payload carrying one failure block with a chain.

    The arriving category and signature are the TRANSIENT ones Fabro's own
    node-layer classifier writes for a spent allowance, which is what makes
    the rewrite observable rather than a value that was already correct.
    """
    return [
        {
            "status": {"kind": "failed"},
            "failure": {
                "causes": [_ACP_WRAPPER, cause],
                "category": "transient_infra",
                "signature": _TRANSIENT_SIGNATURE,
            },
        }
    ]


def _message_only_payload(*, message: str) -> list[object]:
    """A Petri-era inspect payload: one `detail.message`, no chain, no payload."""
    return [
        {
            "status": {"kind": "failed"},
            "failure": {
                "reason": "workflow_error",
                "detail": {"message": message, "category": "transient_infra"},
            },
        }
    ]


def test_both_codex_spellings_are_read_as_fields_whatever_the_serialization() -> None:
    """camelCase, snake_case, and snake_case reordered and respaced all match."""
    for cause in _MEASURED_CODEX_STRUCTURED_FORMS:
        causes = (_ACP_WRAPPER, cause)
        assert fabro_permanent_cause(causes=causes) == cause, cause
        assert fabro_usage_limit_provider(causes=causes) == "codex", cause


def test_the_measured_field_carrying_another_value_is_not_a_ceiling() -> None:
    """CONTROL: the VALUE is the token, so the key alone decides nothing.

    Without this, matching on the field name would report every Codex error
    that happens to carry `codex_error_info` as a spent allowance.
    """
    causes = (_ACP_WRAPPER, _CODEX_OTHER_ERROR_INFO)
    assert fabro_permanent_cause(causes=causes) is None
    assert fabro_usage_limit_provider(causes=causes) is None


def test_a_codex_structured_ceiling_is_permanent_in_category_signature_and_state() -> None:
    """Scenario 65: the category, the signature and the typed flag all agree."""
    for cause in _MEASURED_CODEX_STRUCTURED_FORMS:
        detail = fabro_failure_detail_from_payload(payload=_chain_payload(cause=cause))
        assert detail is not None, cause
        assert detail.category == "deterministic", cause
        assert detail.signature == _PERMANENT_SIGNATURE, cause
        assert detail.provider_usage_limit is True, cause
        assert detail.provider_usage_limit_provider == "codex", cause


def test_a_message_only_codex_payload_is_recognized_from_its_text_alone() -> None:
    """With no structured payload left, both measured Codex sentences suffice."""
    for message in (_CODEX_USAGE_LIMIT_SENTENCE, _CODEX_USAGE_LIMIT_EXCEEDED):
        detail = fabro_failure_detail_from_payload(payload=_message_only_payload(message=message))
        assert detail is not None, message
        assert detail.provider_usage_limit is True, message
        assert detail.category == "deterministic", message
