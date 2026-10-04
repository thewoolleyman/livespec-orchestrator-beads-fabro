"""EXACT emitted model identity: one trailing date suffix stripped, nothing more.

Binds the identity half of `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority" -> "Cost follows every attempt in a
successful fallback run": "Emitted model identity, normalized only by stripping
one trailing `-YYYYMMDD` date suffix (any broader prefix match is not exact
identity), selects built-in pricing only for the matching built-in candidate and
endpoint."

THE DISCRIMINATING ASSERTION IS THE BROADER PREFIX, NOT THE DATE STRIP. The
shipped `normalize_model_id` already stripped a date suffix before this change --
it did so by PREFIX-MATCHING the price table longest-first, which also matched
`claude-opus-4-8-preview` and `claude-opus-4-8-anything` onto the opus rate. A
test that only asserted the dated form would therefore have passed against the
prefix matcher and proved nothing about exactness. The load-bearing cases below
are the ones a prefix matcher gets WRONG: a non-date suffix must select no price
at all.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_pricing import normalize_model_id

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_MODULE = "_acp_model_identity"
_MODULE_PATH = _COMMANDS / f"{_MODULE}.py"


def _exact_model_identity(*, raw_model: str) -> str | None:
    """Call the identity normalizer through an in-body import.

    The import is in the body rather than at module top so this module's FIRST
    assertion is a genuine check on the committed file rather than a collection
    error -- the decomposition pattern this repo's prior new-module slices use.
    """
    assert _MODULE_PATH.is_file(), _MODULE_PATH
    module = importlib.import_module(f"livespec_orchestrator_beads_fabro.commands.{_MODULE}")
    return module.exact_model_identity(raw_model=raw_model)  # pyright: ignore[reportAttributeAccessIssue]


@pytest.mark.parametrize(
    ("raw_model", "expected"),
    [
        ("claude-haiku-4-5-20251001", "claude-haiku-4-5"),
        ("claude-opus-4-8-20260101", "claude-opus-4-8"),
        ("gpt-5.5-20260612", "gpt-5.5"),
    ],
)
def test_one_trailing_date_suffix_is_stripped(*, raw_model: str, expected: str) -> None:
    """A single trailing `-YYYYMMDD` is removed and nothing else is."""
    assert _exact_model_identity(raw_model=raw_model) == expected


def test_only_one_date_suffix_is_stripped() -> None:
    """Two stacked date suffixes lose exactly one -- "only by stripping one"."""
    assert (
        _exact_model_identity(raw_model="claude-haiku-4-5-20251001-20251002")
        == "claude-haiku-4-5-20251001"
    )


@pytest.mark.parametrize(
    "raw_model",
    [
        "claude-opus-4-8",
        "claude-opus-4-8-preview",
        "claude-opus-4-8-2026010",
        "claude-opus-4-8-202601011",
        "claude-opus-4-8-2026-01-01",
    ],
)
def test_a_non_date_suffix_is_never_stripped(*, raw_model: str) -> None:
    """Only the exact eight-digit shape is a date suffix.

    The three near-misses are deliberate: seven digits, nine digits, and a
    dashed calendar date are all suffixes a looser matcher would eat.
    """
    assert _exact_model_identity(raw_model=raw_model) == raw_model


@pytest.mark.parametrize("raw_model", ["", "   ", "-20251001"])
def test_an_identityless_value_is_none(*, raw_model: str) -> None:
    """Blank text, and a value that is ONLY a date suffix, carry no identity."""
    assert _exact_model_identity(raw_model=raw_model) is None


def test_surrounding_whitespace_is_not_part_of_the_identity() -> None:
    """A padded attribute value names the same model as its bare form."""
    assert _exact_model_identity(raw_model="  claude-haiku-4-5  ") == "claude-haiku-4-5"


@pytest.mark.parametrize(
    ("raw_model", "expected"),
    [
        ("claude-haiku-4-5", "claude-haiku-4-5"),
        ("claude-haiku-4-5-20251001", "claude-haiku-4-5"),
    ],
)
def test_normalize_model_id_accepts_the_exact_identity(*, raw_model: str, expected: str) -> None:
    """The priced-model resolver accepts an exact identity, dated or bare."""
    assert normalize_model_id(raw_model=raw_model) == expected


@pytest.mark.parametrize(
    "raw_model",
    [
        "claude-opus-4-8-preview",
        "claude-opus-4-8-turbo",
        "gpt-5.5-mini",
    ],
)
def test_a_broader_prefix_match_selects_no_price(*, raw_model: str) -> None:
    """A broader prefix is NOT exact identity, so it resolves to no priced model.

    This is the assertion the shipped longest-prefix matcher fails: each value
    below starts with a priced table key, so the prefix matcher returned that
    key's price for a model the table never named. `gpt-5.5-mini` is the
    sharpest of the three -- it is a DIFFERENT real model whose price is lower,
    so the prefix match did not merely guess, it over-charged.
    """
    assert normalize_model_id(raw_model=raw_model) is None
