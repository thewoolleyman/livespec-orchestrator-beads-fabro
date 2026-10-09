"""A failed run's category, derived on both engines without guessing.

Plan `fabro-currency` P4 (`bd-ib-227cbw`). The fail-closed classification this
repository added for provider spend ceilings reads a cause chain: Fabro's own
classifier labels a usage-limit refusal `transient_infra`, which makes it
RETRYABLE, so the port rewrites it to `deterministic` and flags the vendor that
refused. The Petri-era engine (v0.378.0-nightly.0, `64b9d88`) carries NO chain —
its failure block is `{reason, detail: {message, category}}` with no `causes`,
no `signature` and no `transient_infra` field (research note 006 and the P3
rider on the work-item) — so the same refusal arrives with its category already
written and its text in one message.

WHAT IS MEASURED AND WHAT IS COMPOSED, stated because the distinction decides
what these tests prove. The CHANNEL is measured: research note 007's probes p2
and p6 established that a node's stderr arrives in
`conclusion.failure.detail.message` on the candidate and in neither field on
0.254. The embedded provider payload is also measured, on the hp factory
2026-08-22, where 10 of 53 failed runs carried the Codex
`usage_limit_exceeded` form. What is COMPOSED here is the pairing: no Petri-era
provider ceiling has been observed yet, because the candidate instance has run
no credentialed agent. The pairing follows from where the payload comes from —
the ACP adapter writes it, the engine only relays the text — so the assertions
below are about the classification, never about an engine sentence nobody has
seen.
"""

from __future__ import annotations

from typing import Any

from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_failure_detail_from_payload,
)

_ACP_WRAPPER = "ACP protocol error"
# Reproduced from run 01M0DN6CTWPF's `fabro inspect --json` (the fixture
# `test_fabro_provider_usage_limit.py` carries), i.e. real provider bytes.
_CODEX_USAGE_LIMIT = (
    'Internal error: {\n  "spawned_at": "/home/u/.cargo/registry/src/'
    'index.crates.io-1949cf8c/agent-client-protocol-0.11.1/src/session.rs:567:14",\n'
    '  "data": {\n    "message": "You\'ve hit your usage limit. Visit '
    "https://chatgpt.com/codex/settings/usage to purchase more credits or try again "
    'at Aug 20th, 2026 3:33 AM.",\n    "codex_error_info": "usage_limit_exceeded"\n'
    "  }\n}"
)


def _petri_payload(*, message: str, category: str) -> list[dict[str, Any]]:
    """One candidate inspect payload carrying one Petri-shaped failure block."""
    return [
        {
            "run_id": "01M4DCR2T008",
            "status": {"kind": "failed", "reason": "workflow_error"},
            "conclusion": {
                "status": "failed",
                "timestamp": "2026-10-08T12:35:02.448190113Z",
                "total_retries": 1,
                "failure": {
                    "reason": "workflow_error",
                    "detail": {"message": message, "category": category},
                },
            },
        }
    ]


def _legacy_payload(*, causes: list[str], category: str, signature: str) -> list[dict[str, Any]]:
    """One pinned-engine inspect payload carrying one `causes` chain."""
    return [
        {
            "run_id": "01M0DN6CTWPF",
            "status": {"kind": "failed", "reason": "workflow_error"},
            "failure": {"causes": causes, "category": category, "signature": signature},
        }
    ]


def test_petri_provider_ceiling_is_reclassified_from_its_message_alone() -> None:
    """No chain, so the message IS the chain the classifiers grade."""
    detail = fabro_failure_detail_from_payload(
        payload=_petri_payload(message=_CODEX_USAGE_LIMIT, category="transient_infra")
    )

    assert detail is not None
    assert detail.provider_usage_limit is True
    assert detail.provider_usage_limit_provider == "codex"
    # The engine said `transient_infra`, which is what made it retryable; a
    # ceiling cannot clear on retry, so the port reports it as permanent.
    assert detail.category == "deterministic"
    assert detail.cause is not None
    assert detail.cause.startswith("You've hit your usage limit.")


def test_an_ordinary_petri_category_passes_through_untouched() -> None:
    """The rewrite fires on a ceiling, not on every Petri failure."""
    detail = fabro_failure_detail_from_payload(
        payload=_petri_payload(
            message="checkpoint operation budget exceeded: git commit timed out after 600001ms",
            category="deterministic",
        )
    )

    assert detail is not None
    assert detail.provider_usage_limit is False
    assert detail.provider_usage_limit_provider is None
    assert detail.category == "deterministic"
    assert detail.signature is None


def test_the_legacy_chain_and_signature_readers_are_unchanged() -> None:
    """A 0.254 payload is still read through its chain, signature rewrite included."""
    detail = fabro_failure_detail_from_payload(
        payload=_legacy_payload(
            causes=[_ACP_WRAPPER, _CODEX_USAGE_LIMIT],
            category="transient_infra",
            signature="implement|transient_infra|acp turn failed",
        )
    )

    assert detail is not None
    assert detail.provider_usage_limit is True
    assert detail.category == "deterministic"
    assert detail.signature == "implement|deterministic|acp turn failed"


def test_an_unknown_failure_variant_classifies_nothing() -> None:
    """Neither variant present, so the port reads nothing rather than guessing.

    A `detail` that is not a mapping and a block carrying only `reason` are both
    UNKNOWN variants. The fail-closed answer is no detail at all, which leaves
    the dispatcher's failed outcome on its raw-stderr fallback — rather than a
    category this parser invented from an unmeasured shape, which every
    downstream record would carry as the engine's own verdict.
    """
    assert (
        fabro_failure_detail_from_payload(
            payload=[{"status": {"kind": "failed"}, "failure": {"detail": "not an object"}}]
        )
        is None
    )
    assert (
        fabro_failure_detail_from_payload(
            payload=[{"status": {"kind": "failed"}, "failure": {"reason": "workflow_error"}}]
        )
        is None
    )
