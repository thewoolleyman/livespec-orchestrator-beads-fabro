"""Pure per-token Claude-Code cost pricing (work-item livespec-impl-beads-efj).

The price table + token→USD math that turns the per-API-call token counts
the host OTLP receiver already sees into the OBSERVED per-dispatch cost
the y0m spend cap consumes. This is the seam that LIFTS 5v9's fail-closed
refusal: `_dispatcher_cost` refuses in autonomous mode whenever run cost
is UNOBSERVABLE, and today it is always unobservable because fabro's
`total_usd_micros` is null on every run. Claude-Code emits per-API-call
token counts on its TRACE spans but NO `cost_usd` ATTRIBUTE on the span
(cost is a metric, not a span attribute — see
`research/loop-reflection-gate/cc-otel-gap-analysis.md` §"Conclusion 9 —
Cost ground truth is split"), so the host DERIVES cost from the tokens
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

__all__: list[str] = [
    "DEFAULT_DISPATCH_COST_MODEL",
    "DEFAULT_DISPATCH_COST_MODEL_ENV",
    "ModelPrice",
    "TokenVector",
    "derive_usd_micros",
    "normalize_model_id",
]

# The env-var NAME (not a secret value) for the fallback model a token sum
# with no resolvable `model` attribute is priced at. CC's own default
# model is the committed default so an unpriceable span never reads as
# free — a spend cap must NOT under-estimate.
DEFAULT_DISPATCH_COST_MODEL_ENV = "LIVESPEC_DISPATCH_COST_MODEL"
DEFAULT_DISPATCH_COST_MODEL = "claude-opus-4-8"

# The ephemeral-prompt-cache write multiplier. Claude Code uses the
# default 5-minute prompt cache, whose write rate is 1.25x the base input
# rate. Named so it is adjustable in ONE place if CC adopts the 1-hour
# (2x) cache TTL. The cache-READ multiplier is the published 0.10x input.
_CACHE_WRITE_MULTIPLIER = 1.25
_CACHE_READ_MULTIPLIER = 0.10

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


def _price_for(*, base_input: float, base_output: float) -> ModelPrice:
    """Build a `ModelPrice` from the two published base rates + the cache multipliers.

    cache-write = 1.25x input (5-minute ephemeral prompt cache);
    cache-read = 0.10x input. Derived from the multipliers so the cache
    rates stay in lockstep with the base input rate.
    """
    return ModelPrice(
        input=base_input,
        output=base_output,
        cache_write=base_input * _CACHE_WRITE_MULTIPLIER,
        cache_read=base_input * _CACHE_READ_MULTIPLIER,
    )


# Per-1M-token USD rates, authoritative as of 2026-06 (the efj price
# table). input/output are the published per-MTok base rates; the cache
# rates derive from the input rate via the named multipliers above
# (opus 5.00→6.25/0.50, sonnet 3.00→3.75/0.30, haiku 1.00→1.25/0.10,
# fable 10.00→12.50/1.00 — exactly the ratified table).
_PRICE_TABLE: dict[str, ModelPrice] = {
    "claude-opus-4-8": _price_for(base_input=5.00, base_output=25.00),
    "claude-sonnet-4-6": _price_for(base_input=3.00, base_output=15.00),
    "claude-haiku-4-5": _price_for(base_input=1.00, base_output=5.00),
    "claude-fable-5": _price_for(base_input=10.00, base_output=50.00),
}


def normalize_model_id(*, raw_model: str) -> str | None:
    """Resolve a span's `model` attribute to a priced model id, or None.

    CC stamps a dated model id (e.g. `claude-haiku-4-5-20251001`); this
    strips any trailing `-<date>` suffix by prefix-matching the known
    priced ids (longest match first so `claude-opus-4-8` is preferred over
    a shorter prefix). An empty / unrecognized model returns None so the
    caller falls back to the configured default model — a token sum with
    no resolvable model is NEVER treated as free.
    """
    candidate = raw_model.strip()
    if candidate == "":
        return None
    if candidate in _PRICE_TABLE:
        return candidate
    for known in sorted(_PRICE_TABLE, key=len, reverse=True):
        if candidate.startswith(known):
            return known
    return None


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
