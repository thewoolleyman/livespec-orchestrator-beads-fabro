"""One attempt's price: the catalog entry its identity names first, its own table second.

Binds `SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Cost follows every attempt in a successful fallback run":
"Pricing resolves through the model catalog entry the candidate's identity
names first (section "Agent and model catalogs") and a per-candidate explicit
table second; for a manual-form candidate with no catalog match only its
explicit table applies."

THE ORDER IS THE ASSERTION, SO BOTH SOURCES MUST DISAGREE. A test that gave the
catalog and the explicit table the same price would pass under either
precedence and prove nothing about which one was consulted. Every two-source
case below deliberately prices the two differently, and asserts the number the
CATALOG names.

THE SECOND SOURCE IS NOT DEAD CODE, which is the other half of a precedence
test. A catalog miss, and a catalogued model whose entry carries NO pricing,
both have to fall through to the explicit table -- otherwise "second" would
mean "never", and a manual-form candidate (which no catalog can name) would be
unpriceable by construction.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_candidate_pricing import AcpCandidatePricing
from livespec_orchestrator_beads_fabro.commands._acp_model_catalog import builtin_model_catalog
from livespec_orchestrator_beads_fabro.commands._acp_model_entry import AcpModelEntry
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_pricing import ModelPrice

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_MODULE = "_acp_attempt_price"
_MODULE_PATH = _COMMANDS / f"{_MODULE}.py"


def _attempt_price(
    *,
    raw_model: str,
    catalog: dict[str, AcpModelEntry],
    candidate_pricing: AcpCandidatePricing | None = None,
) -> ModelPrice | None:
    """Resolve one attempt's price through an in-body import of the new module."""
    assert _MODULE_PATH.is_file(), _MODULE_PATH
    module = importlib.import_module(f"livespec_orchestrator_beads_fabro.commands.{_MODULE}")
    return module.attempt_price(  # pyright: ignore[reportAttributeAccessIssue]
        raw_model=raw_model,
        catalog=catalog,
        candidate_pricing=candidate_pricing,
    )


def _table(*, model: str, base_input: float) -> AcpCandidatePricing:
    """A complete four-price table whose every component is derived from one number.

    Each component is a DISTINCT multiple of `base_input`, so an assertion on
    any single component identifies which table was consulted -- a table whose
    four prices were equal could not distinguish a wrong-field pairing from a
    wrong-table choice.
    """
    return AcpCandidatePricing(
        model=model,
        input_usd_per_million=base_input,
        output_usd_per_million=base_input * 2,
        cache_write_usd_per_million=base_input * 3,
        cache_read_usd_per_million=base_input * 4,
    )


def _entry(*, model: str, pricing: AcpCandidatePricing | None, **extra: object) -> AcpModelEntry:
    aliases = extra.get("aliases", ())
    canonical_id = extra.get("canonical_id", model)
    assert isinstance(aliases, tuple)
    assert isinstance(canonical_id, str)
    return AcpModelEntry(
        provider="anthropic",
        model=model,
        display_name="Test Model",
        canonical_id=canonical_id,
        aliases=aliases,
        pricing=pricing,
    )


def _catalog(*entries: AcpModelEntry) -> dict[str, AcpModelEntry]:
    return {entry.key: entry for entry in entries}


def test_the_catalog_entry_the_identity_names_wins_over_the_candidate_table() -> None:
    """Catalog FIRST: both sources name the model and the catalog's price is used."""
    catalog = _catalog(
        _entry(model="test-model", pricing=_table(model="test-model", base_input=7.0))
    )

    price = _attempt_price(
        raw_model="test-model",
        catalog=catalog,
        candidate_pricing=_table(model="test-model", base_input=99.0),
    )

    assert price == ModelPrice(input=7.0, output=14.0, cache_write=21.0, cache_read=28.0)


def test_a_dated_emitted_identity_resolves_the_bare_catalog_entry() -> None:
    """The exact-identity rule applies to the catalog key: one date suffix stripped."""
    catalog = _catalog(
        _entry(model="test-model", pricing=_table(model="test-model", base_input=7.0))
    )

    price = _attempt_price(raw_model="test-model-20260101", catalog=catalog)

    assert price is not None
    assert price.input == 7.0


def test_a_dated_catalog_key_is_normalized_too() -> None:
    """A catalog entry written WITH a date suffix still answers to the bare identity.

    The contract puts the rule on the catalog key, not only on the emitted
    value, so the normalization has to run on both sides. Normalizing only the
    emitted identity would leave a legitimately-dated committed entry
    permanently unreachable.
    """
    catalog = _catalog(
        _entry(model="test-model-20260101", pricing=_table(model="test-model", base_input=7.0))
    )

    price = _attempt_price(raw_model="test-model", catalog=catalog)

    assert price is not None
    assert price.input == 7.0


def test_a_canonical_id_names_the_entry() -> None:
    """An identity matching the entry's canonical id resolves that entry's price."""
    catalog = _catalog(
        _entry(
            model="short",
            canonical_id="test-model-canonical",
            pricing=_table(model="short", base_input=7.0),
        )
    )

    price = _attempt_price(raw_model="test-model-canonical", catalog=catalog)

    assert price is not None
    assert price.input == 7.0


def test_an_alias_names_the_entry() -> None:
    """An identity matching a declared alias resolves that entry's price."""
    catalog = _catalog(
        _entry(
            model="test-model",
            aliases=("legacy-spelling",),
            pricing=_table(model="test-model", base_input=7.0),
        )
    )

    price = _attempt_price(raw_model="legacy-spelling", catalog=catalog)

    assert price is not None
    assert price.input == 7.0


def test_a_broader_prefix_never_names_a_catalog_entry() -> None:
    """A prefix of a catalogued model is not that model, so it selects no price."""
    catalog = _catalog(
        _entry(model="test-model", pricing=_table(model="test-model", base_input=7.0))
    )

    assert _attempt_price(raw_model="test-model-preview", catalog=catalog) is None


def test_the_candidate_table_applies_when_no_catalog_entry_names_the_identity() -> None:
    """Explicit table SECOND: a manual-form candidate is priced by its own table.

    No catalog can name a manual-form candidate -- it declares a command, not
    an agent and model -- so this is the only route to a price for one.
    """
    price = _attempt_price(
        raw_model="vendor-model",
        catalog=_catalog(
            _entry(model="test-model", pricing=_table(model="test-model", base_input=7.0))
        ),
        candidate_pricing=_table(model="vendor-model", base_input=3.0),
    )

    assert price == ModelPrice(input=3.0, output=6.0, cache_write=9.0, cache_read=12.0)


def test_the_candidate_table_applies_when_the_named_entry_carries_no_price() -> None:
    """A catalogued-but-unpriced model falls through to the candidate's own table.

    This is the case that makes "second" mean second rather than never: the
    identity DOES name a catalog entry, and that entry simply has no measured
    price, so the ladder must continue instead of stopping at the match.
    """
    price = _attempt_price(
        raw_model="test-model",
        catalog=_catalog(_entry(model="test-model", pricing=None)),
        candidate_pricing=_table(model="test-model", base_input=3.0),
    )

    assert price is not None
    assert price.input == 3.0


def test_a_candidate_table_for_a_different_model_does_not_apply() -> None:
    """A table "applies only when emitted identity matches" its own `model`."""
    price = _attempt_price(
        raw_model="vendor-model",
        catalog={},
        candidate_pricing=_table(model="some-other-model", base_input=3.0),
    )

    assert price is None


def test_a_dated_table_model_matches_the_bare_emitted_identity() -> None:
    """The exact-identity rule applies to the table's `model` field as well."""
    price = _attempt_price(
        raw_model="vendor-model",
        catalog={},
        candidate_pricing=_table(model="vendor-model-20260101", base_input=3.0),
    )

    assert price is not None
    assert price.input == 3.0


def test_an_identity_no_source_names_resolves_to_no_price() -> None:
    """Neither source names the identity, so there is no price -- not a default."""
    assert _attempt_price(raw_model="unknown-vendor-model", catalog={}) is None


def test_a_blank_identity_resolves_to_no_price() -> None:
    """An attempt that emitted no model identity cannot be priced."""
    catalog = _catalog(
        _entry(model="test-model", pricing=_table(model="test-model", base_input=7.0))
    )

    assert _attempt_price(raw_model="   ", catalog=catalog) is None
    assert (
        _attempt_price(
            raw_model="",
            catalog=catalog,
            candidate_pricing=_table(model="test-model", base_input=3.0),
        )
        is None
    )


def test_the_shipped_catalog_prices_this_factory_s_implementer_default() -> None:
    """End to end against the COMMITTED catalog, not a fixture.

    Every case above builds its own catalog, which proves the resolution rule
    and says nothing about whether the shipped bytes satisfy it. This one asks
    the question an operator cares about: can the model this factory's
    implement node actually runs be priced from committed bytes alone?
    """
    price = _attempt_price(
        raw_model="claude-opus-5-20260101", catalog=dict(builtin_model_catalog())
    )

    assert price == ModelPrice(input=5.00, output=25.00, cache_write=6.25, cache_read=0.50)
