"""Tests for the pure CC-token cost pricing (work-item livespec-impl-beads-efj).

The pricing half of efj's cap-wiring: `derive_usd_micros` turns the
per-API-call token counts the host OTLP receiver sees into the OBSERVED
per-dispatch micro-USD the y0m spend cap reads, lifting 5v9's fail-closed
refusal. These tests pin the EXACT ratified price table (four models x
four categories), the cache multipliers, model normalization (date-suffix
strip + prefix match), and the not-free fallback for an unknown model.

Pure-module tests: no I/O, no fakes — `derive_usd_micros` /
`normalize_model_id` are deterministic functions over a token vector + a
model id, so each branch is driven by synthetic vectors. No real CC
session is launched.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_pricing import (
    DEFAULT_DISPATCH_COST_MODEL,
    TokenVector,
    derive_usd_micros,
    normalize_model_id,
)


def test_golden_opus_carrier_vector() -> None:
    """The carrier vector in:out:cw:cr = 5244:3748:47620:418529 @ opus-4-8 ⇒ ~$0.63.

    The golden assertion from the efj brief: opus-4-8 rates
    5.00/25.00/6.25/0.50 per MTok give 626810 micro-USD ($0.6268). Since a
    per-MTok rate x tokens is already micro-USD (1 USD == 1e6 micro-USD),
    the four products sum directly.
    """
    vector = TokenVector(input=5244, output=3748, cache_write=47620, cache_read=418529)
    assert derive_usd_micros(tokens=vector, model_id="claude-opus-4-8") == 626810


@pytest.mark.parametrize(
    ("model_id", "expected_micros"),
    [
        # 1M tokens in each category isolates the per-category rate as
        # exact micro-USD (tokens x rate where rate is per-1M-token USD).
        ("claude-opus-4-8", 5_000_000),
        ("claude-sonnet-4-6", 3_000_000),
        ("claude-haiku-4-5", 1_000_000),
        ("claude-fable-5", 10_000_000),
    ],
)
def test_input_rate_per_model(*, model_id: str, expected_micros: int) -> None:
    """1M input tokens prices to the model's published per-MTok input rate."""
    vector = TokenVector(input=1_000_000, output=0, cache_write=0, cache_read=0)
    assert derive_usd_micros(tokens=vector, model_id=model_id) == expected_micros


@pytest.mark.parametrize(
    ("model_id", "expected_micros"),
    [
        ("claude-opus-4-8", 25_000_000),
        ("claude-sonnet-4-6", 15_000_000),
        ("claude-haiku-4-5", 5_000_000),
        ("claude-fable-5", 50_000_000),
    ],
)
def test_output_rate_per_model(*, model_id: str, expected_micros: int) -> None:
    """1M output tokens prices to the model's published per-MTok output rate."""
    vector = TokenVector(input=0, output=1_000_000, cache_write=0, cache_read=0)
    assert derive_usd_micros(tokens=vector, model_id=model_id) == expected_micros


@pytest.mark.parametrize(
    ("model_id", "expected_micros"),
    [
        # cache-write = 1.25x input: opus 6.25, sonnet 3.75, haiku 1.25, fable 12.50.
        ("claude-opus-4-8", 6_250_000),
        ("claude-sonnet-4-6", 3_750_000),
        ("claude-haiku-4-5", 1_250_000),
        ("claude-fable-5", 12_500_000),
    ],
)
def test_cache_write_rate_is_one_point_two_five_times_input(
    *, model_id: str, expected_micros: int
) -> None:
    """1M cache-creation tokens prices at 1.25x the input rate (5-min ephemeral)."""
    vector = TokenVector(input=0, output=0, cache_write=1_000_000, cache_read=0)
    assert derive_usd_micros(tokens=vector, model_id=model_id) == expected_micros


@pytest.mark.parametrize(
    ("model_id", "expected_micros"),
    [
        # cache-read = 0.10x input: opus 0.50, sonnet 0.30, haiku 0.10, fable 1.00.
        ("claude-opus-4-8", 500_000),
        ("claude-sonnet-4-6", 300_000),
        ("claude-haiku-4-5", 100_000),
        ("claude-fable-5", 1_000_000),
    ],
)
def test_cache_read_rate_is_one_tenth_input(*, model_id: str, expected_micros: int) -> None:
    """1M cache-read tokens prices at 0.10x the input rate."""
    vector = TokenVector(input=0, output=0, cache_write=0, cache_read=1_000_000)
    assert derive_usd_micros(tokens=vector, model_id=model_id) == expected_micros


def test_zero_tokens_costs_nothing() -> None:
    """An all-zero token vector costs zero micro-USD (no spurious charge)."""
    vector = TokenVector(input=0, output=0, cache_write=0, cache_read=0)
    assert derive_usd_micros(tokens=vector, model_id="claude-opus-4-8") == 0


def test_normalize_strips_date_suffix() -> None:
    """A dated CC model id normalizes to its priced base id by prefix match."""
    assert normalize_model_id(raw_model="claude-haiku-4-5-20251001") == "claude-haiku-4-5"


def test_normalize_exact_match() -> None:
    """An already-bare priced model id normalizes to itself."""
    assert normalize_model_id(raw_model="claude-opus-4-8") == "claude-opus-4-8"


def test_normalize_unknown_model_is_none() -> None:
    """An unrecognized model id normalizes to None (caller applies the default)."""
    assert normalize_model_id(raw_model="gpt-9") is None


def test_normalize_empty_model_is_none() -> None:
    """An empty / whitespace model id normalizes to None."""
    assert normalize_model_id(raw_model="   ") is None


def test_unknown_model_priced_at_default_not_free() -> None:
    """An unknown model id is priced at the committed default — NEVER free.

    A spend cap must not under-count: a token vector whose model id is not
    in the table is priced at `DEFAULT_DISPATCH_COST_MODEL` (CC's own
    default model), so the derived cost equals pricing the SAME vector at
    that default rather than $0.
    """
    vector = TokenVector(input=1000, output=500, cache_write=200, cache_read=300)
    at_unknown = derive_usd_micros(tokens=vector, model_id="totally-unknown-model")
    at_default = derive_usd_micros(tokens=vector, model_id=DEFAULT_DISPATCH_COST_MODEL)
    assert at_unknown == at_default
    assert at_unknown > 0
