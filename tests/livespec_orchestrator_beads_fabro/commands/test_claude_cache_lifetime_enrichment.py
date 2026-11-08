"""Regression coverage for Claude cache-write lifetime forwarding."""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._claude_cache_lifetimes import (
    cache_write_lifetimes,
)
from livespec_orchestrator_beads_fabro.commands._otel_enrich import enrich_span
from livespec_orchestrator_beads_fabro.commands._otel_scrub import ATTRIBUTE_ALLOWLIST


def _attr(*, key: str, value: object) -> dict[str, object]:
    return {"key": key, "value": value}


def _values(*, span: dict[str, object]) -> dict[str, object]:
    return {
        entry["key"]: next(iter(entry["value"].values()))
        for entry in span["attributes"]
        if isinstance(entry, dict)
        and isinstance(entry.get("key"), str)
        and isinstance(entry.get("value"), dict)
    }


@pytest.mark.parametrize(
    ("cache_creation", "expected"),
    [
        (
            {"ephemeral_5m_input_tokens": 125, "ephemeral_1h_input_tokens": 40},
            {"cache_creation_5m_tokens": "125", "cache_creation_1h_tokens": "40"},
        ),
        ({"ephemeral_5m_input_tokens": 125}, {"cache_creation_5m_tokens": "125"}),
        ({"ephemeral_1h_input_tokens": 40}, {"cache_creation_1h_tokens": "40"}),
        ({}, {}),
    ],
)
def test_claude_api_response_enrichment_forwards_lifetimes_and_join_keys(
    *, cache_creation: dict[str, int], expected: dict[str, str]
) -> None:
    span = {
        "name": "claude_code.llm_request",
        "usage": {"cache_creation": cache_creation},
        "attributes": [
            _attr(key="request_id", value={"stringValue": "req-1"}),
            _attr(key="cache_creation_tokens", value={"intValue": "165"}),
        ],
    }

    enriched = enrich_span(
        span=span,
        triple={"livespec.dispatch.id": "dispatch-1"},
    )

    assert enriched is not None
    values = _values(span=enriched)
    assert values["request_id"] == "req-1"
    assert values["livespec.dispatch.id"] == "dispatch-1"
    assert {key: values[key] for key in expected} == expected
    assert {"cache_creation_5m_tokens", "cache_creation_1h_tokens"} - expected.keys() == {
        key for key in ("cache_creation_5m_tokens", "cache_creation_1h_tokens") if key not in values
    }
    assert {"cache_creation_5m_tokens", "cache_creation_1h_tokens"} <= ATTRIBUTE_ALLOWLIST


@pytest.mark.parametrize(
    ("usage", "expected"),
    [
        (None, {}),
        ({"cache_creation": None}, {}),
        ({"cache_creation": {"ephemeral_5m_input_tokens": True}}, {}),
        ({"cache_creation": {"ephemeral_1h_input_tokens": -1}}, {}),
    ],
)
def test_cache_write_lifetimes_omits_unmeasured_or_invalid_counts(
    *, usage: object, expected: dict[str, int]
) -> None:
    assert cache_write_lifetimes(usage=usage) == expected


def test_non_claude_record_does_not_interpret_a_usage_block() -> None:
    enriched = enrich_span(
        span={
            "name": "another.provider.request",
            "usage": {"cache_creation": {"ephemeral_5m_input_tokens": 125}},
        },
        triple={},
    )

    assert enriched is not None
    assert enriched["attributes"] == []
    assert "usage" not in enriched
