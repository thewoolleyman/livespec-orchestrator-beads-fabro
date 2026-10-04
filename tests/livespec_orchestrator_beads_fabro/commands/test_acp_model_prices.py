"""The shipped model catalog carries its four USD-per-million prices.

Binds `SPECIFICATION/contracts.md` section "Agent and model catalogs": model
catalog entries "carry the canonical model id, aliases, the four
USD-per-million prices in the `pricing` shape of section
"Factory-configurable ACP fallback priority", and measured availability
signatures in that section's signature grammar", and the all-or-none pricing
rule "applies to catalog entry and override alike".

`claude-opus-5` IS THE NAMED ENTRY, and it is named because it was a retained
review hazard: it is this factory's own implementer default (section "Built-in
ACP node defaults"), so a catalog that priced every model BUT it would leave
the one model nearly every attempt actually runs unpriceable -- which, under
the no-default rule of the cost paragraph, makes the whole run cost
unobservable rather than merely approximate.

ONE BASE-RATE TABLE, TWO CONSUMERS. The catalog's prices and the per-token
price table the legacy span path reads are the same fact, so the assertions
below pin them against each other rather than against two transcriptions: a
catalog price that disagreed with the table would price one path's attempt
differently from the other's with nothing in either output to show it.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._acp_model_catalog import builtin_model_catalog
from livespec_orchestrator_beads_fabro.commands._acp_model_entry import AcpModelEntry
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_pricing import (
    TokenVector,
    derive_usd_micros,
)

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_MODULE = "_acp_model_prices"
_MODULE_PATH = _COMMANDS / f"{_MODULE}.py"

# The four price fields a complete table owes, in the order the contract lists
# them, each paired with the token category it prices.
_PRICE_FIELDS = (
    "input_usd_per_million",
    "output_usd_per_million",
    "cache_write_usd_per_million",
    "cache_read_usd_per_million",
)


def _prices_module() -> object:
    """The shipped base-rate module, through an in-body import.

    In-body rather than at module top so the FIRST failing assertion is a
    genuine check on the committed file instead of a collection error.
    """
    assert _MODULE_PATH.is_file(), _MODULE_PATH
    return importlib.import_module(f"livespec_orchestrator_beads_fabro.commands.{_MODULE}")


def _opus_five() -> AcpModelEntry:
    return builtin_model_catalog()["anthropic/claude-opus-5"]


def test_the_catalog_prices_claude_opus_five_with_all_four_components() -> None:
    """`anthropic/claude-opus-5` carries a complete, finite, non-negative table."""
    pricing = _opus_five().pricing

    assert pricing is not None
    assert pricing.model == "claude-opus-5"
    for name in _PRICE_FIELDS:
        price = getattr(pricing, name)
        assert isinstance(price, float), name
        assert price >= 0.0, name


def test_claude_opus_five_prices_at_the_opus_family_rates() -> None:
    """Opus 5 takes the Opus family's published 5.00 / 25.00 per-MTok rates.

    Pinned as values rather than left to the base-rate table alone: these two
    numbers are what every Opus attempt's cost is derived from, so a silent
    edit of them is a silent re-pricing of this factory's whole implement node.
    """
    pricing = _opus_five().pricing

    assert pricing is not None
    assert pricing.input_usd_per_million == 5.00
    assert pricing.output_usd_per_million == 25.00
    assert pricing.cache_write_usd_per_million == 6.25
    assert pricing.cache_read_usd_per_million == 0.50


@pytest.mark.parametrize(
    "catalog_key",
    [
        "anthropic/claude-opus-5",
        "anthropic/claude-opus-4-8",
        "anthropic/claude-sonnet-4-6",
        "anthropic/claude-haiku-4-5",
        "openai/gpt-5.5",
        "openai/gpt-5.4-mini",
    ],
)
def test_every_measured_model_is_priced_in_the_catalog(*, catalog_key: str) -> None:
    """Each model this repository already priced carries that price in the catalog."""
    entry = builtin_model_catalog()[catalog_key]

    assert entry.pricing is not None, catalog_key
    assert entry.pricing.model == entry.model


def test_an_unmeasured_model_carries_no_guessed_price() -> None:
    """A model nobody priced carries NO pricing rather than a plausible guess.

    `zai/glm-5.2` is in the catalog by ratification (Scenario 129) and has no
    measured rate here. The honest value is the absence: a guessed price is
    summed into a run cost and read back as an observation, which is worse than
    a gap the no-default rule turns into an explicit unobservable.
    """
    assert builtin_model_catalog()["zai/glm-5.2"].pricing is None


@pytest.mark.parametrize(
    ("model", "tokens", "expected_micros"),
    [
        (
            "claude-opus-5",
            TokenVector(input=1_000_000, output=0, cache_write=0, cache_read=0),
            5_000_000,
        ),
        (
            "claude-opus-5",
            TokenVector(input=0, output=1_000_000, cache_write=0, cache_read=0),
            25_000_000,
        ),
        (
            "claude-opus-5",
            TokenVector(input=0, output=0, cache_write=1_000_000, cache_read=0),
            6_250_000,
        ),
        (
            "claude-opus-5",
            TokenVector(input=0, output=0, cache_write=0, cache_read=1_000_000),
            500_000,
        ),
    ],
)
def test_the_per_token_table_prices_claude_opus_five_too(
    *, model: str, tokens: TokenVector, expected_micros: int
) -> None:
    """The legacy span path prices Opus 5 at the same four rates, not at a default.

    The discriminating part is the comparison, not the numbers: before this
    change `claude-opus-5` was absent from the per-token table and fell through
    to the configured default model, which happens to be `claude-opus-4-8` --
    an answer that looks right for input and output and is WRONG for nothing,
    which is exactly why a value assertion alone could not catch it. The
    cache-component rows are the ones a default fallback could not have
    produced had the two models' rates differed.
    """
    assert derive_usd_micros(tokens=tokens, model_id=model) == expected_micros


def test_the_catalog_price_and_the_per_token_table_agree() -> None:
    """One base-rate fact, read two ways, gives one answer.

    Drives a mixed four-category vector through the per-token table and through
    the catalog entry's own `pricing` arithmetic. A disagreement here is the
    two-copies-of-one-fact drift this module's own docstring names.
    """
    tokens = TokenVector(input=5244, output=3748, cache_write=47620, cache_read=418529)
    pricing = _opus_five().pricing
    assert pricing is not None

    from_catalog = round(
        tokens.input * pricing.input_usd_per_million
        + tokens.output * pricing.output_usd_per_million
        + tokens.cache_write * pricing.cache_write_usd_per_million
        + tokens.cache_read * pricing.cache_read_usd_per_million
    )

    assert derive_usd_micros(tokens=tokens, model_id="claude-opus-5") == from_catalog


def test_the_base_rate_table_is_the_single_source_of_both() -> None:
    """The shipped module exposes every priced model id and a complete table each."""
    module = _prices_module()
    priced = module.priced_model_ids()  # pyright: ignore[reportAttributeAccessIssue]

    assert "claude-opus-5" in priced
    for model in priced:
        pricing = module.builtin_model_pricing(model=model)  # pyright: ignore[reportAttributeAccessIssue]
        assert pricing is not None, model
        assert pricing.model == model


def test_an_unknown_model_has_no_built_in_price() -> None:
    """A model the base-rate table never named resolves to no price at all."""
    module = _prices_module()

    assert module.builtin_model_pricing(model="totally-unknown-model") is None  # pyright: ignore[reportAttributeAccessIssue]


def test_pricing_is_in_the_model_catalog_digest() -> None:
    """A changed price changes the snapshot digest.

    `model_catalog_digest`'s own docstring promised this projection would be
    extended when the pricing item landed, "which is a digest change and
    therefore a snapshot change -- which is the correct signal". A digest blind
    to pricing would let a re-priced catalog ship under an unchanged snapshot
    id.
    """
    catalog_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._acp_model_catalog"
    )
    shipped = dict(builtin_model_catalog())
    digest = catalog_module.model_catalog_digest(catalog=shipped)  # pyright: ignore[reportAttributeAccessIssue]

    opus = shipped["anthropic/claude-opus-5"]
    assert opus.pricing is not None
    repriced = dict(shipped)
    repriced["anthropic/claude-opus-5"] = AcpModelEntry(
        provider=opus.provider,
        model=opus.model,
        display_name=opus.display_name,
        canonical_id=opus.canonical_id,
        aliases=opus.aliases,
        pricing=type(opus.pricing)(
            model=opus.pricing.model,
            input_usd_per_million=opus.pricing.input_usd_per_million + 1.0,
            output_usd_per_million=opus.pricing.output_usd_per_million,
            cache_write_usd_per_million=opus.pricing.cache_write_usd_per_million,
            cache_read_usd_per_million=opus.pricing.cache_read_usd_per_million,
        ),
        signatures=opus.signatures,
    )

    assert catalog_module.model_catalog_digest(catalog=repriced) != digest  # pyright: ignore[reportAttributeAccessIssue]
