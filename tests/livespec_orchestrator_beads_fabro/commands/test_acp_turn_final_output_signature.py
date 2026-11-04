"""The codex-acp capacity refusal is a measured `turn.final_output` built-in signature.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": the measured minimum set "carries one form that is neither `cause:
quota` nor domain-scoped: for `codex-acp`, the capacity form, source
`turn.final_output`, `cause: provider_capacity`, `scope: candidate`,
`final_text` `Selected model is at capacity. Please try a different model.`"
A `turn.final_output` signature "requires one non-empty `final_text` ... and
forbids `all_literals`, `machine_code` and `exit_code`; it MUST declare
`scope: candidate`. No other source accepts `final_text`."
"""

from __future__ import annotations

from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_builtin_candidates import (
    ANTHROPIC_DOMAIN,
    CODEX_DOMAIN,
)
from livespec_orchestrator_beads_fabro.commands._acp_builtin_signatures import (
    builtin_availability_signatures,
)
from livespec_orchestrator_beads_fabro.commands._acp_candidate_signatures import (
    SIGNATURE_SOURCES,
    parse_availability_signatures,
)

_CAPACITY_TEXT = "Selected model is at capacity. Please try a different model."
_SOURCE = "turn.final_output"


def _parse(*, entry: dict[str, Any]) -> object:
    return parse_availability_signatures(value=[entry], key="probe")


def test_the_codex_builtin_table_carries_the_measured_capacity_form() -> None:
    matches = [
        signature
        for signature in builtin_availability_signatures(availability_key=CODEX_DOMAIN)
        if signature.source == _SOURCE
    ]
    assert len(matches) == 1
    capacity = matches[0]
    assert capacity.cause == "provider_capacity"
    assert capacity.scope == "candidate"
    assert capacity.final_text == _CAPACITY_TEXT
    assert capacity.all_literals == ()
    assert capacity.machine_code is None
    assert capacity.exit_code is None


def test_the_claude_builtin_table_carries_no_final_output_form() -> None:
    sources = {
        signature.source
        for signature in builtin_availability_signatures(availability_key=ANTHROPIC_DOMAIN)
    }
    assert _SOURCE not in sources


def test_the_grammar_names_the_final_output_source() -> None:
    assert _SOURCE in SIGNATURE_SOURCES


def test_a_final_output_signature_with_final_text_parses() -> None:
    parsed = _parse(
        entry={
            "source": _SOURCE,
            "cause": "provider_capacity",
            "scope": "candidate",
            "final_text": _CAPACITY_TEXT,
        }
    )
    assert not isinstance(parsed, str), parsed
    assert parsed[0].final_text == _CAPACITY_TEXT


def test_a_final_output_signature_refuses_a_missing_or_blank_final_text() -> None:
    base = {"source": _SOURCE, "cause": "provider_capacity", "scope": "candidate"}
    assert isinstance(_parse(entry=base), str)
    assert isinstance(_parse(entry={**base, "final_text": "   "}), str)


def test_a_final_output_signature_refuses_every_other_discriminator() -> None:
    base = {
        "source": _SOURCE,
        "cause": "provider_capacity",
        "scope": "candidate",
        "final_text": _CAPACITY_TEXT,
    }
    assert isinstance(_parse(entry={**base, "all_literals": ["capacity"]}), str)
    assert isinstance(_parse(entry={**base, "machine_code": "capacity"}), str)
    assert isinstance(_parse(entry={**base, "exit_code": 1}), str)


def test_a_final_output_signature_must_be_candidate_scoped() -> None:
    refused = _parse(
        entry={
            "source": _SOURCE,
            "cause": "provider_capacity",
            "scope": "availability-domain",
            "final_text": _CAPACITY_TEXT,
        }
    )
    assert isinstance(refused, str)
    assert "candidate" in refused


def test_no_other_source_accepts_final_text() -> None:
    for source in ("protocol.message", "process.terminal_diagnostic"):
        refused = _parse(
            entry={
                "source": source,
                "cause": "quota",
                "scope": "availability-domain",
                "all_literals": ["usage limit"],
                "final_text": _CAPACITY_TEXT,
            }
        )
        assert isinstance(refused, str), source
    refused_code = _parse(
        entry={
            "source": "protocol.machine_code",
            "cause": "quota",
            "scope": "availability-domain",
            "machine_code": "usageLimitExceeded",
            "final_text": _CAPACITY_TEXT,
        }
    )
    assert isinstance(refused_code, str)
