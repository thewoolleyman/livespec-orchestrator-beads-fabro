"""One candidate's ALL-OR-NONE explicit pricing table.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" makes candidate pricing a complete table naming the exact
emitted model plus finite, non-negative USD-per-million input, output,
cache-write and cache-read prices, applied only when the emitted model
identity matches exactly.

WHY IT IS ALL-OR-NONE AT PARSE RATHER THAN AT PRICING TIME. The same
section makes ANY unpriceable nonzero usage component render the WHOLE
run cost unobservable rather than a known partial subtotal. A table
missing its cache-read price would therefore be silently useless the
first time a run reported cache reads -- the cost would simply stop being
observable, with nothing pointing at the three-line table that caused it.
Refusing the incomplete table before any claim puts the diagnosis where
the edit is.

WHAT IS NOT HERE. Applying a table to observed usage, the exact-identity
normalization that strips at most one trailing `-YYYYMMDD` suffix, and
the precedence of an explicit table over a built-in endpoint's belong to
the cost slice. This module only decides whether a configured table is
one the cost slice could honour.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._acp_schema_fields import (
    finite_price,
    missing_keys_refusal,
    non_empty_text,
    unknown_keys_refusal,
)

__all__: list[str] = [
    "PRICE_FIELDS",
    "AcpCandidatePricing",
    "parse_candidate_pricing",
]

# The four priced components, in the order the contract lists them.
PRICE_FIELDS: tuple[str, ...] = (
    "input_usd_per_million",
    "output_usd_per_million",
    "cache_write_usd_per_million",
    "cache_read_usd_per_million",
)

_PRICING_KEYS: frozenset[str] = frozenset({"model", *PRICE_FIELDS})


@dataclass(frozen=True, kw_only=True)
class AcpCandidatePricing:
    """One candidate's complete price table for one exact emitted model."""

    model: str
    input_usd_per_million: float
    output_usd_per_million: float
    cache_write_usd_per_million: float
    cache_read_usd_per_million: float


def parse_candidate_pricing(*, value: object, key: str) -> AcpCandidatePricing | str:
    """Parse one `pricing` table, or refuse naming the key at fault."""
    if not isinstance(value, dict):
        return f"{key} must be a pricing table; got {value!r}"
    table = cast("dict[str, Any]", value)
    unknown = unknown_keys_refusal(entry=table, allowed=_PRICING_KEYS, key=key)
    if unknown is not None:
        return unknown
    missing = missing_keys_refusal(entry=table, required=_PRICING_KEYS, key=key)
    if missing is not None:
        return missing
    model = non_empty_text(value=table["model"])
    if model is None:
        return (
            f"{key}.model must be the exact non-empty emitted model identity; "
            f"got {table['model']!r}"
        )
    prices: list[float] = []
    for name in PRICE_FIELDS:
        price = finite_price(value=table[name])
        if price is None:
            return (
                f"{key}.{name} must be a finite, non-negative USD-per-million price; "
                f"got {table[name]!r}"
            )
        prices.append(price)
    return AcpCandidatePricing(
        model=model,
        input_usd_per_million=prices[0],
        output_usd_per_million=prices[1],
        cache_write_usd_per_million=prices[2],
        cache_read_usd_per_million=prices[3],
    )
