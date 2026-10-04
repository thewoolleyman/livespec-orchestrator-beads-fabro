"""The MEASURED per-million base rates every priced model entry is built from.

`SPECIFICATION/contracts.md` section "Agent and model catalogs" makes a model
catalog entry carry "the four USD-per-million prices in the `pricing` shape of
section "Factory-configurable ACP fallback priority"", and the cost paragraph
of that section resolves a candidate's price "through the model catalog entry
the candidate's identity names first".

WHY THE BASE RATES LIVE HERE RATHER THAN IN EITHER TABLE THAT READS THEM. Two
tables are keyed by model and priced from the same published numbers: the
committed model catalog (`_acp_model_catalog`, which the per-attempt chain cost
resolves through) and the per-token table the legacy host-OTLP span path reads
(`_dispatcher_cost_pricing`). Writing the rates twice is writing one fact twice,
and the drift is silent in the worst available direction -- the two paths would
price the SAME attempt differently, each reporting a well-formed observation,
with nothing in either output to show that they disagree. One table, two
readers.

WHICH MODELS ARE PRICED, AND WHY NOT EVERY CATALOGUED ONE. Only the models this
repository has a published rate for. A model in the catalog with no rate here
carries NO pricing, which is the honest value: under the cost paragraph's
no-default rule an unpriceable nonzero component makes the whole run cost
unobservable, so the absence surfaces as an explicit gap an operator fixes with
one `dispatcher.model_catalog` entry. A guessed rate instead gets summed into a
run cost and read back as an observation, which is the failure this file exists
to avoid.
"""

from __future__ import annotations

from collections.abc import Mapping

from livespec_orchestrator_beads_fabro.commands._acp_candidate_pricing import AcpCandidatePricing

__all__: list[str] = [
    "builtin_model_pricing",
    "builtin_model_pricing_table",
    "priced_model_ids",
]

# The ephemeral-prompt-cache write multiplier. Claude Code uses the
# default 5-minute prompt cache, whose write rate is 1.25x the base input
# rate. Named so it is adjustable in ONE place if CC adopts the 1-hour
# (2x) cache TTL. The cache-READ multiplier is the published 0.10x input.
_CACHE_WRITE_MULTIPLIER = 1.25
_CACHE_READ_MULTIPLIER = 0.10

# Per-1M-token USD base rates (input, output), authoritative as of 2026-06
# (the efj price table) plus `claude-opus-5` at the Opus family's published
# rates. The two cache rates derive from the input rate via the named
# multipliers above (opus 5.00->6.25/0.50, sonnet 3.00->3.75/0.30, haiku
# 1.00->1.25/0.10, fable 10.00->12.50/1.00 -- exactly the ratified table).
_BASE_RATES: Mapping[str, tuple[float, float]] = {
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-fable-5": (10.00, 50.00),
    "gpt-5.5": (5.00, 30.00),
    "gpt-5.4-mini": (0.75, 4.50),
}


def priced_model_ids() -> tuple[str, ...]:
    """Every model id this build carries a published base rate for."""
    return tuple(_BASE_RATES)


def builtin_model_pricing(*, model: str) -> AcpCandidatePricing | None:
    """The complete four-component table for `model`, or None when unpriced.

    `model` is matched EXACTLY -- callers normalize an emitted identity through
    `_acp_model_identity.exact_model_identity` first. A table is returned whole
    or not at all, which is the all-or-none rule the contract applies "to
    catalog entry and override alike": a three-price table would be silently
    useless the first time a run reported the fourth category.
    """
    rates = _BASE_RATES.get(model)
    return None if rates is None else _price_for(model=model, rates=rates)


def builtin_model_pricing_table() -> Mapping[str, AcpCandidatePricing]:
    """Every priced model's complete table, keyed by model id."""
    return {model: _price_for(model=model, rates=rates) for model, rates in _BASE_RATES.items()}


def _price_for(*, model: str, rates: tuple[float, float]) -> AcpCandidatePricing:
    """Build a complete table from the two published base rates + the multipliers.

    cache-write = 1.25x input (5-minute ephemeral prompt cache);
    cache-read = 0.10x input. Derived from the multipliers so the cache
    rates stay in lockstep with the base input rate.
    """
    base_input, base_output = rates
    return AcpCandidatePricing(
        model=model,
        input_usd_per_million=base_input,
        output_usd_per_million=base_output,
        cache_write_usd_per_million=base_input * _CACHE_WRITE_MULTIPLIER,
        cache_read_usd_per_million=base_input * _CACHE_READ_MULTIPLIER,
    )
