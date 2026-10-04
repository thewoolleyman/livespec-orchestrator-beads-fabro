"""Pure per-token Claude-Code cost pricing (work-item livespec-impl-beads-efj).

The price table + token→USD math that turns the per-API-call token counts
the host OTLP receiver already sees into the OBSERVED per-dispatch cost
the y0m spend cap consumes. This is the seam that LIFTS 5v9's fail-closed
refusal: `_dispatcher_cost` refuses in an unattended queue drain (a run
with no explicit `--item` selection) whenever run cost is UNOBSERVABLE;
a human-hand-picked `--item` dispatch warns instead of refusing (only
under `LIVESPEC_COST_MODE=enforce`; the default `report` posture never
refuses). Today it is always unobservable because fabro's
`total_usd_micros` is null on every run. Claude-Code emits per-API-call
token counts on its TRACE spans but NO `cost_usd` ATTRIBUTE on the span
(cost is a metric, not a span attribute — see
`loop-reflection-gate/cc-otel-gap-analysis.md`), so the host DERIVES cost from the tokens
x the published per-model price.

Per the user-ratified 2026-06-13 direction (which SUPERSEDES the efj bd
item's stale "requires a fabro upgrade" title): treat CC-token-derived
cost as the PRIMARY signal; fabro's `total_usd_micros` is corroboration
when present. This module is the pricing half — PURE (no I/O, no env
reads, no clock): `derive_usd_micros` is a deterministic function over a
token vector + a model id, so the hermetic test tier drives every branch
with synthetic token vectors and never launches a real CC session.

The four token categories map to the CC span scalar attributes the
`_otel_scrub` allowlist already forwards (`input_tokens`, `output_tokens`,
`cache_creation_tokens`, `cache_read_tokens`). Rates are per-1M-token USD,
authoritative as of 2026-06; cost is returned in integer micro-USD to
match the `usd_micros_to_usd` unit boundary `_dispatcher_cost` funnels the
cap-VALUE comparison through.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._acp_candidate_pricing import AcpCandidatePricing
from livespec_orchestrator_beads_fabro.commands._acp_model_identity import exact_model_identity
from livespec_orchestrator_beads_fabro.commands._acp_model_prices import (
    builtin_model_pricing_table,
)

__all__: list[str] = [
    "DEFAULT_DISPATCH_COST_MODEL",
    "DEFAULT_DISPATCH_COST_MODEL_ENV",
    "ModelPrice",
    "TokenVector",
    "derive_usd_micros",
    "model_price_of",
    "normalize_model_id",
]

# The env-var NAME (not a secret value) for the fallback model a token sum
# with no resolvable `model` attribute is priced at. CC's own default
# model is the committed default so an unpriceable span never reads as
# free — a spend cap must NOT under-estimate.
DEFAULT_DISPATCH_COST_MODEL_ENV = "LIVESPEC_DISPATCH_COST_MODEL"
DEFAULT_DISPATCH_COST_MODEL = "claude-opus-4-8"

# Micro-USD per USD: cost = Σ(tokens x rate_per_MTok) where rate is USD per
# 1_000_000 tokens, so tokens x rate is ALREADY micro-USD (1 USD == 1e6
# micro-USD and 1e6 tokens share the denominator). The conversion is the
# identity below; kept explicit so the unit reasoning is auditable.
_MICRO_USD_PER_USD = 1_000_000


@dataclass(frozen=True, kw_only=True)
class ModelPrice:
    """Per-1M-token USD rates for one model, four categories.

    `input` / `output` are the published per-MTok base rates;
    `cache_write` is the 5-minute-ephemeral write rate (1.25x input) and
    `cache_read` is the read rate (0.10x input). All four are plain USD
    floats per 1_000_000 tokens.
    """

    input: float
    output: float
    cache_write: float
    cache_read: float


@dataclass(frozen=True, kw_only=True)
class TokenVector:
    """The four per-API-call token counts read off a CC span (leak-free).

    Maps the scrub-allowlisted CC span scalars onto the pricing
    categories: `input` ← `input_tokens`, `output` ← `output_tokens`,
    `cache_write` ← `cache_creation_tokens`, `cache_read` ←
    `cache_read_tokens`. All are non-negative integer token counts — no
    goal text, no credentials, just numbers.
    """

    input: int
    output: int
    cache_write: int
    cache_read: int


def model_price_of(*, pricing: AcpCandidatePricing) -> ModelPrice:
    """The four-category `ModelPrice` one complete USD-per-million table names.

    The adapter between the two spellings of one price: a catalog entry's and
    a per-candidate override's `pricing` object carry the four
    `*_usd_per_million` fields the contract's grammar names, while this
    module's arithmetic takes a `ModelPrice`. Written once, here, so a caller
    pricing an attempt through the catalog cannot pair the wrong field with
    the wrong token category.
    """
    return ModelPrice(
        input=pricing.input_usd_per_million,
        output=pricing.output_usd_per_million,
        cache_write=pricing.cache_write_usd_per_million,
        cache_read=pricing.cache_read_usd_per_million,
    )


# Per-1M-token USD rates, derived from the shared base-rate table in
# `_acp_model_prices` — the SAME fact the committed model catalog's own
# `pricing` entries are built from, so the legacy span path and the
# catalog-first chain path cannot price one attempt two ways.
_PRICE_TABLE: dict[str, ModelPrice] = {
    model: model_price_of(pricing=pricing)
    for model, pricing in builtin_model_pricing_table().items()
}


def normalize_model_id(*, raw_model: str) -> str | None:
    """Resolve a span's `model` attribute to a priced model id, or None.

    CC stamps a dated model id (e.g. `claude-haiku-4-5-20251001`), so the
    identity is normalized by stripping one trailing `-YYYYMMDD` suffix —
    and by nothing else. The resulting identity must match a price-table
    key EXACTLY; a broader prefix match is not identity and selects no
    price, per `SPECIFICATION/contracts.md` section "Factory-configurable
    ACP fallback priority" → "Cost follows every attempt in a successful
    fallback run".

    An empty / unrecognized model returns None so the caller falls back to
    the configured default model — a token sum with no resolvable model is
    NEVER treated as free.
    """
    identity = exact_model_identity(raw_model=raw_model)
    if identity is None or identity not in _PRICE_TABLE:
        return None
    return identity


def derive_usd_micros(*, tokens: TokenVector, model_id: str) -> int:
    """Cost in integer micro-USD for one token vector priced at `model_id`.

    cost = Σ over the four categories (tokens x per-MTok rate); since the
    rate is USD per 1_000_000 tokens, `tokens x rate` is already micro-USD,
    so the four products sum directly and round to the integer micro-USD
    boundary `_dispatcher_cost` compares against the caps. An unknown
    `model_id` (one not in the table) is priced at the committed default
    model rather than treated as free — a spend cap must not under-count.
    """
    price = _PRICE_TABLE.get(model_id) or _PRICE_TABLE[DEFAULT_DISPATCH_COST_MODEL]
    micro_usd = (
        tokens.input * price.input
        + tokens.output * price.output
        + tokens.cache_write * price.cache_write
        + tokens.cache_read * price.cache_read
    )
    return round(micro_usd)
