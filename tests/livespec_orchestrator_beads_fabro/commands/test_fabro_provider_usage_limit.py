"""Provider usage/spend ceilings are permanent failures, and say so.

Fabro's own classifier labels a provider usage-limit refusal `transient_infra`,
so the run is RETRIED against an allowance that is already gone and then parked
at the human gate. The dispatcher surfaced none of that: the cause chain's outer
element is a fixed transport wrapper, so every one of these read as a bare
"ACP protocol error".

Measured 2026-08-22 across the 53 failed runs on the hp factory: 11 carried a
provider-limit refusal in their cause chain (10 Codex `usage_limit_exceeded`,
1 Anthropic monthly spend limit), all classified `transient_infra`.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._fabro_port_failure import (
    fabro_failure_detail_from_payload,
)

# The Codex form, reproduced from run 01M0DN6CTWPF's `fabro inspect --json`.
_CODEX_USAGE_LIMIT = (
    'Internal error: {\n  "spawned_at": "/home/u/.cargo/registry/src/'
    'index.crates.io-1949cf8c/agent-client-protocol-0.11.1/src/session.rs:567:14",\n'
    '  "data": {\n    "message": "You\'ve hit your usage limit. Visit '
    "https://chatgpt.com/codex/settings/usage to purchase more credits or try again "
    'at Aug 20th, 2026 3:33 AM.",\n    "codex_error_info": "usage_limit_exceeded"\n'
    "  }\n}"
)
_ANTHROPIC_SPEND_LIMIT = (
    "Internal error: You've hit your org's monthly spend limit "
    "· ask your admin to raise it at claude.ai/settings/usage"
)
_ACP_WRAPPER = "ACP protocol error"


def _payload(*, causes: list[str], category: str = "transient_infra") -> list[object]:
    """A single-element inspect payload carrying one failure block."""
    return [{"status": {"kind": "failed"}, "failure": {"causes": causes, "category": category}}]


def test_root_cause_is_the_innermost_element_not_the_transport_wrapper() -> None:
    """`causes[0]` is a fixed wrapper in 17 of 17 measured blocks; the root is last."""
    detail = fabro_failure_detail_from_payload(
        payload=_payload(causes=[_ACP_WRAPPER, "the real fault"])
    )
    assert detail is not None
    assert detail.cause == "the real fault"


def test_codex_usage_limit_is_permanent_and_flagged() -> None:
    """The machine-readable `usage_limit_exceeded` field drives the decision."""
    detail = fabro_failure_detail_from_payload(
        payload=_payload(causes=[_ACP_WRAPPER, _CODEX_USAGE_LIMIT])
    )
    assert detail is not None
    assert detail.provider_usage_limit is True
    assert detail.category == "deterministic"


def test_codex_usage_limit_surfaces_the_providers_own_sentence() -> None:
    """The embedded `data.message` wins over the raw text, which leads with a path."""
    detail = fabro_failure_detail_from_payload(
        payload=_payload(causes=[_ACP_WRAPPER, _CODEX_USAGE_LIMIT])
    )
    assert detail is not None
    assert detail.cause is not None
    assert detail.cause.startswith("You've hit your usage limit.")
    assert "try again at Aug 20th, 2026 3:33 AM." in detail.cause
    assert "spawned_at" not in detail.cause


def test_anthropic_monthly_spend_limit_is_also_permanent() -> None:
    """Both vendors' ceilings surface here, so both hint families must match."""
    detail = fabro_failure_detail_from_payload(
        payload=_payload(causes=[_ACP_WRAPPER, _ANTHROPIC_SPEND_LIMIT])
    )
    assert detail is not None
    assert detail.provider_usage_limit is True
    assert detail.category == "deterministic"


def test_the_anthropic_ceiling_names_the_anthropic_provider() -> None:
    """The vendor is READ OFF the observed cause, not assumed.

    Detection is deliberately vendor-agnostic — the typed flag is set for
    either vendor — so a fixed provider label would record this Anthropic
    ceiling under the Codex vendor and hold no record for the one that
    actually refused.
    """
    detail = fabro_failure_detail_from_payload(
        payload=_payload(causes=[_ACP_WRAPPER, _ANTHROPIC_SPEND_LIMIT])
    )
    assert detail is not None
    assert detail.provider_usage_limit_provider == "anthropic"


def test_the_codex_ceiling_names_the_codex_provider() -> None:
    """CONTROL for the case above: the Codex form still classifies as Codex.

    Without it, a classifier that answered "anthropic" unconditionally would
    pass the Anthropic case, which is the same fixed-constant defect one
    vendor to the left.
    """
    detail = fabro_failure_detail_from_payload(
        payload=_payload(causes=[_ACP_WRAPPER, _CODEX_USAGE_LIMIT])
    )
    assert detail is not None
    assert detail.provider_usage_limit_provider == "codex"


def test_an_ordinary_transient_failure_names_no_provider() -> None:
    """A failure that is not a ceiling attributes no vendor at all."""
    detail = fabro_failure_detail_from_payload(
        payload=_payload(causes=[_ACP_WRAPPER, "connection reset by peer"])
    )
    assert detail is not None
    assert detail.provider_usage_limit_provider is None


def test_a_bare_usage_limit_sentence_falls_back_to_its_hint_vendor() -> None:
    """A ceiling naming no vendor is attributed by the hint that matched it.

    The measured Anthropic form carries `claude.ai` and the measured Codex
    form carries `chatgpt.com/codex`, so the marker pass answers both. A
    provider that ships neither still has to land somewhere, and the hint
    family it matched is the only evidence left.
    """
    detail = fabro_failure_detail_from_payload(
        payload=_payload(causes=[_ACP_WRAPPER, "Internal error: monthly spend limit reached"])
    )
    assert detail is not None
    assert detail.provider_usage_limit_provider == "anthropic"


def test_an_ordinary_transient_failure_is_left_alone() -> None:
    """CONTROL: this assertion fails if the reclassification is applied blindly.

    Without it, "every category is deterministic" would read as a pass whether
    the rule discriminates or not.
    """
    detail = fabro_failure_detail_from_payload(
        payload=_payload(causes=[_ACP_WRAPPER, "connection reset by peer"])
    )
    assert detail is not None
    assert detail.provider_usage_limit is False
    assert detail.category == "transient_infra"
    assert detail.cause == "connection reset by peer"


def test_a_cause_bearing_block_wins_over_an_earlier_causeless_one() -> None:
    """Traversal order hid the real cause on 2 of the 10 measured Codex runs."""
    payload: list[object] = [
        {
            "status": {"kind": "failed"},
            "failure": {"category": "deterministic"},
            "nested": {"failure": {"causes": [_ACP_WRAPPER, _CODEX_USAGE_LIMIT]}},
        }
    ]
    detail = fabro_failure_detail_from_payload(payload=payload)
    assert detail is not None
    assert detail.provider_usage_limit is True


def test_a_block_with_no_causes_still_yields_its_category() -> None:
    """The causeless stall-watchdog block keeps working (28 of 38 measured)."""
    payload: list[object] = [
        {"status": {"kind": "failed"}, "failure": {"category": "deterministic"}}
    ]
    detail = fabro_failure_detail_from_payload(payload=payload)
    assert detail is not None
    assert detail.cause is None
    assert detail.category == "deterministic"
    assert detail.provider_usage_limit is False
