"""Every MEASURED Claude provider-limit sentence is a permanent ceiling.

`SPECIFICATION/contracts.md` section "Provider-limit permanence and root-cause
surfacing" requires detection to cover "every measured form", and section
"Factory-configurable ACP fallback priority" fixes that set exactly: for
`claude-acp` the session-limit form (`hit your session limit`), the generic
limit form (`hit your limit` plus `resets`), the usage-limit form (`hit your
usage limit`), and the organisation spend-limit form (`org` plus `spend
limit`). Scenario 65's outline grades each one.

WHY THESE TWO FORMS WERE INVISIBLE. The hint list carried only the Codex
usage-limit prose and the Anthropic spend-limit prose, so Claude's five-hour
session ceiling -- "You've hit your session limit - resets 3:40am (UTC)",
arriving with a structured `errorKind` of `rate_limit` -- was classified
`transient_infra` with no provider at all on 2026-08-23, 2026-09-09 (twice) and
2026-10-09, and the Petri-era wording "You've hit your limit - resets ..."
matched nothing either (investigation D2(b) and D2(d),
`plan/factory-configurable-model-fallback-priority/research/
dispatcher-fallback-downsides-2026-10-12.md`). Measured over this
repository's October journal, the existing detection labelled ZERO
provider-limit failures.

THE `rate_limit` CONTROL IS THE LOAD-BEARING ONE, and it is asserted beside
its own positive on purpose. The contract says "A Claude `rate_limit` kind
alone does not establish quota exhaustion; its measured message discriminator
is required", and a true transient carries the identical structured kind
(journal 2026-10-09). A rule keyed on the kind would pass every positive case
below and fail only there -- while a control with no positive beside it would
pass against a classifier that recognises nothing at all.

The generic-limit and organisation spend-limit bytes are reproduced verbatim
from the recorded ACP spend-limit reproduction
(`plan/fabro-currency/research/004-acp-spend-limit-evidence.json`, modes
`usage-cap` and `monthly-cap`).
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

# The five-hour Claude session ceiling, with the structured kind that made it
# read as a retryable rate limit.
_CLAUDE_SESSION_LIMIT = (
    f'Internal error: {{\n  "spawned_at": "{_SPAWNED_AT}",\n'
    '  "data": {\n    "message": "You\'ve hit your session limit · resets '
    '3:40am (UTC)",\n    "errorKind": "rate_limit"\n  }\n}'
)
# The SAME structured kind with no measured sentence: the control.
_CLAUDE_RATE_LIMIT_ONLY = (
    f'Internal error: {{\n  "spawned_at": "{_SPAWNED_AT}",\n'
    '  "data": {\n    "message": "Overloaded, please retry shortly.",\n'
    '    "errorKind": "rate_limit"\n  }\n}'
)
# The Petri-era forms, where only the failure message text survives.
_CLAUDE_GENERIC_LIMIT = (
    "the agent answered `session/prompt` with an error: "
    "You've hit your limit · resets Jul 31, 5am (UTC)"
)
_CLAUDE_USAGE_LIMIT = (
    "the agent answered `session/prompt` with an error: "
    "You've hit your usage limit · resets Jul 31, 5am (UTC)"
)
_CLAUDE_ORG_SPEND_LIMIT = (
    "the agent answered `session/prompt` with an error: You've hit your org's "
    "monthly spend limit · ask your admin to raise it at claude.ai/settings/usage"
)

_MEASURED_CLAUDE_FORMS = (
    _CLAUDE_SESSION_LIMIT,
    _CLAUDE_GENERIC_LIMIT,
    _CLAUDE_USAGE_LIMIT,
    _CLAUDE_ORG_SPEND_LIMIT,
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
    """A Petri-era inspect payload: one `detail.message`, no chain, no payload.

    Measured on v0.378.0-nightly.0: the block is `{reason, detail: {message,
    category}}` and the provider's structured `data` object is gone, so the
    sentence is the ONLY evidence left.
    """
    return [
        {
            "status": {"kind": "failed"},
            "failure": {
                "reason": "workflow_error",
                "detail": {"message": message, "category": "transient_infra"},
            },
        }
    ]


def test_every_measured_claude_sentence_is_recognized_as_a_provider_usage_limit() -> None:
    """All four measured `claude-acp` forms are provider usage limits."""
    for cause in _MEASURED_CLAUDE_FORMS:
        causes = (_ACP_WRAPPER, cause)
        assert fabro_permanent_cause(causes=causes) == cause, cause
        assert fabro_usage_limit_provider(causes=causes) is not None, cause


def test_a_cause_naming_no_measured_ceiling_is_recognized_as_none_of_them() -> None:
    """CONTROL: recognition discriminates rather than claiming every cause.

    Without this, a reader that answered "provider usage limit" for anything
    would satisfy the four positives above.
    """
    causes = (_ACP_WRAPPER, "connection reset by peer")
    assert fabro_permanent_cause(causes=causes) is None
    assert fabro_usage_limit_provider(causes=causes) is None


def test_a_claude_ceiling_is_permanent_in_category_signature_and_typed_state() -> None:
    """Scenario 65: the category, the signature and the typed flag all agree."""
    for cause in _MEASURED_CLAUDE_FORMS:
        detail = fabro_failure_detail_from_payload(payload=_chain_payload(cause=cause))
        assert detail is not None, cause
        assert detail.category == "deterministic", cause
        assert detail.signature == _PERMANENT_SIGNATURE, cause
        assert detail.provider_usage_limit is True, cause


def test_a_claude_rate_limit_kind_without_a_measured_sentence_keeps_its_category() -> None:
    """The structured kind is not the discriminator; the measured sentence is.

    Both payloads below carry `errorKind: "rate_limit"`. The session-limit one
    is a spent allowance and the other is an ordinary overload, so a rule
    keyed on the kind would be wrong in one direction or the other whichever
    verdict it picked.
    """
    ceiling = fabro_failure_detail_from_payload(payload=_chain_payload(cause=_CLAUDE_SESSION_LIMIT))
    assert ceiling is not None
    assert ceiling.provider_usage_limit is True
    assert ceiling.category == "deterministic"

    transient = fabro_failure_detail_from_payload(
        payload=_chain_payload(cause=_CLAUDE_RATE_LIMIT_ONLY)
    )
    assert transient is not None
    assert transient.provider_usage_limit is False
    assert transient.provider_usage_limit_provider is None
    assert transient.category == "transient_infra"
    assert transient.signature == _TRANSIENT_SIGNATURE


def test_a_message_only_claude_payload_is_recognized_from_its_text_alone() -> None:
    """The Petri-era block carries no structured data, so the text must suffice."""
    for message in (_CLAUDE_GENERIC_LIMIT, _CLAUDE_USAGE_LIMIT, _CLAUDE_ORG_SPEND_LIMIT):
        detail = fabro_failure_detail_from_payload(payload=_message_only_payload(message=message))
        assert detail is not None, message
        assert detail.provider_usage_limit is True, message
        assert detail.category == "deterministic", message
